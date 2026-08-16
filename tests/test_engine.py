from __future__ import annotations

import pytest

from engine import ActionType, Game, GameConfig, Phase, Role, Team


def make_game(room_code="TEST", names=None, role_counts=None):
    names = names or [f"P{i}" for i in range(8)]
    game = Game(room_code=room_code, config=GameConfig(role_counts=role_counts or {}))
    for i, name in enumerate(names):
        game.add_player(str(i), name)
    return game


def by_role(game: Game, role: Role):
    return [p for p in game.players if p.role is role]


def test_config_validate_rejects_too_many_roles():
    errors = GameConfig(role_counts={Role.MAFIA: 10}).validate(8)
    assert any("roles for" in e for e in errors)


def test_config_validate_requires_evil_role():
    errors = GameConfig(role_counts={Role.DOCTOR: 1}).validate(8)
    assert any("evil role" in e for e in errors)


def test_config_validate_rejects_parity_start():
    errors = GameConfig(role_counts={Role.MAFIA: 4}).validate(8)
    assert any("parity" in e for e in errors)


def test_start_game_assigns_all_roles_and_fills_villagers():
    game = make_game(role_counts={Role.MAFIA: 2, Role.DETECTIVE: 1, Role.DOCTOR: 1})
    game.start_game()
    assert game.phase == Phase.NIGHT
    assert len(by_role(game, Role.MAFIA)) == 2
    assert len(by_role(game, Role.DETECTIVE)) == 1
    assert len(by_role(game, Role.DOCTOR)) == 1
    assert len(by_role(game, Role.VILLAGER)) == 4


def test_mafia_kill_resolves():
    game = make_game(role_counts={Role.MAFIA: 1})
    game.start_game()
    mafia = by_role(game, Role.MAFIA)[0]
    victim = next(p for p in game.players if p.role is not Role.MAFIA)
    game.submit_night_action(mafia.id, ActionType.KILL, victim.id)
    game.resolve_night()
    assert not victim.alive
    assert game.phase == Phase.DAY_DISCUSSION


def test_doctor_can_save_the_target():
    game = make_game(role_counts={Role.MAFIA: 1, Role.DOCTOR: 1})
    game.start_game()
    mafia = by_role(game, Role.MAFIA)[0]
    doctor = by_role(game, Role.DOCTOR)[0]
    victim = next(p for p in game.players if p.role not in (Role.MAFIA, Role.DOCTOR))
    game.submit_night_action(mafia.id, ActionType.KILL, victim.id)
    game.submit_night_action(doctor.id, ActionType.PROTECT, victim.id)
    game.resolve_night()
    assert victim.alive


def test_doctor_self_heal_allowed_once_then_blocked():
    game = make_game(role_counts={Role.MAFIA: 1, Role.DOCTOR: 1})
    game.start_game()
    doctor = by_role(game, Role.DOCTOR)[0]
    mafia = by_role(game, Role.MAFIA)[0]
    other = next(p for p in game.players if p.id not in (doctor.id, mafia.id))

    game.submit_night_action(doctor.id, ActionType.PROTECT, doctor.id)
    game.resolve_night()
    game.begin_voting()
    game.resolve_lynch()  # no votes cast -> advances to next night

    with pytest.raises(Exception):
        game.submit_night_action(doctor.id, ActionType.PROTECT, doctor.id)


def test_doctor_cannot_heal_same_target_consecutive_nights():
    game = make_game(role_counts={Role.MAFIA: 1, Role.DOCTOR: 1})
    game.start_game()
    doctor = by_role(game, Role.DOCTOR)[0]
    target = next(p for p in game.players if p.id != doctor.id)

    game.submit_night_action(doctor.id, ActionType.PROTECT, target.id)
    game.resolve_night()
    game.begin_voting()
    game.resolve_lynch()

    with pytest.raises(Exception):
        game.submit_night_action(doctor.id, ActionType.PROTECT, target.id)


def test_detective_sees_godfather_as_innocent():
    game = make_game(role_counts={Role.MAFIA: 1, Role.GODFATHER: 1, Role.DETECTIVE: 1})
    game.start_game()
    detective = by_role(game, Role.DETECTIVE)[0]
    gf = by_role(game, Role.GODFATHER)[0]
    game.submit_night_action(detective.id, ActionType.INVESTIGATE, gf.id)
    game.resolve_night()
    assert any("INNOCENT" in msg for msg in game.private_log.get(detective.id, []))


def test_detective_sees_mafia_as_guilty():
    game = make_game(role_counts={Role.MAFIA: 1, Role.DETECTIVE: 1})
    game.start_game()
    detective = by_role(game, Role.DETECTIVE)[0]
    mafia = by_role(game, Role.MAFIA)[0]
    game.submit_night_action(detective.id, ActionType.INVESTIGATE, mafia.id)
    game.resolve_night()
    assert any("GUILTY" in msg for msg in game.private_log.get(detective.id, []))


