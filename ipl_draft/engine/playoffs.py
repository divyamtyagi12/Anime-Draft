"""IPL top-four playoff bracket. Pure.

  ELIMINATOR   : rank 3 v rank 4          winner → Qualifier 2, loser out
  QUALIFIER_1  : rank 1 v rank 2          winner → Final,       loser → Qualifier 2
  QUALIFIER_2  : loser(Q1) v winner(Elim) winner → Final,       loser out
  FINAL        : winner(Q1) v winner(Q2)  winner = champion
Order of play: Eliminator, Qualifier 1, Qualifier 2, Final.
"""
from __future__ import annotations

from typing import Mapping, Sequence

ORDER = ("ELIMINATOR", "QUALIFIER_1", "QUALIFIER_2", "FINAL")
STATE_FOR_STAGE = {"ELIMINATOR": "PLAYOFF_ELIMINATOR", "QUALIFIER_1": "PLAYOFF_QUALIFIER_1",
                   "QUALIFIER_2": "PLAYOFF_QUALIFIER_2", "FINAL": "PLAYOFF_FINAL"}
STAGE_LABEL = {"LEAGUE": "League", "ELIMINATOR": "Eliminator", "QUALIFIER_1": "Qualifier 1",
               "QUALIFIER_2": "Qualifier 2", "FINAL": "Grand Final"}


def initial_pairings(ranking: Sequence[int]) -> dict[str, tuple[int, int]]:
    if len(ranking) < 4:
        raise ValueError("need four qualified teams")
    return {"ELIMINATOR": (ranking[2], ranking[3]), "QUALIFIER_1": (ranking[0], ranking[1])}


def next_pairing(stage_done: str, results: Mapping[str, tuple[int, int]]) -> tuple[str, tuple[int, int]] | None:
    """results[stage] = (winner, loser). Returns the next stage and its (home, away) once its inputs exist."""
    if stage_done == "QUALIFIER_1" and "ELIMINATOR" in results:
        return "QUALIFIER_2", (results["QUALIFIER_1"][1], results["ELIMINATOR"][0])
    if stage_done == "QUALIFIER_2" and "QUALIFIER_1" in results:
        return "FINAL", (results["QUALIFIER_1"][0], results["QUALIFIER_2"][0])
    return None


def run_bracket(ranking: Sequence[int], play) -> dict:
    """Plays the whole bracket with `play(stage, home, away) -> winner`. Used by tests and the offline simulator."""
    p = initial_pairings(ranking)
    res: dict[str, tuple[int, int]] = {}
    for stage in ("ELIMINATOR", "QUALIFIER_1"):
        h, a = p[stage]
        w = play(stage, h, a)
        res[stage] = (w, a if w == h else h)
    h, a = next_pairing("QUALIFIER_1", res)[1]
    w = play("QUALIFIER_2", h, a)
    res["QUALIFIER_2"] = (w, a if w == h else h)
    h, a = next_pairing("QUALIFIER_2", res)[1]
    w = play("FINAL", h, a)
    res["FINAL"] = (w, a if w == h else h)
    return {"results": res, "champion": res["FINAL"][0], "runner_up": res["FINAL"][1]}
