"""Offline calibration / sanity report for the IPL match engine (no database, no Telegram).

    python -m scripts.ipl_calibrate [matches=2000]
Prints scoring statistics for random squads and the win-rate of strong vs weak squads.
"""
from __future__ import annotations

import random
import statistics as st
import sys
import time

from ipl_draft.data.seed_loader import build_seed_payload
from ipl_draft.engine.match_engine import simulate_match
from ipl_draft.engine.model import Player, Ratings, Squad


def pool() -> list[Player]:
    _, rows = build_seed_payload()
    return [Player(id=r["slug"], name=r["display_name"], role=r["role"], bowling_type=r["bowling_type"],
                   batting_style=r["batting_style"], ratings=Ratings.from_mapping(r["ratings"])) for r in rows]


def squad(tid: int, players: list[Player]) -> Squad:
    return Squad(tid, f"T{tid}", f"T{tid}", tuple(players))


def balanced(rng: random.Random, players: list[Player], strength: str | None = None) -> list[Player]:
    wk = [p for p in players if p.role == "WK"]
    bw = [p for p in players if p.role == "BOWL"]
    ar = [p for p in players if p.role == "AR"]
    bt = [p for p in players if p.role == "BAT"]
    key = lambda p: p.ratings.overall_rating  # noqa: E731
    if strength == "top":
        pick = lambda xs, n: sorted(xs, key=key, reverse=True)[:n]   # noqa: E731
    elif strength == "bottom":
        pick = lambda xs, n: sorted(xs, key=key)[:n]                  # noqa: E731
    else:
        pick = lambda xs, n: rng.sample(xs, n)                        # noqa: E731
    return pick(wk, 1) + pick(bt, 3) + pick(ar, 3) + pick(bw, 4)


def main(n: int = 2000) -> None:
    rng = random.Random(7)
    P = pool()
    t0 = time.time()
    s1, w1, rr, ties, sos, maxb, wins_top, tot_top = [], [], [], 0, 0, 0, 0, 0
    for i in range(n):
        ids = set()
        a = balanced(rng, P)
        rest = [p for p in P if p not in a]
        b = balanced(rng, rest)
        m = simulate_match(squad(1, a), squad(2, b), rng)
        i1, i2 = m.innings[0], m.innings[1]
        s1 += [i1.runs, i2.runs]
        w1 += [i1.wickets, i2.wickets]
        rr += [i1.runs * 6 / max(1, i1.legal_balls)]
        ties += m.result_type == "TIE_SUPER_OVER"
        for inn in m.innings:
            for bl in inn.bowl_lines:
                if not inn.is_super_over:
                    maxb = max(maxb, bl.balls)
    el = time.time() - t0
    print(f"random balanced squads: {n} matches in {el:.1f}s ({el / n * 1000:.1f} ms/match)")
    print(f"  mean innings total {st.mean(s1):.1f}  sd {st.pstdev(s1):.1f}  min {min(s1)}  max {max(s1)}")
    print(f"  mean wickets {st.mean(w1):.2f}   mean 1st-inns run rate {st.mean(rr):.2f}   ties {ties / n:.2%}   max bowler balls {maxb}")
    top = squad(1, balanced(rng, P, "top"))
    rest = [p for p in P if p not in top.players]
    bot = squad(2, balanced(rng, rest, "bottom"))
    w = sum(simulate_match(top, bot, rng).winner == 1 for _ in range(600))
    print(f"  TOP-rated XI beats BOTTOM-rated XI: {w / 600:.1%}")
    midA = squad(1, balanced(rng, P)); midB = squad(2, balanced(rng, [p for p in P if p not in midA.players]))
    w = sum(simulate_match(midA, midB, rng).winner == 1 for _ in range(600))
    print(f"  two random XIs (A wins): {w / 600:.1%}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
