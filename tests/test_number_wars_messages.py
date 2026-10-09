import random
from fractions import Fraction as F
from html.parser import HTMLParser

from game import number_wars as engine
from services import number_wars_service as svc
from utils import nw_messages as nm


class _Balance(HTMLParser):
    """Telegram rejects unbalanced / unknown tags, so verify what we send is well-formed."""
    ALLOWED = {"b", "i", "a", "code", "pre", "u", "s"}

    def __init__(self):
        super().__init__()
        self.stack, self.bad = [], []

    def handle_starttag(self, tag, attrs):
        (self.stack.append(tag) if tag in self.ALLOWED else self.bad.append(tag))

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            self.bad.append("/" + tag)


def assert_valid_html(text):
    p = _Balance()
    p.feed(text)
    assert not p.bad and not p.stack, (p.bad, p.stack)
    assert len(text) <= 4096


def test_keypad_callbacks_fit_telegram_limit_at_every_value():
    for rid in (1, 999_999_999_999):
        for v in range(1, 101):
            for row in svc.keypad(rid, v).inline_keyboard:
                for b in row:
                    assert len(b.callback_data.encode()) <= 64, b.callback_data
                    kind, val = b.callback_data.split(":")[1], int(b.callback_data.split(":")[3])
                    assert kind in ("s", "l") and 1 <= val <= 100          # never leaves 1–100


def test_selector_text_round_trips_for_stateless_editing():
    rnd = {"round_number": 3, "multiplier": 0.8, "sudden_death": False}
    text_no_val = nm.dm_prompt(rnd, 8, 7, 30)
    assert_valid_html(text_no_val)
    text = nm.dm_prompt(rnd, 8, 7, 30, 50)
    base = text.rsplit(nm.TAIL_MARK, 1)[0]
    assert base + nm.selected_tail(73) == nm.dm_prompt(rnd, 8, 7, 30, 73)
    assert_valid_html(text)


def test_full_20_player_round_and_final_fit_in_one_message():
    rng = random.Random(3)
    names = {u: f"Player_{u}_with_a_fairly_long_display_name" for u in range(20)}
    out = engine.resolve_round({u: 10 for u in names}, {u: rng.randint(1, 100) for u in list(names)[:17]})
    rnd = {"round_number": 12, "multiplier": 0.8, "sudden_death": False}
    assert_valid_html(nm.round_result(rnd, out, names))
    players = [{"user_id": u, "display_name": names[u], "hp": 0 if u else 4, "alive": u == 0,
                "round_wins": u % 5, "total_distance": u * 3.5, "eliminated_round": None if u == 0 else u}
               for u in names]
    match = {"winner_ids": [0], "end_reason": engine.END_LAST_STANDING, "current_round": 19}
    assert_valid_html(nm.final_text(match, players))
    assert nm.final_text(match, players).index("CHAMPION") < nm.final_text(match, players).index("Final standings")


def test_user_supplied_names_are_escaped():
    out = engine.resolve_round({1: 10, 2: 10}, {1: 5, 2: 60})
    text = nm.round_result({"round_number": 1, "multiplier": 0.8}, out, {1: "<b>evil</b> & co", 2: "ok"})
    assert "&lt;b&gt;evil" in text and "<b>evil" not in text
    assert_valid_html(text)


def test_sudden_death_and_multiplier_labels():
    assert nm.mult_label(0.8) == "×0.8" and nm.mult_label("1.20") == "×1.2" and nm.mult_label(1.5) == "×1.5"
    rnd = {"round_number": 4, "multiplier": 1.5, "sudden_death": True}
    assert "SUDDEN DEATH" in nm.round_start_group(rnd, 5, 30) and "SUDDEN DEATH" in nm.dm_prompt(rnd, 9, 5, 30, 50)
    assert nm.num(F(40, 3)) == "13.33" and nm.num(F(40)) == "40" and nm.num(None) == "—"


def test_rules_and_lobby_text_are_valid():
    assert_valid_html(nm.rules_text(30, 30))
    match = {"status": "LOBBY", "max_players": 20, "min_players": 3}
    for n in (0, 2, 5):
        players = [{"display_name": f"P{i}"} for i in range(n)]
        assert_valid_html(nm.lobby_text(match, players, 30, 60))
