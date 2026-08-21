from __future__ import annotations

import pytest

from engine import ActionType, Faction, Game, GameConfig, Phase, Role, effective_faction
from engine.game import NO_VISIBLE_DEATH_MESSAGE, IllegalActionError


def make_game(room_code="TEST", names=None, role_counts=None):
    # Show Your Hands is disabled here so these Recruitment tests (mostly
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


def make_offer_game(names=None, role_counts=None):
    game = make_game(names=names or ["A", "B", "C", "D"], role_counts=role_counts or {Role.HAND: 1})
    game.start_game()
    return game


def test_offer_can_be_made_at_most_once_per_game():
    game = make_offer_game(names=["A", "B", "C", "D", "E"])
    hand = by_role(game, Role.HAND)[0]
    others = [p for p in game.players if p.role is not Role.HAND]

    game.submit_night_action(hand.id, ActionType.OFFER, others[0].id)
    game.resolve_night()
    game.resolve_offer_timeout()  # refused/timed out, recruitment_used stays True

    game.begin_voting()
    game.resolve_lynch()  # nothing voted -> advances to next night

    with pytest.raises(IllegalActionError):
        game.submit_night_action(hand.id, ActionType.OFFER, others[1].id)


def test_accepted_player_faction_becomes_hand():
    game = make_offer_game()
    hand = by_role(game, Role.HAND)[0]
    recruit = next(p for p in game.players if p.role is not Role.HAND)
    game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    game.resolve_night()
    assert game.phase == Phase.OFFER

    game.respond_to_offer(recruit.id, accepted=True)
    assert recruit.marked is True
    assert recruit.alive is True
    assert effective_faction(recruit) == Faction.HAND
    # literal role never changes -- only the marked flag does
    assert recruit.role is not Role.HAND


def test_accepted_player_gains_allies_and_shared_target_visibility():
    game = make_offer_game(names=["A", "B", "C", "D", "E"])
    hand = by_role(game, Role.HAND)[0]
    recruit = next(p for p in game.players if p.role is not Role.HAND)
    game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    game.resolve_night()
    game.respond_to_offer(recruit.id, accepted=True)

    assert recruit.name in [p.name for p in game.hand_team()]
    view = game.view_for(recruit.id)
    assert "allies" in view
    assert hand.name in view["allies"]


def test_refusing_player_dies():
    game = make_offer_game()
    hand = by_role(game, Role.HAND)[0]
    recruit = next(p for p in game.players if p.role is not Role.HAND)
    game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    game.resolve_night()

    game.respond_to_offer(recruit.id, accepted=False)
    assert not recruit.alive
    assert recruit.marked is False


def test_timeout_is_treated_as_refusal():
    game = make_offer_game()
    hand = by_role(game, Role.HAND)[0]
    recruit = next(p for p in game.players if p.role is not Role.HAND)
    game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    game.resolve_night()

    game.resolve_offer_timeout()
    assert not recruit.alive
    assert recruit.marked is False


def test_watchman_protection_does_not_block_the_offer():
    game = make_offer_game(names=["A", "B", "C", "D", "E"], role_counts={Role.HAND: 1, Role.WATCHMAN: 1})
    hand = by_role(game, Role.HAND)[0]
    watchman = by_role(game, Role.WATCHMAN)[0]
    recruit = next(p for p in game.players if p.role not in (Role.HAND, Role.WATCHMAN))

    game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    game.submit_night_action(watchman.id, ActionType.PROTECT, recruit.id)
    game.resolve_night()
    assert game.phase == Phase.OFFER  # the offer still happened, protection didn't stop it

    game.respond_to_offer(recruit.id, accepted=True)
    assert recruit.marked is True


