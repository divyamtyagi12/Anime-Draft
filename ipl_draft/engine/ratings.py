"""HIDDEN player rating methodology  (version ipl-ratings-v1)  — pure functions, no I/O.

Two sources, one scale (0-100, "average IPL regular" ≈ 45-55):

1. CRICSHEET_STATS — computed from real IPL career numbers with Bayesian shrinkage:
     adjusted = (observed_total + prior_rate * prior_weight) / (observed_volume + prior_weight)
   so a player with 3 innings and an average of 90 is pulled hard toward the role prior and can never rank above
   a proven performer purely through a tiny sample. Priors/weights are the constants below. Batting uses
   average + strike rate; bowling uses economy + bowling strike rate; power/rotation/death/consistency use
   boundary share, non-boundary scoring share, overs 16-20 splits and "useful innings" share. The same formulas
   apply to historical and current players.
2. EDITORIAL_TIER — used ONLY while no statistics exist for a player (the labelled seed dataset). A coarse S/A/B/C
   judgement plus a deterministic per-player jitter. These are NOT statistics and are stored as such.

Ratings are never shown to users; see docs/IPL_DRAFT.md.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Mapping

from .model import Ratings

METHOD_VERSION = "ipl-ratings-v1"


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def scale(x: float, lo: float, hi: float) -> float:
    """Linear map lo→0, hi→1 (clipped). hi < lo inverts (lower is better)."""
    return clip((x - lo) / (hi - lo))


def _i(x: float) -> int:
    return int(round(clip(x, 0, 100)))


@dataclass(frozen=True)
class CareerStats:
    matches: int = 0
    innings_bat: int = 0
    runs: int = 0
    balls_faced: int = 0
    outs: int = 0
    fours: int = 0
    sixes: int = 0
    dots_faced: int = 0
    death_runs: int = 0          # overs 16-20
    death_balls: int = 0
    inn_20plus: int = 0          # innings with 20+ runs
    ducks: int = 0
    balls_bowled: int = 0
    runs_conceded: int = 0
    wickets: int = 0
    innings_bowl: int = 0
    good_bowl_innings: int = 0   # >=1 wicket or economy <= 8
    death_bowl_balls: int = 0
    death_bowl_runs: int = 0
    catches: int = 0
    stumpings: int = 0
    run_outs: int = 0

    @classmethod
    def from_mapping(cls, m: Mapping) -> "CareerStats":
        return cls(**{k: int(m.get(k) or 0) for k in cls.__dataclass_fields__})


# ───────────── priors (documented, tweak with care) ─────────────
BAT_PRIOR = {"BAT": (22.0, 124.0), "WK": (22.0, 124.0), "AR": (19.0, 128.0), "BOWL": (8.0, 105.0)}  # (avg, SR)
K_OUTS, K_BALLS = 15, 250
SAMPLE_FULL_INNINGS = 40   # batting rating is capped until a player has this many innings (see below)
BOWLER_PRIOR = (8.8, 23.0)       # (economy, balls per wicket) for bowlers / all-rounders
PART_TIMER_PRIOR = (9.6, 34.0)   # for batters/keepers who barely bowl
K_BOWL_BALLS, K_WKTS = 120, 4


def rate_from_stats(s: CareerStats, role: str, bowling_type: str) -> Ratings:
    avg0, sr0 = BAT_PRIOR.get(role, BAT_PRIOR["BAT"])
    outs = max(s.outs, 0)
    avg_adj = (s.runs + avg0 * K_OUTS) / (outs + K_OUTS)
    sr_adj = (s.runs + sr0 / 100 * K_BALLS) / (s.balls_faced + K_BALLS) * 100
    batting = 100 * (0.5 * scale(avg_adj, 10, 42) + 0.5 * scale(sr_adj, 100, 170))
    batting = min(batting, 45 + 55 * min(1.0, s.innings_bat / SAMPLE_FULL_INNINGS))   # low-sample cap

    bnd = (s.fours + 2.2 * s.sixes)
    bnd_prior = 0.10 if role != "BOWL" else 0.07
    bnd_adj = (bnd + bnd_prior * K_BALLS) / (s.balls_faced + K_BALLS)
    power = 100 * scale(bnd_adj, 0.08, 0.30)

    bnd_balls = s.fours + s.sixes
    nb = 1 - ((s.dots_faced + 0.35 * K_BALLS) / (s.balls_faced + K_BALLS)) - (
        (bnd_balls + 0.15 * K_BALLS) / (s.balls_faced + K_BALLS))
    rotation = 100 * scale(nb, 0.38, 0.58)

    dsr = (s.death_runs + 1.45 * 40) / (s.death_balls + 40) * 100
    death_bat = 0.7 * 100 * scale(dsr, 120, 190) + 0.3 * batting

    c = (s.inn_20plus + 0.25 * 8) / (s.innings_bat + 8)
    duck = (s.ducks + 0.06 * 8) / (s.innings_bat + 8)
    bat_cons = 100 * scale(c - 0.3 * duck, 0.10, 0.55)

    part_timer = role in ("BAT", "WK") and s.balls_bowled < 120
    econ0, bsr0 = PART_TIMER_PRIOR if part_timer else BOWLER_PRIOR
    kb = K_BOWL_BALLS * (2 if part_timer else 1)
    econ_adj = (s.runs_conceded + econ0 / 6 * kb) / (s.balls_bowled + kb) * 6
    bsr_adj = (s.balls_bowled + bsr0 * K_WKTS) / (s.wickets + K_WKTS)
    bowling = 100 * (0.5 * scale(econ_adj, 10.0, 6.4) + 0.5 * scale(bsr_adj, 32, 14))
    if part_timer:
        bowling = min(bowling, 38)

    decon = (s.death_bowl_runs + 10.5 / 6 * 60) / (s.death_bowl_balls + 60) * 6
    death_bowl = 0.7 * 100 * scale(decon, 12.5, 7.5) + 0.3 * bowling
    gb = (s.good_bowl_innings + 0.5 * 8) / (s.innings_bowl + 8)
    bowl_cons = 100 * scale(gb, 0.25, 0.75)

    kind = bowling_type
    spin = bowling * (1.0 if kind == "SPIN" else 0.3)
    pace = bowling * (1.0 if kind == "PACE" else 0.3)
    if kind == "NONE":
        spin = pace = bowling * 0.6

    field_rate = (s.catches + 1.5 * s.run_outs + 0.35 * 20) / (s.matches + 20)
    fielding = 100 * scale(field_rate, 0.15, 0.62)
    if role == "WK":
        keep = 52 + 22 * min(1, s.stumpings / 12) + 12 * min(1, s.matches / 80)
        fielding = max(fielding, 55)
    else:
        keep = 12 if role != "AR" else 14

    r = Ratings(
        batting_rating=_i(batting), bowling_rating=_i(bowling), fielding_rating=_i(fielding),
        wicketkeeping_rating=_i(keep), batting_consistency=_i(bat_cons), bowling_consistency=_i(bowl_cons),
        power_hitting=_i(power), strike_rotation=_i(rotation), death_overs_batting=_i(death_bat),
        death_overs_bowling=_i(death_bowl), spin_effectiveness=_i(spin), pace_effectiveness=_i(pace),
        overall_rating=0)
    return _with_overall(r, role)


def _with_overall(r: Ratings, role: str) -> Ratings:
    b, w, f, k = r.batting_rating, r.bowling_rating, r.fielding_rating, r.wicketkeeping_rating
    if role == "BAT":
        o = 0.85 * b + 0.10 * f + 0.05 * w
    elif role == "WK":
        o = 0.78 * b + 0.12 * k + 0.10 * f
    elif role == "BOWL":
        o = 0.85 * w + 0.10 * f + 0.05 * b
    else:  # AR — both skills count, the weaker one a little less
        o = 0.62 * max(b, w) + 0.38 * min(b, w)
    d = r.as_dict()
    d["overall_rating"] = _i(o)
    return Ratings(**d)


# ───────────── editorial-tier fallback ─────────────
TIER_BASE = {"S": 80, "A": 69, "B": 58, "C": 46}


def _jit(slug: str, key: str) -> float:
    """Deterministic value in [-1, 1] from (slug, key): reproducible across imports and machines."""
    h = hashlib.sha256(f"{slug}:{key}".encode()).digest()
    return int.from_bytes(h[:4], "big") / 0xFFFFFFFF * 2 - 1


def rate_from_tier(role: str, tier: str, bowling_type: str, slug: str) -> Ratings:
    base = TIER_BASE.get(tier, TIER_BASE["C"])
    j = lambda k, amp: _jit(slug, k) * amp          # noqa: E731
    bowls = bowling_type != "NONE"
    if role == "BAT":
        bat, bowl = base + j("b", 5), (22 + (base - 46) * 0.2 if bowls else 12)
    elif role == "WK":
        bat, bowl = base - 3 + j("b", 5), 10
    elif role == "BOWL":
        bat, bowl = 14 + (base - 46) * 0.12 + j("b", 4), base + j("w", 5)
    else:
        lean = j("lean", 9)
        bat, bowl = base - 6 + lean, base - 6 - lean
    power = bat + j("p", 10) + (4 if role == "AR" else 0) - (8 if role == "BOWL" else 0)
    rot = 50 + (bat - 50) * 0.5 + j("r", 10)
    cons = bat * 0.8 + 10 + j("c", 8)
    bowl_cons = bowl * 0.8 + 10 + j("bc", 8)
    kind = bowling_type
    spin = bowl * (1.0 if kind == "SPIN" else 0.3 if kind == "PACE" else 0.6)
    pace = bowl * (1.0 if kind == "PACE" else 0.3 if kind == "SPIN" else 0.6)
    fielding = 52 + (base - 46) * 0.25 + j("f", 12)
    keep = (58 + (base - 46) * 0.5 + j("k", 6)) if role == "WK" else (12 if role != "AR" else 14)
    r = Ratings(
        batting_rating=_i(bat), bowling_rating=_i(bowl), fielding_rating=_i(fielding), wicketkeeping_rating=_i(keep),
        batting_consistency=_i(cons), bowling_consistency=_i(bowl_cons), power_hitting=_i(power),
        strike_rotation=_i(rot), death_overs_batting=_i(bat + j("d", 8) + (power - bat) * 0.3),
        death_overs_bowling=_i(bowl + j("db", 8)), spin_effectiveness=_i(spin), pace_effectiveness=_i(pace),
        overall_rating=0)
    return _with_overall(r, role)
