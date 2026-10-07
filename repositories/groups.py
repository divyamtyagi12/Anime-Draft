from __future__ import annotations

from database.client import Database


class GroupRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def upsert(self, group_id: int, title: str | None) -> None:
        row = {"id": group_id, "title": title or ""}
        await self.db.exec(lambda c: c.table("groups").upsert(row, on_conflict="id"))

    async def get(self, group_id: int) -> dict | None:
        rows = await self.db.exec(lambda c: c.table("groups").select("*").eq("id", group_id).limit(1))
        return rows[0] if rows else None
