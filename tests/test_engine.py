from __future__ import annotations

import pytest

from engine import SKIP_VOTE, ActionType, Faction, Game, GameConfig, Phase, Role
from engine.game import IllegalActionError


def make_game(room_code="TEST", names=None, role_counts=None):
    # Show Your Hands is disabled here so these pre-existing tests (mostly
    # small player counts) aren't affected by an unrelated Phase 3
    # mechanic. See tests/test_show_hands.py for that feature's own tests.
    names = names or [f"P{i}" for i in range(8)]
    config = GameConfig(role_counts=role_counts or {}, show_hands_enabled=False)
    game = Game(room_code=room_code, config=config)
    for i, name in enumerate(names):
        game.add_player(str(i), name)
    return game


def by_role(game: Game, role: Role):
    return [p for p in game.players if p.role is role]


def role_faction_is_table(player):
    return player.role in (Role.CIVILIAN, Role.INSPECTOR, Role.WATCHMAN)


def test_config_validate_rejects_too_many_roles():
    errors = GameConfig(role_counts={Role.HAND: 10}).validate(8)
    assert any("roles assigned for" in e for e in errors)


def test_config_validate_requires_a_hand():
    errors = GameConfig(role_counts={Role.WATCHMAN: 1}).validate(8)
    assert any("at least one Hand" in e for e in errors)


def test_config_validate_rejects_parity_start():
    errors = GameConfig(role_counts={Role.HAND: 4}).validate(8)
    assert any("already holds the table" in e for e in errors)


def test_config_validate_rejects_too_few_players():
    errors = GameConfig(role_counts={Role.HAND: 1}).validate(5)
    assert any("at least 6 players" in e for e in errors)


def test_config_validate_rejects_too_many_players():
    errors = GameConfig(role_counts={Role.HAND: 1}).validate(13)
    assert any("at most 12 players" in e for e in errors)


def test_config_validate_accepts_the_boundary_player_counts():
    # Section 3.1's table runs 6 to 12 players inclusive; both ends must
    # pass the floor/ceiling check on their own (other rules, like hand
    # count, are exercised by the tests above, not this one).
    assert GameConfig(role_counts={Role.HAND: 1}).validate(6) == []
    assert GameConfig(role_counts={Role.HAND: 3}).validate(12) == []


def test_start_game_rejects_too_few_players():
    game = make_game(names=["A", "B", "C"], role_counts={Role.HAND: 1})
    with pytest.raises(IllegalActionError):
        game.start_game()


def test_start_game_assigns_all_roles_and_fills_civilians():
    game = make_game(role_counts={Role.HAND: 2, Role.INSPECTOR: 1, Role.WATCHMAN: 1})
    game.start_game()
    assert game.phase == Phase.NIGHT
    assert len(by_role(game, Role.HAND)) == 2
    assert len(by_role(game, Role.INSPECTOR)) == 1
    assert len(by_role(game, Role.WATCHMAN)) == 1
    assert len(by_role(game, Role.CIVILIAN)) == 4


def test_hand_kill_resolves():
    game = make_game(role_counts={Role.HAND: 1})
    game.start_game()
    hand = by_role(game, Role.HAND)[0]
    victim = next(p for p in game.players if p.role is not Role.HAND)
    game.submit_night_action(hand.id, ActionType.KILL, victim.id)
    game.resolve_night()
    assert not victim.alive
    assert game.phase == Phase.DAY_DISCUSSION


def test_watchman_can_save_the_target():
    game = make_game(role_counts={Role.HAND: 1, Role.WATCHMAN: 1})
    game.start_game()
    hand = by_role(game, Role.HAND)[0]
    watchman = by_role(game, Role.WATCHMAN)[0]
    victim = next(p for p in game.players if p.role not in (Role.HAND, Role.WATCHMAN))
    game.submit_night_action(hand.id, ActionType.KILL, victim.id)
    game.submit_night_action(watchman.id, ActionType.PROTECT, victim.id)
    game.resolve_night()
    assert victim.alive


