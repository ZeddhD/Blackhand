from __future__ import annotations

import asyncio
import os
import re
import uuid

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from engine import ActionType, GameConfig, Phase, Role
from engine.game import IllegalActionError
from .rooms import (
    MAX_PHASE_SECONDS,
    MIN_PHASE_SECONDS,
    ROLE_BY_NAME,
    Room,
    RoomManager,
    broadcast_mafia_chat,
    broadcast_state,
    cancel_disconnect_removal,
    reap_idle_rooms,
    run_room,
    sanitize_name,
    schedule_disconnect_removal,
    touch,
)

app = FastAPI()
manager = RoomManager()
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")


@app.on_event("startup")
async def _start_room_reaper() -> None:
    asyncio.create_task(reap_idle_rooms(manager))


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


async def _send_error(ws: WebSocket, message: str) -> None:
    try:
        await ws.send_json({"type": "error", "message": message})
    except Exception:
        pass


async def _attach(room: Room, player_id: str, ws: WebSocket) -> None:
    room.connections[player_id] = ws
    room.connected[player_id] = True
    cancel_disconnect_removal(room, player_id)


def _detach(room: Room, player_id: str) -> None:
    if room.connections.get(player_id) is not None:
        room.connections.pop(player_id, None)
    room.connected[player_id] = False
    schedule_disconnect_removal(room, player_id)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    room: Room | None = None
    player_id: str | None = None

    try:
        while True:
            msg = await websocket.receive_json()
            mtype = msg.get("type")
            if room is not None:
                touch(room)

            if mtype == "create_room":
                room = manager.create_room()
                player_id = str(uuid.uuid4())
                room.game.add_player(player_id, sanitize_name(msg.get("name"), "Host"))
                room.host_id = player_id
                await _attach(room, player_id, websocket)
                await websocket.send_json(
                    {"type": "room_created", "room_code": room.code, "player_id": player_id}
                )
                await broadcast_state(room)

            elif mtype == "join":
                code = (msg.get("room_code") or "").upper()
                target = manager.get(code)
                if target is None:
                    await _send_error(websocket, f"No room with code {code}")
                    continue
                reconnect_id = msg.get("player_id")
                if reconnect_id and any(p.id == reconnect_id for p in target.game.players):
                    room = target
                    player_id = reconnect_id
                    await _attach(room, player_id, websocket)
                    await websocket.send_json(
                        {"type": "joined", "room_code": room.code, "player_id": player_id}
                    )
                    await broadcast_state(room)
                    await broadcast_mafia_chat(room)
                    continue
                if target.game.phase != Phase.LOBBY:
                    await _send_error(websocket, "Game already in progress")
                    continue
                room = target
                player_id = str(uuid.uuid4())
                room.game.add_player(player_id, sanitize_name(msg.get("name"), "Player"))
                await _attach(room, player_id, websocket)
                await websocket.send_json(
                    {"type": "joined", "room_code": room.code, "player_id": player_id}
                )
                await broadcast_state(room)

            elif mtype == "start_game":
                if room is None or player_id != room.host_id:
                    await _send_error(websocket, "Only the host can start the game")
                    continue
                role_counts = {
                    ROLE_BY_NAME[name]: count
                    for name, count in (msg.get("role_counts") or {}).items()
                    if name in ROLE_BY_NAME and count
                }

                show_hands_enabled = bool(msg.get("show_hands_enabled", True))
                try:
                    show_hands_threshold = int(msg.get("show_hands_threshold", 6))
                except (TypeError, ValueError):
                    show_hands_threshold = 6
                # Section 7.1: Show Your Hands threshold is configurable 5 to 7.
                show_hands_threshold = max(5, min(7, show_hands_threshold))

                room.game.config = GameConfig(
                    role_counts=role_counts,
                    show_hands_enabled=show_hands_enabled,
                    show_hands_threshold=show_hands_threshold,
                )
                timers = msg.get("timers") or {}

                def _clamp_seconds(value, fallback):
                    try:
                        value = int(value)
                    except (TypeError, ValueError):
                        return fallback
                    return max(MIN_PHASE_SECONDS, min(MAX_PHASE_SECONDS, value))

                room.discussion_seconds = _clamp_seconds(timers.get("discussion"), room.discussion_seconds)
                room.voting_seconds = _clamp_seconds(timers.get("voting"), room.voting_seconds)
                try:
                    room.game.start_game()
                except IllegalActionError as e:
                    await _send_error(websocket, str(e))
                    continue
                await broadcast_state(room)
                room.runner_task = asyncio.create_task(run_room(room))

            elif mtype == "night_action":
                if room is None or player_id is None:
                    continue
                try:
                    action_type = ActionType(msg.get("action_type"))
                    room.game.submit_night_action(player_id, action_type, msg.get("target_id"))
                except (IllegalActionError, ValueError, KeyError) as e:
                    await _send_error(websocket, str(e))
                    continue
                await broadcast_state(room)
                if room.game.night_actions_ready():
                    room.night_ready_event.set()

            elif mtype == "leave_room":
                if room is None or player_id is None:
                    continue
                try:
                    room.game.remove_player(player_id)
                except IllegalActionError as e:
                    await _send_error(websocket, str(e))
                    continue
                # A voluntary leave, not a dropped connection -- clean up
                # directly rather than going through _detach, which would
                # schedule a pointless reconnect-grace removal for someone
                # who is already gone from the game.
                room.connections.pop(player_id, None)
                room.connected.pop(player_id, None)
                cancel_disconnect_removal(room, player_id)
                room.reassign_host_if_needed()
                left_room, left_player = room, player_id
                room, player_id = None, None
                await websocket.send_json({"type": "left"})
                await broadcast_state(left_room)

            elif mtype == "return_to_lobby":
                if room is None or player_id is None:
                    continue
                try:
                    room.game.return_to_lobby()
                except IllegalActionError as e:
                    await _send_error(websocket, str(e))
                    continue
                room.mafia_chat.clear()
                await broadcast_state(room)

            elif mtype == "vote":
                if room is None or player_id is None:
                    continue
                try:
                    room.game.submit_vote(player_id, msg.get("target_id"))
                except (IllegalActionError, KeyError) as e:
                    await _send_error(websocket, str(e))
                    continue
                await broadcast_state(room)
                if room.game.votes_complete():
                    room.early_end_event.set()

            elif mtype == "offer_response":
                if room is None or player_id is None:
                    continue
                try:
                    room.game.respond_to_offer(player_id, bool(msg.get("accepted")))
                except IllegalActionError as e:
                    await _send_error(websocket, str(e))
                    continue
                await broadcast_state(room)
                room.early_end_event.set()

            elif mtype == "show_hands_vote":
                if room is None or player_id is None:
                    continue
                try:
                    room.game.submit_show_hands_vote(player_id, msg.get("choice"))
                except IllegalActionError as e:
                    await _send_error(websocket, str(e))
                    continue
                await broadcast_state(room)
                if room.game.show_hands_votes_complete():
                    room.early_end_event.set()

            elif mtype == "mafia_chat":
                if room is None or player_id is None:
                    continue
                if room.game.phase == Phase.SHOW_HANDS:
                    await _send_error(websocket, "The channel is disabled during Show Your Hands")
                    continue
                if player_id not in room.mafia_channel_ids():
                    await _send_error(websocket, "You are not in the mafia channel")
                    continue
                text = (msg.get("text") or "").strip()[:500]
                if not text:
                    continue
                sender = room.game.player(player_id)
                from .rooms import ChatMessage

                room.mafia_chat.append(ChatMessage(player_id=player_id, name=sender.name, text=text))
                await broadcast_mafia_chat(room)

            else:
                await _send_error(websocket, f"Unknown message type: {mtype}")

    except WebSocketDisconnect:
        if room is not None and player_id is not None:
            _detach(room, player_id)


# Serve the built React frontend as static files (single-service deploy).
# A room code URL like /ABCD has no matching static file, so it needs an
# explicit fallback to index.html for the client-side router to pick up.
if os.path.isdir(FRONTEND_DIST):

    @app.get("/{code}")
    async def room_code_fallback(code: str):
        # This single-segment catch-all is registered before the
        # StaticFiles mount below, so without this check it swallows any
        # root-level static file whose name isn't a 4-letter room code
        # (favicon.svg, robots.txt, etc.) before the mount ever sees it,
        # 404ing instead of serving the real file.
        static_path = os.path.join(FRONTEND_DIST, code)
        if os.path.isfile(static_path):
            return FileResponse(static_path)
        if re.fullmatch(r"[A-Za-z]{4}", code):
            return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
        raise HTTPException(status_code=404)

    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
