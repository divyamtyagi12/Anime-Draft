"""Tournament awards computed ONLY from stored scorecard aggregates (ipl_player_tournament_stats). Pure.

Player of the Tournament — documented points (fantasy-style, all from scorecards):
   runs + fours*1 + sixes*2 + 25*wickets + 8*maidens + (4/5-wicket bonus 8/16)
   + 10*catches + 12*stumpings + 8*run-outs + 30*Player-of-the-Match awards
"""
from __future__ import annotations

from typing import Mapping, Sequence


def impact_points(p: Mapping) -> float:
    pts = p["runs"] + p["fours"] + 2 * p["sixes"] + 25 * p["wickets"] + 8 * p["maidens"]
    pts += 10 * p["catches"] + 12 * p["stumpings"] + 8 * p["run_outs"] + 30 * p["pom"]
    if p["best_w"] >= 5:
        pts += 16
    elif p["best_w"] >= 4:
        pts += 8
    return float(pts)


def _sr(p):
    return p["runs"] / p["balls"] if p["balls"] else 0.0


def _econ(p):
    return p["bowl_runs"] * 6 / p["bowl_balls"] if p["bowl_balls"] else 99.0


def compute_awards(stats: Sequence[Mapping], champion: Mapping | None, runner_up: Mapping | None) -> list[dict]:
    out: list[dict] = []
    if champion:
        out.append({"award": "CHAMPION", "team_id": champion["id"], "value_text": champion["name"]})
    if runner_up:
        out.append({"award": "RUNNER_UP", "team_id": runner_up["id"], "value_text": runner_up["name"]})
    bats = [p for p in stats if p["runs"] > 0]
    if bats:
        p = max(bats, key=lambda p: (p["runs"], _sr(p), -p["bat_innings"], p["name"]))
        out.append({"award": "ORANGE_CAP", "player_id": p["player_id"], "team_id": p["team_id"], "value_num": p["runs"],
                    "value_text": f"{p['runs']} runs ({p['bat_innings']} inns)"})
    bowls = [p for p in stats if p["wickets"] > 0]
    if bowls:
        p = max(bowls, key=lambda p: (p["wickets"], -_econ(p), p["name"]))
        out.append({"award": "PURPLE_CAP", "player_id": p["player_id"], "team_id": p["team_id"], "value_num": p["wickets"],
                    "value_text": f"{p['wickets']} wickets (econ {_econ(p):.2f})"})
    if stats:
        p = max(stats, key=lambda p: (impact_points(p), p["name"]))
        out.append({"award": "PLAYER_OF_TOURNAMENT", "player_id": p["player_id"], "team_id": p["team_id"],
                    "value_num": impact_points(p), "value_text": f"{impact_points(p):.0f} impact points"})
    sx = [p for p in stats if p["sixes"] > 0]
    if sx:
        p = max(sx, key=lambda p: (p["sixes"], p["runs"], p["name"]))
        out.append({"award": "MOST_SIXES", "player_id": p["player_id"], "team_id": p["team_id"], "value_num": p["sixes"],
                    "value_text": f"{p['sixes']} sixes"})
    hs = [p for p in stats if p["high"] > 0]
    if hs:
        p = max(hs, key=lambda p: (p["high"], -p["high_balls"], p["name"]))
        out.append({"award": "BEST_INNINGS", "player_id": p["player_id"], "team_id": p["team_id"], "value_num": p["high"],
                    "value_text": f"{p['high']} ({p['high_balls']} balls)"})
    return out
