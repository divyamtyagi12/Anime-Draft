from __future__ import annotations

from database.client import Database


class StandingsRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def list_for_game(self, game_id: int) -> list[dict]:
        return await self.db.exec(lambda c: c.table("standings").select("*").eq("game_id", game_id))
