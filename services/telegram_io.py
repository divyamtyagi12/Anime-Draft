"""Resilient Telegram I/O: retries, rate limits, blocked users, deleted messages."""
from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardMarkup, Message
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError, TimedOut

from services.context import AppContext

log = logging.getLogger(__name__)


async def send_message(ctx: AppContext, chat_id: int, text: str, *,
                       reply_markup: InlineKeyboardMarkup | None = None) -> Message | None:
    """Returns None on failure; a blocked user is flagged so the lobby refuses them."""
    for attempt in range(1, 4):
        try:
            return await ctx.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML,
                                              reply_markup=reply_markup)
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 0.5)
        except Forbidden:
            log.warning("Cannot message chat %s (blocked / removed)", chat_id)
            if chat_id > 0:
                await ctx.users.set_dm(chat_id, False)
            return None
        except (TimedOut, NetworkError):
            await asyncio.sleep(attempt)
        except TelegramError as exc:
            log.warning("send_message to %s failed: %s", chat_id, exc)
            return None
    return None


async def safe_edit(ctx: AppContext, chat_id: int, message_id: int, text: str, *,
                    reply_markup: InlineKeyboardMarkup | None = None) -> str:
    """Returns 'ok' | 'gone' (message deleted/uneditable) | 'error' (transient)."""
    for attempt in range(1, 4):
        try:
            await ctx.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
                                            parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            return "ok"
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 0.5)
        except BadRequest as exc:
            msg = str(exc).lower()
            if "not modified" in msg:
                return "ok"
            if "not found" in msg or "can't be edited" in msg or "message_id_invalid" in msg:
                return "gone"
            log.warning("edit in %s failed: %s", chat_id, exc)
            return "error"
        except Forbidden:
            return "gone"
        except (TimedOut, NetworkError):
            await asyncio.sleep(attempt)
        except TelegramError as exc:
            log.warning("edit in %s failed: %s", chat_id, exc)
            return "error"
    return "error"


async def safe_delete(ctx: AppContext, chat_id: int, message_id: int) -> None:
    try:
        await ctx.bot.delete_message(chat_id, message_id)
    except TelegramError:
        pass


async def delete_later(ctx: AppContext, chat_id: int, message_id: int, seconds: float) -> None:
    await asyncio.sleep(seconds)
    await safe_delete(ctx, chat_id, message_id)


async def check_dm(ctx: AppContext, user_id: int) -> bool:
    """Can the bot DM this user right now? (typing action is invisible & harmless)"""
    try:
        await ctx.bot.send_chat_action(user_id, ChatAction.TYPING)
        return True
    except (Forbidden, BadRequest):
        await ctx.users.set_dm(user_id, False)
        return False
    except TelegramError:
        return True  # transient problem: don't punish the player
