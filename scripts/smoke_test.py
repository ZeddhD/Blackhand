"""End-to-end smoke test against a running server: creates a room, joins
players, plays a full game via the real WebSocket protocol, and exercises
reconnection. Not part of the pytest suite -- run manually against a live
`uvicorn server.main:app`.
"""
import asyncio
import json

import websockets

URL = "ws://127.0.0.1:8000/ws"


async def connect():
    return await websockets.connect(URL)


async def recv_until(ws, mtype, timeout=5):
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        msg = json.loads(raw)
        if msg["type"] == mtype:
            return msg
        if msg["type"] == "error":
            print("SERVER ERROR:", msg["message"])


async def main():
    names = ["Host", "Alice", "Bob", "Carol", "Dave"]
    sockets = [await connect() for _ in names]

    await sockets[0].send(json.dumps({"type": "create_room", "name": names[0]}))
    created = await recv_until(sockets[0], "room_created")
    code = created["room_code"]
    player_ids = {names[0]: created["player_id"]}
    print("Room created:", code)

    for ws, name in zip(sockets[1:], names[1:]):
        await ws.send(json.dumps({"type": "join", "room_code": code, "name": name}))
        joined = await recv_until(ws, "joined")
        player_ids[name] = joined["player_id"]
    print("All joined:", player_ids)

    # drain the lobby state broadcasts
    for ws in sockets:
        try:
            while True:
                await asyncio.wait_for(ws.recv(), timeout=0.3)
        except asyncio.TimeoutError:
            pass

    await sockets[0].send(
        json.dumps(
            {
                "type": "start_game",
                "role_counts": {"mafia": 1, "detective": 1, "doctor": 1, "godfather": 1},
            }
        )
    )

    states = {}

    async def collect_states(ws, name, seconds=1.0):
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=seconds)
                msg = json.loads(raw)
                if msg["type"] == "state":
                    states[name] = msg["state"]
        except asyncio.TimeoutError:
            pass

    for ws, name in zip(sockets, names):
        await collect_states(ws, name)

    assert states["Host"]["phase"] == "night", states["Host"]["phase"]
    roles = {name: s["your_role"] for name, s in states.items()}
    print("Roles:", roles)

    mafia_name = next(n for n, r in roles.items() if r == "mafia")
    detective_name = next(n for n, r in roles.items() if r == "detective")
    doctor_name = next(n for n, r in roles.items() if r == "doctor")
    victim_name = next(n for n in names if n not in (mafia_name,))

    victim_id = next(p["id"] for p in states[mafia_name]["players"] if p["id"] != player_ids[mafia_name])
    # mafia kills someone who isn't the doctor, to keep the game going
    victim_id = next(
        p["id"] for p in states[mafia_name]["players"] if player_ids[victim_name] == p["id"]
    )

    mafia_ws = sockets[names.index(mafia_name)]
    await mafia_ws.send(json.dumps({"type": "night_action", "action_type": "kill", "target_id": victim_id}))
    await recv_until(mafia_ws, "state")

    detective_ws = sockets[names.index(detective_name)]
    target_id = next(p["id"] for p in states[detective_name]["players"] if p["id"] != player_ids[detective_name])
    await detective_ws.send(
        json.dumps({"type": "night_action", "action_type": "investigate", "target_id": target_id})
    )
    await recv_until(detective_ws, "state")

    # force-advance the night timer (host only) instead of waiting 75s
    await sockets[0].send(json.dumps({"type": "force_advance"}))

    for ws, name in zip(sockets, names):
        await collect_states(ws, name, seconds=2.0)

    print("Phase after night resolve:", states["Host"]["phase"])
    print("Events:", states["Host"]["events"])
    assert states["Host"]["phase"] in ("day_discussion", "game_over")

    # --- reconnection test: kill Bob's socket, reconnect with the same player_id ---
    bob_id = player_ids["Bob"]
    await sockets[names.index("Bob")].close()
    new_ws = await connect()
    await new_ws.send(json.dumps({"type": "join", "room_code": code, "player_id": bob_id}))
    rejoined = await recv_until(new_ws, "joined")
    assert rejoined["player_id"] == bob_id
    print("Reconnection OK for Bob")

    for ws in sockets:
        if not ws.closed:
            await ws.close()
    await new_ws.close()
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
