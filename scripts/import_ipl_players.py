"""Import IPL cricketers into the database (idempotent — safe to re-run).

    python -m scripts.import_ipl_players --seed                      # labelled names/roles seed (NO statistics)
    python -m scripts.import_ipl_players --cricsheet ipl_json.zip    # REAL stats from a downloaded Cricsheet archive
    python -m scripts.import_ipl_players --cricsheet ipl_json.zip --dry-run   # validate + report only
    python -m scripts.import_ipl_players --cricsheet ipl_json.zip --download  # fetch the archive first (needs internet)

Credentials come from the same environment variables as the bot (SUPABASE_URL / SUPABASE_KEY); nothing is printed.
Cricsheet data is never invented: players found in the archive get computed statistics and `ipl_verified = true`;
seed-only players keep `data_quality = SEED` and an editorial rating tier, and are listed in the report.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

from ipl_draft.data import cricsheet
from ipl_draft.data.names import normalize_name
from ipl_draft.data.seed_loader import build_seed_payload
from ipl_draft.data.seed_players import SEED_PLAYERS

BATCH = 40
URL = cricsheet.CRICSHEET_SOURCE["url"]


def load_matches(path: Path):
    """Yield parsed match dicts from a Cricsheet zip or a directory of *.json files."""
    if path.is_dir():
        for f in sorted(path.glob("*.json")):
            yield json.loads(f.read_text(encoding="utf-8"))
        return
    with zipfile.ZipFile(path) as z:
        for n in sorted(z.namelist()):
            if n.endswith(".json"):
                yield json.loads(z.read(n).decode("utf-8"))


def seeds_by_key() -> dict[str, tuple]:
    return {normalize_name(t[0]): t for t in SEED_PLAYERS}


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


async def push(source: dict, players: list[dict]) -> dict:
    from config import load_settings
    from database.client import Database
    from ipl_draft.repository import IplRepo
    s = load_settings()
    repo = IplRepo(Database(s.supabase_url, s.supabase_key))
    tot = {"inserted": 0, "updated": 0}
    for part in chunks(players, BATCH):
        res = await repo.import_players(source, part)
        tot["inserted"] += res["inserted"]
        tot["updated"] += res["updated"]
    pool = await repo.pool_summary()
    return {**tot, "pool": pool}


def print_report(report: dict) -> None:
    print(json.dumps({k: v for k, v in report.items() if k != "seed_unmatched"}, indent=2))
    um = report.get("seed_unmatched") or []
    if um:
        print(f"\n{len(um)} seed name(s) were NOT found in the Cricsheet data (not verified, kept only if no real "
              f"record exists):\n  " + "\n  ".join(um[:80]) + ("\n  …" if len(um) > 80 else ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--seed", action="store_true")
    g.add_argument("--cricsheet", metavar="ZIP_OR_DIR")
    ap.add_argument("--download", action="store_true", help="download ipl_json.zip to the --cricsheet path first")
    ap.add_argument("--min-matches", type=int, default=5, help="players with fewer IPL matches are stored but not draftable")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if a.seed:
        source, players = build_seed_payload()
        print(f"Seed: {len(players)} players (names/roles only — NO statistics, data_quality=SEED).")
        report = {"players": len(players), "note": "seed data is unverified; run --cricsheet for real statistics"}
    else:
        path = Path(a.cricsheet)
        if a.download:
            print("Downloading Cricsheet archive …")
            urllib.request.urlretrieve(URL, path)          # noqa: S310 — fixed https URL
        if not path.exists():
            print(f"Not found: {path}. Download {URL} (or pass --download).", file=sys.stderr)
            return 2
        accs = cricsheet.aggregate(load_matches(path))
        source, players, report = cricsheet.build_payload(accs, seeds_by_key(), min_matches=a.min_matches)
    print_report(report)
    if a.dry_run:
        print("\n(dry run — nothing written)")
        return 0
    if not players:
        print("No players to import.", file=sys.stderr)
        return 1
    print("\nImporting …")
    print(json.dumps(asyncio.run(push(source, players)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
