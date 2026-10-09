"""NUMBER WARS — all user-facing text (HTML parse mode). Pure functions, no Telegram imports."""
from __future__ import annotations

from fractions import Fraction
from typing import Any, Mapping, Sequence

from game.number_wars import (END_ALL_ELIMINATED, END_LAST_STANDING, END_ROUND_LIMIT, MAX_HP,
                              RoundOutcome)
from utils.messages import esc, rank_badge

SEP = "━━━━━━━━━━━━━━━━━━"


def num(x: Fraction | float | int | None, places: int = 2) -> str:
    """12 → '12', 40/3 → '13.33'."""
    if x is None:
        return "—"
    f = float(x)
    text = f"{f:.{places}f}".rstrip("0").rstrip(".")
    return text or "0"


def hp_bar(hp: int) -> str:
    return "❤️" * hp + "🖤" * (MAX_HP - hp)


# ───────────────────────── static ─────────────────────────
def rules_text(round_seconds: int = 30, max_rounds: int = 30) -> str:
    return (
        "📜 <b>NUMBER WARS — Rules</b>\n\n"
        f"Everyone secretly picks a number from <b>0 to 100</b> in a private chat with me ({round_seconds}s).\n"
        "Then: <b>Target = Average × 0.8</b>. The closest number to the target wins the round.\n\n"
        f"❤️ Everyone starts with <b>{MAX_HP} HP</b>.\n"
        "• Closest number (ties share it): <b>no damage</b>\n"
        "• Everyone else who submitted: <b>−1 HP</b>\n"
        "• Exact target match: <b>+2 HP</b> (max 10)\n"
        "• No submission: <b>−2 HP</b> (and you're left out of the average)\n"
        "• 0 HP = eliminated. Last one standing is champion! 👑\n\n"
        "<b>Special cases</b>\n"
        "• Only one player submits → they win the round, others −2 HP.\n"
        "• Nobody submits → no target, everyone −2 HP.\n"
        "• 3 rounds in a row where nobody loses HP → ⚡ <b>sudden death</b>: a random multiplier "
        "(0.5, 0.8, 1.2 or 1.5) is announced <i>before</i> you pick.\n"
        f"• After <b>{max_rounds} rounds</b> survivors are ranked by HP → round wins → lowest total distance.\n"
        "• Everyone knocked out together → best pre-round HP / wins / distance takes the crown.\n\n"
        "<b>Locking</b> is final. Numbers stay hidden until the round ends.\n"
        "<b>Rating:</b> start 1000 · +25 win · +10 shared title · −5 loss."
    )


def dm_prompt_hint() -> str:
    return "Tap the buttons — or just send me a number from 0 to 100."


# ───────────────────────── lobby ─────────────────────────
def lobby_text(match: Mapping[str, Any], players: Sequence[Mapping[str, Any]],
               round_seconds: int, countdown: int) -> str:
    status = match["status"]
    lines = ["🔢 <b>NUMBER WARS</b>", "<i>Elimination Lobby</i>", "",
             f"👥 Players: {len(players)}/{match['max_players']}",
             f"❤️ Starting HP: {MAX_HP}", f"⏱ Round timer: {round_seconds} seconds"]
    if players:
        lines += ["", "<b>Joined players:</b>"]
        lines += [f"{i}. {esc(p['display_name'])}" for i, p in enumerate(players, 1)]
    lines.append("")
    if status == "LOBBY":
        need = match["min_players"]
        if len(players) < need:
            lines.append(f"Waiting for players… (need {need - len(players)} more)")
        else:
            lines.append("✅ Enough players — the host or an admin can press START."
                         + (f"\n⏳ It also starts automatically {countdown}s after the minimum was reached."
                            if countdown else ""))
        lines.append(f"<i>Minimum {need} players. You must have started the bot in DM first.</i>")
    elif status == "ACTIVE":
        lines.append("🔒 Lobby locked — the match is underway! Watch your DMs.")
    elif status == "FINISHED":
        lines.append("🏆 This match has finished.")
    elif status == "CANCELLED":
        lines.append("❌ This match was cancelled.")
    return "\n".join(lines)


