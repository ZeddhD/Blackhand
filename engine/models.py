"""Core data types for the Blackhand game engine. No web framework imports."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Role(Enum):
    CIVILIAN = "civilian"
    INSPECTOR = "inspector"
    WATCHMAN = "watchman"
    HAND = "hand"


class Faction(Enum):
    TABLE = "table"
    HAND = "hand"


# Roles that count as Black Hand for parity / win-condition checks.
HAND_ROLES = {Role.HAND}


def faction_of(role: Role) -> Faction:
    return Faction.HAND if role in HAND_ROLES else Faction.TABLE


class InvestigationResult(Enum):
    INNOCENT = "innocent"
    GUILTY = "guilty"
    BLOCKED = "blocked"  # roleblocked Inspector; reserved for a future Roleblocker role


class Phase(Enum):
    LOBBY = "lobby"
    ASSIGN_ROLES = "assign_roles"
    SHOW_HANDS = "show_hands"
    NIGHT = "night"
    OFFER = "offer"
    RESOLVE_NIGHT = "resolve_night"
    DAY_DISCUSSION = "day_discussion"
    VOTING = "voting"
    RESOLVE_LYNCH = "resolve_lynch"
    GAME_OVER = "game_over"


@dataclass
class Player:
    id: str
    name: str
    role: Optional[Role] = None
    alive: bool = True
    marked: bool = False  # accepted a Black Hand recruitment offer

    def to_public_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "alive": self.alive}


def effective_faction(player: Player) -> Faction:
    """A Marked player counts as Black Hand for every parity, win, and
    investigation check from the moment they accept, even though their
    literal role never changes (section 2.3)."""
    if player.role is Role.HAND or player.marked:
        return Faction.HAND
    return Faction.TABLE


def inspector_reads_as(player: Player) -> InvestigationResult:
    return InvestigationResult.GUILTY if effective_faction(player) == Faction.HAND else InvestigationResult.INNOCENT


@dataclass
class GameConfig:
    role_counts: Dict[Role, int] = field(default_factory=dict)
    show_hands_enabled: bool = True
    show_hands_threshold: int = 6  # Show Your Hands becomes available at or below this many living players

    def hand_count(self) -> int:
        return sum(count for role, count in self.role_counts.items() if role in HAND_ROLES)

    def validate(self, player_count: int) -> List[str]:
        errors: List[str] = []
        if player_count < 6:
            errors.append("Blackhand needs at least 6 players")
        if player_count > 12:
            errors.append("Blackhand supports at most 12 players")
        assigned = sum(self.role_counts.values())
        if assigned > player_count:
            errors.append(f"{assigned} roles assigned for {player_count} players")
        if self.hand_count() == 0:
            errors.append("The game needs at least one Hand")
        elif self.hand_count() * 2 >= player_count:
            errors.append("The Black Hand already holds the table")
        return errors

    def build_role_list(self, player_count: int) -> List[Role]:
        """Full shuffled role list for `player_count` players."""
        roles: List[Role] = []
        for role, count in self.role_counts.items():
            roles.extend([role] * count)
        roles.extend([Role.CIVILIAN] * (player_count - len(roles)))
        random.shuffle(roles)
        return roles
