"""Pure Python game engine. Zero web framework imports -- fully testable headless.

Decided ambiguities -- see README.md for rationale:
  - Watchman CAN self-heal, but only once per game.
  - Watchman cannot target the same player on consecutive nights.
  - A roleblocked Inspector gets an explicit "blocked" result (reserved for
    a future Roleblocker role; v1 has none, so this never fires yet).
  - The Inspector's result reflects the target's current effective faction
    (role, or Marked status) at the moment of investigation, not a
    snapshot from earlier in the game. This is what makes a stale clear
    decay: a target investigated and cleared before being recruited would
    read guilty if investigated again afterward.
  - The Black Hand's kill (or offer) is a single shared choice: any living
    Hand can set or change it, and it is visible live to the whole Black
    Hand. There is no way for two Hands to target two different people at
    once, so there is nothing to tie-break. Tied lynch votes -> no lynch.
  - Recruitment: protection neither blocks the offer nor saves a refuser.
    A protected refuser surviving would leak the mechanic (section 2.3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import resolution
from .actions import ActionType, NightAction
from .models import (
    Faction,
    GameConfig,
    Phase,
    Player,
    Role,
    effective_faction,
)


class IllegalActionError(Exception):
    pass


# Sentinel vote value meaning "I choose not to vote for anyone this round."
# Not a real player id, so it can never collide with one.
SKIP_VOTE = "skip"

# The exact public message for every night with no visible death: no
# target chosen, a kill blocked by the Watchman, or an accepted offer.
# These three causes must be indistinguishable to living players -- see
# section 2.3. Do not let any of them use a different string.
NO_VISIBLE_DEATH_MESSAGE = "Nobody was killed last night."

# Show Your Hands choices. Not real player ids, just sentinel values.
HOLD_VOTE = "hold"
CALL_IT_VOTE = "call_it"
MAX_SHOW_HANDS_OCCURRENCES = 3


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

    hand_action_mode: Optional[str] = None  # "kill" or "offer", chosen by any living Hand
    hand_target_id: Optional[str] = None
    hand_target_actor_id: Optional[str] = None
    recruitment_used: bool = False  # the Black Hand gets at most one offer per game, ever
    _offer_recipient_id: Optional[str] = None

    show_hands_votes: Dict[str, str] = field(default_factory=dict)
    show_hands_count: int = 0

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
        self.hand_action_mode = None
        self.hand_target_id = None
        self.hand_target_actor_id = None
        self.recruitment_used = False
        self._offer_recipient_id = None
        self.show_hands_votes.clear()
        self.show_hands_count = 0
        self._watchman_self_heal_used = False
        self._watchman_last_target = None
        for p in self.players:
            p.role = None
            p.alive = True
            p.marked = False

    def player(self, player_id: str) -> Player:
        for p in self.players:
            if p.id == player_id:
                return p
        raise KeyError(player_id)

    def alive_players(self) -> List[Player]:
        return [p for p in self.players if p.alive]

    def hand_team(self) -> List[Player]:
        """Players who chat and kill together as the Black Hand. Includes
        Marked players from the moment they accept an offer."""
        return [p for p in self.players if effective_faction(p) == Faction.HAND]

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
        self._begin_round()

    # -- round start / Show Your Hands ---------------------------------------

    def _show_hands_eligible(self) -> bool:
        return (
            self.config.show_hands_enabled
            and self.show_hands_count < MAX_SHOW_HANDS_OCCURRENCES
            and len(self.alive_players()) <= self.config.show_hands_threshold
        )

    def _begin_round(self) -> None:
        """Called at the start of every round, before the Dark. Opens Show
        Your Hands instead of Night if the room is small enough and it
        hasn't already fired three times this game (section 2.4)."""
        if self._show_hands_eligible():
            self.show_hands_count += 1
            self.show_hands_votes.clear()
            self.phase = Phase.SHOW_HANDS
            return
        self._begin_night()

    def submit_show_hands_vote(self, player_id: str, choice: str) -> None:
        if self.phase != Phase.SHOW_HANDS:
            raise IllegalActionError("Not in Show Your Hands")
        player = self.player(player_id)
        if not player.alive:
            raise IllegalActionError("Dead players cannot vote")
        if choice not in (HOLD_VOTE, CALL_IT_VOTE):
            raise IllegalActionError("Invalid Show Your Hands choice")
        self.show_hands_votes[player_id] = choice

    def show_hands_votes_complete(self) -> bool:
        return {p.id for p in self.alive_players()} <= set(self.show_hands_votes.keys())

    def resolve_show_hands(self) -> None:
        """Majority CALL IT ends the game immediately: the Table wins if
        every Hand is already dead, otherwise the Black Hand wins outright
        -- this bypasses the normal parity win check entirely. A tie or a
        HOLD majority just proceeds into the Dark. Results are counts
        only, never names (section 2.4)."""
        if self.phase != Phase.SHOW_HANDS:
            raise IllegalActionError("Not in Show Your Hands")

        hold = sum(1 for v in self.show_hands_votes.values() if v == HOLD_VOTE)
        call_it = sum(1 for v in self.show_hands_votes.values() if v == CALL_IT_VOTE)
        self.events.append(f"Show Your Hands: {hold} HOLD, {call_it} CALL IT")
        self.round_log.append(
            {
                "title": "Show Your Hands",
                "lines": [f"{hold} players chose HOLD, {call_it} chose CALL IT."],
            }
        )

        if call_it > hold:
            hand_alive = [p for p in self.alive_players() if effective_faction(p) == Faction.HAND]
            self.winner = Faction.TABLE if not hand_alive else Faction.HAND
            self.phase = Phase.GAME_OVER
            self.events.append("The Table wins!" if self.winner == Faction.TABLE else "The Black Hand wins!")
            return

        self._begin_night()

    # -- night -------------------------------------------------------------

    def _begin_night(self) -> None:
        self.phase = Phase.NIGHT
        self.night_number += 1
        self.pending_actions.clear()
        self.private_log.clear()
        self.hand_action_mode = None
        self.hand_target_id = None
        self.hand_target_actor_id = None
        self._offer_recipient_id = None

    INDIVIDUAL_NIGHT_ACTION_ROLES = (Role.WATCHMAN, Role.INSPECTOR)

    def required_night_actor_ids(self) -> set:
        """Living players who each individually owe a night action (Watchman,
        Inspector). The Black Hand's kill-or-offer is a single shared team
        choice, tracked separately -- see hand_ready()."""
        return {p.id for p in self.alive_players() if p.role in self.INDIVIDUAL_NIGHT_ACTION_ROLES}

    def hand_ready(self) -> bool:
        hand_alive = [p for p in self.alive_players() if effective_faction(p) == Faction.HAND]
        return not hand_alive or self.hand_target_id is not None

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
            if effective_faction(actor) != Faction.HAND:
                raise IllegalActionError("Only the Black Hand can submit a kill")
            # Shared team choice: any living Hand (including a Marked
            # recruit) can set or change it.
            self.hand_action_mode = "kill"
            self.hand_target_id = target_id
            self.hand_target_actor_id = actor_id
        elif action_type == ActionType.OFFER:
            if effective_faction(actor) != Faction.HAND:
                raise IllegalActionError("Only the Black Hand can make an offer")
            if self.recruitment_used:
                raise IllegalActionError("The Black Hand has already made its one offer this game")
            if effective_faction(target) == Faction.HAND:
                raise IllegalActionError("Cannot offer to a member of the Black Hand")
            self.hand_action_mode = "offer"
            self.hand_target_id = target_id
            self.hand_target_actor_id = actor_id
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

        # 3. Kills, or the Offer (the Black Hand chooses one)
        if self.hand_action_mode == "offer" and self.hand_target_id:
            # Recruitment consumes the Black Hand's one-per-game offer the
            # moment it's actually delivered, regardless of the outcome.
            self.recruitment_used = True
            self._offer_recipient_id = self.hand_target_id
            chooser = self.player(self.hand_target_actor_id) if self.hand_target_actor_id else None
            recipient = self.player(self.hand_target_id)
            if chooser:
                lines.append(f"{chooser.name} the Black Hand made an offer to {recipient.name}.")
            self.round_log.append({"title": f"Night {self.night_number}", "lines": lines})
            # Stages 4 (offer resolution) and 5 (investigations) wait for
            # the recipient's answer -- see respond_to_offer / resolve_offer_timeout.
            self.phase = Phase.OFFER
            return

        if self.hand_target_id:
            victim = self.player(self.hand_target_id)
            chooser = self.player(self.hand_target_actor_id) if self.hand_target_actor_id else None
            if chooser:
                lines.append(f"{chooser.name} the Black Hand chose to kill {victim.name}.")
            if victim.id in protected_ids:
                self.events.append(NO_VISIBLE_DEATH_MESSAGE)
                lines.append(f"{victim.name} was attacked but saved by the Watchman.")
            else:
                victim.alive = False
                self.events.append(f"{victim.name} was killed during the night.")
                lines.append(f"{victim.name} was killed.")
        else:
            self.events.append(NO_VISIBLE_DEATH_MESSAGE)
            lines.append("The Black Hand did not choose a target.")

        # 4. Offer resolution -- not applicable this night, see above.

        # 5. Investigations
        resolution.resolve_investigations(self, lines)

        # 6. Death triggers -- no v1 role has one; reserved stage.

        self.round_log.append({"title": f"Night {self.night_number}", "lines": lines})

        # 7. Win condition check
        if self._check_win():
            return
        self.phase = Phase.DAY_DISCUSSION

    def respond_to_offer(self, player_id: str, accepted: bool) -> None:
        """The recipient's answer to the Offer -- 'Take it' or 'Refuse'."""
        if self.phase != Phase.OFFER:
            raise IllegalActionError("There is no offer to respond to")
        if player_id != self._offer_recipient_id:
            raise IllegalActionError("This offer was not made to you")
        self._resolve_offer(accepted)

    def resolve_offer_timeout(self) -> None:
        """The recipient did not answer within the time limit. Mechanically
        identical to a refusal -- the Black Hand is never told which one
        happened (section 2.3)."""
        if self.phase != Phase.OFFER:
            raise IllegalActionError("There is no offer to time out")
        self._resolve_offer(accepted=False)

    def _resolve_offer(self, accepted: bool) -> None:
        lines: List[str] = []
        resolution.resolve_offer_response(self, accepted, lines)
        resolution.resolve_investigations(self, lines)
        self.round_log.append({"title": f"Night {self.night_number} Offer", "lines": lines})

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
                caught = (
                    " They were a Hand." if effective_faction(victim) == Faction.HAND else " They were not a Hand."
                )
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
        self._begin_round()

    # -- win -----------------------------------------------------------------

    def _check_win(self) -> bool:
        hand_alive = [p for p in self.alive_players() if effective_faction(p) == Faction.HAND]
        table_alive = [p for p in self.alive_players() if effective_faction(p) == Faction.TABLE]
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
            "marked": me.marked,
            "private_log": list(self.private_log.get(player_id, [])),
            "winner": self.winner.value if self.winner else None,
        }
        if effective_faction(me) == Faction.HAND:
            base["allies"] = [p.name for p in self.hand_team() if p.id != me.id]
            base["hand_action_mode"] = self.hand_action_mode
            base["hand_target_id"] = self.hand_target_id
            base["hand_target_name"] = self.player(self.hand_target_id).name if self.hand_target_id else None
            base["recruitment_used"] = self.recruitment_used
        if self.phase == Phase.NIGHT:
            required = self.required_night_actor_ids()
            hand_alive_exists = any(effective_faction(p) == Faction.HAND for p in self.alive_players())
            base["night_actions_total"] = len(required) + (1 if hand_alive_exists else 0)
            base["night_actions_done"] = len(required & set(self.pending_actions.keys())) + (
                1 if hand_alive_exists and self.hand_target_id else 0
            )
        if self.phase == Phase.OFFER and player_id == self._offer_recipient_id:
            base["offer_pending"] = True
        if self.phase == Phase.SHOW_HANDS:
            # Private ballot: each player only ever learns their own choice.
            # Final results are counts only, published as a public event
            # once resolve_show_hands runs -- never a per-player breakdown.
            base["show_hands_total"] = len(self.alive_players())
            base["show_hands_done"] = len(self.show_hands_votes)
            base["show_hands_your_vote"] = self.show_hands_votes.get(player_id)
        if self.phase == Phase.VOTING:
            base["votes_total"] = len(self.alive_players())
            base["votes_done"] = len(self.votes)
        if not me.alive or self.phase == Phase.GAME_OVER:
            base["round_log"] = list(self.round_log)
        if self.phase == Phase.GAME_OVER:
            base["hand_reveal"] = [p.name for p in self.players if effective_faction(p) == Faction.HAND]
        return base
