"""Upsert character data into Supabase:  python -m scripts.seed_characters"""
import asyncio

from config import load_settings
from database.client import Database
from database.seed import sync_characters


async def _main() -> None:
    s = load_settings()
    await sync_characters(Database(s.supabase_url, s.supabase_key))
    print("Characters synced.")


if __name__ == "__main__":
    asyncio.run(_main())
