"""Battle engine — pure functions, no I/O.

Clash model
-----------
    effective_score = category_rating × U(0.95, 1.05)

Ratings are predefined (never invented per battle). The ±5 % band means a
character needs to be within ~10 % of the opponent to ever win an upset; an
overwhelming gap (e.g. 99 vs 80) can never be overturned.

Ultimate tiebreaker (Grand Final only; with five clashes a tie cannot occur, so this is a safety net)
-----------------------------------------------------------------------
    base  = 0.8 × mean(slot ratings) + 0.2 × mean(each character's peak rating)
    score = base × U(0.97, 1.03)
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import fmean
from typing import Mapping

from game.categories import CATEGORY_KEYS
from models.character import Character

CLASH_RANDOM_LOW = 0.95
CLASH_RANDOM_HIGH = 1.05
TIEBREAK_RANDOM_LOW = 0.97
TIEBREAK_RANDOM_HIGH = 1.03

Team = Mapping[str, Character]  # category key -> drafted character


@dataclass(frozen=True)
class ClashResult:
    clash_no: int
    category: str
    p1_char: Character
    p2_char: Character
    p1_rating: int
    p2_rating: int
    p1_score: float
    p2_score: float
    winner_side: int  # 1 or 2

    @property
    def winner_char(self) -> Character:
        return self.p1_char if self.winner_side == 1 else self.p2_char


@dataclass(frozen=True)
class Tiebreak:
    p1_score: float
    p2_score: float
    winner_side: int


@dataclass
class MatchResult:
    clashes: list[ClashResult]
    tiebreak: Tiebreak | None = None

    @property
    def p1_wins(self) -> int:
        return sum(1 for c in self.clashes if c.winner_side == 1)

    @property
    def p2_wins(self) -> int:
        return sum(1 for c in self.clashes if c.winner_side == 2)

    @property
    def winner_side(self) -> int:
        """1 / 2 / 0 (draw)."""
        if self.tiebreak is not None:
            return self.tiebreak.winner_side
        if self.p1_wins > self.p2_wins:
            return 1
        if self.p2_wins > self.p1_wins:
            return 2
        return 0


def margin_label(clash: ClashResult) -> str:
    hi = max(clash.p1_score, clash.p2_score)
    gap = abs(clash.p1_score - clash.p2_score) / hi if hi else 0
    if gap < 0.02:
        return "😬 a razor-thin finish!"
    if gap < 0.08:
        return "a hard-fought win"
    return "💥 a dominant win!"


def resolve_clash(clash_no: int, category: str, c1: Character, c2: Character,
                  rng: random.Random) -> ClashResult:
    r1, r2 = c1.rating(category), c2.rating(category)
    s1 = r1 * rng.uniform(CLASH_RANDOM_LOW, CLASH_RANDOM_HIGH)
    s2 = r2 * rng.uniform(CLASH_RANDOM_LOW, CLASH_RANDOM_HIGH)
    if s1 > s2:
        side = 1
    elif s2 > s1:
        side = 2
    elif r1 != r2:
        side = 1 if r1 > r2 else 2
    else:
        side = rng.choice((1, 2))
    return ClashResult(clash_no, category, c1, c2, r1, r2, round(s1, 3), round(s2, 3), side)


def team_score(team: Team, rng: random.Random) -> float:
    slot = fmean(c.rating(cat) for cat, c in team.items())
    peak = fmean(c.peak_rating for c in team.values())
    return (0.8 * slot + 0.2 * peak) * rng.uniform(TIEBREAK_RANDOM_LOW, TIEBREAK_RANDOM_HIGH)


def ultimate_tiebreak(team1: Team, team2: Team, rng: random.Random) -> Tiebreak:
    for _ in range(5):
        s1, s2 = round(team_score(team1, rng), 3), round(team_score(team2, rng), 3)
        if s1 != s2:
            return Tiebreak(s1, s2, 1 if s1 > s2 else 2)
    return Tiebreak(s1, s2, rng.choice((1, 2)))  # astronomically unlikely


def play_match(team1: Team, team2: Team, rng: random.Random, *, final: bool = False) -> MatchResult:
    """Five category clashes (odd count, so no draws). Safety net: an equal final still gets the tiebreaker."""
    clashes = [
        resolve_clash(i, cat, team1[cat], team2[cat], rng)
        for i, cat in enumerate(CATEGORY_KEYS, start=1)
    ]
    result = MatchResult(clashes)
    if final and result.p1_wins == result.p2_wins:
        result.tiebreak = ultimate_tiebreak(team1, team2, rng)
    return result
