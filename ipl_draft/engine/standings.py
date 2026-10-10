"""IPL points table: points, Net Run Rate, ordering and tie-breaks. Pure."""
from __future__ import annotations

from typing import Mapping, Sequence

FULL_BALLS = 120
POINTS_WIN, POINTS_NR = 2, 1


def overs_str(balls: int) -> str:
    return f"{balls // 6}.{balls % 6}"


def nrr(runs_for: int, balls_faced: int, runs_against: int, balls_bowled: int) -> float:
    """(runs scored / overs faced) - (runs conceded / overs bowled); overs = legal balls / 6 (never decimal overs)."""
    if balls_faced <= 0 or balls_bowled <= 0:
        return 0.0
    return round(runs_for * 6 / balls_faced - runs_against * 6 / balls_bowled, 3)


def nrr_balls(innings_balls: int, all_out: bool) -> int:
    """An all-out innings counts as the full 20 overs for NRR (standard rule)."""
    return FULL_BALLS if all_out else innings_balls


def rank_teams(rows: Sequence[Mapping], league_results: Sequence[Mapping] = ()) -> list[int]:
    """Ordered team ids. Tie-break chain (documented):
       1. points  2. net run rate  3. wins  4. head-to-head wins among the tied teams  5. lowest team_no (deterministic)."""
    h2h: dict[tuple[int, int], int] = {}
    for m in league_results:
        w = m.get("winner")
        if w is None:
            continue
        o = m["team2"] if w == m["team1"] else m["team1"]
        h2h[(w, o)] = h2h.get((w, o), 0) + 1

    def base(r):
        return (-r["points"], -round(float(r["nrr"]), 3), -r["won"])

    groups: dict[tuple, list[Mapping]] = {}
    for r in rows:
        groups.setdefault(base(r), []).append(r)
    ordered: list[int] = []
    for key in sorted(groups):
        grp = groups[key]
        ids = [g["team_id"] for g in grp]
        wins_vs_group = {g["team_id"]: sum(h2h.get((g["team_id"], o), 0) for o in ids if o != g["team_id"]) for g in grp}
        grp.sort(key=lambda g: (-wins_vs_group[g["team_id"]], g.get("team_no", 0), g["team_id"]))
        ordered += [g["team_id"] for g in grp]
    return ordered


def apply_result(row: dict, *, won: bool | None, runs_for: int, balls_faced: int,
                 runs_against: int, balls_bowled: int) -> None:
    """Executable spec of the SQL update in ipl_settle_match (used by tests to cross-check the database)."""
    row["played"] += 1
    if won is None:
        row["no_result"] += 1
        row["points"] += POINTS_NR
    elif won:
        row["won"] += 1
        row["points"] += POINTS_WIN
    else:
        row["lost"] += 1
    row["runs_for"] += runs_for
    row["balls_faced"] += balls_faced
    row["runs_against"] += runs_against
    row["balls_bowled"] += balls_bowled
    row["nrr"] = nrr(row["runs_for"], row["balls_faced"], row["runs_against"], row["balls_bowled"])
