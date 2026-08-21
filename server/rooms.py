"""Room/session layer: wraps the pure engine with connections, timers, and
reconnection. No game rules live here -- see engine/game.py."""
from __future__ import annotations

import asyncio
import json
import random
import string
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fastapi import WebSocket

from engine import Game, Phase, Role

DEFAULT_DISCUSSION_SECONDS = 60
# Section 6.8: The Table runs "45 seconds or all voted," a fixed number,
# not one of section 7.1's configurable settings. The lobby no longer
# offers a control for it (Phase 14); this default is what actually
# takes effect now that nothing overrides it in ordinary play.
DEFAULT_VOTING_SECONDS = 45
MIN_PHASE_SECONDS = 15
MAX_PHASE_SECONDS = 600

# Fixed durations, not host-configurable -- the document lists Show Your
# Hands' threshold as configurable (section 7.1) but never its duration,
# and the Offer's 30s is stated as part of the mechanic itself (section 2.3).
SHOW_HANDS_SECONDS = 15
OFFER_SECONDS = 30

# A dropped connection isn't necessarily gone for good -- phones lock,
# wifi blips. Give it a grace period to reconnect before treating it as a
# real departure.
DISCONNECT_GRACE_SECONDS = 30

# Rooms nobody is connected to and nothing has happened in for this long
# are swept up so the server doesn't hold every room ever created forever.
ROOM_IDLE_LIMIT_SECONDS = 2 * 60 * 60
REAP_INTERVAL_SECONDS = 5 * 60

MAX_NAME_LENGTH = 24

ROLE_BY_NAME = {r.value: r for r in Role}


def sanitize_name(raw: Optional[str], fallback: str) -> str:
    name = (raw or "").strip()[:MAX_NAME_LENGTH]
    return name or fallback


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
    disconnect_tasks: Dict[str, asyncio.Task] = field(default_factory=dict)
    last_activity: float = field(default_factory=time.time)
    seconds_left: int = 0
    discussion_seconds: int = DEFAULT_DISCUSSION_SECONDS
    voting_seconds: int = DEFAULT_VOTING_SECONDS

    def reassign_host_if_needed(self) -> None:
        if self.host_id is not None and any(p.id == self.host_id for p in self.game.players):
            return
        self.host_id = self.game.players[0].id if self.game.players else None

    def mafia_channel_ids(self) -> set:
        # "The channel is disabled during Show Your Hands" (section 2.4) --
        # nobody can read or send during this window, enforced by simply
        # returning no recipients at all rather than a separate check.
        if self.game.phase == Phase.SHOW_HANDS:
            return set()
        return {p.id for p in self.game.hand_team()}


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
    connected_map = {p.id: room.connected.get(p.id, False) for p in room.game.players}
    for player in room.game.players:
        ws = room.connections.get(player.id)
        if ws is None:
            continue
        try:
            view = room.game.view_for(player.id)
            view["is_host"] = player.id == room.host_id
            view["connected"] = connected_map
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


def _log_game_result(room: Room) -> None:
    """Anonymous per-game balance logging (Phase 15, section 3.3). No
    player names or ids, no persistent storage per the Phase 0 audit's
    confirmed decision: stdout only, read from Render's own log
    dashboard when anyone wants to check the Black Hand win rate against
    the 45-55% target."""
    game = room.game
    offer = game.offer_outcome
    payload = {
        "player_count": len(game.players),
        "config": {
            "role_counts": {role.value: count for role, count in game.config.role_counts.items()},
            "show_hands_enabled": game.config.show_hands_enabled,
            "show_hands_threshold": game.config.show_hands_threshold,
            "recruitment_enabled": game.config.recruitment_enabled,
            "discussion_seconds": room.discussion_seconds,
            "voting_seconds": room.voting_seconds,
        },
        "round_count": game.night_number,
        "winner": game.winner.value if game.winner else None,
        "offer_made": offer is not None,
        "offer_accepted": offer["accepted"] if offer else None,
        "show_hands_fired": game.show_hands_count > 0,
        "show_hands_occurrences": game.show_hands_count,
    }
    print(f"blackhand_game_result {json.dumps(payload)}", flush=True)


