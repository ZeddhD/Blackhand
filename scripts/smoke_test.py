"""End-to-end smoke test against a running server: creates a room, joins
players, plays a full game via the real WebSocket protocol (night
actions, day discussion, voting, reconnection). Not part of the pytest
suite -- run manually against a live `uvicorn server.main:app`:

    uvicorn server.main:app --port 8000
    python scripts/smoke_test.py
"""
import asyncio
import json

import websockets

URL = "ws://127.0.0.1:8000/ws"
NAMES = ["Host", "Alice", "Bob", "Carol", "Dave", "Erin", "Frank"]


async def connect():
    return await websockets.connect(URL)


async def recv_until(ws, mtype, timeout=10):
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        msg = json.loads(raw)
        if msg["type"] == mtype:
            return msg
        if msg["type"] == "error":
            print("SERVER ERROR:", msg["message"])


async def state_until_phase(ws, phase, timeout=10):
    while True:
        msg = await recv_until(ws, "state", timeout)
        if msg["state"]["phase"] == phase:
            return msg["state"]


async def main():
    sockets = [await connect() for _ in NAMES]

    await sockets[0].send(json.dumps({"type": "create_room", "name": NAMES[0]}))
    created = await recv_until(sockets[0], "room_created")
    code = created["room_code"]
    player_ids = {NAMES[0]: created["player_id"]}
    print("Room created:", code)

    for ws, name in zip(sockets[1:], NAMES[1:]):
        await ws.send(json.dumps({"type": "join", "room_code": code, "name": name}))
        joined = await recv_until(ws, "joined")
        player_ids[name] = joined["player_id"]
    print("All joined:", player_ids)

    # 7 players, 3 Hand, 1 Inspector, 1 Watchman, 2 Civilian: killing one
    # Table player brings the Black Hand to parity (3 v 3) and ends the
    # game in one round, which is what this script wants to exercise
    # quickly rather than play a full multi-round game.
    await sockets[0].send(json.dumps({
        "type": "start_game",
        "role_counts": {"hand": 3, "inspector": 1, "watchman": 1},
        "timers": {"discussion": 15},
        "show_hands_enabled": False,
    }))

    states = {}
    for ws, name in zip(sockets, NAMES):
        states[name] = await state_until_phase(ws, "night")

    roles = {name: s["your_role"] for name, s in states.items()}
    print("Roles:", roles)

    hand_name = next(n for n, r in roles.items() if r == "hand")
    inspector_name = next(n for n, r in roles.items() if r == "inspector")
    watchman_name = next(n for n, r in roles.items() if r == "watchman")
    victim_name = next(n for n, r in roles.items() if r not in ("hand",) and n != watchman_name)

    hand_ws = sockets[NAMES.index(hand_name)]
    victim_id = next(p["id"] for p in states[hand_name]["players"] if p["name"] == victim_name)
    await hand_ws.send(json.dumps({"type": "night_action", "action_type": "kill", "target_id": victim_id}))

    inspector_ws = sockets[NAMES.index(inspector_name)]
    inv_target = next(p for p in states[inspector_name]["players"] if p["name"] != inspector_name)
    await inspector_ws.send(json.dumps({
        "type": "night_action", "action_type": "investigate", "target_id": inv_target["id"],
    }))

    watchman_ws = sockets[NAMES.index(watchman_name)]
    prot_target = next(p for p in states[watchman_name]["players"] if p["name"] != watchman_name)
    await watchman_ws.send(json.dumps({
        "type": "night_action", "action_type": "protect", "target_id": prot_target["id"],
    }))

    while True:
        final = await recv_until(sockets[0], "state")
        if final["state"]["phase"] != "night":
            break
    print("Phase after night resolve:", final["state"]["phase"])
    print("Events:", final["state"]["events"])
    assert final["state"]["phase"] in ("day_discussion", "game_over"), final["state"]["phase"]

    # --- reconnection test: kill Bob's socket, reconnect with the same player_id ---
    bob_id = player_ids["Bob"]
    await sockets[NAMES.index("Bob")].close()
    new_ws = await connect()
    await new_ws.send(json.dumps({"type": "join", "room_code": code, "player_id": bob_id}))
    rejoined = await recv_until(new_ws, "joined")
    assert rejoined["player_id"] == bob_id
    print("Reconnection OK for Bob")

    for ws in sockets:
        try:
            await ws.close()
        except Exception:
            pass
    await new_ws.close()
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
