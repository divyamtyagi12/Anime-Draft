"""Round-robin fixtures and league ranking — pure logic."""
from __future__ import annotations

import random
import zlib
from itertools import groupby
from typing import Any, Mapping, Sequence


def round_robin(ids: Sequence[int]) -> list[list[tuple[int, int]]]:
    """Circle method: every pair meets exactly once; nobody plays twice per round."""
    players: list[int | None] = list(ids)
    if len(players) % 2:
        players.append(None)  # bye
    n = len(players)
    rounds: list[list[tuple[int, int]]] = []
    for _ in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = players[i], players[n - 1 - i]
            if a is not None and b is not None:
                pairs.append((a, b))
        rounds.append(pairs)
        players = [players[0], players[-1]] + players[1:-1]
    return rounds


def _tie_key(seed: int, player_id: int) -> int:
    """Deterministic pseudo-random value → a perfect tie renders the same every time."""
    return zlib.crc32(f"{seed}:{player_id}".encode())


def rank_standings(standings: Sequence[Mapping[str, Any]], matches: Sequence[Mapping[str, Any]],
                   seed: int = 0) -> list[Mapping[str, Any]]:
    """Order: points → clash difference → clashes won → head-to-head → random (last resort).

    Head-to-head among 3+ tied players uses a mini-league of the matches between them.
    """
    def primary(r: Mapping[str, Any]) -> tuple[int, int, int]:
        return (-r["points"], -r["clash_difference"], -r["clashes_won"])

    ordered = sorted(standings, key=primary)
    result: list[Mapping[str, Any]] = []
    for _, grp_iter in groupby(ordered, key=primary):
        grp = list(grp_iter)
        if len(grp) == 1:
            result.extend(grp)
            continue
        ids = {r["game_player_id"] for r in grp}
        mini = {i: [0, 0] for i in ids}  # [h2h points, h2h clash diff]
        for m in matches:
            if m.get("status") != "DONE" or m.get("stage") != "LEAGUE":
                continue
            a, b = m["p1_id"], m["p2_id"]
            if a in ids and b in ids:
                s1, s2 = m["p1_score"] or 0, m["p2_score"] or 0
                mini[a][1] += s1 - s2
                mini[b][1] += s2 - s1
                if s1 > s2:
                    mini[a][0] += 3
                elif s2 > s1:
                    mini[b][0] += 3
                else:
                    mini[a][0] += 1
                    mini[b][0] += 1
        grp.sort(key=lambda r: (-mini[r["game_player_id"]][0], -mini[r["game_player_id"]][1],
                                _tie_key(seed, r["game_player_id"])))
        result.extend(grp)
    return result
