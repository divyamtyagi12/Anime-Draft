"""All user-facing text (HTML parse mode). Pure functions, no Telegram imports."""
from __future__ import annotations

import html
from typing import Any, Mapping, Sequence

from game.battle import ClashResult, MatchResult, margin_label
from game.categories import CATEGORY_BY_KEY, CATEGORY_KEYS, TEAM_SIZE
from models.character import RARITY_EMOJI, Character

RANK_BADGES = ["🥇", "🥈", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def esc(text: Any) -> str:
    return html.escape(str(text), quote=False)


def rank_badge(i: int) -> str:
    return RANK_BADGES[i] if i < len(RANK_BADGES) else f"{i + 1}."


# ───────────────────────── static texts ─────────────────────────
def welcome_dm() -> str:
    return (
        "🎴 <b>ANIME DRAFT</b>\n\n"
        "✅ You're all set — I can DM you now!\n\n"
        "<b>How to play</b>\n"
        "1️⃣ Add me to a group and send /start there\n"
        "2️⃣ Everyone presses ⚔️ JOIN (3–8 players)\n"
        "3️⃣ Draft six characters here in DM\n"
        "4️⃣ Round-robin league → 🔥 Grand Final\n\n"
        "Games must be created in a <b>group</b>. See /rules and /help."
    )


def help_text() -> str:
    return (
        "🎴 <b>ANIME DRAFT — Commands</b>\n\n"
        "/start — create a lobby (group) or register (DM)\n"
        "/rules — how the game works\n"
        "/team — your drafted team (DM)\n"
        "/draft — resend your current draft prompt (DM)\n"
        "/table — league standings (group)\n"
        "/status — current game status\n"
        "/cancelgame — cancel the game (host/admin)\n"
    )


def rules_text() -> str:
    return (
        "📜 <b>ANIME DRAFT — Rules</b>\n\n"
        "<b>Franchises:</b> Re:ZERO · Black Clover · Death Note · Ben 10\n\n"
        "<b>Draft</b> — in your DM you build a team of six, one per category: "
        "⚔️ Attack · 🛡️ Defense · 🏰 Tanking · ⚡ Speed · 💚 Healing · 🧠 Intelligence. "
        "Each category offers 5 random eligible characters. A character can't fill two of your slots.\n\n"
        "<b>League</b> — everyone fights everyone once. Each match = 6 clashes "
        "(category vs same category). Ratings are fixed; a small ±5% luck factor only matters in close fights.\n"
        "Win = 3 pts · Draw (3-3) = 1 pt · Loss = 0.\n"
        "Ranking: points → clash difference → clashes won → head-to-head → random.\n\n"
        "<b>Grand Final</b> — top two meet. 4+ clashes wins. A 3-3 goes to the "
        "🔥 Ultimate Tiebreaker (whole-team strength)."
    )


def dm_prompt_text() -> str:
    return "⚠️ You need to start the bot in DM first."


# ───────────────────────── lobby / draft ─────────────────────────
def lobby_text(game: Mapping[str, Any], players: Sequence[Mapping[str, Any]]) -> str:
    status = game["status"]
    lines = ["🎴 <b>ANIME DRAFT</b>", "", "Build your team and battle for the championship!", "",
             f"👥 Players: {len(players)}/{game['max_players']}"]
    if players:
        lines += [""] + [f"{i}. {esc(p['display_name'])}" for i, p in enumerate(players, 1)]
    lines.append("")
    if status == "LOBBY":
        need = game["min_players"]
        lines.append("Waiting for players..." if len(players) < need
                     else "✅ Enough players — the host can press FORCE START.")
        lines.append(f"<i>Minimum {need} players. You must have started the bot in DM first.</i>")
    elif status == "DRAFTING":
        lines.append("🔒 Lobby locked — check your DMs and draft your team!")
    elif status in ("LEAGUE", "FINAL"):
        lines.append("🏟 The tournament is underway!")
    elif status == "COMPLETED":
        lines.append("🏆 This tournament has finished.")
    elif status == "CANCELLED":
        lines.append("❌ This game was cancelled.")
    return "\n".join(lines)


def progress_text(players: Sequence[Mapping[str, Any]], counts: Mapping[int, int]) -> str:
    lines = ["🎴 <b>Draft Progress</b>", ""]
    for p in players:
        if p["draft_done"]:
            lines.append(f"✅ {esc(p['display_name'])}")
        else:
            lines.append(f"⏳ {esc(p['display_name'])} ({counts.get(p['id'], 0)}/{TEAM_SIZE})")
    if players and all(p["draft_done"] for p in players):
        lines += ["", "🔒 All teams locked! The league begins now…"]
    return "\n".join(lines)


def draft_intro(group_title: str) -> str:
    return (
        f"🎴 <b>ANIME DRAFT</b> has begun in <b>{esc(group_title or 'your group')}</b>!\n\n"
        f"Pick {TEAM_SIZE} characters — one for each category. Choices are final, and your team "
        "stays secret until the battles."
    )


def button_labels(chars: Sequence[Character]) -> list[str]:
    firsts = [c.short_name for c in chars]
    return [c.name if firsts.count(c.short_name) > 1 else c.short_name for c in chars]


def offer_text(category: str, idx: int, chars: Sequence[Character]) -> str:
    info = CATEGORY_BY_KEY[category]
    lines = [f"{info.emoji} <b>{info.label.upper()} DRAFT</b>  ({idx + 1}/{TEAM_SIZE})", "",
             f"Choose your {info.label} character:", ""]
    for i, c in enumerate(chars, 1):
        lines.append(f"{i}. <b>{esc(c.name)}</b> <i>({esc(c.series)})</i> · "
                     f"{RARITY_EMOJI.get(c.rarity, '')} {c.rating(category)}")
    lines += ["", "<i>Tap a name below — choices are final.</i>"]
    return "\n".join(lines)


def pick_locked_text(category: str, char: Character, auto: bool = False) -> str:
    info = CATEGORY_BY_KEY[category]
    suffix = " (auto-picked)" if auto else ""
    return f"✅ {info.emoji} {info.label} locked in: <b>{esc(char.name)}</b>{suffix}"


def team_text(picks: Mapping[str, Character], locked: bool) -> str:
    lines = ["🎴 <b>YOUR ANIME DRAFT TEAM</b>", ""]
    for cat in CATEGORY_KEYS:
        info = CATEGORY_BY_KEY[cat]
        c = picks.get(cat)
        lines.append(f"{info.emoji} {info.label} — " + (f"{esc(c.name)} <i>({c.rating(cat)})</i>" if c else "—"))
    if locked:
        lines += ["", "🔒 <b>TEAM LOCKED</b>"]
    return "\n".join(lines)


# ───────────────────────── battles ─────────────────────────
def battle_intro(title: str, n1: str, n2: str) -> str:
    return f"<b>{esc(title)}</b>\n{esc(n1)} 🆚 {esc(n2)}\n\n⏳ The teams enter the arena…"


def battle_progress_text(title: str, n1: str, n2: str, clashes: Sequence[ClashResult], shown: int) -> str:
    cur = clashes[shown - 1]
    s1 = sum(1 for c in clashes[:shown] if c.winner_side == 1)
    s2 = shown - s1
    info = CATEGORY_BY_KEY[cur.category]
    lines = [f"<b>{esc(title)}</b>", f"{esc(n1)} 🆚 {esc(n2)}", ""]
    for c in clashes[: shown - 1]:
        e = CATEGORY_BY_KEY[c.category].emoji
        lines.append(f"{e} {esc(c.p1_char.short_name)} 🆚 {esc(c.p2_char.short_name)} → 🏆 {esc(c.winner_char.short_name)}")
    if shown > 1:
        lines.append("")
    lines += [
        f"{info.emoji} <b>{info.label.upper()} CLASH</b>", "",
        f"<b>{esc(n1.upper())}</b>", f"{esc(cur.p1_char.name)} <i>({cur.p1_rating})</i>", "",
        "VS", "",
        f"<b>{esc(n2.upper())}</b>", f"{esc(cur.p2_char.name)} <i>({cur.p2_rating})</i>", "",
        f"🏆 <b>{esc(cur.winner_char.name)}</b> — {margin_label(cur)}", "",
        f"<b>{esc(n1)} {s1} - {s2} {esc(n2)}</b>",
    ]
    return "\n".join(lines)


def tiebreak_text(title: str, n1: str, n2: str, result: MatchResult, reveal: bool) -> str:
    base = battle_progress_text(title, n1, n2, result.clashes, len(result.clashes))
    lines = [base, "", "🔥 <b>ULTIMATE TIEBREAKER</b>", "Comparing the complete six-character teams…"]
    if reveal and result.tiebreak:
        tb = result.tiebreak
        w = n1 if tb.winner_side == 1 else n2
        lines += ["", f"{esc(n1)}: {tb.p1_score:.1f}  |  {esc(n2)}: {tb.p2_score:.1f}", f"🏆 <b>{esc(w)}</b> takes it!"]
    return "\n".join(lines)


def scorecard_text(n1: str, n2: str, result: MatchResult, final: bool = False) -> str:
    head = "🏁 <b>GRAND FINAL COMPLETE</b>" if final else "🏁 <b>MATCH COMPLETE</b>"
    lines = [head, "", f"<b>{esc(n1.upper())} {result.p1_wins} - {result.p2_wins} {esc(n2.upper())}</b>", ""]
    for c in result.clashes:
        info = CATEGORY_BY_KEY[c.category]
        w = n1 if c.winner_side == 1 else n2
        lines.append(f"{info.emoji} {info.label}: {esc(w)} <i>({esc(c.p1_char.short_name)} vs {esc(c.p2_char.short_name)})</i>")
    lines.append("")
    if result.tiebreak:
        tb = result.tiebreak
        lines.append(f"🔥 Ultimate Tiebreaker: {tb.p1_score:.1f} vs {tb.p2_score:.1f}")
    side = result.winner_side
    lines.append("🤝 <b>DRAW</b>" if side == 0 else f"🏆 <b>{esc((n1 if side == 1 else n2).upper())} WINS</b>")
    return "\n".join(lines)


# ───────────────────────── standings / final ─────────────────────────
def table_text(ranked: Sequence[Mapping[str, Any]], names: Mapping[int, str], subtitle: str | None = None) -> str:
    lines = ["🏆 <b>ANIME DRAFT LEAGUE</b>"]
    if subtitle:
        lines.append(f"<i>{esc(subtitle)}</i>")
    lines.append("")
    if not ranked:
        return "\n".join(lines + ["No standings yet — the league hasn't started."])
    body = ["   Player      P  W  D  L  +/-  PTS"]
    for i, r in enumerate(ranked):
        name = esc(f"{names.get(r['game_player_id'], '?')[:10]:<10}")
        body.append(f"{rank_badge(i)} {name} {r['played']:>2} {r['wins']:>2} {r['draws']:>2} "
                    f"{r['losses']:>2} {r['clash_difference']:>+4} {r['points']:>4}")
    lines.append("<pre>" + "\n".join(body) + "</pre>")
    return "\n".join(lines)


def league_complete_text(n1: str, pts1: int, n2: str, pts2: int) -> str:
    return (
        "🏆 <b>LEAGUE STAGE COMPLETE</b>\n\n"
        f"🥇 {esc(n1)} — {pts1} PTS\n🥈 {esc(n2)} — {pts2} PTS\n\n"
        f"🔥 <b>GRAND FINAL</b>\n\n<b>{esc(n1.upper())}</b>\nVS\n<b>{esc(n2.upper())}</b>\n\n"
        "<i>The final is being fought in the finalists' DMs…</i>"
    )


def final_announcement(n1: str, n2: str, result: MatchResult) -> str:
    side = result.winner_side
    champ, runner = (n1, n2) if side == 1 else (n2, n1)
    lines = ["🏆 <b>ANIME DRAFT CHAMPIONSHIP</b> 🏆", "", "🔥 <b>GRAND FINAL RESULT</b>", "",
             f"TEAM {esc(n1.upper())}", f"<b>{result.p1_wins} - {result.p2_wins}</b>", f"TEAM {esc(n2.upper())}"]
    if result.tiebreak:
        lines.append("<i>(3-3 — decided by the Ultimate Tiebreaker)</i>")
    lines.append("")
    for c in result.clashes:
        info = CATEGORY_BY_KEY[c.category]
        lines.append(f"{info.emoji} {info.label} — {esc(n1 if c.winner_side == 1 else n2)}")
    lines += ["", "👑 <b>CHAMPION</b>", "", f"🎉 <b>TEAM {esc(champ.upper())} WINS!</b> 🪩", "",
              f"🥇 {esc(champ)}", f"🥈 {esc(runner)}", "", "Congratulations!"]
    return "\n".join(lines)
