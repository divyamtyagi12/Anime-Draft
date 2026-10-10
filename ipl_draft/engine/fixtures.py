"""Double round-robin schedule (circle method). Pure. Odd team counts (e.g. 3 humans + 8 system teams = 11) get a
rotating bye: N rounds of (N-1)/2 matches per leg, still exactly N*(N-1) matches in total."""
from __future__ import annotations

from typing import Sequence


def round_robin_rounds(teams: Sequence[int]) -> list[list[tuple[int, int]]]:
    """Single round robin with the circle method. Even N: N-1 rounds of N/2 pairs (home, away).
    Odd N: a bye slot is added, giving N rounds of (N-1)/2 pairs (the team paired with the bye rests that round)."""
    arr: list = list(teams)
    if len(arr) < 2:
        raise ValueError("need at least two teams")
    if len(arr) % 2:
        arr.append(None)
    n = len(arr)
    rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = arr[i], arr[n - 1 - i]
            if a is None or b is None:
                continue
            # alternate home/away so nobody is always home; the fixed team alternates by round
            pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        rounds.append(pairs)
        arr = [arr[0]] + [arr[-1]] + arr[1:-1]
    return rounds


def double_round_robin(teams: Sequence[int]) -> list[dict]:
    """Every team plays every other twice (home & away). Returns fixtures with match_no / matchday / leg."""
    first = round_robin_rounds(teams)
    n_r = len(first)
    fixtures: list[dict] = []
    no = 0
    for leg, rounds in ((1, first), (2, [[(b, a) for a, b in rd] for rd in first])):
        for r, pairs in enumerate(rounds):
            for home, away in pairs:
                no += 1
                fixtures.append({"match_no": no, "matchday": (leg - 1) * n_r + r + 1, "leg": leg,
                                 "home": home, "away": away})
    return fixtures


def validate(fixtures: Sequence[dict], teams: Sequence[int]) -> None:
    n = len(teams)
    if len(fixtures) != n * (n - 1):
        raise AssertionError("fixture count")
    seen: dict[tuple[int, int], int] = {}
    per_team = {t: 0 for t in teams}
    for f in fixtures:
        key = (min(f["home"], f["away"]), max(f["home"], f["away"]))
        seen[key] = seen.get(key, 0) + 1
        per_team[f["home"]] += 1
        per_team[f["away"]] += 1
    if any(c != 2 for c in seen.values()) or len(seen) != n * (n - 1) // 2:
        raise AssertionError("every pair must meet exactly twice")
    if any(c != 2 * (n - 1) for c in per_team.values()):
        raise AssertionError("matches per team")
    if len({(f["home"], f["away"]) for f in fixtures}) != len(fixtures):
        raise AssertionError("duplicate ordered pair")
    for md in {f["matchday"] for f in fixtures}:
        ts = [t for f in fixtures if f["matchday"] == md for t in (f["home"], f["away"])]
        if len(ts) != len(set(ts)):
            raise AssertionError("a team plays twice on one matchday")
