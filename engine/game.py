"""Pure Python game engine. Zero web framework imports -- fully testable headless.

Decided ambiguities (spec section 6) -- see README.md for rationale:
  - Doctor CAN self-heal, but only once per game.
  - Doctor cannot target the same player on consecutive nights.
  - A roleblocked Detective gets an explicit "blocked" result (reserved for
    future Roleblocker roles; v1 has none, so this never fires yet).
  - The Detective sees the true role of a target who died earlier the same
    night (kills resolve before investigations, but role data never changes).
  - Godfather succession is checked immediately after night resolution AND
    after lynch resolution, so whichever kill happens "last" in the actual
    phase sequence is authoritative -- there is no true simultaneity to
    arbitrate since night and day are always separate phases.
  - Tied mafia kill votes -> no kill that night. Tied lynch votes -> no lynch.
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
        if self.phase != Phase.LOBBY:
            raise IllegalActionError("Cannot leave after the game has started")
        self.players = [p for p in self.players if p.id != player_id]

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

    NIGHT_ACTION_ROLES = (Role.MAFIA, Role.DOCTOR, Role.DETECTIVE)

    def required_night_actor_ids(self) -> set:
        """Living players whose role has a night action -- night resolves as
        soon as all of them have acted, rather than waiting out a timer."""
        return {p.id for p in self.alive_players() if p.role in self.NIGHT_ACTION_ROLES}

    def night_actions_ready(self) -> bool:
        return self.required_night_actor_ids() <= set(self.pending_actions.keys())

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
                raise IllegalActionError("Only the Doctor can protect")
            if target.id == actor.id and self._doctor_self_heal_used:
                raise IllegalActionError("Doctor has already used their one self-heal")
            if target.id == self._doctor_last_target:
                raise IllegalActionError("Doctor cannot heal the same target on consecutive nights")
        elif action_type == ActionType.KILL:
            if role_team(actor.role) != Team.MAFIA or actor.role == Role.GODFATHER:
                raise IllegalActionError("Only Mafia can submit a kill")
        elif action_type == ActionType.INVESTIGATE:
            if actor.role != Role.DETECTIVE:
                raise IllegalActionError("Only the Detective can investigate")

        self.pending_actions[actor_id] = NightAction(actor_id, action_type, target_id)

    def resolve_night(self) -> None:
        if self.phase != Phase.NIGHT:
            raise IllegalActionError("Not the night phase")

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
        else:
            self._doctor_last_target = None

        # 3. Kills (shared: plurality vote among mafia, tie = no kill)
        kill_votes = [a.target_id for a in self.pending_actions.values() if a.action_type == ActionType.KILL]
        if kill_votes:
            tally: Dict[str, int] = {}
            for target_id in kill_votes:
                tally[target_id] = tally.get(target_id, 0) + 1
            top = max(tally.values())
            leaders = [t for t, c in tally.items() if c == top]
            if len(leaders) == 1:
                target_id = leaders[0]
                if target_id in protected_ids:
                    self.events.append(f"The Doctor saved {self.player(target_id).name} last night.")
                else:
                    victim = self.player(target_id)
                    victim.alive = False
                    self.events.append(f"{victim.name} was killed during the night.")
            else:
                self.events.append("The Mafia could not agree on a target -- no kill last night.")
        else:
            self.events.append("Nothing happened last night.")

        # 4. Investigations
        for action in self.pending_actions.values():
            if action.action_type != ActionType.INVESTIGATE:
                continue
            target = self.player(action.target_id)
            result = detective_reads_as(target.role)
            self._log(action.actor_id, f"Investigation of {target.name}: {result.value.upper()}")

        # 5. Death triggers -- no v1 role has one; reserved stage.

        # 6. Godfather succession check
        self._check_succession()

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

        tally: Dict[str, int] = {}
        for target_id in self.votes.values():
            tally[target_id] = tally.get(target_id, 0) + 1

        if tally:
            top = max(tally.values())
            leaders = [t for t, c in tally.items() if c == top]
            if len(leaders) == 1:
                victim = self.player(leaders[0])
                victim.alive = False
                self.events.append(f"{victim.name} was lynched by the town.")
            else:
                self.events.append("The vote was tied -- no one was lynched.")
        else:
            self.events.append("No votes were cast -- no one was lynched.")

        # Death triggers -- reserved stage, no-op in v1.

        self._check_succession()

        if self._check_win():
            return
        self._begin_night()

    # -- win / succession -----------------------------------------------------

    def _check_succession(self) -> None:
        mafia_alive = [p for p in self.alive_players() if p.role is Role.MAFIA]
        gf = next((p for p in self.alive_players() if p.role is Role.GODFATHER), None)
        if not mafia_alive and gf:
            gf.role = Role.MAFIA
            self._log(gf.id, "The family has fallen. You are now the Mafia.")
            self.events.append(f"{gf.name} has stepped up to lead the Mafia.")

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
        self.events.append(f"{self.winner.value.title()} wins!")
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
        if me.role == Role.GODFATHER:
            base["known_mafia"] = [p.name for p in self.mafia_team()]
        if self.phase == Phase.NIGHT:
            required = self.required_night_actor_ids()
            base["night_actions_total"] = len(required)
            base["night_actions_done"] = len(required & set(self.pending_actions.keys()))
        return base
