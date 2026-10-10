"""Batting order selection flow (post-draft DM interaction).

After a human team's 11-player draft is complete, the user is asked to set
their batting lineup via DM.  The state is stored in the 'batting_order'
column of ipl_team_rosters (slot ordering is repurposed as batting position).

In-memory state for the current DM session is minimal: the session is driven
purely from the database (ordered slots already confirmed + remaining unset).
A simple 5-minute timeout auto-assigns the smart order if the user doesn't act.
"""
from __future__ import annotations

import asyncio
import logging
import time

from .. import keyboards as kb
from .. import messages as m
from ..engine.match_engine import batting_order as smart_batting_order
from ..engine.model import Squad
from ..runtime import IplRuntime
from . import notification_service as notify

log = logging.getLogger(__name__)

# seconds the user has to set their batting order before auto-assignment
BATTING_ORDER_TIMEOUT = 300

# In-memory: tid → {team_id: (last_dm_message_id, deadline_monotonic)}
_sessions: dict[int, dict[int, tuple[int | None, float]]] = {}


# ─────────────────────────── helpers ───────────────────────────────

def _session(tid: int) -> dict[int, tuple[int | None, float]]:
    if tid not in _sessions:
        _sessions[tid] = {}
    return _sessions[tid]


def _set_session(tid: int, team_id: int, msg_id: int | None, deadline: float) -> None:
    _sessions.setdefault(tid, {})[team_id] = (msg_id, deadline)


def _pop_session(tid: int, team_id: int) -> None:
    _sessions.get(tid, {}).pop(team_id, None)


# ─────────────────────────── public API ────────────────────────────

async def start_batting_order_flow(rt: IplRuntime, team: dict, players: list[dict]) -> None:
    """Send the first batting order DM to the human user after their squad is complete."""
    tid = team["tournament_id"]
    team_id = team["id"]
    user_id = team["user_id"]
    deadline = time.monotonic() + BATTING_ORDER_TIMEOUT

    # Build ordered / remaining from scratch (none set yet)
    ordered: list[dict] = []
    remaining = [{"pos": i + 1, "player": p} for i, p in enumerate(players)]
    text = m.batting_order_prompt(players, ordered, remaining)
    markup = kb.batting_order(team_id, remaining, 0)
    sent = await notify.dm(rt, user_id, text, markup)
    msg_id = sent.message_id if sent else None
    _set_session(tid, team_id, msg_id, deadline)


async def get_batting_order_state(rt: IplRuntime, team_id: int) -> dict | None:
    """Fetch the current batting order state from the database.
    Returns {'ordered': [...], 'remaining': [...], 'players': [...]} or None."""
    return await rt.repo.get_batting_order_state(team_id)


async def pick_batter(rt: IplRuntime, user_id: int, team_id: int, pos: int, dm_msg_id: int | None) -> str:
    """User pressed a player button. Returns: OK | NOT_YOURS | ALREADY | DONE."""
    team = await rt.repo.team_by_id(team_id)
    if not team or team.get("user_id") != user_id:
        return "NOT_YOURS"
    if team.get("batting_order_confirmed"):
        return "DONE"
    res = await rt.repo.batting_order_pick(team_id, pos)
    if res.get("status") not in ("OK", "LAST"):
        return res.get("status", "ERROR")
    state = await get_batting_order_state(rt, team_id)
    if not state:
        return "ERROR"
    tid = team["tournament_id"]
    sess = _session(tid).get(team_id)
    deadline = sess[1] if sess else time.monotonic() + BATTING_ORDER_TIMEOUT
    _set_session(tid, team_id, dm_msg_id, deadline)
    if res.get("status") == "LAST" or not state["remaining"]:
        # All 11 assigned → show confirm screen
        text = m.batting_order_prompt(state["players"], state["ordered"], [])
        markup = kb.batting_order_confirm(team_id)
    else:
        text = m.batting_order_prompt(state["players"], state["ordered"], state["remaining"])
        markup = kb.batting_order(team_id, state["remaining"], len(state["ordered"]))
    if dm_msg_id:
        await notify.edit_dm(rt, user_id, dm_msg_id, text, markup)
    else:
        sent = await notify.dm(rt, user_id, text, markup)
        if sent:
            _set_session(tid, team_id, sent.message_id, deadline)
    return "OK"


async def undo_pick(rt: IplRuntime, user_id: int, team_id: int, dm_msg_id: int | None) -> str:
    """Undo the last batting position assignment."""
    team = await rt.repo.team_by_id(team_id)
    if not team or team.get("user_id") != user_id:
        return "NOT_YOURS"
    if team.get("batting_order_confirmed"):
        return "DONE"
    await rt.repo.batting_order_undo(team_id)
    return await _refresh_dm(rt, user_id, team_id, dm_msg_id, team["tournament_id"])


