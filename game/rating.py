"""Leaderboard rating rules — pure logic (no I/O).

The authoritative implementation runs inside Postgres (`record_game_results` in
database/schema.sql) so ratings are updated atomically under row locks. This module is
the executable specification of the same formula: tests pin it, and the SQL mirrors it.

Pairwise ("multiplayer") Elo
    For every pair (me, opponent) in a tournament of N players:
        S = 1 if I finished above the opponent, else 0
        E = 1 / (1 + 10 ** ((R_opp - R_me) / 400))
    change = round( K / (N - 1) * sum(S - E over all opponents) )
Ratings used are those from BEFORE the tournament. Beating a stronger opponent earns
more (S - E is large); losing to a weaker one costs more (E is large). With K = 32 the
total gain/loss of one player in one tournament is bounded by ±K.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

START_RATING = 1000
K_FACTOR = 32
PAGE_SIZE = 10
MIN_MATCHES_FOR_WIN_RATE = 5  # a 1-0 record must not top the win-rate board


def expected_score(rating: float, opponent: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((opponent - rating) / 400.0))


def _round_half_away(x: float) -> int:
    """Matches Postgres numeric round() (half away from zero), not Python's banker's rounding."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def rating_changes(ratings: Mapping[int, int], placements: Sequence[int],
                   k: float = K_FACTOR) -> dict[int, int]:
    """`placements` lists user ids from 1st place to last (no ties). Returns user_id -> change."""
    n = len(placements)
    if n < 2:
        raise ValueError("a rated tournament needs at least two players")
    if len(set(placements)) != n or set(placements) != set(ratings):
        raise ValueError("placements must list every rated player exactly once")
    out: dict[int, int] = {}
    for i, me in enumerate(placements):
        total = 0.0
        for j, opp in enumerate(placements):
            if me == opp:
                continue
            s = 1.0 if i < j else 0.0
            total += s - expected_score(ratings[me], ratings[opp])
        out[me] = _round_half_away(k / (n - 1) * total)
    return out


def placement_order(league_order: Sequence[int], final_p1: int, final_p2: int, winner: int) -> list[int]:
    """Game-player ids, 1st place first: final winner, final loser, then the rest in final
    league-table order (the table already resolves every tie deterministically)."""
    runner_up = final_p2 if winner == final_p1 else final_p1
    rest = [x for x in league_order if x not in (final_p1, final_p2)]
    return [winner, runner_up, *rest]
