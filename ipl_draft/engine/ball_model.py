"""Ball-by-ball outcome model: batting vs bowling skill, phase, pressure. Pure; all randomness comes from the rng passed in.

For each legal delivery we start from IPL-like base probabilities for the phase (powerplay / middle / death) of
{dot, 1, 2, 3, 4, 6, wicket}, multiply them by factors derived from the striker's and the bowler's hidden ratings and
the match situation, and renormalise. Extras (wides, no-balls, byes, leg-byes) are sampled before the outcome.
"""
from __future__ import annotations

import math
import random
from typing import Sequence

from .model import Player

PP, MID, DEATH = "pp", "mid", "death"
OUTCOMES = ("0", "1", "2", "3", "4", "6", "W")

BASE = {
    PP:    {"0": .365, "1": .305, "2": .055, "3": .006, "4": .152, "6": .050, "W": .028},
    MID:   {"0": .345, "1": .388, "2": .075, "3": .006, "4": .108, "6": .046, "W": .036},
    DEATH: {"0": .285, "1": .305, "2": .070, "3": .008, "4": .110, "6": .107, "W": .075},
}
PAR_RPO = {PP: 8.4, MID: 7.9, DEATH: 10.5}

# extras per delivery (average bowler)
P_WIDE, P_NOBALL, P_BYE, P_LEGBYE = 0.024, 0.0045, 0.0030, 0.0070


def phase_of(over_index: int) -> str:
    return PP if over_index < 6 else MID if over_index < 15 else DEATH


SK_CENTER = 56.0   # rating of a league-average XI member (so an 'average' side scores the base IPL numbers)


def sk(x: float) -> float:
    return (x - SK_CENTER) / 50.0


def batter_quality(p: Player, phase: str) -> float:
    r = p.ratings
    spec = r.power_hitting if phase == PP else r.strike_rotation if phase == MID else r.death_overs_batting
    return 0.6 * sk(r.batting_rating) + 0.4 * sk(spec)


def power_quality(p: Player) -> float:
    r = p.ratings
    return 0.5 * sk(r.power_hitting) + 0.5 * sk(r.batting_rating)


def bowler_quality(p: Player, phase: str) -> float:
    r = p.ratings
    if p.bowling_type == "PACE":
        eff = r.pace_effectiveness
    elif p.bowling_type == "SPIN":
        eff = r.spin_effectiveness
    else:
        eff = (r.pace_effectiveness + r.spin_effectiveness) / 2
    if phase == DEATH:
        eff = 0.5 * eff + 0.5 * r.death_overs_bowling
    elif phase == PP and p.bowling_type == "SPIN":
        eff *= 0.93
    elif phase == MID and p.bowling_type == "SPIN":
        eff = min(100, eff * 1.04)
    return 0.6 * sk(r.bowling_rating) + 0.4 * sk(eff)


def aggression(phase: str, wickets: int, balls_left: int, runs_needed: int | None, balls_bowled_inn: int) -> float:
    a = {PP: 1.05, MID: 0.95, DEATH: 1.2}[phase]
    if phase != DEATH and wickets >= 7:
        a *= 0.85
    if phase == DEATH:
        a *= 1.0 + 0.025 * (10 - wickets)
    if runs_needed is not None and balls_left > 0:
        rrr = runs_needed * 6 / balls_left
        par = PAR_RPO[phase]
        if rrr > par + 1.5:
            a *= 1.0 + 0.06 * min(rrr - par, 9.0)
        elif rrr < par - 2.0:
            a *= 0.93
    return max(0.7, min(a, 1.9))


def outcome_probs(phase: str, bq: float, pq: float, rot: float, wq: float, agg: float, settle: float,
                  field_q: float, pitch: float, free_hit: bool) -> list[float]:
    b = BASE[phase]
    a = bq - wq
    bp = pq - wq
    w = {
        "0": b["0"] * math.exp(-0.20 * a) * agg ** -0.9,
        "1": b["1"] * math.exp(0.14 * (rot - 0.25 * wq)) * agg ** -0.25,
        "2": b["2"] * math.exp(0.14 * (rot - 0.25 * wq)),
        "3": b["3"],
        "4": b["4"] * math.exp(0.30 * bp) * agg ** 0.8 * pitch / (1.0 + 0.25 * (settle - 1.0)),
        "6": b["6"] * math.exp(0.45 * bp) * agg ** 1.1 * pitch ** 1.3,
        "W": b["W"] * math.exp(-0.42 * bq + 0.40 * wq + 0.20 * field_q) * settle * agg ** 0.9 / pitch ** 0.5,
    }
    if free_hit:
        w["W"] = 0.0
        w["6"] *= 1.1
        w["4"] *= 1.1
    tot = sum(w.values())
    return [w[o] / tot for o in OUTCOMES]


def sample(rng: random.Random, probs: Sequence[float], labels: Sequence[str] = OUTCOMES) -> str:
    x = rng.random()
    acc = 0.0
    for p, l in zip(probs, labels):
        acc += p
        if x < acc:
            return l
    return labels[-1]


def extras_probs(wq: float, bowl_cons: float, keeper_rating: int) -> tuple[float, float, float, float]:
    k = math.exp(-0.5 * sk(bowl_cons)) * math.exp(-0.15 * wq)
    byes = P_BYE * (1 + max(0.0, (55 - keeper_rating) / 55) * 2.0)
    return P_WIDE * k, P_NOBALL * k, byes, P_LEGBYE


def dismissal_kind(rng: random.Random, bowling_type: str, free_hit: bool) -> str:
    if free_hit:
        return "run out"
    x = rng.random()
    spin = bowling_type == "SPIN"
    cuts = [("bowled", .27), ("lbw", .10), ("stumped", .06 if spin else .008), ("run out", .055)]
    acc = 0.0
    for k, p in cuts:
        acc += p
        if x < acc:
            return k
    return "caught"
