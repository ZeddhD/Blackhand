"""Pure Python game engine. Zero web framework imports -- fully testable headless.

Decided ambiguities (spec section 6) -- see README.md for rationale:
  - Doctor (Healer) CAN self-heal, but only once per game.
  - Doctor cannot target the same player on consecutive nights.
  - A roleblocked Detective (Police) gets an explicit "blocked" result
    (reserved for future Roleblocker roles; v1 has none, so this never
    fires yet).
  - The Detective sees the true role of a target who died earlier the same
    night (kills resolve before investigations, but role data never changes).
  - Godfather succession is checked immediately after night resolution AND
    after lynch resolution, so whichever kill happens "last" in the actual
    phase sequence is authoritative -- there is no true simultaneity to
    arbitrate since night and day are always separate phases.
  - The Mafia's kill is a single shared choice: any living Mafia member can
    set or change it, and it is visible live to the whole Mafia team. There
    is no way for two Mafia members to target two different people at once,
    so there is nothing to tie-break. Tied lynch votes -> no lynch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .actions import ActionType, NightAction
from .models import (
    GameConfig,
    InvestigationResult,
    Phase,
    Player,
    Role,
    Team,
    detective_reads_as,
    role_team,
)


class IllegalActionError(Exception):
    pass


@dataclass
class Game:
    room_code: str
    config: GameConfig = field(default_factory=GameConfig)
    players: List[Player] = field(default_factory=list)
    phase: Phase = Phase.LOBBY
    night_number: int = 0
    winner: Optional[Team] = None

    pending_actions: Dict[str, NightAction] = field(default_factory=dict)
    votes: Dict[str, str] = field(default_factory=dict)

    events: List[str] = field(default_factory=list)  # public log
    private_log: Dict[str, List[str]] = field(default_factory=dict)  # player_id -> messages
    round_log: List[dict] = field(default_factory=list)  # full detail, revealed to dead players and post-game

    mafia_kill_target: Optional[str] = None
    mafia_kill_actor: Optional[str] = None

    _doctor_self_heal_used: bool = False
    _doctor_last_target: Optional[str] = None

    # -- setup -----------------------------------------------------------

    def add_player(self, player_id: str, name: str) -> Player:
        if self.phase != Phase.LOBBY:
            raise IllegalActionError("Cannot join after the game has started")
        player = Player(id=player_id, name=name)
        self.players.append(player)
        return player

    def remove_player(self, player_id: str) -> None:
        if self.phase not in (Phase.LOBBY, Phase.GAME_OVER):
            raise IllegalActionError("Cannot leave while a game is in progress")
        self.players = [p for p in self.players if p.id != player_id]

    def return_to_lobby(self) -> None:
        """Reset a finished game back to the lobby so the same room can play
        again, keeping the same players and room code."""
        if self.phase != Phase.GAME_OVER:
            raise IllegalActionError("Can only return to the lobby after a game has ended")
        self.phase = Phase.LOBBY
        self.night_number = 0
        self.winner = None
        self.pending_actions.clear()
        self.votes.clear()
        self.events.clear()
        self.private_log.clear()
        self.round_log.clear()
        self.mafia_kill_target = None
        self.mafia_kill_actor = None
        self._doctor_self_heal_used = False
        self._doctor_last_target = None
        for p in self.players:
            p.role = None
            p.alive = True

    def player(self, player_id: str) -> Player:
        for p in self.players:
            if p.id == player_id:
                return p
        raise KeyError(player_id)

    def alive_players(self) -> List[Player]:
        return [p for p in self.players if p.alive]

    def mafia_team(self) -> List[Player]:
        """Players the Mafia chat/kill together with -- excludes the Godfather,
        who the spec requires stay hidden from the regular Mafia (section 4)."""
        return [p for p in self.players if p.role in (Role.MAFIA,)]

    def start_game(self) -> None:
        if self.phase != Phase.LOBBY:
            raise IllegalActionError("Game already started")
        errors = self.config.validate(len(self.players))
        if errors:
            raise IllegalActionError("; ".join(errors))
        self.phase = Phase.ASSIGN_ROLES
        roles = self.config.build_role_list(len(self.players))
        for player, role in zip(self.players, roles):
            player.role = role
        self._begin_night()

    # -- night -------------------------------------------------------------

    def _begin_night(self) -> None:
        self.phase = Phase.NIGHT
        self.night_number += 1
        self.pending_actions.clear()
        self.private_log.clear()
        self.mafia_kill_target = None
        self.mafia_kill_actor = None

    INDIVIDUAL_NIGHT_ACTION_ROLES = (Role.DOCTOR, Role.DETECTIVE)

    def required_night_actor_ids(self) -> set:
        """Living players who each individually owe a night action (Healer,
        Police). The Mafia's kill is a single shared team choice, tracked
        separately -- see mafia_ready()."""
        return {p.id for p in self.alive_players() if p.role in self.INDIVIDUAL_NIGHT_ACTION_ROLES}

    def mafia_ready(self) -> bool:
        mafia_alive = [p for p in self.alive_players() if p.role is Role.MAFIA]
        return not mafia_alive or self.mafia_kill_target is not None

    def night_actions_ready(self) -> bool:
        return self.mafia_ready() and self.required_night_actor_ids() <= set(self.pending_actions.keys())

    def submit_night_action(self, actor_id: str, action_type: ActionType, target_id: str) -> None:
        if self.phase != Phase.NIGHT:
            raise IllegalActionError("Not the night phase")
        actor = self.player(actor_id)
        target = self.player(target_id)
        if not actor.alive:
            raise IllegalActionError("Dead players cannot act")
        if not target.alive:
            raise IllegalActionError("Cannot target a dead player")

        if action_type == ActionType.PROTECT:
            if actor.role != Role.DOCTOR:
                raise IllegalActionError("Only the Healer can protect")
            if target.id == actor.id and self._doctor_self_heal_used:
                raise IllegalActionError("The Healer has already used their one self-heal")
            if target.id == self._doctor_last_target:
                raise IllegalActionError("The Healer cannot protect the same person two nights in a row")
        elif action_type == ActionType.KILL:
            if role_team(actor.role) != Team.MAFIA or actor.role == Role.GODFATHER:
                raise IllegalActionError("Only Mafia can submit a kill")
            # Shared team choice: any living Mafia member can set or change it.
            self.mafia_kill_target = target_id
            self.mafia_kill_actor = actor_id
        elif action_type == ActionType.INVESTIGATE:
            if actor.role != Role.DETECTIVE:
                raise IllegalActionError("Only the Police can investigate")

        self.pending_actions[actor_id] = NightAction(actor_id, action_type, target_id)

    def resolve_night(self) -> None:
        if self.phase != Phase.NIGHT:
            raise IllegalActionError("Not the night phase")

        lines: List[str] = []

        # 1. Roleblocks / redirects -- no v1 role produces these; reserved stage.

        # 2. Protections
        protected_ids = {
            a.target_id for a in self.pending_actions.values() if a.action_type == ActionType.PROTECT
        }
        doctor_action = next(
            (a for a in self.pending_actions.values() if a.action_type == ActionType.PROTECT), None
        )
        if doctor_action:
            if doctor_action.target_id == doctor_action.actor_id:
                self._doctor_self_heal_used = True
            self._doctor_last_target = doctor_action.target_id
            healer = self.player(doctor_action.actor_id)
            target = self.player(doctor_action.target_id)
            lines.append(f"{healer.name} the Healer protected {target.name}.")
        else:
            self._doctor_last_target = None

        # 3. Kills (single shared Mafia choice)
        if self.mafia_kill_target:
            victim = self.player(self.mafia_kill_target)
            chooser = self.player(self.mafia_kill_actor) if self.mafia_kill_actor else None
            if chooser:
                lines.append(f"{chooser.name} the Mafia chose to kill {victim.name}.")
            if victim.id in protected_ids:
                self.events.append(f"The Healer saved {victim.name} last night.")
                lines.append(f"{victim.name} was attacked but saved by the Healer.")
            else:
                victim.alive = False
                self.events.append(f"{victim.name} was killed during the night.")
                lines.append(f"{victim.name} was killed.")
        else:
            self.events.append("Nothing happened last night.")
            lines.append("The Mafia did not choose a target.")

        # 4. Investigations
        for action in self.pending_actions.values():
            if action.action_type != ActionType.INVESTIGATE:
                continue
            police = self.player(action.actor_id)
            target = self.player(action.target_id)
            result = detective_reads_as(target.role)
            self._log(action.actor_id, f"Investigation of {target.name}: {result.value.upper()}")
            lines.append(f"{police.name} the Police investigated {target.name}: {result.value.upper()}.")

        # 5. Death triggers -- no v1 role has one; reserved stage.

        # 6. Godfather succession check
        promo = self._check_succession()
        if promo:
            lines.append(promo)

        self.round_log.append({"title": f"Night {self.night_number}", "lines": lines})

        if self._check_win():
            return
        self.phase = Phase.DAY_DISCUSSION

    # -- day / voting --------------------------------------------------------

    def begin_voting(self) -> None:
        if self.phase != Phase.DAY_DISCUSSION:
            raise IllegalActionError("Not the discussion phase")
        self.votes.clear()
        self.phase = Phase.VOTING

    def submit_vote(self, voter_id: str, target_id: str) -> None:
        if self.phase != Phase.VOTING:
            raise IllegalActionError("Not the voting phase")
        voter = self.player(voter_id)
        if not voter.alive:
            raise IllegalActionError("Dead players cannot vote")
        if not self.player(target_id).alive:
            raise IllegalActionError("Cannot vote for a dead player")
        self.votes[voter_id] = target_id

    def public_votes(self) -> Dict[str, str]:
        return dict(self.votes)

    def resolve_lynch(self) -> None:
        if self.phase != Phase.VOTING:
            raise IllegalActionError("Not the voting phase")

        lines: List[str] = []
        tally: Dict[str, int] = {}
        for target_id in self.votes.values():
            tally[target_id] = tally.get(target_id, 0) + 1

        if tally:
            top = max(tally.values())
            leaders = [t for t, c in tally.items() if c == top]
            if len(leaders) == 1:
                victim = self.player(leaders[0])
                victim.alive = False
                self.events.append(f"{victim.name} was voted out.")
                caught = " They were Mafia." if role_team(victim.role) == Team.MAFIA else " They were not Mafia."
                lines.append(f"{victim.name} was voted out ({top} votes).{caught}")
            else:
                self.events.append("The vote was tied -- no one was voted out.")
                lines.append("The vote was tied. No one was voted out.")
        else:
            self.events.append("No votes were cast -- no one was voted out.")
            lines.append("No votes were cast. No one was voted out.")

        # Death triggers -- reserved stage, no-op in v1.

        promo = self._check_succession()
        if promo:
            lines.append(promo)

        self.round_log.append({"title": f"Day {self.night_number} Vote", "lines": lines})

        if self._check_win():
            return
        self._begin_night()

    # -- win / succession -----------------------------------------------------

    def _check_succession(self) -> Optional[str]:
        mafia_alive = [p for p in self.alive_players() if p.role is Role.MAFIA]
        gf = next((p for p in self.alive_players() if p.role is Role.GODFATHER), None)
        if not mafia_alive and gf:
            gf.role = Role.MAFIA
            self._log(gf.id, "The family has fallen. You are now the Mafia.")
            line = f"{gf.name} has stepped up to lead the Mafia."
            self.events.append(line)
            return line
        return None

    def _check_win(self) -> bool:
        evil_alive = [p for p in self.alive_players() if role_team(p.role) == Team.MAFIA]
        town_alive = [p for p in self.alive_players() if role_team(p.role) == Team.TOWN]
        if not evil_alive:
            self.winner = Team.TOWN
        elif len(evil_alive) >= len(town_alive):
            self.winner = Team.MAFIA
        else:
            return False
        self.phase = Phase.GAME_OVER
        self.events.append("The Civilians win!" if self.winner == Team.TOWN else "The Mafia win!")
        return True

    def _log(self, player_id: str, message: str) -> None:
        self.private_log.setdefault(player_id, []).append(message)

    # -- per-player view ---------------------------------------------------

    def view_for(self, player_id: str) -> dict:
        """Construct the state visible to one player. Never send full state to clients."""
        me = self.player(player_id)
        base = {
            "room_code": self.room_code,
            "phase": self.phase.value,
            "night_number": self.night_number,
            "players": [p.to_public_dict() for p in self.players],
            "votes": self.public_votes(),
            "events": list(self.events),
            "your_id": me.id,
            "your_role": me.role.value if me.role else None,
            "your_alive": me.alive,
            "private_log": list(self.private_log.get(player_id, [])),
            "winner": self.winner.value if self.winner else None,
        }
        if me.role == Role.MAFIA:
            base["allies"] = [p.name for p in self.mafia_team() if p.id != me.id]
            base["mafia_kill_target_id"] = self.mafia_kill_target
            base["mafia_kill_target_name"] = (
                self.player(self.mafia_kill_target).name if self.mafia_kill_target else None
            )
        if me.role == Role.GODFATHER:
            base["known_mafia"] = [p.name for p in self.mafia_team()]
        if self.phase == Phase.NIGHT:
            required = self.required_night_actor_ids()
            mafia_alive_exists = any(p.role is Role.MAFIA for p in self.alive_players())
            base["night_actions_total"] = len(required) + (1 if mafia_alive_exists else 0)
            base["night_actions_done"] = len(required & set(self.pending_actions.keys())) + (
                1 if mafia_alive_exists and self.mafia_kill_target else 0
            )
        if not me.alive or self.phase == Phase.GAME_OVER:
            base["round_log"] = list(self.round_log)
        if self.phase == Phase.GAME_OVER:
            base["mafia_reveal"] = [p.name for p in self.players if role_team(p.role) == Team.MAFIA]
        return base
