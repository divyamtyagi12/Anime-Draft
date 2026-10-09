"""All Supabase access for Number Wars. Atomic work lives in SQL functions (database/number_wars.sql)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from postgrest.exceptions import APIError

from database.client import Database, is_unique_violation
from game.number_wars import RoundOutcome

ACTIVE = ("LOBBY", "ACTIVE")


class NumberWarsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ── matches ──
    async def create_match(self, group_id: int, host_id: int, min_players: int, max_players: int) -> dict | None:
        """None when the group already has an unfinished game (of either kind)."""
        row = {"group_id": group_id, "host_id": host_id,
               "min_players": min_players, "max_players": max_players}
        try:
            data = await self.db.exec(lambda c: c.table("nw_matches").insert(row))
            return data[0]
        except APIError as exc:
            if is_unique_violation(exc):
                return None
            raise

    async def get_match(self, match_id: int) -> dict | None:
        rows = await self.db.exec(lambda c: c.table("nw_matches").select("*").eq("id", match_id).limit(1))
        return rows[0] if rows else None

    async def active_for_group(self, group_id: int) -> dict | None:
        rows = await self.db.exec(lambda c: c.table("nw_matches").select("*")
                                  .eq("group_id", group_id).in_("status", list(ACTIVE)).limit(1))
        return rows[0] if rows else None

    async def active_for_user(self, user_id: int) -> dict | None:
        mine = await self.db.exec(lambda c: c.table("nw_players").select("match_id")
                                  .eq("user_id", user_id).order("joined_at", desc=True).limit(10))
        for row in mine:
            m = await self.get_match(row["match_id"])
            if m and m["status"] in ACTIVE:
                return m
        return None

    async def by_status(self, statuses: list[str]) -> list[dict]:
        return await self.db.exec(lambda c: c.table("nw_matches").select("*").in_("status", statuses))

    async def unannounced_finished(self) -> list[dict]:
        return await self.db.exec(lambda c: c.table("nw_matches").select("*")
                                  .eq("status", "FINISHED").eq("announced", False))

    async def update_match(self, match_id: int, **fields: Any) -> None:
        await self.db.exec(lambda c: c.table("nw_matches").update(fields).eq("id", match_id))

    async def cancel(self, match_id: int) -> bool:
        rows = await self.db.exec(lambda c: c.table("nw_matches")
                                  .update({"status": "CANCELLED",
                                           "finished_at": datetime.now(timezone.utc).isoformat()})
                                  .eq("id", match_id).in_("status", list(ACTIVE)))
        return bool(rows)

    async def claim_announce(self, match_id: int) -> bool:
        return bool(await self.db.rpc("nw_claim_announce", {"p_match_id": match_id}))

    async def release_announce(self, match_id: int) -> None:
        await self.update_match(match_id, announced=False)

    # ── players ──
    async def players(self, match_id: int) -> list[dict]:
        return await self.db.exec(lambda c: c.table("nw_players").select("*")
                                  .eq("match_id", match_id).order("joined_at").order("user_id"))

    async def join(self, match_id: int, user_id: int, name: str) -> str:
        return await self.db.rpc("nw_join", {"p_match_id": match_id, "p_user_id": user_id, "p_name": name})

    async def leave(self, match_id: int, user_id: int) -> str:
        return await self.db.rpc("nw_leave", {"p_match_id": match_id, "p_user_id": user_id})

    async def start(self, match_id: int) -> bool:
        return bool(await self.db.rpc("nw_start", {"p_match_id": match_id}))

    # ── rounds ──
    async def open_round(self, match_id: int, seconds: int) -> dict | None:
        return await self.db.rpc("nw_open_round", {"p_match_id": match_id, "p_seconds": seconds})

    async def close_round(self, round_id: int) -> str:
        return await self.db.rpc("nw_close_round", {"p_round_id": round_id})

    async def submit(self, round_id: int, user_id: int, number: int) -> dict:
        return await self.db.rpc("nw_submit", {"p_round_id": round_id, "p_user_id": user_id, "p_number": number})

    async def open_round_for_user(self, user_id: int) -> int | None:
        return await self.db.rpc("nw_open_round_for_user", {"p_user_id": user_id})

    async def submissions(self, round_id: int) -> dict[int, int]:
        rows = await self.db.exec(lambda c: c.table("nw_submissions")
                                  .select("user_id,selected_number").eq("round_id", round_id))
        return {r["user_id"]: r["selected_number"] for r in rows}

    async def apply_round(self, round_id: int, outcome: RoundOutcome,
                          end: tuple[list[int], str] | None) -> bool:
        """Atomic + idempotent: False if the round was already applied (or the match is over)."""
        results = [{"user_id": r.user_id, "number": r.number,
                    "distance": None if r.distance is None else round(float(r.distance), 4),
                    "hp_delta": r.hp_delta, "is_winner": r.is_winner} for r in outcome.results]
        return bool(await self.db.rpc("nw_apply_round", {
            "p_round_id": round_id,
            "p_target": None if outcome.target is None else round(float(outcome.target), 4),
            "p_results": results,
            "p_zero_damage": outcome.zero_damage,
            "p_winner_ids": list(end[0]) if end else [],
            "p_end_reason": end[1] if end else None}))

    # ── stats ──
    async def leaderboard(self, group_id: int, limit: int = 10) -> list[dict]:
        """group_id 0 = global."""
        return await self.db.exec(lambda c: c.table("nw_stats")
                                  .select("user_id,rating,wins,losses,matches_played,round_wins,users(first_name,username)")
                                  .eq("group_id", group_id).order("rating", desc=True)
                                  .order("wins", desc=True).limit(limit))

    async def stats_for(self, user_id: int, group_id: int = 0) -> dict | None:
        rows = await self.db.exec(lambda c: c.table("nw_stats").select("*")
                                  .eq("user_id", user_id).eq("group_id", group_id).limit(1))
        return rows[0] if rows else None

    async def rank_of(self, user_id: int, group_id: int, rating: int) -> int:
        rows = await self.db.exec(lambda c: c.table("nw_stats").select("user_id")
                                  .eq("group_id", group_id).gt("rating", rating))
        return len(rows) + 1
