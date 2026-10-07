from __future__ import annotations

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from handlers.common import get_ctx, safe_answer
from services import draft_service


async def draft_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ctx = get_ctx(context)
    q = update.callback_query
    try:
        _, gp, idx, pos = (q.data or "").split(":")
        gp_id, cat_idx, position = int(gp), int(idx), int(pos)
    except ValueError:
        return await safe_answer(q, "⚠️ Invalid button.")
    await draft_service.handle_pick(ctx, q, gp_id, cat_idx, position)


async def draft_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/draft (DM) — resend the current draft prompt if the message got lost."""
    ctx = get_ctx(context)
    chat, user, message = update.effective_chat, update.effective_user, update.effective_message
    if chat.type != ChatType.PRIVATE:
        return await message.reply_html("ℹ️ Use /draft in my DM.")
    for gp in await ctx.players.for_user(user.id, 5):
        game = await ctx.games.get(gp["game_id"])
        if game and game["status"] == "DRAFTING" and not gp["draft_done"]:
            if not await draft_service.send_prompt(ctx, gp):
                await message.reply_html("⚠️ Couldn't resend the prompt — try again in a moment.")
            return
    await message.reply_html("You have no draft in progress.")
