# Mafia / Werewolf

Browser-based social deduction game. Players talk over a Discord voice
channel; the web app owns all private information, roles, and game state.
Built from `mafia-game-spec.md`.

## Stack

- **`engine/`** -- pure Python game engine (roles, state machine, night
  resolution pipeline, win conditions). Zero web framework imports; runs
  headless in pytest.
- **`server/`** -- FastAPI + WebSocket room layer (room codes, per-player
  views, reconnection, phase timers).
- **`frontend/`** -- React (Vite) client.

## Role names

The engine and network protocol still use the original spec names
internally (`detective`, `doctor`, `villager`), but the UI displays them as:

| Internal name | Displayed as |
|---|---|
| villager | Civilian |
| detective | Police |
| doctor | Healer |
| mafia | Mafia |
| godfather | Godfather |

This is a display-only rename (`frontend/src/roles.js`); role behavior is
unchanged.

## Decisions on the spec's open ambiguities (section 6)

The spec explicitly leaves these for the implementer to decide and document:

- **Healer self-heal:** allowed, but only **once per game**.
- **Healer same target on consecutive nights:** not allowed.
- **Roleblocked Police:** gets an explicit "blocked" result rather than
  silence. (No v1 role can roleblock, so this never actually fires yet --
  the engine's resolution pipeline reserves the stage for a future
  Roleblocker/Redirector role.)
- **Police investigating someone who died the same night:** sees their
  true role. Kills resolve before investigations in the pipeline, but a
  player's role never changes on death, so the result is accurate either way.
- **Last Mafia dies at night vs. Godfather dying "the same night":** there's
  no true simultaneity -- Night and Day/lynch are always separate phases.
  The succession check (`_check_succession`) runs immediately after *both*
  night resolution and lynch resolution, so whichever kill actually happened
  most recently in the phase sequence is authoritative.
- **The Mafia's kill is a single shared choice**, not a per-member vote. Any
  living Mafia member can set or change the target; it is visible live to
  the whole Mafia team (`mafia_kill_target_name` in the view). There is
  never a tie to break, since there is only ever one target. Tied lynch
  votes still result in no lynch.

## Bugs found and fixed during development (historical, not current)

These were caught and corrected before anything shipped. Listed here only
so the reasoning behind the current Godfather visibility rules is on
record, not because they are still present.

- An early draft let the Godfather see the Mafia's private chat before
  promotion. Fixed: the chat channel now only opens for players whose role
  is exactly `Mafia`, never `Godfather` (`server/rooms.py`,
  `mafia_channel_ids`).
- An early draft built the Mafia's "allies" list from "everyone on the evil
  team," which technically includes the Godfather, so his name leaked into
  the regular Mafia's own screen. Fixed: `allies` (shown to Mafia) and
  `known_mafia` (shown to the Godfather) are now two separate, one-way
  lists in `engine/game.py::view_for` -- Mafia players see only other
  Mafia; the Godfather separately sees all the Mafia; neither list ever
  crosses over.

Current, correct behavior (covered by `tests/test_engine.py`): the Mafia
never learn who the Godfather is, and the Godfather never sees Mafia chat
or their kill target -- only the list of who they are. If every regular
Mafia player dies, `_check_succession` flips the Godfather's role to
`Mafia` outright, and the game continues with him now getting full Mafia
access.

## Dead players and the game log

Once a player dies, their screen switches to a spectator view: a clear "YOU
ARE DEAD" banner (they are asked not to talk for the rest of the game) plus
a full round-by-round log of exactly what happened each night and day,
including who the Mafia targeted, who the Healer protected, and each Police
result. Living players never see this level of detail, only the vague
public feed (e.g. "X was killed during the night"), to keep roles hidden
until the game ends. The same full log is shown to everyone once the game
ends, alongside a clear reveal: if the Mafia win, their names are shown; if
the Civilians win, the names of everyone who was secretly Mafia are shown.

## Run locally

**Backend:**

```bash
python -m venv venv
./venv/Scripts/activate        # Windows; use `source venv/bin/activate` on macOS/Linux
pip install -r requirements-dev.txt
pytest tests/ -q                # 26 headless engine tests
uvicorn server.main:app --reload --port 8000
```

**Frontend (separate terminal, dev mode with hot reload):**

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`). The dev client
talks to the backend at `ws://localhost:8000/ws` automatically.

To play with others on your phone over the same WiFi: find your machine's
LAN IP (`ipconfig`), then have players visit `http://<your-ip>:5173`.

**Single-service mode** (what actually ships): build the frontend once and
let FastAPI serve it directly, matching production:

```bash
cd frontend && npm run build && cd ..
uvicorn server.main:app --port 8000
```

Then everything -- app and WebSocket -- is on `http://localhost:8000`.

## Deploy (free tier)

This repo includes a `Dockerfile` and `render.yaml` for
[Render](https://render.com) (WebSockets work out of the box on their free
tier, no credit card required):

1. Push this repo to GitHub.
2. In the Render dashboard: **New > Blueprint**, point it at the repo. Render
   reads `render.yaml` and provisions the service automatically.
   (Or: **New > Web Service**, environment = Docker, and it'll pick up the
   `Dockerfile`.)
3. Wait for the build (~2-3 min: npm build + pip install). Render gives you
   a `https://<name>.onrender.com` URL -- that's what players open.
4. Free tier spins down after 15 minutes idle and takes ~30-60s to wake back
   up on the next request. Fine for a game night; not for always-on use.

Fly.io and Railway also work with the same `Dockerfile` if you'd rather use
one of those.

## Timers

- **Night has no fixed duration.** It ends as soon as every living player
  whose role has a night action (Mafia, Doctor, Detective) has submitted
  one -- not on a clock. Each player's screen shows a live "X / Y players
  have acted" count.
- **Discussion and Voting are host-configurable**, set in the lobby before
  starting (15-600s each, default 60s). The host can also skip either early
  with "Skip timer (host)".
- Players can leave the lobby before the game starts ("Leave Lobby"); if the
  host leaves, the next remaining player becomes host.
- Suggested room size: 8-12 players, ~1 mafia per 3-4 players (spec section 7).

## Known limitations (spec section 10, by design)

- No way to stop players from side-channel texting/talking outside the app.
- No Discord API integration -- Discord is voice-only infrastructure.
- No speaking-order enforcement during Day.

## Testing gap: no manual browser testing yet

The engine (26 pytest tests) and the server protocol (verified live with
scripted WebSocket clients: leave-lobby, custom timers, action-driven
night ending, the shared Mafia kill syncing across members, dead players
seeing the round log) are both tested end to end. The frontend has only
been checked for a successful `npm run build` -- it has not been opened in
a real browser. That matters most for anything purely visual or
client-side: the circular timer ring, the sound cues, the grayscale dead
screen, avatar rendering. A clean build proves the code compiles, not that
it looks or sounds right. Play a real round in a browser and report
anything that looks or sounds wrong.
