"""Inline keyboards. Callback data is namespaced `ipl:` and always < 64 bytes (ids are compact integers)."""
from __future__ import annotations

from typing import Sequence

from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Markup


def lobby(tid: int) -> Markup:
    return Markup([[Btn("✅ JOIN", callback_data=f"ipl:j:{tid}"), Btn("❌ LEAVE", callback_data=f"ipl:lv:{tid}")],
                   [Btn("🚀 FORCE START", callback_data=f"ipl:st:{tid}")],
                   [Btn("📖 RULES", callback_data=f"ipl:ru:{tid}")]])


def open_bot(bot_username: str) -> Markup:
    return Markup([[Btn("🤖 START THE BOT", url=f"https://t.me/{bot_username}?start=ipl")]])


def offer(offer_id: int, cands: Sequence[dict], team_id: int) -> Markup:
    rows = [[Btn(f"{c['pos']}. {c['player']['name']}", callback_data=f"ipl:pk:{offer_id}:{c['pos']}")] for c in cands]
    rows.append([Btn("📋 MY TEAM", callback_data=f"ipl:tm:{team_id}")])
    return Markup(rows)


def confirm(offer_id: int, pos: int) -> Markup:
    return Markup([[Btn("✅ CONFIRM", callback_data=f"ipl:cf:{offer_id}:{pos}")],
                   [Btn("🔙 BACK", callback_data=f"ipl:bk:{offer_id}")]])


def draft_done(team_id: int, tid: int) -> Markup:
    return Markup([[Btn("📋 VIEW MY SQUAD", callback_data=f"ipl:tm:{team_id}")],
                   [Btn("🏆 TOURNAMENT STATUS", callback_data=f"ipl:ts:{tid}")]])


def group_dashboard(tid: int) -> Markup:
    return Markup([[Btn("🏆 POINTS TABLE", callback_data=f"ipl:tb:{tid}"), Btn("📅 FIXTURES", callback_data=f"ipl:fx:{tid}:0")],
                   [Btn("📋 MATCH HISTORY", callback_data=f"ipl:mh:{tid}:0"), Btn("🔥 PLAYOFF BRACKET", callback_data=f"ipl:br:{tid}")],
                   [Btn("📋 VIEW ALL TEAMS", callback_data=f"ipl:at:{tid}:0")]])


def teams_ready(tid: int) -> Markup:
    return Markup([[Btn("📋 VIEW ALL TEAMS", callback_data=f"ipl:at:{tid}:0")],
                   [Btn("🏆 START TOURNAMENT", callback_data=f"ipl:ts:{tid}")]])


def match_buttons(tid: int, match_id: int) -> Markup:
    return Markup([[Btn("📊 FULL SCORECARD", callback_data=f"ipl:sc:{match_id}:0")],
                   [Btn("🏆 POINTS TABLE", callback_data=f"ipl:tb:{tid}"), Btn("📅 FIXTURES", callback_data=f"ipl:fx:{tid}:0")]])


PAGER = {"fx": "fp", "mh": "mp", "at": "ap"}      # dashboard entry button → in-place paging button


def pager(prefix: str, ident: int, page: int, pages: int, back: str | None = None) -> Markup:
    prefix = PAGER.get(prefix, prefix)
    row = []
    if page > 0:
        row.append(Btn("◀️", callback_data=f"ipl:{prefix}:{ident}:{page - 1}"))
    row.append(Btn(f"{page + 1}/{pages}", callback_data=f"ipl:{prefix}:{ident}:{page}"))
    if page < pages - 1:
        row.append(Btn("▶️", callback_data=f"ipl:{prefix}:{ident}:{page + 1}"))
    rows = [row]
    if back:
        rows.append([Btn("🔙 BACK", callback_data=back)])
    return Markup(rows)


def table_markup(tid: int) -> Markup:
    return Markup([[Btn("🔥 PLAYOFF BRACKET", callback_data=f"ipl:br:{tid}"), Btn("📋 MATCH HISTORY", callback_data=f"ipl:mh:{tid}:0")],
                   [Btn("🔄 REFRESH", callback_data=f"ipl:tr:{tid}")]])


def final_buttons(tid: int, last_match_id: int | None) -> Markup:
    rows = []
    if last_match_id:
        rows.append([Btn("📊 FINAL SCORECARD", callback_data=f"ipl:sc:{last_match_id}:0")])
    rows += [[Btn("🏆 TOURNAMENT SUMMARY", callback_data=f"ipl:sm:{tid}")],
             [Btn("🥇 LEADERBOARD", callback_data="ipl:lb:g:0"), Btn("🔄 PLAY AGAIN", callback_data="ipl:pa")]]
    return Markup(rows)


def leaderboard(scope: str, group_id: int, page: int) -> Markup:
    g = f"ipl:lb:g:{page}"
    c = f"ipl:lb:c:{page}"
    return Markup([[Btn("🌍 GLOBAL" + (" ✅" if scope == "g" else ""), callback_data="ipl:lb:g:0"),
                    Btn("👥 GROUP" + (" ✅" if scope == "c" else ""), callback_data="ipl:lb:c:0")],
                   [Btn("◀️", callback_data=f"ipl:lb:{scope}:{max(page - 1, 0)}"), Btn("▶️", callback_data=f"ipl:lb:{scope}:{page + 1}")],
                   [Btn("🔙 BACK", callback_data="lbd:menu")]])
