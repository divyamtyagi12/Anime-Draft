from __future__ import annotations

from game.tournament import rank_standings
from services.context import AppContext
from services.telegram_io import safe_edit, send_message
from utils import messages as msg


async def build_table(ctx: AppContext, game_id: int):
    players = await ctx.players.list_for_game(game_id)
    standings = await ctx.standings.list_for_game(game_id)
    matches = await ctx.matches.list_for_game(game_id, "LEAGUE")
    ranked = rank_standings(standings, matches, seed=game_id)
    names = {p["id"]: p["display_name"] for p in players}
    return ranked, names, matches


async def table_message(ctx: AppContext, game_id: int, subtitle: str | None = None) -> str:
    ranked, names, _ = await build_table(ctx, game_id)
    return msg.table_text(ranked, names, subtitle)


async def post_table(ctx: AppContext, game_id: int, subtitle: str | None = None) -> None:
    """Update the single standings message in the group (edit in place)."""
    game = await ctx.games.get(game_id)
    if not game:
        return
    text = await table_message(ctx, game_id, subtitle)
    mid = game.get("table_message_id")
    if mid and await safe_edit(ctx, game["group_id"], mid, text) != "gone":
        return
    sent = await send_message(ctx, game["group_id"], text)
    if sent:
        await ctx.games.update(game_id, table_message_id=sent.message_id)
