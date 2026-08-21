from __future__ import annotations

import re
from pathlib import Path

import pytest

from engine import SKIP_VOTE, Game, GameConfig, Role


def make_game(room_code="TEST", names=None, role_counts=None):
    names = names or [f"P{i}" for i in range(8)]
    config = GameConfig(role_counts=role_counts or {}, show_hands_enabled=False)
    game = Game(room_code=room_code, config=config)
    for i, name in enumerate(names):
        game.add_player(str(i), name)
    return game


def by_role(game: Game, role: Role):
    return [p for p in game.players if p.role is role]


def to_voting(game: Game):
    game.start_game()
    game.resolve_night()
    game.begin_voting()


def test_every_vote_recorded_with_round_voter_and_target():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    to_voting(game)
    a, b = game.players[0], game.players[1]
    game.submit_vote(a.id, b.id)

    assert game.vote_history == [{"round": 1, "voter_id": a.id, "target_id": b.id}]


def test_a_changed_vote_is_recorded_as_a_second_entry_not_overwritten():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    to_voting(game)
    a, b, c = game.players[0], game.players[1], game.players[2]
    game.submit_vote(a.id, b.id)
    game.submit_vote(a.id, c.id)  # changed their mind

    assert len(game.vote_history) == 2
    assert game.vote_history[0] == {"round": 1, "voter_id": a.id, "target_id": b.id}
    assert game.vote_history[1] == {"round": 1, "voter_id": a.id, "target_id": c.id}
    # only the final choice is what's actually tallied
    assert game.votes[a.id] == c.id


def test_stand_asides_recorded_distinctly_from_votes():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    to_voting(game)
    a, b = game.players[0], game.players[1]
    game.submit_vote(a.id, b.id)
    game.submit_vote(b.id, SKIP_VOTE)

    real_vote = next(e for e in game.vote_history if e["voter_id"] == a.id)
    stand_aside = next(e for e in game.vote_history if e["voter_id"] == b.id)
    assert real_vote["target_id"] == b.id
    assert stand_aside["target_id"] is None  # distinct from a real target, and from the SKIP_VOTE sentinel


def test_votes_received_derived_from_history():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    to_voting(game)
    a, b, c, d = game.players[:4]
    game.submit_vote(a.id, d.id)
    game.submit_vote(b.id, d.id)
    game.submit_vote(c.id, SKIP_VOTE)

    received = game.votes_received(d.id)
    assert len(received) == 2
    assert {e["voter_id"] for e in received} == {a.id, b.id}


def test_losing_side_of_a_lynch_computed_per_player():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    to_voting(game)
    a, b, c, d = game.players[:4]
    # b, c vote for d (the eventual lynch target); a votes for b (loses); d stands aside
    game.submit_vote(a.id, b.id)
    game.submit_vote(b.id, d.id)
    game.submit_vote(c.id, d.id)
    game.submit_vote(d.id, SKIP_VOTE)
    game.resolve_lynch()

    assert not d.alive
    assert game.losing_side_counts.get(a.id) == 1  # voted for someone who wasn't lynched
    assert a.id in game.losing_side_counts
    assert b.id not in game.losing_side_counts  # voted for the actual lynch target
    assert c.id not in game.losing_side_counts
    assert d.id not in game.losing_side_counts  # stood aside, not a side at all


def test_losing_side_accumulates_across_multiple_rounds():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    a = game.players[0]

    for _ in range(2):
        game.resolve_night()
        game.begin_voting()
        alive = [p for p in game.alive_players() if p.id != a.id]
        target = alive[0]
        game.submit_vote(a.id, alive[1].id if len(alive) > 1 else alive[0].id)  # a votes for someone who won't win
        for voter in alive:
            game.submit_vote(voter.id, target.id)
        if game.phase.value == "voting":
            game.resolve_lynch()
        if game.phase.value == "game_over":
            break

    assert game.losing_side_counts.get(a.id, 0) >= 1


def test_no_losing_side_recorded_on_a_tied_vote():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    to_voting(game)
    a, b, c, d = game.players[:4]
    game.submit_vote(a.id, b.id)
    game.submit_vote(c.id, d.id)
    game.resolve_lynch()

    assert game.losing_side_counts == {}


def test_speaking_time_accumulated_per_player():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    a = game.players[0]
    game.record_speaking_time(a.id, 4.5)
    game.record_speaking_time(a.id, 2.0)
    assert game.speaking_seconds[a.id] == 6.5


def test_speaking_time_rejects_unknown_player():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    with pytest.raises(KeyError):
        game.record_speaking_time("nobody", 5.0)


def test_speaking_time_ignores_non_positive_values():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    a = game.players[0]
    game.record_speaking_time(a.id, 0)
    game.record_speaking_time(a.id, -3)
    assert a.id not in game.speaking_seconds


def test_ledger_is_public_and_always_present_in_every_view():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    to_voting(game)
    a, b = game.players[0], game.players[1]
    game.submit_vote(a.id, b.id)
    game.record_speaking_time(a.id, 3.0)

    for p in game.players:
        view = game.view_for(p.id)
        assert "ledger" in view
        assert view["ledger"]["votes"] == game.vote_history
        assert view["ledger"]["speaking_seconds"] == {a.id: 3.0}


def test_ledger_survives_a_return_to_lobby_is_cleared_for_rematch():
    game = make_game(names=["A", "B", "C", "D", "E", "F"], role_counts={Role.HAND: 1})
    game.start_game()
    hand = by_role(game, Role.HAND)[0]
    hand.alive = False
    game.resolve_night()
    assert game.phase.value == "game_over"

    game.return_to_lobby()
    assert game.vote_history == []
    assert game.losing_side_counts == {}
    assert game.speaking_seconds == {}


def test_no_scoring_or_ranking_function_exists_in_the_engine():
    # The document's own verification method, run as an actual test so it
    # stays enforced rather than being a one-time manual check.
    engine_dir = Path(__file__).resolve().parent.parent / "engine"
    pattern = re.compile(r"suspicion|score|rank|sort_by_sus", re.IGNORECASE)
    offenders = []
    for path in engine_dir.glob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert offenders == []
