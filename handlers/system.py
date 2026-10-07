from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatType
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

from handlers.common import get_ctx, safe_answer

log = logging.getLogger(__name__)


async def stale_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await safe_answer(q, "⚠️ This button is no longer active.", True)
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Track users blocking/unblocking the bot in DM."""
    ctx = get_ctx(context)
    ev = update.my_chat_member
    if not ev or ev.chat.type != ChatType.PRIVATE:
        return
    status = ev.new_chat_member.status
    if status in ("kicked", "left"):
        await ctx.users.set_dm(ev.chat.id, False)
    elif status == "member":
        await ctx.users.upsert(ev.chat.id, ev.chat.username, ev.chat.first_name, dm_started=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, (NetworkError, TimedOut)):
        log.warning("Network issue talking to Telegram: %s", err)
        return
    log.error("Unhandled exception", exc_info=err)
    if isinstance(update, Update) and update.callback_query:
        await safe_answer(update.callback_query, "⚠️ Something went wrong. Please try again.")
