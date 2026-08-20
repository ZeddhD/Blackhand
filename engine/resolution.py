"""Night-resolution stages that run after the Black Hand's Kill-or-Offer
choice: investigations, and the Offer's own accept/refuse/timeout outcome.

Split out from game.py because Recruitment can defer investigations behind
the Offer's response -- a kill resolves everything in one call, but an
offer pauses at Phase.OFFER until the recipient answers or times out, and
investigations must not run until that answer is known (section 2.7: the
Offer resolves at pipeline stage 4, Investigations at stage 5).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List

from .actions import ActionType
from .models import inspector_reads_as

if TYPE_CHECKING:
    from .game import Game


def resolve_investigations(game: "Game", lines: List[str]) -> None:
    for action in game.pending_actions.values():
        if action.action_type != ActionType.INVESTIGATE:
            continue
        inspector = game.player(action.actor_id)
        target = game.player(action.target_id)
        result = inspector_reads_as(target)
        game._log(action.actor_id, f"Investigation of {target.name}: {result.value.upper()}")
        lines.append(f"{inspector.name} the Inspector investigated {target.name}: {result.value.upper()}.")


def resolve_offer_response(game: "Game", accepted: bool, lines: List[str]) -> None:
    """Stage 4: the Offer resolves. Never touches protection -- protection
    neither blocks recruitment nor saves a refuser (section 2.3)."""
    recipient = game.player(game._offer_recipient_id)

    if accepted:
        recipient.marked = True
        game.events.append("Nobody was killed last night.")
        lines.append(f"{recipient.name} accepted the hand. They are now Black Hand.")
    else:
        recipient.alive = False
        game.events.append(f"{recipient.name} was killed during the night.")
        lines.append(f"{recipient.name} refused or did not answer the hand, and was killed.")
