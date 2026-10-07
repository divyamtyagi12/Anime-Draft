from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from handlers.common import get_ctx
from services import lobby_service
from services.telegram_io import send_message
from utils import messages as msg

GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ctx = get_ctx(context)
    chat, user, message = update.effective_chat, update.effective_user, update.effective_message
    if not chat or not user or not message:
        return

    if chat.type == ChatType.PRIVATE:
        await ctx.users.upsert(user.id, user.username, user.first_name, dm_started=True)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            "➕ Add me to a group", url=f"https://t.me/{ctx.bot_username}?startgroup=true")]])
        await message.reply_html(msg.welcome_dm(), reply_markup=kb)
        return

    if chat.type not in GROUP_TYPES:
        return

    await ctx.groups.upsert(chat.id, chat.title)
    await ctx.users.upsert(user.id, user.username, user.first_name)  # keeps dm_started untouched
    existing = await ctx.games.active_for_group(chat.id)
    if existing:
        if existing["status"] == "LOBBY":  # bring the lobby back to the bottom of the chat
            await lobby_service.refresh_lobby(ctx, existing["id"], repost=True)
        else:
            await message.reply_html("⚠️ A game is already in progress here. Use /status to see it.")
        return

    game = await ctx.games.create(chat.id, user.id, ctx.settings.min_players, ctx.settings.max_players)
    if game is None:  # lost a race with another /start
        await message.reply_html("⚠️ A game is already in progress here. Use /status to see it.")
        return
    await lobby_service.refresh_lobby(ctx, game["id"], repost=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_html(msg.help_text())


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_html(msg.rules_text())
