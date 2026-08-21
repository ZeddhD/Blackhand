from __future__ import annotations

import pytest

from engine import Faction, Game, GameConfig, Phase, Role
from engine.game import CALL_IT_VOTE, HOLD_VOTE, IllegalActionError


def make_game(room_code="TEST", names=None, role_counts=None, **config_kwargs):
    names = names or [f"P{i}" for i in range(8)]
    config = GameConfig(role_counts=role_counts or {}, **config_kwargs)
    game = Game(room_code=room_code, config=config)
    for i, name in enumerate(names):
        game.add_player(str(i), name)
    return game


def by_role(game: Game, role: Role):
    return [p for p in game.players if p.role is role]


def vote_all(game: Game, choice: str, except_ids=()):
    for p in game.alive_players():
        if p.id not in except_ids:
            game.submit_show_hands_vote(p.id, choice)


def test_not_available_above_the_threshold():
    game = make_game(names=[f"P{i}" for i in range(7)], role_counts={Role.HAND: 1})  # 7 > default threshold 6
    game.start_game()
    assert game.phase == Phase.NIGHT


def test_available_at_or_below_the_threshold():
    game = make_game(names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 1})  # 6 <= default threshold 6
    game.start_game()
    assert game.phase == Phase.SHOW_HANDS


def test_configurable_threshold():
    game = make_game(
        names=[f"P{i}" for i in range(7)], role_counts={Role.HAND: 1}, show_hands_threshold=7
    )
    game.start_game()
    assert game.phase == Phase.SHOW_HANDS


def test_majority_call_it_ends_the_game():
    game = make_game(names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 1})
    game.start_game()
    assert game.phase == Phase.SHOW_HANDS
    vote_all(game, CALL_IT_VOTE)
    game.resolve_show_hands()
    assert game.phase == Phase.GAME_OVER


def test_all_hands_dead_plus_call_it_means_table_wins():
    game = make_game(names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 1})
    game.start_game()
    by_role(game, Role.HAND)[0].alive = False
    vote_all(game, CALL_IT_VOTE)
    game.resolve_show_hands()
    assert game.winner == Faction.TABLE


def test_any_hand_alive_plus_call_it_means_black_hand_wins():
    game = make_game(names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 1})
    game.start_game()
    assert by_role(game, Role.HAND)[0].alive
    vote_all(game, CALL_IT_VOTE)
    game.resolve_show_hands()
    assert game.winner == Faction.HAND


def test_black_hand_wins_even_at_bad_parity_once_called():
    # 1 Hand alive vs 5 Table alive is nowhere near normal parity, but a
    # successful CALL IT is a direct win for whichever side the Hand
    # status implies, bypassing the usual hand_count >= table_count math.
    game = make_game(names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 1})
    game.start_game()
    vote_all(game, CALL_IT_VOTE)
    game.resolve_show_hands()
    assert game.winner == Faction.HAND
    assert len(game.alive_players()) == 6  # nobody died, parity was never close


def test_tie_results_in_hold_game_continues():
    game = make_game(names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 1})
    game.start_game()
    ids = [p.id for p in game.alive_players()]
    for i, pid in enumerate(ids):
        game.submit_show_hands_vote(pid, CALL_IT_VOTE if i % 2 == 0 else HOLD_VOTE)
    game.resolve_show_hands()
    assert game.phase != Phase.GAME_OVER
    assert game.phase == Phase.NIGHT


def test_hold_majority_proceeds_to_night():
    game = make_game(names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 1})
    game.start_game()
    vote_all(game, HOLD_VOTE)
    game.resolve_show_hands()
    assert game.phase == Phase.NIGHT


def test_maximum_three_occurrences_per_game():
    # 6 players at the default threshold of 6 is always <= threshold, so
    # every round is eligible; the 4th round must skip straight into
    # Night instead.
    game = make_game(names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 1})
    game.start_game()
    for _ in range(3):
        assert game.phase == Phase.SHOW_HANDS
        vote_all(game, HOLD_VOTE)
        game.resolve_show_hands()
        if game.phase == Phase.NIGHT:
            game.resolve_night()
            game.begin_voting()
            game.resolve_lynch()
    assert game.show_hands_count == 3
    assert game.phase != Phase.SHOW_HANDS


def test_disabled_via_config_never_triggers():
    game = make_game(
        names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 1}, show_hands_enabled=False
    )
    game.start_game()
    assert game.phase == Phase.NIGHT


def test_results_expose_counts_only_never_names():
    game = make_game(
        names=["Alice", "Bob", "Carol", "Dave", "Erin", "Frank"], role_counts={Role.HAND: 1}
    )
    game.start_game()
    a, b, c, d, e, f = game.players
    game.submit_show_hands_vote(a.id, CALL_IT_VOTE)
    game.submit_show_hands_vote(b.id, CALL_IT_VOTE)
    game.submit_show_hands_vote(c.id, HOLD_VOTE)

    # Nobody else's view ever exposes another player's individual choice.
    for viewer in (d, e, f):
        view = game.view_for(viewer.id)
        assert "show_hands_your_vote" in view
        assert view["show_hands_your_vote"] is None  # they haven't voted
        assert not any(k.startswith("show_hands") and isinstance(v, dict) for k, v in view.items())

    game.resolve_show_hands()
    result_event = next(e for e in game.events if "HOLD" in e)
    assert result_event == "Show Your Hands: 1 HOLD, 2 CALL IT"
    # the public event is a count string, not a per-player list
    names = {p.name for p in game.players}
    assert not any(name in result_event for name in names)


def test_own_vote_is_visible_only_to_self():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    a, b = game.players[0], game.players[1]
    game.submit_show_hands_vote(a.id, CALL_IT_VOTE)

    a_view = game.view_for(a.id)
    assert a_view["show_hands_your_vote"] == CALL_IT_VOTE

    b_view = game.view_for(b.id)
    assert b_view["show_hands_your_vote"] is None


def test_dead_players_cannot_vote():
    game = make_game(names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 1})
    game.start_game()
    dead = next(p for p in game.players if p.role is not Role.HAND)
    dead.alive = False
    with pytest.raises(IllegalActionError):
        game.submit_show_hands_vote(dead.id, HOLD_VOTE)


def test_invalid_choice_rejected():
    game = make_game(names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 1})
    game.start_game()
    alive = game.alive_players()[0]
    with pytest.raises(IllegalActionError):
        game.submit_show_hands_vote(alive.id, "maybe")


def test_votes_complete_once_every_alive_player_has_voted():
    game = make_game(names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 1})
    game.start_game()
    ids = [p.id for p in game.alive_players()]
    assert not game.show_hands_votes_complete()
    for pid in ids[:-1]:
        game.submit_show_hands_vote(pid, HOLD_VOTE)
    assert not game.show_hands_votes_complete()
    game.submit_show_hands_vote(ids[-1], HOLD_VOTE)
    assert game.show_hands_votes_complete()