async def reset_order(rt: IplRuntime, user_id: int, team_id: int, dm_msg_id: int | None) -> str:
    """Reset all batting order picks."""
    team = await rt.repo.team_by_id(team_id)
    if not team or team.get("user_id") != user_id:
        return "NOT_YOURS"
    if team.get("batting_order_confirmed"):
        return "DONE"
    await rt.repo.batting_order_reset(team_id)
    return await _refresh_dm(rt, user_id, team_id, dm_msg_id, team["tournament_id"])


async def confirm_order(rt: IplRuntime, user_id: int, team_id: int, dm_msg_id: int | None) -> str:
    """User confirms their batting order. Returns OK | NOT_YOURS | INCOMPLETE."""
    team = await rt.repo.team_by_id(team_id)
    if not team or team.get("user_id") != user_id:
        return "NOT_YOURS"
    if team.get("batting_order_confirmed"):
        return "ALREADY"
    res = await rt.repo.batting_order_confirm(team_id)
    if res.get("status") != "OK":
        return res.get("status", "ERROR")
    tid = team["tournament_id"]
    _pop_session(tid, team_id)
    state = await get_batting_order_state(rt, team_id)
    players = state["players"] if state else []
    if dm_msg_id:
        await notify.edit_dm(rt, user_id, dm_msg_id, m.batting_order_confirmed_text(players))
    else:
        await notify.dm(rt, user_id, m.batting_order_confirmed_text(players))
    # Attempt to advance the tournament
    await _maybe_advance(rt, tid)
    return "OK"


async def auto_assign_order(rt: IplRuntime, team: dict) -> None:
    """Called when the timeout fires. Smart-assign the batting order silently."""
    team_id = team["id"]
    tid = team["tournament_id"]
    user_id = team["user_id"]
    _pop_session(tid, team_id)
    # Build smart order from the match engine helper using ratings
    squad_rows = await rt.repo.engine_squads(tid)
    squad_map = {int(r["team_id"]): r for r in squad_rows}
    if team_id not in squad_map:
        # Ratings not yet computed (shouldn't happen, but be safe)
        await rt.repo.batting_order_auto_assign(team_id)
    else:
        sq = Squad.from_rpc(squad_map[team_id])
        ordered_ids = [p.id for p in smart_batting_order(sq)]
        await rt.repo.batting_order_set_order(team_id, ordered_ids)
    state = await get_batting_order_state(rt, team_id)
    players = state["players"] if state else []
    sess = _sessions.get(tid, {}).get(team_id)
    dm_msg_id = sess[0] if sess else None
    if dm_msg_id:
        await notify.edit_dm(rt, user_id, dm_msg_id, m.batting_order_timeout_text(players))
    else:
        await notify.dm(rt, user_id, m.batting_order_timeout_text(players))
    await _maybe_advance(rt, tid)


async def _refresh_dm(rt: IplRuntime, user_id: int, team_id: int, dm_msg_id: int | None, tid: int) -> str:
    state = await get_batting_order_state(rt, team_id)
    if not state:
        return "ERROR"
    text = m.batting_order_prompt(state["players"], state["ordered"], state["remaining"])
    markup = (kb.batting_order_confirm(team_id) if not state["remaining"]
              else kb.batting_order(team_id, state["remaining"], len(state["ordered"])))
    if dm_msg_id:
        await notify.edit_dm(rt, user_id, dm_msg_id, text, markup)
    return "OK"


async def _maybe_advance(rt: IplRuntime, tid: int) -> None:
    """If all human teams have confirmed their batting order, kick off the simulation."""
    pending = await rt.repo.teams_pending_batting_order(tid)
    if not pending:
        from . import simulation_worker
        rt.ctx.spawn(simulation_worker.advance(rt, tid), name=f"ipl-advance-{tid}")


# ─────────────────────── timeout worker ───────────────────────────

async def batting_order_tick(rt: IplRuntime) -> None:
    """Called from the main simulation worker tick to auto-assign overdue batting orders."""
    now = time.monotonic()
    for tid, teams in list(_sessions.items()):
        for team_id, (msg_id, deadline) in list(teams.items()):
            if now >= deadline:
                try:
                    team = await rt.repo.team_by_id(team_id)
                    if team and not team.get("batting_order_confirmed"):
                        await auto_assign_order(rt, team)
                except Exception:  # noqa: BLE001
                    log.exception("batting_order_tick auto-assign failed for team %s", team_id)
