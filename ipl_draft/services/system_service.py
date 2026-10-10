"""System franchises draft through the SAME offer mechanism as humans (11 random cards per pick)."""
from __future__ import annotations

import logging

from ..engine.team_builder import FRANCHISES, choose, force_roles, franchise_payload, snake_order
from ..runtime import IplRuntime

log = logging.getLogger(__name__)


class SystemDraftError(RuntimeError):
    pass


async def run_system_draft(rt: IplRuntime, tid: int) -> None:
    """Resumable: every pick is committed individually, so a restart simply continues where it stopped."""
    prog = await rt.repo.system_progress(tid)
    rosters = {p["team_id"]: list(p["roster"]) for p in prog}
    picks = {p["team_id"]: p["picks"] for p in prog}
    order_ids = [p["team_id"] for p in sorted(prog, key=lambda p: p["team_no"])]
    guard = 0
    while any(picks[t] < 11 for t in order_ids):
        guard += 1
        if guard > 11 * len(order_ids) + 50:
            raise SystemDraftError("system draft made no progress")
        rnd = min(picks[t] for t in order_ids if picks[t] < 11) + 1
        for team_id in snake_order(order_ids, rnd):
            if picks[team_id] != rnd - 1:
                continue
            offer = await rt.repo.open_offer(team_id, force_roles(rosters[team_id]))
            st = offer.get("status")
            if st == "DONE":
                picks[team_id] = 11
                continue
            if st != "OPEN":
                raise SystemDraftError(f"cannot open offer for team {team_id}: {st}")
            ratings = {r["pos"]: r for r in await rt.repo.system_offer_ratings(offer["offer_id"])}
            cards = [{"pos": c["pos"], "role": c["player"]["role"], "bowling_type": c["player"]["bowling_type"],
                      "ratings": ratings[c["pos"]]["ratings"]} for c in offer["candidates"] if c["pos"] in ratings]
            if not cards:
                raise SystemDraftError("offer without rating snapshot")
            pos = choose(cards, rosters[team_id], rt.rng)
            res = await rt.repo.pick(offer["offer_id"], pos, 0, "SYSTEM")
            if res.get("status") not in ("OK", "ALREADY"):
                raise SystemDraftError(f"system pick rejected: {res}")
            if res["status"] == "OK":
                rosters[team_id].append({"role": res["player"]["role"], "bowling_type": res["player"]["bowling_type"]})
            picks[team_id] += 1


async def direct_system_draft_fallback(rt: IplRuntime, tid: int) -> None:
    """Directly fills system teams with balanced squads if RPC cannot pick."""
    teams = await rt.repo.all_teams(tid)
    sys_teams = [x for x in teams if x["kind"] == "SYSTEM"]
    if not sys_teams:
        return

    taken_res = await rt.repo.db.exec(
        lambda c: c.table("ipl_team_rosters").select("player_id").eq("tournament_id", tid)
    )
    taken_ids = {r["player_id"] for r in (taken_res or [])}

    pool_res = await rt.repo.db.exec(
        lambda c: c.table("ipl_tournament_pool")
        .select("player_id, ipl_players(id, display_name, role, bowling_type, batting_style)")
        .eq("tournament_id", tid)
    )
    available: list[dict] = []
    for row in (pool_res or []):
        pid = row["player_id"]
        if pid not in taken_ids and row.get("ipl_players"):
            p = row["ipl_players"]
            available.append({
                "id": pid,
                "role": p.get("role", "BAT"),
                "bowling_type": p.get("bowling_type"),
                "batting_style": p.get("batting_style"),
            })

    by_role: dict[str, list[dict]] = {"WK": [], "BAT": [], "AR": [], "BOWL": []}
    for p in available:
        by_role.setdefault(p["role"], []).append(p)

    for tm in sys_teams:
        existing = await rt.repo.db.exec(
            lambda c, t_id=tm["id"]: c.table("ipl_team_rosters").select("slot, player_id").eq("team_id", t_id)
        )
        existing_slots = {r["slot"] for r in (existing or [])}
        if len(existing_slots) >= 11:
            continue

        needed_slots = [s for s in range(1, 12) if s not in existing_slots]
        composition = ["WK"] + ["BAT"] * 4 + ["AR"] * 2 + ["BOWL"] * 4
        roster_inserts = []
        for slot in needed_slots:
            target_role = composition[slot - 1] if slot <= len(composition) else "BAT"
            candidate = None
            if by_role.get(target_role):
                candidate = by_role[target_role].pop(0)
            else:
                for alt_role in ["BAT", "AR", "BOWL", "WK"]:
                    if by_role.get(alt_role):
                        candidate = by_role[alt_role].pop(0)
                        break
            if candidate:
                taken_ids.add(candidate["id"])
                roster_inserts.append({
                    "tournament_id": tid,
                    "team_id": tm["id"],
                    "player_id": candidate["id"],
                    "slot": slot,
                    "source": "SYSTEM",
                    "batting_order": slot,
                })

        if roster_inserts:
            await rt.repo.db.exec(lambda c: c.table("ipl_team_rosters").insert(roster_inserts))

        await rt.repo.db.exec(
            lambda c, t_id=tm["id"]: c.table("ipl_tournament_teams")
            .update({"squad_complete": True, "batting_order_confirmed": True})
            .eq("id", t_id)
        )


async def prepare_system_teams(rt: IplRuntime, tid: int) -> None:
    """Ensure all 5 system franchises are created, drafted, and ready to go before user draft."""
    t = await rt.repo.get(tid)
    if not t or t["state"] in ("COMPLETED", "CANCELLED"):
        return

    # 1. Ensure the 5 system franchises exist
    teams = await rt.repo.all_teams(tid)
    system_teams = [x for x in teams if x["kind"] == "SYSTEM"]
    if len(system_teams) < len(FRANCHISES):
        await rt.repo.begin_system_teams(tid, franchise_payload())
        system_teams = [x for x in await rt.repo.all_teams(tid) if x["kind"] == "SYSTEM"]

    # 2. Complete draft for any system franchise that needs picks
    prog = await rt.repo.system_progress(tid)
    if not prog or any(p.get("picks", 0) < 11 or not p.get("done") for p in prog):
        try:
            await run_system_draft(rt, tid)
        except Exception as exc:
            log.warning("run_system_draft failed (%s); using direct fallback", exc)
            await direct_system_draft_fallback(rt, tid)

    # 3. Mark complete
    try:
        await rt.repo.complete_system_teams(tid)
    except Exception:
        pass

    # 4. Auto-assign batting order for each franchise
    for s_team in [x for x in await rt.repo.all_teams(tid) if x["kind"] == "SYSTEM"]:
        try:
            await rt.repo.batting_order_auto_assign(s_team["id"])
        except Exception:
            pass
