"""Lobby lifecycle: create, join/leave, force-start, cancel."""
from __future__ import annotations

import asyncio
import logging

from services.telegram_io import check_dm

from .. import keyboards as kb
from .. import messages as m
from ..runtime import IplRuntime
from . import draft_service, notification_service as notify

log = logging.getLogger(__name__)


async def create_lobby(rt: IplRuntime, group_id: int, host_id: int) -> dict | None:
    """None when the group already has an unfinished game of ANY kind (enforced by the database)."""
    t = await rt.repo.create_tournament(group_id, host_id, rt.s.min_humans, rt.s.max_humans, rt.s.draft_seconds)
    if t is None:
        return None
    await notify.refresh_lobby(rt, t["id"], repost=True)
    return t


async def can_receive_dm(rt: IplRuntime, user_id: int) -> bool:
    row = await rt.ctx.users.get(user_id)
    if not row or not row.get("dm_started"):
        return False
    return await check_dm(rt.ctx, user_id)


async def join(rt: IplRuntime, tid: int, user, display_name: str) -> str:
    """Returns OK | ALREADY | FULL | CLOSED | NO_DM."""
    await rt.ctx.users.upsert(user.id, user.username, user.first_name)
    if not await can_receive_dm(rt, user.id):
        return "NO_DM"
    res = await rt.repo.join(tid, user.id, display_name)
    if res == "OK":
        await notify.refresh_lobby(rt, tid)
    return res


async def leave(rt: IplRuntime, tid: int, user_id: int) -> str:
    res = await rt.repo.leave(tid, user_id)
    if res == "OK":
        await notify.refresh_lobby(rt, tid)
    return res


async def force_start(rt: IplRuntime, tid: int) -> tuple[bool, str]:
    """Verifies every human can be DM'd, then moves LOBBY → DRAFTING and sends the first offers."""
    t = await rt.repo.get(tid)
    if not t or t["state"] != "LOBBY":
        return False, "⚠️ This lobby is closed."
    teams = await rt.repo.lobby_teams(tid)
    if len(teams) < t["min_humans"]:
        return False, f"❌ Need at least {t['min_humans']} players to start."
    checks = await asyncio.gather(*(can_receive_dm(rt, tm["user_id"]) for tm in teams))
    bad = [tm["owner_name"] for tm, ok in zip(teams, checks) if not ok]
    if bad:
        return False, "⚠️ Can't DM: " + ", ".join(bad) + ". They must start the bot privately first."
    res = await rt.repo.start_draft(tid, rt.s.pool_margin)
    st = res.get("status")
    if st == "POOL_TOO_SMALL":
        log.error("IPL pool too small: have %s need %s", res.get("have"), res.get("need"))
        return False, (f"❌ Not enough IPL players in the database to start ({res.get('have')} available, "
                       f"{res.get('need')} needed). The bot owner must import more players.")
    if st == "TOO_FEW":
        return False, f"❌ Need at least {res.get('need')} players."
    if st != "OK":
        return False, "⚠️ Could not start the draft."
    await notify.refresh_lobby(rt, tid)
    rt.ctx.spawn(draft_service.kickoff(rt, tid), name=f"ipl-kickoff-{tid}")
    return True, "🚀 Draft started!"


async def cancel(rt: IplRuntime, t: dict, by_name: str) -> bool:
    if not await rt.repo.cancel(t["id"]):
        return False
    await notify.refresh_lobby(rt, t["id"])
    await notify.group(rt, t["group_id"], f"❌ IPL Draft cancelled by {m.esc(by_name)}.")
    teams = await rt.repo.all_teams(t["id"])
    await asyncio.gather(*(notify.dm(rt, tm["user_id"], "❌ The IPL DRAFT in your group was cancelled.")
                           for tm in teams if tm["kind"] == "HUMAN"), return_exceptions=True)
    return True
