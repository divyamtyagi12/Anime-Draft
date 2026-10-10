"""Turns the labelled seed list into an `ipl_import_players` payload (idempotent: slugs are stable)."""
from __future__ import annotations

from ..engine.ratings import METHOD_VERSION, rate_from_tier
from .names import disambiguate, normalize_name, slugify
from .seed_players import SEED_PLAYERS, SEED_VERSION

SEED_SOURCE = {
    "name": "GameArena IPL seed (names/roles only, unverified)",
    "data_version": SEED_VERSION,
    "url": None,
    "license": "hand-compiled identity data; contains no statistics",
    "notes": ("Roster of well-known all-time IPL cricketers compiled by hand. Roles/nationalities are unverified; "
              "ratings come from an EDITORIAL tier prior, not statistics. Replace with the Cricsheet import."),
}


def build_seed_payload() -> tuple[dict, list[dict]]:
    rows = [(slugify(n), n) for n, *_ in SEED_PLAYERS]
    display = disambiguate(rows)
    out = []
    for name, role, nat, bat, bowl, tier in SEED_PLAYERS:
        slug = slugify(name)
        btype = {"P": "PACE", "S": "SPIN", "-": "NONE"}[bowl]
        r = rate_from_tier(role, tier, btype, slug)
        out.append({
            "slug": slug, "full_name": name, "display_name": display[slug], "name_key": normalize_name(name),
            "role": role, "batting_style": {"R": "RHB", "L": "LHB"}[bat], "bowling_type": btype,
            "nationality": nat, "is_eligible": True, "ipl_verified": False, "data_quality": "SEED",
            "ratings": {**r.as_dict(), "rating_source": "EDITORIAL_TIER", "method_version": METHOD_VERSION},
        })
    return SEED_SOURCE, out
