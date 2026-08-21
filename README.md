# Blackhand

Link: https://mafia-game-bo9t.onrender.com (still mid-deploy of this
rewrite; see the testing gap section below before trusting what's live)

Browser-based social deduction game, inspired by the historical Black
Hand extortion letters. Players talk over a voice channel (Discord or
similar); the web app owns all private information, roles, and game
state. Built from `BLACKHAND.md`, the full 15-phase design and build
specification; `BLACKHAND_PROGRESS.md` tracks what each phase actually
did and why, phase by phase, and is the more detailed record if this
file and that one ever seem to disagree.

## Stack

- **`engine/`** -- pure Python game engine (roles, factions, the night
  resolution pipeline, Recruitment, Show Your Hands, the Ledger, win
  conditions). Zero web framework imports; runs headless in pytest.
- **`server/`** -- FastAPI + WebSocket room layer (room codes, per-player
  views, reconnection, phase timers, anonymous per-game logging).
- **`frontend/`** -- React (Vite) client. `frontend/src/phases/` holds
  the beat-specific screens (the Waiting Room, the Crossing, the Table,
  the Offer, the Reading); `frontend/src/audio/` is the fully
  synthesized (no audio files) sound module.

## Vocabulary

The game's roles and factions: Civilian, the Inspector, and the Watchman
play for the Table; a Hand plays for the Black Hand. A Table player who
accepts the Black Hand's one-per-game Offer becomes Marked: their
literal role never changes, but they count as Black Hand from that
point on (`engine/models.py::effective_faction`). There is no Godfather;
see `BLACKHAND_PROGRESS.md`'s Phase 1 entry for why. The full vocabulary
table is `BLACKHAND.md` section 1.3.

## Decisions on mechanics the spec leaves to the implementer

- **Watchman self-heal:** allowed, but only **once per game**.
- **Watchman, same target on consecutive nights:** not allowed.
- **A roleblocked Inspector** gets an explicit "blocked" result rather
  than silence, reserved for a future Roleblocker role -- no current
  role can roleblock, so this never actually fires yet.
- **The Inspector's result reflects the target's current effective
  faction**, not a snapshot from earlier in the game: investigating a
  player cleared earlier, then Marked since, now correctly reads guilty.
  This is what makes a stale clear decay (`BLACKHAND.md` section 3.4).
- **The Black Hand's kill (or Offer) is a single shared choice**, not a
  per-member vote. Any living Hand can set or change the target; it's
  visible live to the whole Black Hand. There's never a tie to break,
  since there's only ever one target. Tied lynch votes result in no lynch.

## Dead players, the Ledger, and The Reading

