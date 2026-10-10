"""Cricsheet IPL ball-by-ball JSON → per-player career/season statistics → import payload.

Source: https://cricsheet.org/downloads/ipl_json.zip  (Cricsheet data is published under the Open Data Commons
Attribution License — keep the attribution in the source record, which this module does).

Pure and offline: `aggregate()` takes already-parsed match dicts, so it is unit-tested with synthetic matches and
never needs the network. Download/unzip lives in scripts/import_ipl_players.py.

Counting rules (documented so numbers can be audited):
  * super-over innings are ignored for career stats;
  * balls faced = every delivery except wides; runs conceded = bat runs + wides + no-balls (byes/leg-byes/penalty excluded);
  * legal balls bowled exclude wides and no-balls; bowler wickets exclude run outs / retirements / obstructing the field;
  * outs = dismissals excluding 'retired hurt' / 'retired out';
  * death overs = overs 16-20 (0-based over index >= 15);
  * a four/six counts only when the runs came off the bat as a boundary (not overthrows: `non_boundary`).
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from ..engine.ratings import CareerStats, METHOD_VERSION, rate_from_stats
from .names import disambiguate, normalize_name, slugify

CRICSHEET_SOURCE = {
    "name": "Cricsheet IPL ball-by-ball",
    "url": "https://cricsheet.org/downloads/ipl_json.zip",
    "license": "Open Data Commons Attribution License (ODC-By) — data by Cricsheet (cricsheet.org)",
}
NOT_BOWLER_WICKET = {"run out", "retired hurt", "retired out", "obstructing the field", "hit the ball twice", "handled the ball", "timed out"}
NOT_OUT = {"retired hurt", "retired out"}


@dataclass
class Acc:
    cricsheet_id: str
    name: str
    matches: set = field(default_factory=set)
    seasons: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    t: dict = field(default_factory=lambda: defaultdict(int))
    hs: int = 0
    best: tuple = (0, 10_000)           # (wickets, runs) — more wickets then fewer runs
    first: int = 9999
    last: int = 0
    keeper_hint: int = 0


def season_year(raw) -> int:
    """'2007/08' → 2008 (IPL 2007/08 was played in 2008); '2019' → 2019."""
    s = str(raw)
    m = re.match(r"(\d{4})/(\d{2})", s)
    if m:
        return int(m.group(1)) + 1
    m = re.match(r"(\d{4})", s)
    return int(m.group(1)) if m else 0


def aggregate(matches: Iterable[Mapping]) -> dict[str, Acc]:
    accs: dict[str, Acc] = {}

    def acc(name: str, reg: Mapping) -> Acc:
        pid = reg.get(name) or f"name:{normalize_name(name)}"
        if pid not in accs:
            accs[pid] = Acc(pid, name)
        return accs[pid]

    for mi, match in enumerate(matches):
        info = match.get("info", {})
        reg = (info.get("registry") or {}).get("people") or {}
        year = season_year(info.get("season"))
        mid = f"{info.get('dates', ['?'])[0]}#{mi}"
        for team_players in (info.get("players") or {}).values():
            for n in team_players:
                a = acc(n, reg)
                a.matches.add(mid)
                a.first, a.last = min(a.first, year), max(a.last, year)
                a.seasons[year]["matches"] += 1
        for inn in match.get("innings", []):
            if inn.get("super_over"):
                continue
            bat_runs: dict[str, int] = defaultdict(int)
            bat_balls: dict[str, int] = defaultdict(int)
            bat_out: dict[str, bool] = defaultdict(bool)
            bowl_balls: dict[str, int] = defaultdict(int)
            bowl_runs: dict[str, int] = defaultdict(int)
            bowl_wkts: dict[str, int] = defaultdict(int)
            for ov in inn.get("overs", []):
                death = ov.get("over", 0) >= 15
                for d in ov.get("deliveries", []):
                    ex = d.get("extras") or {}
                    r = d.get("runs") or {}
                    bt, bw = d["batter"], d["bowler"]
                    wide, noball = "wides" in ex, "noballs" in ex
                    batter_runs = int(r.get("batter", 0))
                    A = acc(bt, reg)
                    B = acc(bw, reg)
                    if not wide:
                        bat_balls[bt] += 1
                        A.t["balls_faced"] += 1
                        A.seasons[year]["balls_faced"] += 1
                        if batter_runs == 0 and int(r.get("total", 0)) == 0:
                            A.t["dots_faced"] += 1
                        if death:
                            A.t["death_balls"] += 1
                            A.t["death_runs"] += batter_runs
                    bat_runs[bt] += batter_runs
                    A.t["runs"] += batter_runs
                    A.seasons[year]["runs"] += batter_runs
                    if batter_runs in (4, 6) and not r.get("non_boundary"):
                        key = "fours" if batter_runs == 4 else "sixes"
                        A.t[key] += 1
                        A.seasons[year][key] += 1
                    conceded = batter_runs + int(ex.get("wides", 0)) + int(ex.get("noballs", 0))
                    bowl_runs[bw] += conceded
                    B.t["runs_conceded"] += conceded
                    B.seasons[year]["runs_conceded"] += conceded
                    if not wide and not noball:
                        bowl_balls[bw] += 1
                        B.t["balls_bowled"] += 1
                        B.seasons[year]["balls_bowled"] += 1
                        if death:
                            B.t["death_bowl_balls"] += 1
                    if death:
                        B.t["death_bowl_runs"] += conceded
                    for w in d.get("wickets") or []:
                        kind = w.get("kind", "")
                        out_p = acc(w["player_out"], reg)
                        if kind not in NOT_OUT:
                            out_p.t["outs"] += 1
                            out_p.seasons[year]["outs"] += 1
                            bat_out[w["player_out"]] = True
                        if kind not in NOT_BOWLER_WICKET:
                            bowl_wkts[bw] += 1
                            B.t["wickets"] += 1
                            B.seasons[year]["wickets"] += 1
                        fielders = [f.get("name") for f in (w.get("fielders") or []) if f.get("name")]
                        if kind == "caught and bowled":
                            B.t["catches"] += 1
                        elif kind == "caught":
                            for f in fielders[:1]:
                                acc(f, reg).t["catches"] += 1
                        elif kind == "stumped":
                            for f in fielders[:1]:
                                k = acc(f, reg)
                                k.t["stumpings"] += 1
                                k.keeper_hint += 1
                        elif kind == "run out":
                            for f in fielders:
                                acc(f, reg).t["run_outs"] += 1
            for n in bat_balls:                      # innings-level facts
                A = acc(n, reg)
                A.t["innings_bat"] += 1
                if bat_runs[n] >= 20:
                    A.t["inn_20plus"] += 1
                if bat_runs[n] == 0 and bat_out[n]:
                    A.t["ducks"] += 1
                if bat_runs[n] >= 50:
                    A.t["fifties"] += 1
                if bat_runs[n] >= 100:
                    A.t["hundreds"] += 1
                A.hs = max(A.hs, bat_runs[n])
            for n in bowl_balls:
                B = acc(n, reg)
                B.t["innings_bowl"] += 1
                if bowl_wkts[n] >= 1 or (bowl_balls[n] >= 6 and bowl_runs[n] * 6 / bowl_balls[n] <= 8):
                    B.t["good_bowl_innings"] += 1
                if (bowl_wkts[n], -bowl_runs[n]) > (B.best[0], -B.best[1]):
                    B.best = (bowl_wkts[n], bowl_runs[n])
    for a in accs.values():
        a.t["matches"] = len(a.matches)
    return accs


def infer_role(a: Acc) -> str:
    m = max(a.t["matches"], 1)
    bowls = a.t["innings_bowl"] / m >= 0.4 and a.t["balls_bowled"] / max(a.t["innings_bowl"], 1) >= 12
    bats = a.t["innings_bat"] / m >= 0.55 and a.t["runs"] / max(a.t["innings_bat"], 1) >= 11
    if a.t["stumpings"] >= 3:
        return "WK"
    if bowls and bats:
        return "AR"
    if bowls:
        return "BOWL"
    return "BAT"


def stats_of(a: Acc) -> CareerStats:
    return CareerStats.from_mapping(a.t)


def build_payload(accs: Mapping[str, Acc], seeds: Mapping[str, tuple] | None = None, *, min_matches: int = 5) -> tuple[dict, list[dict], dict]:
    """Returns (source, players, report). `seeds` maps normalised seed full name → seed tuple and is used only to
    supply roles / bowling type / nationality hints and nicer display names; statistics always come from Cricsheet."""
    seeds = seeds or {}
    by_surname: dict[str, list[tuple]] = defaultdict(list)
    for key, tup in seeds.items():
        by_surname[key.split()[-1]].append((key, tup))
    matched_seeds: set[str] = set()
    rows, display_in = [], []
    for a in sorted(accs.values(), key=lambda x: x.cricsheet_id):
        if a.t["matches"] == 0:
            continue
        hint = _match_seed(a.name, by_surname)
        full = a.name
        role = infer_role(a)
        btype = "NONE"
        nat, bat_style = "", None
        if hint:
            key, (sname, srole, snat, sbat, sbowl, _tier) = hint
            matched_seeds.add(key)
            full, role, nat = sname, srole, snat
            bat_style = {"R": "RHB", "L": "LHB"}.get(sbat)
            btype = {"P": "PACE", "S": "SPIN", "-": "NONE"}[sbowl]
        elif role in ("BOWL", "AR"):
            btype = "PACE"                               # unknown without a seed hint — reported, see `report`
        slug = slugify(full)
        stats = stats_of(a)
        r = rate_from_stats(stats, role, btype)
        rows.append((slug, a, full, role, btype, nat, bat_style, stats, r))
        display_in.append((slug, full))
    disp = disambiguate(display_in)
    players = []
    for slug, a, full, role, btype, nat, bat_style, stats, r in rows:
        players.append({
            "slug": slug, "full_name": full, "display_name": disp[slug], "name_key": normalize_name(full),
            "cricsheet_id": a.cricsheet_id if not a.cricsheet_id.startswith("name:") else None,
            "role": role, "batting_style": bat_style, "bowling_type": btype, "nationality": nat,
            "first_ipl_season": a.first or None, "last_ipl_season": a.last or None,
            "is_eligible": a.t["matches"] >= min_matches, "ipl_verified": True, "data_quality": "CRICSHEET",
            "career": {"matches": a.t["matches"], "innings_bat": a.t["innings_bat"], "runs": a.t["runs"],
                       "balls_faced": a.t["balls_faced"], "outs": a.t["outs"], "fours": a.t["fours"], "sixes": a.t["sixes"],
                       "highest_score": a.hs, "fifties": a.t["fifties"], "hundreds": a.t["hundreds"],
                       "innings_bowl": a.t["innings_bowl"], "balls_bowled": a.t["balls_bowled"],
                       "runs_conceded": a.t["runs_conceded"], "wickets": a.t["wickets"],
                       "best_bowling": f"{a.best[0]}/{a.best[1]}" if a.best[1] < 10_000 and a.t["balls_bowled"] else None,
                       "catches": a.t["catches"], "stumpings": a.t["stumpings"], "run_outs": a.t["run_outs"]},
            "seasons": [{"season": y, "matches": v["matches"], "runs": v["runs"], "balls_faced": v["balls_faced"], "outs": v["outs"],
                         "fours": v["fours"], "sixes": v["sixes"], "balls_bowled": v["balls_bowled"],
                         "runs_conceded": v["runs_conceded"], "wickets": v["wickets"]} for y, v in sorted(a.seasons.items()) if y],
            "ratings": {**r.as_dict(), "rating_source": "CRICSHEET_STATS", "method_version": METHOD_VERSION},
        })
    report = {
        "players": len(players), "eligible": sum(p["is_eligible"] for p in players),
        "by_role": {k: sum(1 for p in players if p["is_eligible"] and p["role"] == k) for k in ("BAT", "BOWL", "AR", "WK")},
        "seed_matched": len(matched_seeds), "seed_total": len(seeds),
        "seed_unmatched": sorted(k for k in seeds if k not in matched_seeds),
        "unknown_bowling_type": sum(1 for p in players if p["role"] in ("BOWL", "AR") and p["bowling_type"] == "PACE"
                                    and not any(True for k in matched_seeds if k == p["name_key"])),
        "min_matches": min_matches,
    }
    return {**CRICSHEET_SOURCE, "data_version": "", "notes": "Career statistics computed from ball-by-ball data."}, players, report


def _match_seed(cs_name: str, by_surname: Mapping[str, list[tuple]]):
    """Cricsheet names are 'V Kohli' / 'MS Dhoni' / 'Mohammed Siraj'. Match on surname + initials; ambiguity → no match
    (the player is then imported under the Cricsheet name with an inferred role, and listed in the report)."""
    toks = normalize_name(cs_name).split()
    if not toks:
        return None
    surname, given = toks[-1], toks[:-1]
    full = " ".join(toks)
    cands = []
    for key, tup in by_surname.get(surname, []):
        if key == full:
            return key, tup
        stoks = key.split()[:-1]
        if not given or not stoks:
            continue
        initials, gj = "".join(t[0] for t in stoks), "".join(t[0] if len(t) > 2 else t for t in given)
        if given[0] == stoks[0] or initials == gj or gj.startswith(initials) or initials.startswith(gj):
            cands.append((key, tup))
    return cands[0] if len(cands) == 1 else None
