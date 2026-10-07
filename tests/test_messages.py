import random

from game.battle import play_match
from game.categories import CATEGORY_KEYS
from tests.helpers import build_catalog
from utils import messages as m

CAT = build_catalog()


def test_rendering_smoke_and_escaping():
    t1 = {c: CAT.get(i) for c, i in zip(CATEGORY_KEYS, ["reinhard", "reid", "regulus", "cecilus", "felix", "light"])}
    t2 = {c: CAT.get(i) for c, i in zip(CATEGORY_KEYS, ["asta", "yuno", "noelle", "luck", "mimosa", "l"])}
    r = play_match(t1, t2, random.Random(1), final=True)
    n1, n2 = "<b>Evil</b>", "Akhil"
    for i in range(1, 7):
        assert len(m.battle_progress_text("T", n1, n2, r.clashes, i)) < 4096
    assert "<b>Evil</b>" not in m.scorecard_text(n1, n2, r)
    assert "CHAMPION" in m.final_announcement(n1, n2, r)
    rows = [{"game_player_id": 1, "played": 3, "wins": 3, "draws": 0, "losses": 0, "clash_difference": 8, "points": 9}]
    assert "9" in m.table_text(rows, {1: "Divyam"})
    assert m.button_labels([CAT.get("julius_j"), CAT.get("julius_n"), CAT.get("asta")])[2] == "Asta"
    assert m.button_labels([CAT.get("julius_j"), CAT.get("julius_n")])[0] == "Julius Juukulius"
