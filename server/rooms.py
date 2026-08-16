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

NIGHT_SECONDS = 75
DISCUSSION_SECONDS = 60
VOTING_SECONDS = 60

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
    skip_event: asyncio.Event = field(default_factory=asyncio.Event)
    runner_task: Optional[asyncio.Task] = None
    seconds_left: int = 0

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


async def broadcast_timer(room: Room, seconds_left: int) -> None:
    room.seconds_left = seconds_left
    payload = {"type": "timer", "phase": room.game.phase.value, "seconds_left": seconds_left}
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
    room.skip_event.clear()
    for remaining in range(seconds, 0, -1):
        await broadcast_timer(room, remaining)
        try:
            await asyncio.wait_for(room.skip_event.wait(), timeout=1.0)
            break  # host force-advanced
        except asyncio.TimeoutError:
            continue
    room.skip_event.clear()


async def run_room(room: Room) -> None:
    """Drives the state machine: NIGHT -> RESOLVE -> DAY -> VOTING -> RESOLVE -> ...

    Phase transitions are the only thing that mutates game state (spec section 5);
    this loop is the sole place that calls the resolving transitions.
    """
    game = room.game
    try:
        while game.phase != Phase.GAME_OVER:
            if game.phase == Phase.NIGHT:
                await _countdown(room, NIGHT_SECONDS)
                game.resolve_night()
                await broadcast_state(room)
                if game.phase == Phase.GAME_OVER:
                    break
            if game.phase == Phase.DAY_DISCUSSION:
                await _countdown(room, DISCUSSION_SECONDS)
                game.begin_voting()
                await broadcast_state(room)
            if game.phase == Phase.VOTING:
                await _countdown(room, VOTING_SECONDS)
                game.resolve_lynch()
                await broadcast_state(room)
    except asyncio.CancelledError:
        pass
