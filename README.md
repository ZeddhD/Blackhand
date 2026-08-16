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

## Decisions on the spec's open ambiguities (section 6)

The spec explicitly leaves these for the implementer to decide and document:

- **Doctor self-heal:** allowed, but only **once per game**.
- **Doctor same target on consecutive nights:** not allowed.
- **Roleblocked Detective:** gets an explicit "blocked" result rather than
  silence. (No v1 role can roleblock, so this never actually fires yet --
  the engine's resolution pipeline reserves the stage for a future
  Roleblocker/Redirector role.)
- **Detective investigating someone who died the same night:** sees their
  true role. Kills resolve before investigations in the pipeline, but a
  player's role never changes on death, so the result is accurate either way.
- **Last Mafia dies at night vs. Godfather dying "the same night":** there's
  no true simultaneity -- Night and Day/lynch are always separate phases.
  The succession check (`_check_succession`) runs immediately after *both*
  night resolution and lynch resolution, so whichever kill actually happened
  most recently in the phase sequence is authoritative.
- **Tied mafia kill vote / tied lynch vote:** no kill / no lynch that round.

Two bugs worth calling out from building this: an early draft let the
Godfather see the Mafia's private chat before promotion, and let the "allies"
view for a Mafia player leak the Godfather's identity -- both violate the
spec's core secrecy requirement (mafia don't know the Godfather; the
Godfather has no chat access until promoted) and were fixed before shipping.

## Run locally

**Backend:**

```bash
python -m venv venv
./venv/Scripts/activate        # Windows; use `source venv/bin/activate` on macOS/Linux
pip install -r requirements-dev.txt
pytest tests/ -q                # 19 headless engine tests
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

## Playtested defaults

- Night: 75s, Discussion: 60s, Voting: 60s (`server/rooms.py`). The host can
  skip any timer early with "Skip timer (host)".
- Suggested room size: 8-12 players, ~1 mafia per 3-4 players (spec section 7).

## Known limitations (spec section 10, by design)

- No way to stop players from side-channel texting/talking outside the app.
- No Discord API integration -- Discord is voice-only infrastructure.
- No speaking-order enforcement during Day.