# ───────────────────────── rounds ─────────────────────────
def mult_label(multiplier: Any) -> str:
    return f"×{num(Fraction(str(multiplier)))}"


def round_start_group(rnd: Mapping[str, Any], alive: int, seconds: int) -> str:
    head = "⚡ <b>SUDDEN DEATH</b> — " if rnd.get("sudden_death") else ""
    return (f"🔢 {head}<b>ROUND {rnd['round_number']}</b>\n\n"
            f"👥 {alive} players alive · ⏱ {seconds} seconds\n"
            f"🎯 Target = Average {mult_label(rnd['multiplier'])}\n\n"
            "📩 Check your DMs and lock in a number!")


def dm_prompt(rnd: Mapping[str, Any], hp: int, alive: int, seconds: int, value: int) -> str:
    head = "⚡ SUDDEN DEATH — " if rnd.get("sudden_death") else ""
    return (f"🔢 <b>{head}ROUND {rnd['round_number']} — Choose Your Number</b>\n\n"
            f"❤️ Your HP: <b>{hp}/{MAX_HP}</b>\n"
            f"👥 Remaining players: <b>{alive}</b>\n"
            f"🎯 Target = Average <b>{mult_label(rnd['multiplier'])}</b>\n"
            f"⏱ You have {seconds} seconds\n\n"
            f"<i>{dm_prompt_hint()}</i>"
            f"{selected_tail(value)}")


TAIL_MARK = "\n\n🎯 Your number:"


def selected_tail(value: int) -> str:
    return f"{TAIL_MARK} <b>{value}</b>"


def locked_text(value: int) -> str:
    return (f"🔒 <b>Locked in: {value}</b>\n"
            "Waiting for the other players… results appear in the group.")


def missed_text(round_number: int | str) -> str:
    return f"⏰ <b>Round {round_number} closed</b> — you didn't lock a number in time (−2 HP)."


def round_result(rnd: Mapping[str, Any], outcome: RoundOutcome, names: Mapping[int, str]) -> str:
    n = rnd["round_number"]
    head = "⚡ SUDDEN DEATH " if rnd.get("sudden_death") else ""
    lines = [f"🔢 <b>{head}ROUND {n} — RESULTS</b>", SEP]
    if outcome.target is None:
        if outcome.submitted == 0:
            lines.append("😴 Nobody submitted a number — no target this round.")
        else:
            lines.append("☝️ Only one player submitted — they win the round automatically.")
    else:
        lines += [f"📊 Average: <b>{num(outcome.average)}</b>",
                  f"🎯 Target ({mult_label(outcome.multiplier)}): <b>{num(outcome.target)}</b>"]
    lines.append(SEP)

    def order(r):
        return (r.number is None, r.distance is None, float(r.distance or 0), not r.is_winner)

    for r in sorted(outcome.results, key=order):
        name = esc(names.get(r.user_id, "?"))
        if r.number is None:
            body = f"😴 {name} — no number"
        else:
            icon = "🎯" if r.exact else ("🏆" if r.is_winner else "▫️")
            dist = "" if r.distance is None else f" (off by {num(r.distance)})"
            body = f"{icon} {name} — <b>{r.number}</b>{dist}"
        delta = f"{r.hp_delta:+d}".replace("-", "−") if r.hp_delta else "±0"
        tail = "💀 ELIMINATED" if r.eliminated else f"❤️ {r.hp_after}/{MAX_HP} ({delta})"
        lines.append(f"{body}\n      {tail}")
    exact = [esc(names.get(r.user_id, "?")) for r in outcome.results if r.exact]
    if exact:
        lines += ["", f"🎯 <b>Exact hit!</b> {', '.join(exact)} +2 HP"]
    return "\n".join(lines)


def eliminated_dm(round_number: int) -> str:
    return (f"💀 <b>You were eliminated in round {round_number}.</b>\n"
            "Thanks for playing — watch the group for the final result!")


# ───────────────────────── final ─────────────────────────
REASONS = {END_LAST_STANDING: "Last player standing",
           END_ROUND_LIMIT: "Round limit reached — ranked by HP, round wins, distance",
           END_ALL_ELIMINATED: "Everyone fell together — decided by pre-round standing"}


