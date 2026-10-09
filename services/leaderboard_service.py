"""Leaderboard bookkeeping after a tournament ends.

record_game() is safe to call any number of times (the SQL function is idempotent and
atomic) and never raises, so a leaderboard hiccup can't break the game's announcement.
"""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from game.rating import K_FACTOR, MIN_MATCHES_FOR_WIN_RATE, placement_order
from services import table_service
from services.context import AppContext
from utils import messages as msg

log = logging.getLogger(__name__)


async def record_game(ctx: AppContext, game_id: int) -> bool:
    """Save results → global rating/stats → group stats. True if the game is (now) recorded."""
    try:
        game = await ctx.games.get(game_id)
        if not game or game["status"] != "COMPLETED":
            return False  # cancelled / unfinished tournaments never count
        if game.get("leaderboard_processed"):
            return True
        final = await ctx.matches.final_for_game(game_id)
        if not final or not final.get("winner_id"):
            return False
        ranked, _, _ = await table_service.build_table(ctx, game_id)
        players = await ctx.players.list_for_game(game_id)
        user_of = {p["id"]: p["user_id"] for p in players}
        order = placement_order([r["game_player_id"] for r in ranked],
                                final["p1_id"], final["p2_id"], final["winner_id"])
        res = await ctx.leaderboard.record_game(game_id, [user_of[gp] for gp in order], K_FACTOR)
        status = (res or {}).get("status")
        log.info("Leaderboard: game %s -> %s", game_id, status)
        return status in ("OK", "ALREADY")
    except Exception:  # noqa: BLE001
        log.exception("Leaderboard update failed for game %s (will retry on next restart)", game_id)
        return False


async def process_pending(ctx: AppContext) -> None:
    """Recovery: finished games whose leaderboard update was missed, oldest first (Elo is order-dependent)."""
    for g in await ctx.games.unprocessed_completed():
        await record_game(ctx, g["id"])


def announcement_markup(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌍 GLOBAL RANKINGS", callback_data="lbd:g:0")],
        [InlineKeyboardButton("👥 GROUP RANKINGS", callback_data=f"lbd:grp:{group_id}:champs:0")],
        [InlineKeyboardButton("🎮 PLAY AGAIN", callback_data="lbd:again")],
    ])


async def final_block(ctx: AppContext, game: dict, players: dict[int, dict],
                      final_match: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Text appended to the championship announcement + its buttons. Never raises."""
    markup = announcement_markup(game["group_id"])
    try:
        winner = players[final_match["winner_id"]]
        loser = players[final_match["p2_id"] if final_match["winner_id"] == final_match["p1_id"]
                        else final_match["p1_id"]]
        changes = {r["user_id"]: r for r in await ctx.leaderboard.rating_changes(game["id"])}
        page = await ctx.leaderboard.group_page(game["group_id"], "champs", winner["user_id"], 1, 0,
                                                MIN_MATCHES_FOR_WIN_RATE)
        me = page.get("me") or {}
        text = msg.final_leaderboard_block(
            winner["display_name"], changes.get(winner["user_id"]),
            loser["display_name"], changes.get(loser["user_id"]),
            me.get("championships_won"), me.get("rnk"))
        return text, markup
    except Exception:  # noqa: BLE001
        log.exception("Could not build the leaderboard block for game %s", game["id"])
        return "", markup
