"""Sync data/characters.py (+ data/image_urls.json) into Supabase. Idempotent."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from data.characters import CHARACTERS
from database.client import Database

log = logging.getLogger(__name__)
_FIELDS = ("id", "name", "series", "attack", "tanking", "speed", "healing",
           "intelligence", "rarity", "abilities", "description")


async def sync_characters(db: Database) -> None:
    rows = [{**{k: ch[k] for k in _FIELDS}, "active": True} for ch in CHARACTERS]
    await db.exec(lambda c: c.table("characters").upsert(rows, on_conflict="id"))

    desired = {(ch["id"], cat) for ch in CHARACTERS for cat in ch["categories"]}
    existing_rows = await db.exec(lambda c: c.table("character_categories").select("character_id,category"))
    existing = {(r["character_id"], r["category"]) for r in existing_rows}
    for cid, cat in existing - desired:
        await db.exec(lambda c, cid=cid, cat=cat: c.table("character_categories")
                      .delete().eq("character_id", cid).eq("category", cat))
    missing = [{"character_id": cid, "category": cat} for cid, cat in desired - existing]
    if missing:
        await db.exec(lambda c: c.table("character_categories").upsert(
            missing, on_conflict="character_id,category", ignore_duplicates=True))

    # Artwork overrides (id -> URL). Changing a URL clears the cached Telegram file_id.
    path = Path(__file__).resolve().parent.parent / "data" / "image_urls.json"
    overrides = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    overrides = {k: v for k, v in overrides.items() if v}
    if overrides:
        current = await db.exec(lambda c: c.table("characters").select("id,image_url"))
        have = {r["id"]: r["image_url"] for r in current}
        for cid, url in overrides.items():
            if cid in have and have[cid] != url:
                await db.exec(lambda c, cid=cid, url=url: c.table("characters")
                              .update({"image_url": url, "image_file_id": None}).eq("id", cid))
    log.info("Character data synced (%d characters)", len(CHARACTERS))