def test_watchman_protection_does_not_save_a_refuser():
    game = make_offer_game(names=["A", "B", "C", "D", "E"], role_counts={Role.HAND: 1, Role.WATCHMAN: 1})
    hand = by_role(game, Role.HAND)[0]
    watchman = by_role(game, Role.WATCHMAN)[0]
    recruit = next(p for p in game.players if p.role not in (Role.HAND, Role.WATCHMAN))

    game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    game.submit_night_action(watchman.id, ActionType.PROTECT, recruit.id)
    game.resolve_night()
    game.respond_to_offer(recruit.id, accepted=False)
    assert not recruit.alive  # protection does not save a refuser


def test_marked_player_counts_for_parity_immediately():
    # 4 players, 1 Hand. Recruiting the only other non-Watchman player
    # should bring the Hand faction to parity and end the game instantly.
    game = make_offer_game(names=["A", "B", "C"], role_counts={Role.HAND: 1})
    hand = by_role(game, Role.HAND)[0]
    recruit = next(p for p in game.players if p.role is not Role.HAND)
    game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    game.resolve_night()

    game.respond_to_offer(recruit.id, accepted=True)
    assert game.phase == Phase.GAME_OVER
    assert game.winner == Faction.HAND


def test_marked_players_other_state_is_left_untouched():
    # No Ledger exists yet (Phase 4), so this verifies the one thing that
    # currently could be disturbed: identity and pre-existing state. Full
    # vote-history-untouched verification is deferred to Phase 4.
    game = make_offer_game()
    hand = by_role(game, Role.HAND)[0]
    recruit = next(p for p in game.players if p.role is not Role.HAND)
    original_name, original_id = recruit.name, recruit.id
    game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    game.resolve_night()
    game.respond_to_offer(recruit.id, accepted=True)
    assert recruit.name == original_name
    assert recruit.id == original_id


def test_public_feed_message_is_byte_identical_across_all_silent_outcomes():
    # No target chosen, a kill blocked by the Watchman, and an accepted
    # offer must all read as literally the same string. This is the
    # single most important test in this project -- section 2.3.
    no_target_game = make_game(role_counts={Role.HAND: 1})
    no_target_game.start_game()
    no_target_game.resolve_night()
    assert no_target_game.events[-1] == NO_VISIBLE_DEATH_MESSAGE

    blocked_game = make_offer_game(role_counts={Role.HAND: 1, Role.WATCHMAN: 1})
    hand = by_role(blocked_game, Role.HAND)[0]
    watchman = by_role(blocked_game, Role.WATCHMAN)[0]
    victim = next(p for p in blocked_game.players if p.role not in (Role.HAND, Role.WATCHMAN))
    blocked_game.submit_night_action(hand.id, ActionType.KILL, victim.id)
    blocked_game.submit_night_action(watchman.id, ActionType.PROTECT, victim.id)
    blocked_game.resolve_night()
    assert blocked_game.events[-1] == NO_VISIBLE_DEATH_MESSAGE

    accepted_game = make_offer_game(names=["A", "B", "C", "D", "E"])
    hand2 = by_role(accepted_game, Role.HAND)[0]
    recruit = next(p for p in accepted_game.players if p.role is not Role.HAND)
    accepted_game.submit_night_action(hand2.id, ActionType.OFFER, recruit.id)
    accepted_game.resolve_night()
    accepted_game.respond_to_offer(recruit.id, accepted=True)
    assert accepted_game.events[-1] == NO_VISIBLE_DEATH_MESSAGE

    assert (
        no_target_game.events[-1]
        == blocked_game.events[-1]
        == accepted_game.events[-1]
        == NO_VISIBLE_DEATH_MESSAGE
    )


