import random

from game.battle import play_match
from game.categories import CATEGORY_KEYS
from tests.helpers import build_catalog
from utils import messages as m

CAT = build_catalog()


def test_rendering_smoke_and_escaping():
    t1 = {c: CAT.get(i) for c, i in zip(CATEGORY_KEYS, ["reinhard", "regulus", "cecilus", "felix", "light"])}
    t2 = {c: CAT.get(i) for c, i in zip(CATEGORY_KEYS, ["asta", "noelle", "luck", "mimosa", "l"])}
    r = play_match(t1, t2, random.Random(1), final=True)
    n1, n2 = "<b>Evil</b>", "Akhil"
    for i in range(1, 6):
        assert len(m.battle_progress_text("T", n1, n2, r.clashes, i)) < 4096
    assert "<b>Evil</b>" not in m.scorecard_text(n1, n2, r)
    assert "CHAMPION" in m.final_announcement(n1, n2, r)
    rows = [{"game_player_id": 1, "played": 3, "wins": 3, "draws": 0, "losses": 0, "clash_difference": 8, "points": 9}]
    assert "9" in m.table_text(rows, {1: "Divyam"})
    assert m.button_labels([CAT.get("julius_j"), CAT.get("julius_n"), CAT.get("asta")])[2] == "Asta"
    assert m.button_labels([CAT.get("julius_j"), CAT.get("julius_n")])[0] == "Julius Juukulius"


def test_leaderboard_texts():
    g = {"total": 12, "rows": [{"rank": 1, "name": "<Div>", "rating": 1250}, {"rank": 2, "name": "Akhil", "rating": 1180}],
         "me": {"rank": 12, "rating": 1005}}
    t = m.global_leaderboard_text(g, 0, 10)
    assert "GLOBAL RANKINGS" in t and "&lt;Div&gt;" in t and "#12" in t and "1005" in t and "1/2" in t
    assert "unranked" in m.global_leaderboard_text({"total": 0, "rows": [], "me": None}, 0, 10)

    st = {"tournaments_played": 4, "championships_won": 2, "runner_up_finishes": 1, "matches_won": 7,
          "matches_drawn": 0, "matches_lost": 3, "matches_played": 10, "clashes_won": 30, "clashes_lost": 20,
          "win_rate": 70.0}
    row = {"rank": 1, "name": "Divyam", **st}
    grp = {"title": "Anime Legends", "total": 1, "rows": [row], "me": {"rank": 1}, "me_stats": st}
    t = m.group_leaderboard_text(grp, "champs", 0, 10, 5)
    assert "Anime Legends" in t and "2 Championships" in t and "#1" in t
    assert "7 Wins" in m.group_leaderboard_text(grp, "wins", 0, 10, 5)
    assert "70% (7/10)" in m.group_leaderboard_text(grp, "winrate", 0, 10, 5)
    assert "minimum 5" in m.group_leaderboard_text(grp, "winrate", 0, 10, 5)
    assert "1 Championship<" not in t  # plural handled


def test_final_leaderboard_block():
    b = m.final_leaderboard_block("Divyam", {"old_rating": 1240, "new_rating": 1265, "rating_change": 25},
                                  "Akhil", {"old_rating": 1100, "new_rating": 1090, "rating_change": -10}, 6, 1)
    assert "1240 → 1265 (+25)" in b and "1100 → 1090 (-10)" in b
    assert "Group Championships: 6" in b and "Group Rank: #1" in b
    assert m.final_leaderboard_block("A", None, "B", None, None, None) == ""
