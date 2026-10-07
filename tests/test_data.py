from collections import Counter

from data.characters import CHARACTERS
from game.categories import CATEGORY_KEYS
from tests.helpers import build_catalog


def test_unique_ids_and_series():
    ids = [c["id"] for c in CHARACTERS]
    assert len(ids) == len(set(ids))
    assert {c["series"] for c in CHARACTERS} == {"Re:ZERO", "Black Clover", "Death Note"}


def test_stat_ranges():
    for c in CHARACTERS:
        for k in CATEGORY_KEYS:
            assert 1 <= c[k.lower()] <= 100, (c["id"], k)
        assert c["categories"], c["id"]


def test_pools_large_enough_for_worst_case_draft():
    cat = build_catalog()
    for k in CATEGORY_KEYS:
        # a player may already own up to 5 characters from this pool
        assert len(cat.pool(k)) >= 5 + 5, k


def test_death_note_is_intelligence_only_and_physically_weak():
    dn = [c for c in CHARACTERS if c["series"] == "Death Note"]
    names = {c["id"] for c in dn}
    assert {"light", "l", "near", "mello", "misora"} <= names
    for c in dn:
        assert c["categories"] == ["INTELLIGENCE"]
        assert max(c["attack"], c["defense"], c["tanking"], c["speed"]) <= 35
    by = {c["id"]: c for c in dn}
    for k in ("light", "l", "near"):
        assert by[k]["intelligence"] >= 95


def test_spec_examples():
    by = {c["id"]: c for c in CHARACTERS}
    assert by["felix"]["categories"] == ["HEALING"]
    assert by["mimosa"]["categories"] == ["HEALING"]
    assert set(by["reinhard"]["categories"]) == {"ATTACK", "DEFENSE", "TANKING", "SPEED"}
    assert set(by["asta"]["categories"]) == {"ATTACK", "DEFENSE", "TANKING", "SPEED"}
    required = ["reinhard", "reid", "cecilus", "subaru", "emilia", "beatrice", "roswaal", "regulus", "garfiel",
                "elsa", "wilhelm", "julius_j", "felix", "rem", "ram", "priscilla", "echidna", "otto", "crusch",
                "capella", "sirius", "petelgeuse", "asta", "yuno", "yami", "noelle", "mereoleona", "julius_n",
                "nacht", "luck", "fuegoleon", "william", "mimosa", "charmy", "grey", "secre", "vanessa",
                "magna", "zenon", "dante", "vanica", "lucius"]
    for r in required:
        assert r in by, r
