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
pytest tests/ -q                # 36 headless engine tests
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
- **Discussion has a fixed, host-configurable duration** (15-600s, default
  60s), set in the lobby before starting. There's no early-exit signal for
  it, since talking has no "done" state to detect.
- **Voting ends on whichever comes first**: the configured timer running
  out, or every living player casting a vote (`Game.votes_complete`). A
  player who doesn't want to accuse anyone can hit "Skip My Vote" -- an
  explicit abstain that still counts as having voted, so the round can end
  early even without unanimous accusations. Skipped votes are excluded
  from the lynch tally.
- There is no host-only "skip timer" control. It was replaced by the
  above: night ends by itself once everyone's acted, and voting ends by
  itself once everyone's voted (or skipped) -- no admin override needed
  for either.
- Players can leave the lobby before the game starts ("Leave Lobby"); if the
  host leaves, the next remaining player becomes host.
- After a game ends, anyone in the room can hit "Return to Lobby" to reset
  the same room (same code, same players) back to a fresh lobby for a
  rematch, or "Leave Game" to exit to the title screen. Leaving is now
  allowed both before a game starts and after one ends, just not mid-game.
- Suggested room size: 8-12 players, ~1 mafia per 3-4 players (spec section 7).

## Disconnects, reconnection, and cleanup

- Every player's connection status is broadcast to everyone (`state.connected`),
  shown as an "OFFLINE" tag on their row in every player list, so a dropped
  connection is never mistaken for someone silently ignoring the game.
- A dropped WebSocket gets a 30-second grace period to reconnect (same
  `player_id` from localStorage, same as the existing reconnect flow) before
  anything happens. If they reconnect in time, nothing changes.
- If the grace period expires: before a game starts or after one ends,
  they're dropped from the room outright, same as leaving voluntarily. If
  it happens mid-game, they're marked eliminated instead of removed
  (`Game.handle_disconnect_removal`) -- this keeps votes, night-action
  requirements, and win checks consistent rather than leaving a hole in
  the roster mid-round. There is no way to manually kick anyone; connection
  loss is the only automatic removal path, by design (see project history).
- A shared "someone died" tone plays for everyone in the room when a death
  happens, distinct from the personal elimination sound the dead player
  themselves hears.
- Rooms with nobody connected and no activity for 2 hours are dropped from
  memory by a background sweep (`reap_idle_rooms`), so a long-running
  server doesn't accumulate every room ever created.
- Player names are capped at 24 characters, enforced both client-side and
  server-side (`sanitize_name`).
- `GET /healthz` is a dedicated health-check endpoint (used by
  `render.yaml`), separate from the Swagger docs page.

## Known limitations (spec section 10, by design)

- No way to stop players from side-channel texting/talking outside the app.
- No Discord API integration -- Discord is voice-only infrastructure.
- No speaking-order enforcement during Day.

## Testing gap: no manual browser testing yet

This project became Blackhand partway through (see `BLACKHAND.md` and
`BLACKHAND_PROGRESS.md` for the full 15-phase build history). What
follows describes the current, honest state of that build, not the
original Mafia project this section used to describe.

**What has actually been verified, and how:**

- The engine: 86 pytest tests, covering every rule in `BLACKHAND.md`
  Part 2 (Recruitment, Show Your Hands, the Ledger, win conditions, the
  night resolution pipeline) plus the player-count validation from
  section 7.3. All passing.
- The server protocol: verified live, repeatedly, with disposable
  scripted WebSocket clients, one per phase, each run against a real
  `uvicorn` instance and then deleted (never kept as a permanent suite,
  per this project's own stated practice). Confirmed this way: the Offer
  is delivered only to its recipient and nobody else's interface
  changes; the Black Hand channel is disabled during Show Your Hands and
  restored after; a Marked player's `allies`/`role_reveal` update
  correctly across a full accept-or-refuse round trip; `role_reveal` and
  `offer_outcome` reach the client with the right shape at game over;
  the 6-12 player floor and ceiling actually reject a real client's
  `start_game`; `show_hands_threshold` sent from the lobby actually
  changes when Show Your Hands fires.
- Every audio function: a disposable Node smoke test (bundled with
  esbuild, run against a mock Web Audio API) confirmed all 32 exported
  functions run without throwing, including the deferred 2-second
  death-silence callback actually firing, not just being scheduled.

**What has never been checked, because nothing in this environment
could check it:** the entire visual and audio result of all 15 phases
has never been opened in a real browser, let alone a real phone. Every
CSS rule, every animation timing, every color, the hand mark's actual
asymmetry and legibility at real screen sizes, whether anything in
`frontend/src/audio/` actually sounds like paper, wood, or room tone
rather than just filtered noise, whether the vote stamp is genuinely
countable by ear with the screen off, whether the Crossing's ring
assembly and the Reading's staggered unfolds look and feel right, none
of it has been seen or heard by anyone. A clean `npm run build` proves
the code compiles. It proves nothing about whether it looks or sounds
like Blackhand.

**Play a full game in a real browser, ideally on a real phone, and
report back anything that looks, sounds, or feels wrong.** Particular
places worth a close look, in rough order of how much is riding on
them: The Crossing and The Table (the document calls this "the most
important frontend phase in the build"); the Offer's full-black screen
and its timing; The Reading's staggered unfolds and the refusal card's
timing; every sound cue, especially whether the ambient bed's per-death
erosion is audible by the final round and whether votes are actually
countable with the screen off; the hand mark at both 200px (the Waiting
Room) and 24px (the favicon).

**Also worth knowing:** the rest of this README, below this section, is
largely unchanged since before the Blackhand rewrite began and still
describes the original Mafia project (old role names, old mechanics).
Updating it was never in scope for any of the 15 Blackhand phases except
this testing-gap section specifically; treat the rest of this file as
historical until someone does a full pass.
