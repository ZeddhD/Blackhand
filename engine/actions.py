from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ActionType(Enum):
    PROTECT = "protect"       # Doctor
    KILL = "kill"              # Mafia
    INVESTIGATE = "investigate"  # Detective


@dataclass
class NightAction:
    actor_id: str
    action_type: ActionType
    target_id: str
