import random

from game.battle import play_match, resolve_clash
from game.categories import CATEGORY_KEYS
from tests.helpers import build_catalog

CAT = build_catalog()


def test_overwhelming_gap_never_upset():
    rng = random.Random(1)
    for _ in range(20000):
        r = resolve_clash(1, "ATTACK", CAT.get("reinhard"), CAT.get("magna"), rng)  # 99 vs 70
        assert r.winner_side == 1


def test_close_fights_can_go_either_way():
    rng = random.Random(2)
    wins = sum(resolve_clash(1, "ATTACK", CAT.get("asta"), CAT.get("yuno"), rng).winner_side == 1 for _ in range(5000))
    assert 1000 < wins < 4900  # 93 vs 92: genuinely close


def test_light_beats_everyone_physical_in_intelligence_only():
    rng = random.Random(3)
    assert resolve_clash(6, "INTELLIGENCE", CAT.get("light"), CAT.get("regulus"), rng).winner_side == 1


def _team(ids):
    return {cat: CAT.get(i) for cat, i in zip(CATEGORY_KEYS, ids)}


def test_match_and_final_tiebreak():
    rng = random.Random(4)
    t1 = _team(["reinhard", "reid", "regulus", "cecilus", "felix", "light"])
    t2 = _team(["asta", "yuno", "noelle", "luck", "mimosa", "l"])
    res = play_match(t1, t2, rng)
    assert len(res.clashes) == 6 and res.p1_wins + res.p2_wins == 6
    assert res.winner_side in (0, 1, 2) and res.tiebreak is None
    tb_seen = False
    for seed in range(3000):
        r = play_match(t1, _team(["reinhard", "reid", "regulus", "cecilus", "mimosa", "l"]), random.Random(seed), final=True)
        assert r.winner_side in (1, 2)
        if r.p1_wins == r.p2_wins:
            assert r.tiebreak is not None
            tb_seen = True
        else:
            assert r.tiebreak is None
    assert tb_seen