def test_watchman_self_heal_allowed_once_then_blocked():
    game = make_game(role_counts={Role.HAND: 1, Role.WATCHMAN: 1})
    game.start_game()
    watchman = by_role(game, Role.WATCHMAN)[0]

    game.submit_night_action(watchman.id, ActionType.PROTECT, watchman.id)
    game.resolve_night()
    game.begin_voting()
    game.resolve_lynch()  # no votes cast -> advances to next night

    with pytest.raises(Exception):
        game.submit_night_action(watchman.id, ActionType.PROTECT, watchman.id)


def test_watchman_cannot_protect_same_target_consecutive_nights():
    game = make_game(role_counts={Role.HAND: 1, Role.WATCHMAN: 1})
    game.start_game()
    watchman = by_role(game, Role.WATCHMAN)[0]
    target = next(p for p in game.players if p.id != watchman.id)

    game.submit_night_action(watchman.id, ActionType.PROTECT, target.id)
    game.resolve_night()
    game.begin_voting()
    game.resolve_lynch()

    with pytest.raises(Exception):
        game.submit_night_action(watchman.id, ActionType.PROTECT, target.id)


def test_inspector_sees_hand_as_guilty():
    game = make_game(role_counts={Role.HAND: 1, Role.INSPECTOR: 1})
    game.start_game()
    inspector = by_role(game, Role.INSPECTOR)[0]
    hand = by_role(game, Role.HAND)[0]
    game.submit_night_action(inspector.id, ActionType.INVESTIGATE, hand.id)
    game.resolve_night()
    assert any("GUILTY" in msg for msg in game.private_log.get(inspector.id, []))


def test_inspector_sees_civilian_as_innocent():
    game = make_game(role_counts={Role.HAND: 1, Role.INSPECTOR: 1})
    game.start_game()
    inspector = by_role(game, Role.INSPECTOR)[0]
    civilian = by_role(game, Role.CIVILIAN)[0]
    game.submit_night_action(inspector.id, ActionType.INVESTIGATE, civilian.id)
    game.resolve_night()
    assert any("INNOCENT" in msg for msg in game.private_log.get(inspector.id, []))


def test_tied_lynch_kills_no_one():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    a, b, c, d = game.players[:4]
    game.resolve_night()
    game.begin_voting()
    game.submit_vote(a.id, b.id)
    game.submit_vote(c.id, d.id)
    alive_before = {p.id for p in game.alive_players()}
    game.resolve_lynch()
    alive_after = {p.id for p in game.alive_players()}
    assert alive_before == alive_after


def test_table_wins_when_all_hands_dead():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    hand = by_role(game, Role.HAND)[0]
    hand.alive = False
    game.resolve_night()
    assert game.winner == Faction.TABLE
    assert game.phase == Phase.GAME_OVER


def test_hand_wins_at_parity():
    # 7 players, 3 Hand, 4 Table: killing exactly one Table player brings
    # the survivors to 3 Hand vs 3 Table, parity.
    game = make_game(names=["A", "B", "C", "D", "E", "F", "G"], role_counts={Role.HAND: 3})
    game.start_game()
    civilians = by_role(game, Role.CIVILIAN)
    civilians[0].alive = False
    game.resolve_night()
    assert game.winner == Faction.HAND


def test_view_for_hides_role_info_from_civilian():
    game = make_game(role_counts={Role.HAND: 2})
    game.start_game()
    civilian = by_role(game, Role.CIVILIAN)[0]
    view = game.view_for(civilian.id)
    assert "allies" not in view
    for p in view["players"]:
        assert "role" not in p


def test_view_for_hand_shows_allies():
    game = make_game(role_counts={Role.HAND: 2})
    game.start_game()
    h1, h2 = by_role(game, Role.HAND)
    view = game.view_for(h1.id)
    assert view["allies"] == [h2.name]


