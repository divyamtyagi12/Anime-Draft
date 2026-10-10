"""Name normalisation helpers for the player import (idempotent slugs, duplicate handling)."""
from __future__ import annotations

import re
import unicodedata


def normalize_name(name: str) -> str:
    """Lower-case, accent-free, punctuation-free key used to detect duplicates ('D'Arcy Short' == 'darcy short')."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9 ]+", "", s.lower().replace("-", " "))
    return re.sub(r"\s+", " ", s).strip()


def slugify(name: str) -> str:
    return normalize_name(name).replace(" ", "-")


def disambiguate(names: list[tuple[str, str]]) -> dict[str, str]:
    """`names` = [(slug, display_name)]. Returns slug -> unique display name; clashes get ' (<n>)' suffixes
    in a stable order so repeated imports always produce the same labels."""
    seen: dict[str, int] = {}
    out: dict[str, str] = {}
    for slug, disp in sorted(names):
        k = disp.lower()
        seen[k] = seen.get(k, 0) + 1
        out[slug] = disp if seen[k] == 1 else f"{disp} ({seen[k]})"
    return out
