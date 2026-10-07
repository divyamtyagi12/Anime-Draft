from __future__ import annotations

from database.client import Database


class PlayerRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def list_for_game(self, game_id: int) -> list[dict]:
        return await self.db.exec(
            lambda c: c.table("game_players").select("*").eq("game_id", game_id).order("id"))

    async def get(self, gp_id: int) -> dict | None:
        rows = await self.db.exec(lambda c: c.table("game_players").select("*").eq("id", gp_id).limit(1))
        return rows[0] if rows else None

    async def for_user(self, user_id: int, limit: int = 10) -> list[dict]:
        return await self.db.exec(
            lambda c: c.table("game_players").select("*").eq("user_id", user_id)
            .order("id", desc=True).limit(limit))

    async def mark_done(self, gp_id: int) -> bool:
        """True only for the caller that flips draft_done false -> true."""
        rows = await self.db.exec(
            lambda c: c.table("game_players").update({"draft_done": True})
            .eq("id", gp_id).eq("draft_done", False))
        return bool(rows)