def test_full_headless_12_player_game_runs_to_completion():
    game = make_game(
        names=[f"P{i}" for i in range(12)],
        role_counts={Role.HAND: 3, Role.INSPECTOR: 1, Role.WATCHMAN: 1},
    )
    game.start_game()
    rounds = 0
    while game.phase != Phase.GAME_OVER and rounds < 50:
        rounds += 1
        hand_alive = [p for p in game.alive_players() if p.role is Role.HAND]
        if hand_alive:
            victim = next((p for p in game.alive_players() if role_faction_is_table(p)), None)
            if victim:
                game.submit_night_action(hand_alive[0].id, ActionType.KILL, victim.id)
        game.resolve_night()
        if game.phase == Phase.GAME_OVER:
            break
        game.begin_voting()
        alive = game.alive_players()
        if len(alive) >= 2:
            target = alive[0]
            for voter in alive[1:]:
                game.submit_vote(voter.id, target.id)
        game.resolve_lynch()
    assert game.phase == Phase.GAME_OVER
    assert game.winner in (Faction.TABLE, Faction.HAND)


def test_dead_player_sees_round_log_but_alive_player_does_not():
    game = make_game(role_counts={Role.HAND: 1})
    game.start_game()
    hand = by_role(game, Role.HAND)[0]
    victim = next(p for p in game.players if p.role is not Role.HAND)
    game.submit_night_action(hand.id, ActionType.KILL, victim.id)
    game.resolve_night()

    dead_view = game.view_for(victim.id)
    assert "round_log" in dead_view

    alive_id = next(p.id for p in game.alive_players() if p.id != hand.id)
    alive_view = game.view_for(alive_id)
    assert "round_log" not in alive_view


def test_votes_complete_once_every_alive_player_has_voted():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    game.resolve_night()
    game.begin_voting()
    a, b, c, d, e, f = game.players
    assert not game.votes_complete()
    game.submit_vote(a.id, b.id)
    game.submit_vote(b.id, a.id)
    game.submit_vote(c.id, SKIP_VOTE)
    game.submit_vote(d.id, SKIP_VOTE)
    game.submit_vote(e.id, SKIP_VOTE)
    assert not game.votes_complete()
    game.submit_vote(f.id, SKIP_VOTE)
    assert game.votes_complete()


def test_skip_vote_does_not_count_toward_lynch_tally():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    game.resolve_night()
    game.begin_voting()
    for p in game.players:
        game.submit_vote(p.id, SKIP_VOTE)
    alive_before = {p.id for p in game.alive_players()}
    game.resolve_lynch()
    alive_after = {p.id for p in game.alive_players()}
    assert alive_before == alive_after  # everyone skipped -- no lynch


def test_votes_complete_ignores_dead_players():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    # Kill a non-Hand player so the game doesn't end before reaching voting.
    dead = next(p for p in game.players if p.role is not Role.HAND)
    dead.alive = False
    game.resolve_night()
    game.begin_voting()
    remaining = [p for p in game.players if p.alive]
    for p in remaining:
        game.submit_vote(p.id, SKIP_VOTE)
    assert game.votes_complete()


def test_handle_disconnect_removal_in_lobby_drops_player_outright():
    game = make_game(names=["A", "B", "C", "D"])
    game.handle_disconnect_removal(game.players[0].id)
    assert len(game.players) == 3


def test_handle_disconnect_removal_mid_game_marks_eliminated_not_removed():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    victim = next(p for p in game.players if p.role is not Role.HAND)
    game.handle_disconnect_removal(victim.id)
    assert victim in game.players  # still in the roster
    assert not victim.alive
    assert game.phase != Phase.GAME_OVER  # 1 hand vs 4 table remaining, not parity yet


def test_handle_disconnect_removal_clears_their_pending_vote():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    game.resolve_night()
    game.begin_voting()
    a, b = game.players[0], game.players[1]
    game.submit_vote(a.id, b.id)
    game.handle_disconnect_removal(a.id)
    assert a.id not in game.votes
    assert not a.alive


def test_handle_disconnect_removal_can_end_the_game():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    hand = by_role(game, Role.HAND)[0]
    game.handle_disconnect_removal(hand.id)
    assert game.phase == Phase.GAME_OVER
    assert game.winner == Faction.TABLE


