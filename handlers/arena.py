"""GAME ARENA — the picker shown when someone sends /start in a group.

callback_data (stateless, < 64 bytes):
    ga:ad:<host_id>   start ANIME DRAFT      ga:nw:<host_id>   start NUMBER WARS
    ga:ipl:<host_id>  start IPL DRAFT
    ga:lb:0 | ga:stats:0 | ga:help:0   shared navigation (leaderboards / my stats / help) — open to everyone
    ga:sa:0 | ga:sn:0 | ga:si:0        my stats for Anime Draft / Number Wars / IPL Draft
    ga:x:<host_id>    dismiss the picker     ga:new:0          open a fresh picker (after a game ends)
Only the person who sent /start (the host) or a group admin may choose; everyone else is told so.
"""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from handlers.common import get_ctx, is_admin, safe_answer
from services import lobby_service, number_wars_service as nw_service
from services.context import AppContext
from services.telegram_io import safe_delete, send_message
from utils import messages as msg

log = logging.getLogger(__name__)
GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)


def picker_markup(host_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [Btn("⚔️ Anime Draft", callback_data=f"ga:ad:{host_id}")],
        [Btn("🔢 Number Wars", callback_data=f"ga:nw:{host_id}")],
        [Btn("🏏 IPL Draft", callback_data=f"ga:ipl:{host_id}")],
        [Btn("🏆 Leaderboards", callback_data="ga:lb:0"), Btn("📊 My Stats", callback_data="ga:stats:0")],
        [Btn("📖 Help", callback_data="ga:help:0"), Btn("✖️ Cancel", callback_data=f"ga:x:{host_id}")],
    ])


async def show_picker(ctx: AppContext, chat_id: int, host) -> None:
    await send_message(ctx, chat_id, msg.arena_picker_text(host.first_name or host.username or "Someone"),
                       reply_markup=picker_markup(host.id))


async def ipl_active_for_group(ctx: AppContext, chat_id: int) -> dict | None:
    """Unfinished IPL tournament of this group (None when IPL isn't installed — the other games must not care)."""
    try:
        return await ctx.db.rpc("ipl_active_for_group", {"p_group_id": chat_id})
    except Exception as exc:  # noqa: BLE001
        log.debug("ipl lookup skipped: %s", type(exc).__name__)
        return None


async def active_game_exists(ctx: AppContext, chat_id: int) -> bool:
    return bool(await ctx.games.active_for_group(chat_id) or await ctx.nw.active_for_group(chat_id)
                or await ipl_active_for_group(ctx, chat_id))


NAV_KINDS = ("lb", "stats", "help", "sa", "sn", "si")


async def _nav(ctx: AppContext, context, q, kind: str) -> None:
    """Shared navigation: replies in place, never touches a lobby or a running game."""
    from handlers import leaderboard, number_wars
    user, chat = q.from_user, q.message.chat
    await safe_answer(q)
    if kind == "lb":
        return await send_message(ctx, chat.id, msg.leaderboard_menu_text(), reply_markup=leaderboard.menu_markup())
    if kind == "help":
        return await send_message(ctx, chat.id, msg.help_text())
    if kind == "stats":
        return await send_message(ctx, chat.id, "📊 <b>MY STATS</b>\n\nWhich game?", reply_markup=stats_menu())
    name = user.first_name or user.username or "Player"
    if kind == "sa":
        data = await ctx.leaderboard.global_page(user.id, 1, 0)
        me = (data or {}).get("me")
        text = (f"⚔️ <b>ANIME DRAFT — stats for {msg.esc(name)}</b>\n\n"
                + (f"Rating: <b>{me.get('rating', 1000)}</b> · Global rank: <b>#{me.get('rank') or me.get('rnk')}</b>"
                   if me else "<i>No finished tournaments yet.</i>"))
    elif kind == "sn":
        text = await number_wars._stats_text(ctx, user)
    else:
        from ipl_draft import messages as im
        rt = context.bot_data.get("ipl")
        st = await rt.repo.user_stats(user.id, chat.id if chat.type in GROUP_TYPES else None) if rt and rt.s.enabled else {}
        text = im.user_stats_text(name, (st or {}).get("global"))
    await send_message(ctx, chat.id, text)


def stats_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[Btn("⚔️ Anime Draft", callback_data="ga:sa:0")],
                                 [Btn("🔢 Number Wars", callback_data="ga:sn:0")],
                                 [Btn("🏏 IPL Draft", callback_data="ga:si:0")]])


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_html("📊 <b>MY STATS</b>\n\nWhich game?", reply_markup=stats_menu())


async def arena_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ctx = get_ctx(context)
    q = update.callback_query
    chat, user = (q.message.chat if q.message else None), q.from_user
    if not chat or chat.type not in GROUP_TYPES:
        return await safe_answer(q, "🎮 Start games from a group with /start.", True)
    try:
        _, kind, raw_host = (q.data or "").split(":")
        host_id = int(raw_host)
    except ValueError:
        return await safe_answer(q, "⚠️ Invalid button.")

    if kind == "new":                                   # "NEW GAME" under a final result
        if await active_game_exists(ctx, chat.id):
            return await safe_answer(q, "⚠️ A game is already in progress here. Use /status.", True)
        await ctx.groups.upsert(chat.id, chat.title)
        await ctx.users.upsert(user.id, user.username, user.first_name)
        await safe_answer(q)
        return await show_picker(ctx, chat.id, user)

    if kind in NAV_KINDS:
        return await _nav(ctx, context, q, kind)

    if user.id != host_id and not await is_admin(context.bot, chat.id, user.id):
        return await safe_answer(q, "❌ Only the person who started this (or an admin) can choose.", True)

    if kind == "x":
        await safe_answer(q)
        return await safe_delete(ctx, chat.id, q.message.message_id)
    if kind not in ("ad", "nw", "ipl"):
        return await safe_answer(q, "⚠️ Invalid button.")

    await ctx.groups.upsert(chat.id, chat.title)
    if kind == "ad":
        game = None if await active_game_exists(ctx, chat.id) else await ctx.games.create(
            chat.id, host_id, ctx.settings.min_players, ctx.settings.max_players)
        if game is None:
            await safe_answer(q, "⚠️ A game is already in progress here. Use /status.", True)
            return await safe_delete(ctx, chat.id, q.message.message_id)
        await safe_answer(q, "⚔️ Anime Draft lobby created!")
        await safe_delete(ctx, chat.id, q.message.message_id)
        await lobby_service.refresh_lobby(ctx, game["id"], repost=True)
    elif kind == "ipl":
        from ipl_draft.handlers.commands import create_ipl_lobby
        res = await create_ipl_lobby(context.bot_data["ipl"], chat, user)
        if res != "CREATED":
            await safe_answer(q, "⚠️ IPL Draft is unavailable." if res == "DISABLED" else
                              "⚠️ A game is already in progress here. Use /status.", True)
            return await safe_delete(ctx, chat.id, q.message.message_id) if res == "BUSY" else None
        await safe_answer(q, "🏏 IPL Draft lobby created!")
        await safe_delete(ctx, chat.id, q.message.message_id)
    else:
        ok = not await active_game_exists(ctx, chat.id) and await nw_service.create_lobby(ctx, chat.id, host_id)
        if not ok:
            await safe_answer(q, "⚠️ A game is already in progress here. Use /status.", True)
            return await safe_delete(ctx, chat.id, q.message.message_id)
        await safe_answer(q, "🔢 Number Wars lobby created!")
        await safe_delete(ctx, chat.id, q.message.message_id)
