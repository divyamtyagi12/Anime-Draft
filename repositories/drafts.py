from __future__ import annotations

from collections import Counter

from postgrest.exceptions import APIError

from database.client import Database, is_unique_violation
from game.categories import CATEGORY_KEYS


class DraftRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_offer(self, gp_id: int, category: str) -> list[str] | None:
        rows = await self.db.exec(
            lambda c: c.table("draft_offers").select("character_ids")
            .eq("game_player_id", gp_id).eq("category", category).limit(1))
        return rows[0]["character_ids"] if rows else None

    async def create_offer(self, gp_id: int, category: str, ids: list[str]) -> list[str]:
        """Race-safe: if another task created the offer first, return that one."""
        row = {"game_player_id": gp_id, "category": category, "character_ids": ids}
        try:
            data = await self.db.exec(lambda c: c.table("draft_offers").insert(row))
            return data[0]["character_ids"]
        except APIError as exc:
            if not is_unique_violation(exc):
                raise
            existing = await self.get_offer(gp_id, category)
            return existing or ids

    async def picks(self, gp_id: int) -> list[dict]:
        return await self.db.exec(
            lambda c: c.table("draft_choices").select("*").eq("game_player_id", gp_id).order("id"))

    async def add_pick(self, gp_id: int, category: str, char_id: str, auto: bool = False) -> None:
        """Raises APIError(23505) on a double pick — callers treat that as 'already done'."""
        row = {"game_player_id": gp_id, "category": category, "character_id": char_id, "auto_picked": auto}
        await self.db.exec(lambda c: c.table("draft_choices").insert(row))

    async def pick_counts(self, gp_ids: list[int]) -> dict[int, int]:
        if not gp_ids:
            return {}
        rows = await self.db.exec(
            lambda c: c.table("draft_choices").select("game_player_id").in_("game_player_id", gp_ids))
        return dict(Counter(r["game_player_id"] for r in rows))

    async def create_team(self, gp_id: int, picks: dict[str, str]) -> None:
        row = {"game_player_id": gp_id, **{f"{cat.lower()}_id": picks[cat] for cat in CATEGORY_KEYS}}
        await self.db.exec(lambda c: c.table("teams").upsert(
            row, on_conflict="game_player_id", ignore_duplicates=True))

    async def get_team(self, gp_id: int) -> dict[str, str] | None:
        rows = await self.db.exec(
            lambda c: c.table("teams").select("*").eq("game_player_id", gp_id).limit(1))
        if not rows:
            return None
        return {cat: rows[0][f"{cat.lower()}_id"] for cat in CATEGORY_KEYS}
