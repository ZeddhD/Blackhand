"""Core data types for the Mafia game engine. No web framework imports."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Role(Enum):
    VILLAGER = "villager"
    DETECTIVE = "detective"
    DOCTOR = "doctor"
    MAFIA = "mafia"
    GODFATHER = "godfather"


class Team(Enum):
    TOWN = "town"
    MAFIA = "mafia"


# Roles that count as evil for parity / win-condition checks.
# The Godfather counts as evil even before promotion (spec section 4).
EVIL_ROLES = {Role.MAFIA, Role.GODFATHER}


def role_team(role: Role) -> Team:
    return Team.MAFIA if role in EVIL_ROLES else Team.TOWN


class InvestigationResult(Enum):
    INNOCENT = "innocent"
    GUILTY = "guilty"
    BLOCKED = "blocked"  # roleblocked detective; reserved for future roleblocker roles


def detective_reads_as(role: Role) -> InvestigationResult:
    """The Godfather reads INNOCENT to the Detective (spec section 4) -- non-negotiable."""
    if role == Role.GODFATHER:
        return InvestigationResult.INNOCENT
    if role == Role.MAFIA:
        return InvestigationResult.GUILTY
    return InvestigationResult.INNOCENT


class Phase(Enum):
    LOBBY = "lobby"
    ASSIGN_ROLES = "assign_roles"
    NIGHT = "night"
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

    def to_public_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "alive": self.alive}


@dataclass
class GameConfig:
    role_counts: Dict[Role, int] = field(default_factory=dict)

    def evil_count(self) -> int:
        return sum(
            count for role, count in self.role_counts.items() if role in EVIL_ROLES
        )

    def validate(self, player_count: int) -> List[str]:
        errors: List[str] = []
        assigned = sum(self.role_counts.values())
        if assigned > player_count:
            errors.append(f"{assigned} roles for {player_count} players")
        if not self.evil_count():
            errors.append("Need at least one evil role")
        elif self.evil_count() * 2 >= player_count:
            errors.append("Evil team starts at parity - game already over")
        return errors

    def build_role_list(self, player_count: int) -> List[Role]:
        """Full shuffled role list for `player_count` players (spec section 7)."""
        roles: List[Role] = []
        for role, count in self.role_counts.items():
            roles.extend([role] * count)
        roles.extend([Role.VILLAGER] * (player_count - len(roles)))
        random.shuffle(roles)
        return roles
