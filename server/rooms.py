"""Room/session layer: wraps the pure engine with connections, timers, and
reconnection. No game rules live here -- see engine/game.py."""
from __future__ import annotations

import asyncio
import random
import string
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fastapi import WebSocket

from engine import ActionType, Game, GameConfig, Phase, Role

DEFAULT_DISCUSSION_SECONDS = 60
DEFAULT_VOTING_SECONDS = 60
MIN_PHASE_SECONDS = 15
MAX_PHASE_SECONDS = 600

ROLE_BY_NAME = {r.value: r for r in Role}


@dataclass
class ChatMessage:
    player_id: str
    name: str
    text: str
    ts: float = field(default_factory=time.time)


@dataclass
class Room:
    code: str
    game: Game
    host_id: Optional[str] = None
    connections: Dict[str, WebSocket] = field(default_factory=dict)
    connected: Dict[str, bool] = field(default_factory=dict)
    mafia_chat: List[ChatMessage] = field(default_factory=list)
    early_end_event: asyncio.Event = field(default_factory=asyncio.Event)
    night_ready_event: asyncio.Event = field(default_factory=asyncio.Event)
    runner_task: Optional[asyncio.Task] = None
    seconds_left: int = 0
    discussion_seconds: int = DEFAULT_DISCUSSION_SECONDS
    voting_seconds: int = DEFAULT_VOTING_SECONDS

    def reassign_host_if_needed(self) -> None:
        if self.host_id is not None and any(p.id == self.host_id for p in self.game.players):
            return
        self.host_id = self.game.players[0].id if self.game.players else None

    def mafia_channel_ids(self) -> set:
        # mafia_team() reflects promotion automatically: once the engine
        # promotes the Godfather to Role.MAFIA, he's included here too.
        return {p.id for p in self.game.mafia_team()}


class RoomManager:
    def __init__(self) -> None:
        self.rooms: Dict[str, Room] = {}

    def _new_code(self) -> str:
        while True:
            code = "".join(random.choices(string.ascii_uppercase, k=4))
            if code not in self.rooms:
                return code

    def create_room(self) -> Room:
        code = self._new_code()
        room = Room(code=code, game=Game(room_code=code))
        self.rooms[code] = room
        return room

    def get(self, code: str) -> Optional[Room]:
        return self.rooms.get(code.upper())


async def broadcast_state(room: Room) -> None:
    for player in room.game.players:
        ws = room.connections.get(player.id)
        if ws is None:
            continue
        try:
            view = room.game.view_for(player.id)
            view["is_host"] = player.id == room.host_id
            await ws.send_json({"type": "state", "state": view})
        except Exception:
            pass


async def broadcast_timer(room: Room, seconds_left: int, total_seconds: int) -> None:
    room.seconds_left = seconds_left
    payload = {
        "type": "timer",
        "phase": room.game.phase.value,
        "seconds_left": seconds_left,
        "total_seconds": total_seconds,
    }
    for ws in list(room.connections.values()):
        try:
            await ws.send_json(payload)
        except Exception:
            pass


async def broadcast_mafia_chat(room: Room) -> None:
    payload = {
        "type": "mafia_chat",
        "messages": [
            {"player_id": m.player_id, "name": m.name, "text": m.text, "ts": m.ts}
            for m in room.mafia_chat
        ],
    }
    for pid in room.mafia_channel_ids():
        ws = room.connections.get(pid)
        if ws is None:
            continue
        try:
            await ws.send_json(payload)
        except Exception:
            pass


async def _countdown(room: Room, seconds: int) -> None:
    """Counts down, but ends early if room.early_end_event is set -- used by
    Voting once every living player has voted (see votes_complete)."""
    room.early_end_event.clear()
    for remaining in range(seconds, 0, -1):
        await broadcast_timer(room, remaining, seconds)
        try:
            await asyncio.wait_for(room.early_end_event.wait(), timeout=1.0)
            break  # ended early
        except asyncio.TimeoutError:
            continue
    room.early_end_event.clear()


async def _wait_for_night(room: Room) -> None:
    """Night has no fixed duration -- it ends once every living player whose
    role has a night action has submitted one."""
    room.early_end_event.clear()
    room.night_ready_event.clear()
    if room.game.night_actions_ready():
        return
    ready = asyncio.ensure_future(room.night_ready_event.wait())
    try:
        await asyncio.wait({ready}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        if not ready.done():
            ready.cancel()
        room.night_ready_event.clear()


async def run_room(room: Room) -> None:
    """Drives the state machine: NIGHT -> RESOLVE -> DAY -> VOTING -> RESOLVE -> ...

    Phase transitions are the only thing that mutates game state (spec section 5);
    this loop is the sole place that calls the resolving transitions.
    """
    game = room.game
    try:
        while game.phase != Phase.GAME_OVER:
            if game.phase == Phase.NIGHT:
                await _wait_for_night(room)
                game.resolve_night()
                await broadcast_state(room)
                if game.phase == Phase.GAME_OVER:
                    break
            if game.phase == Phase.DAY_DISCUSSION:
                await _countdown(room, room.discussion_seconds)
                game.begin_voting()
                await broadcast_state(room)
            if game.phase == Phase.VOTING:
                await _countdown(room, room.voting_seconds)
                game.resolve_lynch()
                await broadcast_state(room)
    except asyncio.CancelledError:
        pass
    except Exception:
        import traceback

        traceback.print_exc()
