import random

from game.categories import CATEGORY_KEYS, OFFER_SIZE
from game.draft import build_offers
from tests.helpers import build_catalog

CAT = build_catalog()


def test_full_random_drafts_never_dead_end():
    rng = random.Random(5)
    for _ in range(3000):
        picked: set[str] = set()
        for cat in CATEGORY_KEYS:
            offers = build_offers(CAT, cat, picked, rng)
            assert len(offers) == OFFER_SIZE == len({o.id for o in offers})
            assert not ({o.id for o in offers} & picked)
            assert all(cat in o.categories for o in offers)   # no fallback needed
            picked.add(rng.choice(offers).id)
        assert len(picked) == 6


def test_offers_vary_between_games():
    rng = random.Random(6)
    seen = {tuple(sorted(o.id for o in build_offers(CAT, "ATTACK", set(), rng))) for _ in range(50)}
    assert len(seen) > 10


def test_fallback_when_pool_too_small():
    offers = build_offers(CAT, "HEALING", {c.id for c in CAT.pool("HEALING")}, random.Random(1))
    assert len(offers) == OFFER_SIZE