def test_return_to_lobby_resets_game_for_a_rematch():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    hand = by_role(game, Role.HAND)[0]
    hand.alive = False
    game.resolve_night()
    assert game.phase == Phase.GAME_OVER

    game.return_to_lobby()
    assert game.phase == Phase.LOBBY
    assert game.winner is None
    assert game.round_log == []
    assert all(p.role is None and p.alive for p in game.players)
    # can configure and start a fresh game afterwards
    game.config = GameConfig(role_counts={Role.HAND: 1}, show_hands_enabled=False)
    game.start_game()
    assert game.phase == Phase.NIGHT


def test_return_to_lobby_rejected_mid_game():
    game = make_game(role_counts={Role.HAND: 1})
    game.start_game()
    with pytest.raises(Exception):
        game.return_to_lobby()


def test_remove_player_allowed_after_game_over():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    hand = by_role(game, Role.HAND)[0]
    hand.alive = False
    game.resolve_night()
    assert game.phase == Phase.GAME_OVER
    game.remove_player(game.players[0].id)
    assert len(game.players) == 5


def test_game_over_reveals_hand_to_everyone():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    hand = by_role(game, Role.HAND)[0]
    hand.alive = False
    game.resolve_night()
    assert game.phase == Phase.GAME_OVER
    view = game.view_for(game.players[0].id)
    assert view["hand_reveal"] == [hand.name]


def test_remove_player_in_lobby():
    game = make_game(names=["A", "B", "C", "D"])
    game.remove_player("1")
    assert [p.id for p in game.players] == ["0", "2", "3"]


def test_remove_player_after_start_is_rejected():
    game = make_game(role_counts={Role.HAND: 1})
    game.start_game()
    with pytest.raises(Exception):
        game.remove_player(game.players[0].id)


def test_hand_kill_is_a_single_shared_target():
    game = make_game(names=[f"P{i}" for i in range(6)], role_counts={Role.HAND: 2})
    game.start_game()
    h1, h2 = by_role(game, Role.HAND)
    victims = [p for p in game.players if p.role is not Role.HAND]

    game.submit_night_action(h1.id, ActionType.KILL, victims[0].id)
    assert game.hand_target_id == victims[0].id
    assert game.night_actions_ready()  # one Hand member is enough

    game.submit_night_action(h2.id, ActionType.KILL, victims[1].id)
    assert game.hand_target_id == victims[1].id  # second member overwrites the shared choice

    game.resolve_night()
    assert not victims[1].alive
    assert victims[0].alive


def test_round_log_records_night_and_lynch_detail():
    game = make_game(role_counts={Role.HAND: 1, Role.WATCHMAN: 1})
    game.start_game()
    hand = by_role(game, Role.HAND)[0]
    victim = next(p for p in game.players if p.role is not Role.HAND)
    game.submit_night_action(hand.id, ActionType.KILL, victim.id)
    game.resolve_night()
    assert game.round_log[-1]["title"] == "Night 1"
    assert any(victim.name in line for line in game.round_log[-1]["lines"])

    game.begin_voting()
    alive = game.alive_players()
    for voter in alive[1:]:
        game.submit_vote(voter.id, alive[0].id)
    game.resolve_lynch()
    assert game.round_log[-1]["title"].startswith("Day")


def test_night_actions_ready_tracks_required_actors():
    game = make_game(role_counts={Role.HAND: 1, Role.WATCHMAN: 1, Role.INSPECTOR: 1})
    game.start_game()
    hand = by_role(game, Role.HAND)[0]
    watchman = by_role(game, Role.WATCHMAN)[0]
    inspector = by_role(game, Role.INSPECTOR)[0]
    civilian = by_role(game, Role.CIVILIAN)[0]

    assert not game.night_actions_ready()
    game.submit_night_action(hand.id, ActionType.KILL, civilian.id)
    assert not game.night_actions_ready()
    game.submit_night_action(watchman.id, ActionType.PROTECT, civilian.id)
    assert not game.night_actions_ready()
    game.submit_night_action(inspector.id, ActionType.INVESTIGATE, civilian.id)
    assert game.night_actions_ready()
