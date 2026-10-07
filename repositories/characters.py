from __future__ import annotations

from collections import defaultdict

from database.client import Database
from models.catalog import CharacterCatalog
from models.character import Character


class CharacterRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def load_catalog(self) -> CharacterCatalog:
        rows = await self.db.exec(lambda c: c.table("characters").select("*").eq("active", True))
        links = await self.db.exec(lambda c: c.table("character_categories").select("character_id,category"))
        cats: dict[str, set[str]] = defaultdict(set)
        for r in links:
            cats[r["character_id"]].add(r["category"])
        return CharacterCatalog(Character.from_row(r, cats[r["id"]]) for r in rows if cats[r["id"]])

    async def set_file_id(self, char_id: str, file_id: str) -> None:
        await self.db.exec(lambda c: c.table("characters").update({"image_file_id": file_id}).eq("id", char_id))

    async def set_image_url(self, char_id: str, url: str) -> None:
        await self.db.exec(lambda c: c.table("characters").update(
            {"image_url": url, "image_file_id": None}).eq("id", char_id))