def test_godfather_promoted_when_last_mafia_dies_at_night():
    game = make_game(
        names=[f"P{i}" for i in range(6)],
        role_counts={Role.MAFIA: 1, Role.GODFATHER: 1},
    )
    game.start_game()
    mafia = by_role(game, Role.MAFIA)[0]
    gf = by_role(game, Role.GODFATHER)[0]
    mafia.alive = False  # simulate the last regular mafia already dead

    game.resolve_night()  # Godfather has no night action pre-promotion
    assert gf.role is Role.MAFIA
    assert any("Mafia" in msg for msg in game.private_log.get(gf.id, []))


def test_godfather_promoted_when_last_mafia_lynched():
    game = make_game(
        names=[f"P{i}" for i in range(6)],
        role_counts={Role.MAFIA: 1, Role.GODFATHER: 1},
    )
    game.start_game()
    mafia = by_role(game, Role.MAFIA)[0]
    gf = by_role(game, Role.GODFATHER)[0]

    game.resolve_night()  # nothing submitted, nothing happens
    game.begin_voting()
    for p in game.players:
        if p.alive and p.id != mafia.id:
            game.submit_vote(p.id, mafia.id)
    game.resolve_lynch()
    assert not mafia.alive
    assert gf.role is Role.MAFIA


def test_tied_lynch_kills_no_one():
    game = make_game(names=["A", "B", "C", "D"], role_counts={Role.MAFIA: 1})
    game.start_game()
    a, b, c, d = game.players
    game.resolve_night()
    game.begin_voting()
    game.submit_vote(a.id, b.id)
    game.submit_vote(c.id, d.id)
    alive_before = {p.id for p in game.alive_players()}
    game.resolve_lynch()
    alive_after = {p.id for p in game.alive_players()}
    assert alive_before == alive_after


def test_town_wins_when_all_mafia_dead():
    game = make_game(names=["A", "B", "C"], role_counts={Role.MAFIA: 1})
    game.start_game()
    mafia = by_role(game, Role.MAFIA)[0]
    mafia.alive = False
    game.resolve_night()
    assert game.winner == Team.TOWN
    assert game.phase == Phase.GAME_OVER


def test_mafia_wins_at_parity():
    game = make_game(names=["A", "B", "C", "D", "E"], role_counts={Role.MAFIA: 2})
    game.start_game()
    villagers = by_role(game, Role.VILLAGER)
    villagers[0].alive = False
    game.resolve_night()
    assert game.winner == Team.MAFIA


def test_view_for_hides_role_info_from_villager():
    game = make_game(role_counts={Role.MAFIA: 2, Role.GODFATHER: 1})
    game.start_game()
    villager = by_role(game, Role.VILLAGER)[0]
    view = game.view_for(villager.id)
    assert "allies" not in view
    assert "known_mafia" not in view
    for p in view["players"]:
        assert "role" not in p


def test_view_for_mafia_shows_allies_but_not_godfather():
    game = make_game(role_counts={Role.MAFIA: 2, Role.GODFATHER: 1})
    game.start_game()
    mafia = by_role(game, Role.MAFIA)[0]
    gf = by_role(game, Role.GODFATHER)[0]
    view = game.view_for(mafia.id)
    assert gf.name not in view["allies"]


def test_view_for_godfather_shows_known_mafia():
    game = make_game(role_counts={Role.MAFIA: 2, Role.GODFATHER: 1})
    game.start_game()
    gf = by_role(game, Role.GODFATHER)[0]
    mafia_names = {p.name for p in by_role(game, Role.MAFIA)}
    view = game.view_for(gf.id)
    assert set(view["known_mafia"]) == mafia_names


def test_full_headless_12_player_game_runs_to_completion():
    game = make_game(
        names=[f"P{i}" for i in range(12)],
        role_counts={Role.MAFIA: 3, Role.GODFATHER: 1, Role.DETECTIVE: 1, Role.DOCTOR: 1},
    )
    game.start_game()
    rounds = 0
    while game.phase != Phase.GAME_OVER and rounds < 50:
        rounds += 1
        mafia_alive = [p for p in game.alive_players() if p.role is Role.MAFIA]
        if mafia_alive:
            victim = next((p for p in game.alive_players() if role_team_is_town(p)), None)
            if victim:
                game.submit_night_action(mafia_alive[0].id, ActionType.KILL, victim.id)
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
    assert game.winner in (Team.TOWN, Team.MAFIA)


def role_team_is_town(player):
    return player.role in (Role.VILLAGER, Role.DETECTIVE, Role.DOCTOR)
