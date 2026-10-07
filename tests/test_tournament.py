import itertools
import random

from game.tournament import rank_standings, round_robin


def test_round_robin_every_pair_once():
    for n in range(2, 17):
        rounds = round_robin(list(range(1, n + 1)))
        pairs = [frozenset(p) for r in rounds for p in r]
        assert len(pairs) == len(set(pairs)) == n * (n - 1) // 2
        for r in rounds:
            seen = [x for p in r for x in p]
            assert len(seen) == len(set(seen))  # nobody twice in a round


def row(i, pts, diff, won):
    return {"game_player_id": i, "points": pts, "clash_difference": diff, "clashes_won": won}


def test_rank_priority():
    rows = [row(1, 3, 0, 10), row(2, 6, -5, 2), row(3, 6, 1, 3), row(4, 6, 1, 5)]
    assert [r["game_player_id"] for r in rank_standings(rows, [])] == [4, 3, 2, 1]


def test_head_to_head_breaks_exact_ties():
    rows = [row(1, 3, 0, 5), row(2, 3, 0, 5)]
    ms = [{"status": "DONE", "stage": "LEAGUE", "p1_id": 1, "p2_id": 2, "p1_score": 2, "p2_score": 4}]
    assert [r["game_player_id"] for r in rank_standings(rows, ms)] == [2, 1]


def test_random_last_resort_is_stable():
    rows = [row(i, 3, 0, 5) for i in range(1, 6)]
    a = [r["game_player_id"] for r in rank_standings(rows, [], seed=7)]
    assert a == [r["game_player_id"] for r in rank_standings(list(reversed(rows)), [], seed=7)]
