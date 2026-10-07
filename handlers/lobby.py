from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from handlers.common import get_ctx, is_admin, safe_answer
from handlers.start import GROUP_TYPES
from services import draft_service, lobby_service
from services.telegram_io import delete_later, send_message
from utils import messages as msg

log = logging.getLogger(__name__)


def _display_name(user, existing: list[str]) -> str:
    base = (user.first_name or user.username or f"Player{user.id % 1000}").strip()[:20]
    taken = {n.lower() for n in existing}
    if base.lower() not in taken:
        return base
    if user.username:
        return f"{base} (@{user.username})"[:30]
    return f"{base} #{user.id % 1000}"


async def lobby_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ctx = get_ctx(context)
    q = update.callback_query
    try:
        _, action, gid = (q.data or "").split(":")
        game_id = int(gid)
    except ValueError:
        return await safe_answer(q, "⚠️ Invalid button.")

    game = await ctx.games.get(game_id)
    if not game or not q.message or q.message.chat.id != game["group_id"]:
        return await safe_answer(q, "⚠️ This lobby is no longer active.", True)
    if game["status"] != "LOBBY":
        return await safe_answer(q, "⚠️ This lobby is closed.", True)
    user = q.from_user

    if action == "join":
        await ctx.users.upsert(user.id, user.username, user.first_name)
        row = await ctx.users.get(user.id)
        if not row or not row["dm_started"]:
            await safe_answer(q, msg.dm_prompt_text(), True)
            sent = await send_message(
                ctx, game["group_id"],
                f'<a href="tg://user?id={user.id}">{msg.esc(user.first_name)}</a>, {msg.dm_prompt_text()}',
                reply_markup=lobby_service.open_bot_markup(ctx))
            if sent:  # keep the group clean
                ctx.spawn(delete_later(ctx, game["group_id"], sent.message_id, 45))
            return
        players = await ctx.players.list_for_game(game_id)
        name = _display_name(user, [p["display_name"] for p in players])
        res = await ctx.games.join(game_id, user.id, name)
        texts = {"OK": "⚔️ You joined the draft!", "ALREADY": "✅ You've already joined.",
                 "FULL": "🚫 The lobby is full.", "CLOSED": "⚠️ This lobby is closed."}
        await safe_answer(q, texts.get(res, "⚠️ Could not join."), res != "OK")
        if res == "OK":
            await lobby_service.refresh_lobby(ctx, game_id)

    elif action == "leave":
        res = await ctx.games.leave(game_id, user.id)
        texts = {"OK": "🚪 You left the lobby.", "NOT_IN": "You're not in this game.",
                 "CLOSED": "⚠️ This lobby is closed."}
        await safe_answer(q, texts.get(res, "⚠️ Could not leave."))
        if res == "OK":
            await lobby_service.refresh_lobby(ctx, game_id)

    elif action == "start":
        if user.id != game["host_id"] and not await is_admin(context.bot, game["group_id"], user.id):
            return await safe_answer(q, "❌ Only the host/admin can start the game.", True)
        players = await ctx.players.list_for_game(game_id)
        if len(players) < game["min_players"]:
            return await safe_answer(q, f"❌ Need at least {game['min_players']} players.", True)
        await safe_answer(q, "🔥 Starting the draft…")
        await draft_service.start_game(ctx, game_id)
    else:
        await safe_answer(q, "⚠️ Invalid button.")


async def cancelgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ctx = get_ctx(context)
    chat, user, message = update.effective_chat, update.effective_user, update.effective_message
    if chat.type not in GROUP_TYPES:
        return await message.reply_html("ℹ️ Use /cancelgame in the group where the game is running.")
    game = await ctx.games.active_for_group(chat.id)
    if not game:
        return await message.reply_html("There is no active game here.")
    if user.id != game["host_id"] and not await is_admin(context.bot, chat.id, user.id):
        return await message.reply_html("❌ Only the host/admin can cancel the game.")
    if not await lobby_service.cancel_game(ctx, game, user.first_name or "the host"):
        await message.reply_html("⚠️ That game already ended.")