def test_black_hand_is_not_told_refusal_from_timeout():
    # The engine exposes no distinguishing field anywhere -- the Hand's own
    # view after either outcome only shows the normal post-night state,
    # with nothing marking which of the two happened.
    refused_game = make_offer_game(names=["A", "B", "C", "D", "E"])
    hand = by_role(refused_game, Role.HAND)[0]
    recruit = next(p for p in refused_game.players if p.role is not Role.HAND)
    refused_game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    refused_game.resolve_night()
    refused_game.respond_to_offer(recruit.id, accepted=False)
    refused_view = refused_game.view_for(hand.id)

    timeout_game = make_offer_game(names=["A", "B", "C", "D", "E"])
    hand2 = by_role(timeout_game, Role.HAND)[0]
    recruit2 = next(p for p in timeout_game.players if p.role is not Role.HAND)
    timeout_game.submit_night_action(hand2.id, ActionType.OFFER, recruit2.id)
    timeout_game.resolve_night()
    timeout_game.resolve_offer_timeout()
    timeout_view = timeout_game.view_for(hand2.id)

    assert set(refused_view.keys()) == set(timeout_view.keys())
    assert "offer_pending" not in refused_view
    assert "offer_pending" not in timeout_view


def test_cannot_offer_to_a_member_of_the_black_hand():
    game = make_offer_game(names=["A", "B", "C", "D", "E"], role_counts={Role.HAND: 2})
    h1, h2 = by_role(game, Role.HAND)
    with pytest.raises(IllegalActionError):
        game.submit_night_action(h1.id, ActionType.OFFER, h2.id)


def test_offer_recipient_only_can_respond():
    game = make_offer_game(names=["A", "B", "C", "D", "E"])
    hand = by_role(game, Role.HAND)[0]
    recruit, bystander = [p for p in game.players if p.role is not Role.HAND][:2]
    game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    game.resolve_night()

    with pytest.raises(IllegalActionError):
        game.respond_to_offer(bystander.id, accepted=True)


def test_investigations_wait_behind_offer_resolution():
    game = make_offer_game(
        names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1, Role.INSPECTOR: 1}
    )
    hand = by_role(game, Role.HAND)[0]
    inspector = by_role(game, Role.INSPECTOR)[0]
    recruit = next(p for p in game.players if p.role not in (Role.HAND, Role.INSPECTOR))

    game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    game.submit_night_action(inspector.id, ActionType.INVESTIGATE, recruit.id)
    game.resolve_night()
    assert game.phase == Phase.OFFER
    assert game.private_log.get(inspector.id, []) == []  # not resolved yet

    game.respond_to_offer(recruit.id, accepted=True)
    # The recruit is now effectively Hand, so the deferred investigation
    # reads guilty -- this is what makes a stale clear decay (section 3.4).
    assert any("GUILTY" in msg for msg in game.private_log.get(inspector.id, []))


def test_switching_from_offer_back_to_kill_before_resolution_does_not_spend_it():
    game = make_offer_game(names=["A", "B", "C", "D", "E"])
    hand = by_role(game, Role.HAND)[0]
    a, b = [p for p in game.players if p.role is not Role.HAND][:2]

    game.submit_night_action(hand.id, ActionType.OFFER, a.id)
    game.submit_night_action(hand.id, ActionType.KILL, b.id)  # changed their mind
    game.resolve_night()

    assert game.phase != Phase.OFFER
    assert not b.alive
    assert a.alive
    assert game.recruitment_used is False  # never actually delivered, still available


def test_night_ends_on_offer_submission_alone_like_a_kill():
    game = make_offer_game()
    hand = by_role(game, Role.HAND)[0]
    recruit = next(p for p in game.players if p.role is not Role.HAND)
    assert not game.night_actions_ready()
    game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    assert game.night_actions_ready()


def test_recipient_disconnecting_during_offer_resolves_it_as_a_timeout():
    # A vanished recipient must not leave the game stuck in Phase.OFFER
    # forever -- the generic disconnect-removal path would just mark them
    # dead without ever resolving the offer.
    game = make_offer_game(names=["A", "B", "C", "D", "E"])
    hand = by_role(game, Role.HAND)[0]
    recruit = next(p for p in game.players if p.role is not Role.HAND)
    game.submit_night_action(hand.id, ActionType.OFFER, recruit.id)
    game.resolve_night()
    assert game.phase == Phase.OFFER

    game.handle_disconnect_removal(recruit.id)
    assert game.phase != Phase.OFFER
    assert not recruit.alive
    assert recruit.marked is False