Once a player dies, their screen switches to a spectator view (no
talking or voice chat for the rest of the game) plus a full round-by-round
case log of exactly what happened each night and day. Living players
never see this level of detail, only the vague public feed (e.g. "X was
killed during the night"), and Recruitment's silence rule keeps a
protected save and a successful Offer indistinguishable even in that
feed (`NO_VISIBLE_DEATH_MESSAGE`, `engine/game.py`).

Every vote any living player casts is public and permanent from the
moment it's cast (the Ledger, `BLACKHAND.md` section 2.5): full history,
never summarized into a score or a suspicion rating anywhere, enforced
by a real test (`test_no_scoring_or_ranking_function_exists_in_the_engine`)
that greps the engine for the banned terms, not just a one-time check.

At game over, The Reading shows everyone: every role, whether each Hand
started that way or was Marked later, the full round-by-round record,
and -- only if an Offer was made and refused or timed out -- one final
line naming who and which night, after a two-second pause, alone. If no
Offer was ever made, or it was accepted, that line simply doesn't
appear. Its absence is deliberate information, not a placeholder.

## Run locally

**Backend:**

```bash
python -m venv venv
./venv/Scripts/activate        # Windows; use `source venv/bin/activate` on macOS/Linux
pip install -r requirements-dev.txt
pytest tests/ -q                # 86 headless engine tests
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

**Manual end-to-end smoke test** (not part of the pytest suite, exercises
the real WebSocket protocol against a running server, including
reconnection):

```bash
uvicorn server.main:app --port 8000   # in one terminal
python scripts/smoke_test.py          # in another
```

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
5. The anonymous per-game log lines (`blackhand_game_result {...}` on
   stdout, `server/rooms.py::_log_game_result`) show up in Render's own
   log dashboard, no separate log service needed.

Fly.io and Railway also work with the same `Dockerfile` if you'd rather use
one of those.

## Timers

Fixed, not host-configurable, per `BLACKHAND.md` section 7.2:

- **Night has no fixed duration.** It ends as soon as every living player
  whose role has a night action (a Hand, the Watchman, the Inspector)
  has submitted one -- not on a clock. Each player's screen shows a live
  "X / Y players have acted" count.
- **The Table (voting) is fixed at 45 seconds** or until everyone has
  voted or stood aside, whichever comes first, per section 6.8. Not
  configurable from the lobby.
- **Show Your Hands is fixed at 15 seconds.** **The Offer is fixed at 30
  seconds**, and a non-answer within that window is treated exactly like
  a refusal.

Host-configurable in the Waiting Room (section 7.1):

- **Discussion length**, 15 to 600 seconds, default 60.
- **Show Your Hands**, on or off, and its threshold (5 to 7 living
  players), default on at 6.
- **Hand count**, auto (section 3.1's table for the current player
  count) or a manual override via the Inspector/Watchman/Hand steppers.

Not yet configurable despite being listed in section 7.1: Watchman
on/off, Recruitment on/off, and Ledger depth (full vs. recent 3 rounds)
have no real engine support yet -- see "Known limitations" below.

Player count is validated 6 to 12 inclusive before a game can start
(`GameConfig.validate`, section 7.3); the host sees the exact error if
it's out of range or the roles don't add up.

## Disconnects, reconnection, and cleanup

- Every player's connection status is broadcast to everyone (`state.connected`),
  shown as an "OFFLINE" tag on their row in every player list, so a dropped
  connection is never mistaken for someone silently ignoring the game.
- A dropped WebSocket gets a 30-second grace period to reconnect (same
  `player_id` from localStorage) before anything happens. If they
  reconnect in time, nothing changes.
- If the grace period expires: before a game starts or after one ends,
  they're dropped from the room outright, same as leaving voluntarily. If
  it happens mid-game, they're marked eliminated instead of removed
  (`Game.handle_disconnect_removal`) -- this keeps votes, night-action
  requirements, and win checks consistent rather than leaving a hole in
  the roster mid-round. A recipient disconnecting during their own Offer
  window resolves it as a refusal rather than leaving the game stuck.
  There is no way to manually kick anyone; connection loss is the only
  automatic removal path, by design.
- Death itself is silence, not a sound: every death forces the ambient
  bed to true silence for 2 seconds, then one of its four layers is gone
  permanently for the rest of the game (`frontend/src/audio/ambient.js`,
  `BLACKHAND.md` section 4.10). By the final round the room sounds
  hollow. This applies the same way whether it's your own death or
  someone else's; there's no separate "personal" vs. "shared" sound
  anymore.
- Rooms with nobody connected and no activity for 2 hours are dropped from
  memory by a background sweep (`reap_idle_rooms`), so a long-running
  server doesn't accumulate every room ever created.
- Player names are capped at 24 characters, enforced both client-side and
  server-side (`sanitize_name`).
- `GET /healthz` is a dedicated health-check endpoint (used by
  `render.yaml`), separate from the Swagger docs page.

## Known limitations

By design, per `BLACKHAND.md` section 10:

- No way to stop players from side-channel texting/talking outside the app.
- No Discord API integration -- Discord is voice-only infrastructure.
- No speaking-order enforcement during discussion.

Gaps in the current build, not by design, tracked in more detail in
`BLACKHAND_PROGRESS.md`:

- **Show Your Hands has no interactive UI anywhere in the app.** The
  engine and server fully support it and it's configurable from the
  lobby, but no phase in the 15-phase build plan ever names a screen for
  it, the same kind of gap as Delivery and First Light below. A game
  that reaches the Show Your Hands threshold currently has no way to
  actually cast that vote from the browser.
- **The Offer has a screen (Phase 12) but no other beat has been
  restructured to the same standard.** Delivery (role reveal) and First
  Light (the 10-second forced pause after night) are both described in
  detail in the document but never assigned their own build phase; role
  reveal today is a persistent card, not the self-closing 4-second
  letter section 6.2 describes.
- **Watchman on/off, Recruitment on/off, and Ledger depth** (section
  7.1) have no real engine support (no `GameConfig` field, nothing
  gating the mechanic), so the lobby doesn't offer fake controls for them.
- **Nothing in this project has been confirmed to work in a real
  browser.** See the section below.

## Testing gap: no manual browser testing yet

**What has actually been verified, and how:**

- The engine: 86 pytest tests, covering every rule in `BLACKHAND.md`
  Part 2 (Recruitment, Show Your Hands, the Ledger, win conditions, the
  night resolution pipeline) plus the player-count validation from
  section 7.3. All passing.
- The server protocol: verified live, repeatedly, with disposable
  scripted WebSocket clients, one per phase, each run against a real
  `uvicorn` instance and then deleted (never kept as a permanent suite;
  `scripts/smoke_test.py` is the one exception kept around on purpose).
  Confirmed this way: the Offer is delivered only to its recipient and
  nobody else's interface changes; the Black Hand channel is disabled
  during Show Your Hands and restored after; a Marked player's
  `allies`/`role_reveal` update correctly across a full accept-or-refuse
  round trip; `role_reveal` and `offer_outcome` reach the client with
  the right shape at game over; the 6-12 player floor and ceiling
  actually reject a real client's `start_game`; `show_hands_threshold`
  sent from the lobby actually changes when Show Your Hands fires; the
  anonymous per-game log line actually appears on a running server's
  stdout after a real game.
- Every audio function: a disposable Node smoke test (bundled with
  esbuild, run against a mock Web Audio API) confirmed all 32 exported
  functions run without throwing, including the deferred 2-second
  death-silence callback actually firing, not just being scheduled.

**What has never been checked, because nothing in this environment
could check it:** the entire visual and audio result of every phase has
never been opened in a real browser, let alone a real phone. Every CSS
rule, every animation timing, every color, the hand mark's actual
asymmetry and legibility at real screen sizes, whether anything in
`frontend/src/audio/` actually sounds like paper, wood, or room tone
rather than just filtered noise, whether the vote stamp is genuinely
countable by ear with the screen off, whether the Crossing's ring
assembly and the Reading's staggered unfolds look and feel right, none
of it has been seen or heard by anyone. A clean `npm run build` proves
the code compiles. It proves nothing about whether it looks or sounds
like Blackhand.

**Play a full game in a real browser and report back anything that
looks, sounds, or feels wrong.** Particular places worth a close look,
in rough order of how much is riding on them: The Crossing and The
Table (the document calls this "the most important frontend phase in
the build"); the Offer's full-black screen and its timing; The
Reading's staggered unfolds and the refusal card's timing; every sound
cue, especially whether the ambient bed's per-death erosion is audible
by the final round and whether votes are actually countable with the
screen off; the hand mark at both 200px (the Waiting Room) and 24px
(the favicon).
