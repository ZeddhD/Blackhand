from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ActionType(Enum):
    PROTECT = "protect"          # Watchman
    KILL = "kill"                 # Black Hand
    OFFER = "offer"               # Black Hand, instead of a kill
    INVESTIGATE = "investigate"   # Inspector


@dataclass
class NightAction:
    actor_id: str
    action_type: ActionType
    target_id: str
