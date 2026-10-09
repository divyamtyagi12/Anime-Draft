from __future__ import annotations

from database.client import Database

CRITERIA = ("champs", "wins", "winrate")


class LeaderboardRepo:
    """Thin wrappers over the leaderboard SQL functions/tables (see database/schema.sql)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def record_game(self, game_id: int, placements: list[int], k: float) -> dict:
        """Atomic + idempotent: applies ratings and stats for one finished game exactly once."""
        return await self.db.rpc("record_game_results",
                                 {"p_game_id": game_id, "p_placements": placements, "p_k": k})

    async def rating_changes(self, game_id: int) -> list[dict]:
        return await self.db.exec(
            lambda c: c.table("rating_history").select("user_id,old_rating,new_rating,rating_change")
            .eq("game_id", game_id))

    async def global_page(self, user_id: int, limit: int, offset: int) -> dict:
        return await self.db.rpc("global_leaderboard",
                                 {"p_user_id": user_id, "p_limit": limit, "p_offset": offset})

    async def group_page(self, group_id: int, criteria: str, user_id: int, limit: int, offset: int,
                         min_matches: int) -> dict:
        if criteria not in CRITERIA:
            criteria = "champs"
        return await self.db.rpc("group_leaderboard", {
            "p_group_id": group_id, "p_criteria": criteria, "p_user_id": user_id,
            "p_limit": limit, "p_offset": offset, "p_min_matches": min_matches})

    async def groups_of_user(self, user_id: int, limit: int = 10) -> list[dict]:
        """Groups where the user has played a finished tournament, most recently active first."""
        rows = await self.db.exec(
            lambda c: c.table("player_group_stats").select("group_id,tournaments_played,groups(title)")
            .eq("user_id", user_id).order("updated_at", desc=True).limit(limit))
        return [{"group_id": r["group_id"], "tournaments_played": r["tournaments_played"],
                 "title": (r.get("groups") or {}).get("title") or ""} for r in rows]

    async def has_group_stats(self, user_id: int, group_id: int) -> bool:
        rows = await self.db.exec(
            lambda c: c.table("player_group_stats").select("user_id")
            .eq("user_id", user_id).eq("group_id", group_id).limit(1))
        return bool(rows)