async def run_room(room: Room) -> None:
    """Drives the state machine: NIGHT -> RESOLVE -> DAY -> VOTING -> RESOLVE -> ...

    Phase transitions are the only thing that mutates game state (spec section 5);
    this loop is the sole place that calls the resolving transitions.
    """
    game = room.game
    try:
        while game.phase != Phase.GAME_OVER:
            if game.phase == Phase.SHOW_HANDS:
                await _countdown(room, SHOW_HANDS_SECONDS)
                game.resolve_show_hands()
                await broadcast_state(room)
                if game.phase == Phase.GAME_OVER:
                    break
            if game.phase == Phase.NIGHT:
                await _wait_for_night(room)
                game.resolve_night()
                await broadcast_state(room)
                if game.phase == Phase.GAME_OVER:
                    break
            if game.phase == Phase.OFFER:
                await _countdown(room, OFFER_SECONDS)
                # A response may have already resolved this (and possibly
                # ended the game) before the timer ran out -- only time it
                # out ourselves if it's still genuinely unanswered.
                if game.phase == Phase.OFFER:
                    game.resolve_offer_timeout()
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

    if game.phase == Phase.GAME_OVER:
        _log_game_result(room)


async def _disconnect_after_grace(room: Room, player_id: str) -> None:
    try:
        await asyncio.sleep(DISCONNECT_GRACE_SECONDS)
    except asyncio.CancelledError:
        return  # reconnected (or the removal was otherwise cancelled)
    if room.connected.get(player_id):
        return  # reconnected in the window between sleep and this check

    room.game.handle_disconnect_removal(player_id)
    room.connected.pop(player_id, None)
    room.connections.pop(player_id, None)
    room.disconnect_tasks.pop(player_id, None)
    room.reassign_host_if_needed()
    await broadcast_state(room)

    # If this removal just satisfied night/voting completion, or ended the
    # game outright, wake whatever run_room is currently waiting on so it
    # notices right away instead of sitting until the timer expires.
    game = room.game
    if game.phase == Phase.GAME_OVER:
        room.night_ready_event.set()
        room.early_end_event.set()
    elif game.phase == Phase.NIGHT and game.night_actions_ready():
        room.night_ready_event.set()
    elif game.phase == Phase.VOTING and game.votes_complete():
        room.early_end_event.set()


def schedule_disconnect_removal(room: Room, player_id: str) -> None:
    existing = room.disconnect_tasks.get(player_id)
    if existing and not existing.done():
        existing.cancel()
    room.disconnect_tasks[player_id] = asyncio.create_task(_disconnect_after_grace(room, player_id))


def cancel_disconnect_removal(room: Room, player_id: str) -> None:
    task = room.disconnect_tasks.pop(player_id, None)
    if task and not task.done():
        task.cancel()


def touch(room: Room) -> None:
    room.last_activity = time.time()


async def reap_idle_rooms(manager: RoomManager) -> None:
    """Background sweep: drop rooms nobody is connected to and nothing has
    happened in for a long time, so long server uptime doesn't accumulate
    every room ever created in memory forever."""
    while True:
        await asyncio.sleep(REAP_INTERVAL_SECONDS)
        now = time.time()
        stale_codes = [
            code
            for code, room in manager.rooms.items()
            if not any(room.connected.values()) and now - room.last_activity > ROOM_IDLE_LIMIT_SECONDS
        ]
        for code in stale_codes:
            room = manager.rooms.pop(code, None)
            if room is None:
                continue
            if room.runner_task and not room.runner_task.done():
                room.runner_task.cancel()
            for task in room.disconnect_tasks.values():
                if not task.done():
                    task.cancel()
