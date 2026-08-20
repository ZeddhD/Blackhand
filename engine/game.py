"""Pure Python game engine. Zero web framework imports -- fully testable headless.

Decided ambiguities -- see README.md for rationale:
  - Watchman CAN self-heal, but only once per game.
  - Watchman cannot target the same player on consecutive nights.
  - A roleblocked Inspector gets an explicit "blocked" result (reserved for
    a future Roleblocker role; v1 has none, so this never fires yet).
  - The Inspector sees the true faction of a target who died earlier the
    same night (kills resolve before investigations, but faction data
    never changes on death).
  - The Black Hand's kill is a single shared choice: any living Hand can
    set or change it, and it is visible live to the whole Black Hand. There
    is no way for two Hands to target two different people at once, so
    there is nothing to tie-break. Tied lynch votes -> no lynch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .actions import ActionType, NightAction
from .models import (
    Faction,
    GameConfig,
    InvestigationResult,
    Phase,
    Player,
    Role,
    faction_of,
    inspector_reads_as,
)


class IllegalActionError(Exception):
    pass


# Sentinel vote value meaning "I choose not to vote for anyone this round."
# Not a real player id, so it can never collide with one.
SKIP_VOTE = "skip"


@dataclass
class Game:
    room_code: str
    config: GameConfig = field(default_factory=GameConfig)
    players: List[Player] = field(default_factory=list)
    phase: Phase = Phase.LOBBY
    night_number: int = 0
    winner: Optional[Faction] = None

    pending_actions: Dict[str, NightAction] = field(default_factory=dict)
    votes: Dict[str, str] = field(default_factory=dict)

    events: List[str] = field(default_factory=list)  # public log
    private_log: Dict[str, List[str]] = field(default_factory=dict)  # player_id -> messages
    round_log: List[dict] = field(default_factory=list)  # full detail, revealed to dead players and post-game

    hand_kill_target: Optional[str] = None
    hand_kill_actor: Optional[str] = None

    _watchman_self_heal_used: bool = False
    _watchman_last_target: Optional[str] = None

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

    def handle_disconnect_removal(self, player_id: str) -> None:
        """Called once a disconnected player's reconnect grace period has
        expired. Before the game starts or after it ends they're dropped
        outright (remove_player). Mid-game they can't be voluntarily
        removed, but a dead-and-gone connection can't be left blocking the
        game forever either -- so they're marked eliminated instead, which
        keeps votes, night-action requirements, and win checks consistent
        rather than leaving a hole in the player list mid-round."""
        if self.phase in (Phase.LOBBY, Phase.GAME_OVER):
            self.remove_player(player_id)
            return
        try:
            player = self.player(player_id)
        except KeyError:
            return
        if not player.alive:
            return
        player.alive = False
        self.votes.pop(player_id, None)
        self.pending_actions.pop(player_id, None)
        self.events.append(f"{player.name} disconnected and was removed from the game.")
        self._check_win()

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
        self.hand_kill_target = None
        self.hand_kill_actor = None
        self._watchman_self_heal_used = False
        self._watchman_last_target = None
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

    def hand_team(self) -> List[Player]:
        """Players who chat and kill together as the Black Hand."""
        return [p for p in self.players if p.role is Role.HAND]

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
        self.hand_kill_target = None
        self.hand_kill_actor = None

    INDIVIDUAL_NIGHT_ACTION_ROLES = (Role.WATCHMAN, Role.INSPECTOR)

    def required_night_actor_ids(self) -> set:
        """Living players who each individually owe a night action (Watchman,
        Inspector). The Black Hand's kill is a single shared team choice,
        tracked separately -- see hand_ready()."""
        return {p.id for p in self.alive_players() if p.role in self.INDIVIDUAL_NIGHT_ACTION_ROLES}

    def hand_ready(self) -> bool:
        hand_alive = [p for p in self.alive_players() if p.role is Role.HAND]
        return not hand_alive or self.hand_kill_target is not None

    def night_actions_ready(self) -> bool:
        return self.hand_ready() and self.required_night_actor_ids() <= set(self.pending_actions.keys())

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
            if actor.role != Role.WATCHMAN:
                raise IllegalActionError("Only the Watchman can protect")
            if target.id == actor.id and self._watchman_self_heal_used:
                raise IllegalActionError("The Watchman has already used their one self-heal")
            if target.id == self._watchman_last_target:
                raise IllegalActionError("The Watchman cannot protect the same person two nights in a row")
        elif action_type == ActionType.KILL:
            if actor.role != Role.HAND:
                raise IllegalActionError("Only the Black Hand can submit a kill")
            # Shared team choice: any living Hand can set or change it.
            self.hand_kill_target = target_id
            self.hand_kill_actor = actor_id
        elif action_type == ActionType.INVESTIGATE:
            if actor.role != Role.INSPECTOR:
                raise IllegalActionError("Only the Inspector can investigate")

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
        watchman_action = next(
            (a for a in self.pending_actions.values() if a.action_type == ActionType.PROTECT), None
        )
        if watchman_action:
            if watchman_action.target_id == watchman_action.actor_id:
                self._watchman_self_heal_used = True
            self._watchman_last_target = watchman_action.target_id
            watchman = self.player(watchman_action.actor_id)
            target = self.player(watchman_action.target_id)
            lines.append(f"{watchman.name} the Watchman protected {target.name}.")
        else:
            self._watchman_last_target = None

        # 3. Kills (single shared Black Hand choice)
        if self.hand_kill_target:
            victim = self.player(self.hand_kill_target)
            chooser = self.player(self.hand_kill_actor) if self.hand_kill_actor else None
            if chooser:
                lines.append(f"{chooser.name} the Black Hand chose to kill {victim.name}.")
            if victim.id in protected_ids:
                self.events.append(f"The Watchman saved {victim.name} last night.")
                lines.append(f"{victim.name} was attacked but saved by the Watchman.")
            else:
                victim.alive = False
                self.events.append(f"{victim.name} was killed during the night.")
                lines.append(f"{victim.name} was killed.")
        else:
            self.events.append("Nothing happened last night.")
            lines.append("The Black Hand did not choose a target.")

        # 4. Investigations
        for action in self.pending_actions.values():
            if action.action_type != ActionType.INVESTIGATE:
                continue
            inspector = self.player(action.actor_id)
            target = self.player(action.target_id)
            result = inspector_reads_as(target.role)
            self._log(action.actor_id, f"Investigation of {target.name}: {result.value.upper()}")
            lines.append(f"{inspector.name} the Inspector investigated {target.name}: {result.value.upper()}.")

        # 5. Death triggers -- no v1 role has one; reserved stage.

        # 6. Win condition check happens below.

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
        if target_id != SKIP_VOTE and not self.player(target_id).alive:
            raise IllegalActionError("Cannot vote for a dead player")
        self.votes[voter_id] = target_id

    def public_votes(self) -> Dict[str, str]:
        return dict(self.votes)

    def votes_complete(self) -> bool:
        """Voting ends as soon as every living player has voted (for someone
        or to skip), the same way night ends once every active role has
        acted -- no need to wait out the full timer if nobody is undecided."""
        return {p.id for p in self.alive_players()} <= set(self.votes.keys())

    def resolve_lynch(self) -> None:
        if self.phase != Phase.VOTING:
            raise IllegalActionError("Not the voting phase")

        lines: List[str] = []
        tally: Dict[str, int] = {}
        for target_id in self.votes.values():
            if target_id == SKIP_VOTE:
                continue
            tally[target_id] = tally.get(target_id, 0) + 1

        if tally:
            top = max(tally.values())
            leaders = [t for t, c in tally.items() if c == top]
            if len(leaders) == 1:
                victim = self.player(leaders[0])
                victim.alive = False
                self.events.append(f"{victim.name} was voted out.")
                caught = " They were a Hand." if faction_of(victim.role) == Faction.HAND else " They were not a Hand."
                lines.append(f"{victim.name} was voted out ({top} votes).{caught}")
            else:
                self.events.append("The vote was tied -- no one was voted out.")
                lines.append("The vote was tied. No one was voted out.")
        else:
            self.events.append("No votes were cast -- no one was voted out.")
            lines.append("No votes were cast. No one was voted out.")

        # Death triggers -- reserved stage, no-op in v1.

        self.round_log.append({"title": f"Day {self.night_number} Vote", "lines": lines})

        if self._check_win():
            return
        self._begin_night()

    # -- win -----------------------------------------------------------------

    def _check_win(self) -> bool:
        hand_alive = [p for p in self.alive_players() if faction_of(p.role) == Faction.HAND]
        table_alive = [p for p in self.alive_players() if faction_of(p.role) == Faction.TABLE]
        if not hand_alive:
            self.winner = Faction.TABLE
        elif len(hand_alive) >= len(table_alive):
            self.winner = Faction.HAND
        else:
            return False
        self.phase = Phase.GAME_OVER
        self.events.append("The Table wins!" if self.winner == Faction.TABLE else "The Black Hand wins!")
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
        if me.role == Role.HAND:
            base["allies"] = [p.name for p in self.hand_team() if p.id != me.id]
            base["hand_kill_target_id"] = self.hand_kill_target
            base["hand_kill_target_name"] = (
                self.player(self.hand_kill_target).name if self.hand_kill_target else None
            )
        if self.phase == Phase.NIGHT:
            required = self.required_night_actor_ids()
            hand_alive_exists = any(p.role is Role.HAND for p in self.alive_players())
            base["night_actions_total"] = len(required) + (1 if hand_alive_exists else 0)
            base["night_actions_done"] = len(required & set(self.pending_actions.keys())) + (
                1 if hand_alive_exists and self.hand_kill_target else 0
            )
        if self.phase == Phase.VOTING:
            base["votes_total"] = len(self.alive_players())
            base["votes_done"] = len(self.votes)
        if not me.alive or self.phase == Phase.GAME_OVER:
            base["round_log"] = list(self.round_log)
        if self.phase == Phase.GAME_OVER:
            base["hand_reveal"] = [p.name for p in self.players if faction_of(p.role) == Faction.HAND]
        return base
