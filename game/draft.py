"""Draft offer generation — pure logic."""
from __future__ import annotations

import random
from typing import Collection

from game.categories import OFFER_SIZE
from models.catalog import CharacterCatalog
from models.character import Character


def build_offers(catalog: CharacterCatalog, category: str, exclude: Collection[str],
                 rng: random.Random, size: int = OFFER_SIZE) -> list[Character]:
    """Pick `size` random eligible characters, never including already-picked ones.

    If (due to a tiny custom pool) fewer than `size` eligible characters remain,
    the best remaining characters by that category's rating fill the gap so a
    draft can never dead-end.
    """
    pool = [c for c in catalog.pool(category) if c.id not in exclude]
    if len(pool) >= size:
        return rng.sample(pool, size)
    chosen = list(pool)
    extras = sorted(
        (c for c in catalog.all() if c.id not in exclude and c not in chosen),
        key=lambda c: (-c.rating(category), c.id),
    )
    chosen += extras[: size - len(chosen)]
    rng.shuffle(chosen)
    return chosen