def _final_order(match: Mapping[str, Any], players: Sequence[Mapping[str, Any]]):
    winners = set(match.get("winner_ids") or [])

    def key(p):
        return (p["user_id"] not in winners,                    # champions first
                -(p["hp"]),                                     # then survivors by HP
                -(p["eliminated_round"] or 10 ** 6),            # then whoever lasted longest
                -p["round_wins"], float(p["total_distance"]))
    return sorted(players, key=key)


def final_text(match: Mapping[str, Any], players: Sequence[Mapping[str, Any]]) -> str:
    winners = set(match.get("winner_ids") or [])
    names = {p["user_id"]: p["display_name"] for p in players}
    ordered = _final_order(match, players)
    lines = ["🏁 <b>NUMBER WARS — FINAL</b>", SEP, ""]
    if len(winners) == 1:
        (w,) = tuple(winners)
        lines.append(f"👑 <b>CHAMPION: {esc(names.get(w, '?'))}</b>")
    else:
        lines.append("👑 <b>JOINT CHAMPIONS:</b> " + ", ".join(esc(names.get(w, "?")) for w in winners))
    lines += [f"<i>{REASONS.get(match.get('end_reason'), '')}</i>", f"Rounds played: {match['current_round']}", "",
              "<b>Final standings</b>"]
    for i, p in enumerate(ordered):
        status = f"❤️ {p['hp']}/{MAX_HP}" if p["alive"] else f"💀 out in round {p['eliminated_round']}"
        crown = " 👑" if p["user_id"] in winners else ""
        lines.append(f"{rank_badge(i)} {esc(p['display_name'])}{crown} — {status} · "
                     f"{p['round_wins']} round wins")
    lines += ["", "<i>Rating: +25 outright win · +10 shared title · −5 for everyone else.</i>"]
    return "\n".join(lines)


def status_text(match: Mapping[str, Any], players: Sequence[Mapping[str, Any]]) -> str:
    lines = ["📊 <b>NUMBER WARS — Status</b>", "", f"Stage: <b>{match['status']}</b>",
             f"Players: {len(players)}"]
    if match["status"] == "ACTIVE":
        alive = [p for p in players if p["alive"]]
        lines.append(f"Round: {match['current_round']} · alive: {len(alive)}")
        lines += [""] + [f"❤️ {p['hp']:>2}  {esc(p['display_name'])}"
                         for p in sorted(alive, key=lambda p: -p["hp"])]
    return "\n".join(lines)


# ───────────────────────── leaderboard / stats ─────────────────────────
def leaderboard_text(rows: Sequence[Mapping[str, Any]], title: str) -> str:
    lines = ["🔢 <b>NUMBER WARS LEADERBOARD</b>", f"<i>{esc(title)}</i>", ""]
    if not rows:
        return "\n".join(lines + ["No ranked matches yet — finish a game to appear here!"])
    for i, r in enumerate(rows):
        u = r.get("users") or {}
        name = u.get("first_name") or (f"@{u['username']}" if u.get("username") else f"Player {r['user_id'] % 1000}")
        lines.append(f"{rank_badge(i)} {esc(name)} — <b>{r['rating']}</b> · {r['wins']}W/{r['losses']}L")
    lines += ["", "<i>Rating measures results (start 1000), not true skill.</i>"]
    return "\n".join(lines)


def stats_text(name: str, glob: Mapping[str, Any] | None, rank: int | None) -> str:
    lines = [f"🔢 <b>NUMBER WARS — {esc(name)}</b>", ""]
    if not glob:
        return "\n".join(lines + ["No finished matches yet. Join one with /start in a group!"])
    played = glob["matches_played"]
    rate = f"{100 * glob['wins'] / played:.0f}%" if played else "—"
    lines += [f"⭐ Rating: <b>{glob['rating']}</b>" + (f" (#{rank} worldwide)" if rank else ""),
              f"🎮 Matches: {played}", f"👑 Wins: {glob['wins']} ({rate})",
              f"💔 Losses: {glob['losses']}", f"🏆 Round wins: {glob['round_wins']}"]
    return "\n".join(lines)
