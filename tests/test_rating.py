from game.rating import expected_score, placement_order, rating_changes


def test_expected_score_basics():
    assert abs(expected_score(1000, 1000) - 0.5) < 1e-12
    assert abs(expected_score(1400, 1000) - 10 / 11) < 1e-12
    assert abs(expected_score(1000, 1400) + expected_score(1400, 1000) - 1.0) < 1e-12


def test_equal_ratings_four_players():
    # K=32, N=4 → weight 32/3 per pair; winner +16, last -16, middle two ±5
    ch = rating_changes({1: 1000, 2: 1000, 3: 1000, 4: 1000}, [1, 2, 3, 4])
    assert ch == {1: 16, 2: 5, 3: -5, 4: -16}


def test_zero_sum_up_to_rounding():
    ratings = {1: 1250, 2: 1000, 3: 940, 4: 1600, 5: 1010}
    ch = rating_changes(ratings, [3, 5, 1, 4, 2])
    assert abs(sum(ch.values())) <= len(ratings)  # rounding only
    assert ch[3] > 0 > ch[2]


def test_stronger_opponents_reward_more():
    base = {1: 1000, 2: 1000, 3: 1000}
    vs_strong = {1: 1000, 2: 1400, 3: 1400}
    win_even = rating_changes(base, [1, 2, 3])[1]
    win_strong = rating_changes(vs_strong, [1, 2, 3])[1]
    assert win_strong > win_even


def test_losing_to_weaker_costs_more():
    even = rating_changes({1: 1000, 2: 1000, 3: 1000}, [2, 3, 1])[1]
    favourite = rating_changes({1: 1400, 2: 1000, 3: 1000}, [2, 3, 1])[1]
    assert favourite < even < 0


def test_changes_bounded_by_k():
    ch = rating_changes({1: 1000, 2: 3000}, [1, 2])
    assert ch[1] == 32 and ch[2] == -32


def _raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


def test_validation():
    assert _raises(lambda: rating_changes({1: 1000}, [1]))
    assert _raises(lambda: rating_changes({1: 1000, 2: 1000}, [1, 1]))
    assert _raises(lambda: rating_changes({1: 1000, 2: 1000}, [1, 3]))


def test_placement_order_winner_runner_then_league_order():
    league = [10, 11, 12, 13]  # finalists are the top two of the league: 10 and 11
    assert placement_order(league, 10, 11, winner=11) == [11, 10, 12, 13]
    assert placement_order(league, 10, 11, winner=10) == [10, 11, 12, 13]
