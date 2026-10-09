"""GAME ARENA — the picker shown when someone sends /start in a group.

callback_data (stateless, < 64 bytes):
    ga:ad:<host_id>   start ANIME DRAFT      ga:nw:<host_id>   start NUMBER WARS
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
        [Btn("✖️ Cancel", callback_data=f"ga:x:{host_id}")],
    ])


async def show_picker(ctx: AppContext, chat_id: int, host) -> None:
    await send_message(ctx, chat_id, msg.arena_picker_text(host.first_name or host.username or "Someone"),
                       reply_markup=picker_markup(host.id))


async def active_game_exists(ctx: AppContext, chat_id: int) -> bool:
    return bool(await ctx.games.active_for_group(chat_id) or await ctx.nw.active_for_group(chat_id))


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

    if user.id != host_id and not await is_admin(context.bot, chat.id, user.id):
        return await safe_answer(q, "❌ Only the person who started this (or an admin) can choose.", True)

    if kind == "x":
        await safe_answer(q)
        return await safe_delete(ctx, chat.id, q.message.message_id)
    if kind not in ("ad", "nw"):
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
    else:
        ok = not await active_game_exists(ctx, chat.id) and await nw_service.create_lobby(ctx, chat.id, host_id)
        if not ok:
            await safe_answer(q, "⚠️ A game is already in progress here. Use /status.", True)
            return await safe_delete(ctx, chat.id, q.message.message_id)
        await safe_answer(q, "🔢 Number Wars lobby created!")
        await safe_delete(ctx, chat.id, q.message.message_id)
