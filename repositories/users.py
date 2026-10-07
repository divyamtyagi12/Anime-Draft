from __future__ import annotations

from database.client import Database
from utils.timeutil import now_iso


class UserRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def upsert(self, user_id: int, username: str | None, first_name: str | None,
                     dm_started: bool | None = None) -> None:
        """dm_started=None leaves the stored flag untouched."""
        row: dict = {"id": user_id, "username": username, "first_name": first_name or "",
                     "updated_at": now_iso()}
        if dm_started is not None:
            row["dm_started"] = dm_started
        await self.db.exec(lambda c: c.table("users").upsert(row, on_conflict="id"))

    async def get(self, user_id: int) -> dict | None:
        rows = await self.db.exec(lambda c: c.table("users").select("*").eq("id", user_id).limit(1))
        return rows[0] if rows else None

    async def set_dm(self, user_id: int, started: bool) -> None:
        await self.db.exec(lambda c: c.table("users").update({"dm_started": started}).eq("id", user_id))
