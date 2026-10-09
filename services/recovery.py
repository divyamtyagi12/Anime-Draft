"""Resume unfinished games from Supabase after a restart."""
from __future__ import annotations

import logging

from services import draft_service, final_service, leaderboard_service, league_service
from services.context import AppContext

log = logging.getLogger(__name__)


async def recover_games(ctx: AppContext) -> None:
    await ctx.matches.reset_running()
    drafting = await ctx.games.by_status(["DRAFTING"])
    running = await ctx.games.by_status(["LEAGUE", "FINAL"])
    pending_announce = await ctx.games.unannounced_completed()
    for g in drafting:
        ctx.spawn(draft_service.resume_draft(ctx, g["id"]), name=f"resume-draft-{g['id']}")
    for g in running:
        league_service.launch(ctx, g["id"])
    for g in pending_announce:
        ctx.spawn(final_service.announce_final(ctx, g["id"]), name=f"announce-{g['id']}")
    ctx.spawn(leaderboard_service.process_pending(ctx), name="leaderboard-backfill")  # sequential, oldest first
    log.info("Recovery: %d drafting, %d running, %d to announce", len(drafting), len(running), len(pending_announce))
