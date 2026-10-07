from __future__ import annotations

from typing import Any

from postgrest.exceptions import APIError

from database.client import Database, is_unique_violation

ACTIVE = ("LOBBY", "DRAFTING", "LEAGUE", "FINAL")


class GameRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(self, group_id: int, host_id: int, min_players: int, max_players: int) -> dict | None:
        """Returns None when the group already has an unfinished game (unique index)."""
        row = {"group_id": group_id, "host_id": host_id,
               "min_players": min_players, "max_players": max_players}
        try:
            data = await self.db.exec(lambda c: c.table("games").insert(row))
            return data[0]
        except APIError as exc:
            if is_unique_violation(exc):
                return None
            raise

    async def get(self, game_id: int) -> dict | None:
        rows = await self.db.exec(lambda c: c.table("games").select("*").eq("id", game_id).limit(1))
        return rows[0] if rows else None

    async def active_for_group(self, group_id: int) -> dict | None:
        rows = await self.db.exec(
            lambda c: c.table("games").select("*").eq("group_id", group_id).in_("status", list(ACTIVE)).limit(1))
        return rows[0] if rows else None

    async def latest_for_group(self, group_id: int) -> dict | None:
        rows = await self.db.exec(
            lambda c: c.table("games").select("*").eq("group_id", group_id)
            .neq("status", "CANCELLED").order("id", desc=True).limit(1))
        return rows[0] if rows else None

    async def by_status(self, statuses: list[str]) -> list[dict]:
        return await self.db.exec(lambda c: c.table("games").select("*").in_("status", statuses))

    async def update(self, game_id: int, **fields: Any) -> None:
        await self.db.exec(lambda c: c.table("games").update(fields).eq("id", game_id))

    async def expired_drafts(self, now_iso: str) -> list[dict]:
        return await self.db.exec(
            lambda c: c.table("games").select("*").eq("status", "DRAFTING").lt("draft_deadline", now_iso))

    async def unannounced_completed(self) -> list[dict]:
        return await self.db.exec(
            lambda c: c.table("games").select("*").eq("status", "COMPLETED").eq("final_announced", False))

    async def claim_announcement(self, game_id: int) -> bool:
        rows = await self.db.exec(
            lambda c: c.table("games").update({"final_announced": True})
            .eq("id", game_id).eq("final_announced", False))
        return bool(rows)

    async def release_announcement(self, game_id: int) -> None:
        await self.update(game_id, final_announced=False)

    async def cancel(self, game_id: int) -> bool:
        rows = await self.db.exec(
            lambda c: c.table("games").update({"status": "CANCELLED"})
            .eq("id", game_id).in_("status", list(ACTIVE)))
        return bool(rows)

    # ── atomic RPCs (see schema.sql) ──
    async def join(self, game_id: int, user_id: int, name: str) -> str:
        return await self.db.rpc("join_game", {"p_game_id": game_id, "p_user_id": user_id, "p_name": name})

    async def leave(self, game_id: int, user_id: int) -> str:
        return await self.db.rpc("leave_game", {"p_game_id": game_id, "p_user_id": user_id})

    async def begin_draft(self, game_id: int, deadline_iso: str | None) -> bool:
        return bool(await self.db.rpc("begin_draft", {"p_game_id": game_id, "p_deadline": deadline_iso}))

    async def begin_league(self, game_id: int) -> bool:
        return bool(await self.db.rpc("begin_league", {"p_game_id": game_id}))

    async def begin_final(self, game_id: int, p1: int, p2: int) -> dict | None:
        return await self.db.rpc("begin_final", {"p_game_id": game_id, "p_p1": p1, "p_p2": p2})
