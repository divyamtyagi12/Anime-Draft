from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from handlers import arena
from handlers.common import get_ctx
from services import lobby_service, number_wars_service as nw_service
from services.telegram_io import send_message
from utils import messages as msg

GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)


def dm_welcome_markup(ctx) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏆 LEADERBOARD", callback_data="lbd:menu")],
        [InlineKeyboardButton("➕ Add me to a group", url=f"https://t.me/{ctx.bot_username}?startgroup=true")],
    ])


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ctx = get_ctx(context)
    chat, user, message = update.effective_chat, update.effective_user, update.effective_message
    if not chat or not user or not message:
        return

    if chat.type == ChatType.PRIVATE:
        await ctx.users.upsert(user.id, user.username, user.first_name, dm_started=True)
        await message.reply_html(msg.welcome_dm(), reply_markup=dm_welcome_markup(ctx))
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

    nw_match = await ctx.nw.active_for_group(chat.id)
    if nw_match:
        if nw_match["status"] == "LOBBY":
            await nw_service.refresh_lobby(ctx, nw_match["id"], repost=True)
        else:
            await message.reply_html("⚠️ A Number Wars match is in progress here. Use /status to see it.")
        return

    await arena.show_picker(ctx, chat.id, user)   # ⚔️ Anime Draft  |  🔢 Number Wars


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_html(msg.help_text())


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_html(msg.rules_text())
