# Ship Flow Playbook

This document captures **how this project went from an idea to a live URL
in one sitting, and stayed easy to change afterward** - not the game
itself, but the process and decisions that made it easy. It's written so
you can hand it to a different, already-working project and adopt the
same flow there.

Everything here is a general pattern. Where useful, it points at the exact
file in this repo that shows the pattern in practice.

---

## 1. The three-layer split that made everything else easy

Almost every "this is getting hard to change" problem traces back to logic,
networking, and presentation being tangled together. This project kept
three layers strictly separate from the first commit:

1. **Pure logic core** (`engine/`) - the actual rules of the game. Zero
   imports from any web framework, zero knowledge that a network exists.
   Just plain classes and functions you can call directly in a Python
   REPL.
2. **A thin session/network layer** (`server/`) - owns rooms, WebSocket
   connections, timers, reconnection. It calls into the logic core but
   contains none of the rules itself.
3. **A presentation layer** (`frontend/`) - renders whatever state the
   server sends it. Contains no rules either.

**Why this is the highest-leverage decision in the whole project:** every
feature added after the first version - custom timers, action-driven
phases, disconnect handling, a full redesign - touched at most one or two
of these layers, never all three tangled together. The engine could be
tested with plain `pytest`, in milliseconds, with no server running and no
browser involved at all. That's what made "add a feature, verify it,
ship it" a fast loop instead of a slow one.

**If you're adopting this in an existing project:** look for the place
where "what should happen" (rules, calculations, business logic) is
currently mixed into the same function as "how it's transmitted" (HTTP
handlers, socket code) or "how it's displayed" (templates, components).
Pulling those apart - even partially, even for just the next feature you
touch - pays for itself immediately.

---

## 2. The deploy flow itself

The whole pipeline, end to end:

```
local code  →  git push to GitHub  →  host reads a Dockerfile  →  live URL
```

No manual server setup, no SSH, no "configure the production environment"
step. The concrete pieces:

### A multi-stage Dockerfile that builds everything and ships only what's needed

See [`Dockerfile`](Dockerfile). Two stages:

- **Stage 1** builds the frontend (Node image, `npm ci`, `npm run build`)
  and produces static files. Nothing about Node ends up in the final image.
- **Stage 2** starts fresh from a lean runtime image (Python here), installs
  only the runtime's own dependencies, copies in the app code, and pulls
  *just the built static output* from stage 1 with
  `COPY --from=<stage-name> ...`.

Result: one small image with only what's needed to actually run - no
build tools, no source files that aren't needed at runtime, no second
language runtime.

The command that starts the app respects the port the host assigns at
runtime rather than hardcoding one:

```dockerfile
CMD ["sh", "-c", "uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

### A single-service deploy, not two

The backend serves the frontend's built static files directly
(`StaticFiles` mount in [`server/main.py`](server/main.py)), so there's
exactly one service, one URL, one deploy, and no CORS configuration to
get right. This only works because of a route ordering detail worth
copying: any client-side route (like a room code URL) needs an explicit
server-side fallback to `index.html` *before* the static file mount,
otherwise refreshing on that URL 404s.

### A declarative deploy config committed to the repo

[`render.yaml`](render.yaml) tells the host what to build and how to
health-check it, so "connect the repo" is the entire manual setup step -
no clicking through dashboard forms. A dedicated `/healthz` endpoint
(not the framework's docs/debug page) is what the health check hits.

### The actual adoption checklist

1. Write a multi-stage Dockerfile: one stage per thing that needs its own
   toolchain to build, one final stage that only copies in build
   *artifacts*, not build *tools*.
2. Make the app read its port from the environment (`$PORT` or
   equivalent) instead of hardcoding it.
3. Add a real health-check endpoint that doesn't depend on debug/docs
   tooling being enabled.
4. Commit a declarative deploy config (`render.yaml`, `fly.toml`,
   `railway.json`, whichever the target host uses) so deploying is
   "connect the repo," not a manual dashboard walkthrough.
5. If frontend and backend are separate today, evaluate whether they
   actually need to be - one service is one less thing to configure,
   deploy, and keep in sync.

---

## 3. The design-decision discipline

Every visual and UX choice in this project traces back to one of a small
number of stated rules, applied consistently, rather than being decided
ad hoc per screen. That's what stopped the UI from drifting into
inconsistency as features were added on top of each other. The rules
themselves (documented in [`frontend/src/index.css`](frontend/src/index.css)'s
top comment):

- **A closed set of colors, each meaning exactly one thing, used nowhere
  else.** Not "red looks cool here too" - if a color means "destructive
  action," it is *never* used for a routine one, anywhere, including
  supposedly-decorative elements like avatars.
- **One repeating structural motif** (a labeled "tab" on every card) so
  the eye learns the pattern once instead of parsing every screen fresh.
- **Every state that needs to be unmistakable gets its own, unique
  treatment.** "You are dead" and "everyone should stay silent right now"
  are both hard rules, but they're visually nothing alike on purpose -
  because the two situations must never be confused for each other at a
  glance under time pressure.
- **Text you need to scan fast is never de-emphasized with three
  compounding techniques at once** (small *and* dim *and* italic). Pick
  one signal, not a stack of them.

**The transferable habit, not just the specific rules:** before adding a
new UI element, ask "which existing rule does this follow?" If the answer
is "none, it's just what looked right here," that's the moment
inconsistency starts compounding. Writing the rules down somewhere
central (even just a comment block) is what makes them checkable later.

---

## 4. The testing philosophy

Two distinct kinds of testing were used for two distinct kinds of claims,
and neither was allowed to stand in for the other:

- **Headless unit tests** (`tests/test_engine.py`, run via plain `pytest`,
  no server, no network) for anything that's pure logic: rules, edge
  cases, win conditions. Fast enough to run after every change, so they
  did.
- **Live, scripted end-to-end checks** against an actually-running server
  (throwaway Python scripts using a real WebSocket client) for anything
  that depends on timing, concurrency, or the network layer - things a
  unit test can't see, like "does the server actually wait for the right
  event before resolving a phase." These scripts were written, run,
  deleted once they'd proven the point, and not kept as permanent
  fixtures - they're a verification tool, not a maintained suite.

**The rule that mattered most:** *"the build succeeded" is not a test
result.* A clean compile or build proves the code is syntactically valid
and type-consistent, nothing more. Several real bugs in this project were
only found by actually running the thing and hammering on it with a
script that behaved like a real client - including bugs where the
underlying logic was completely correct and the test itself was flawed,
which only became clear by adding tracing and watching what actually
happened over the wire rather than trusting the first failure.

**Adoption note:** if a project's "tests" are entirely "did it build" or
"did it deploy," that's a gap worth naming explicitly (this project's
README has a standing "testing gap" section for exactly this reason,
updated honestly as new untested surface area gets added) rather than
letting a clean build quietly stand in for verification.

---

## 5. Patterns worth lifting directly

A few specific, reusable techniques from this codebase, independent of
what the app does:

- **Per-recipient views, constructed server-side, never trust the client
  to hide anything.** ([`engine/game.py::view_for`](engine/game.py)) If
  different users should see different things, build the *different
  payloads* server-side rather than sending everything and hiding parts
  in the UI. Anyone can open devtools.
- **Let completion drive state transitions instead of a fixed timer,
  when there's a natural "everyone's done" signal.** Night and Voting
  both end the instant all needed input has arrived, not on a clock -
  removing the need for a manual "force skip" admin control entirely,
  which had been a real feature before this pattern replaced it.
- **Graceful reconnection built on a stable client-side identity token**,
  not the transient connection. A dropped socket isn't a departure; it's
  given a grace period, and only becomes a real removal if it doesn't
  resolve.
- **A structured, detailed log kept separately from the vague public
  one**, so different audiences (a live player who shouldn't know
  everything yet vs. a spectator/eliminated player who should) get
  different levels of detail from the same underlying events, without
  duplicating the event-recording logic.
- **Idle-resource cleanup as a background sweep, not a manual step** -
  long-running server state (rooms, sessions, anything created per-user)
  needs an automatic expiry path or it accumulates forever.

---

## 6. Quick-reference adoption checklist

Copy this list into the target project's issue tracker or a scratch note:

- [ ] Separate pure logic from I/O and presentation, even partially
- [ ] Logic layer has fast, headless unit tests with no server/network involved
- [ ] Multi-stage Dockerfile: build stage(s) produce artifacts, final stage only copies them in
- [ ] App reads its port from the environment, not hardcoded
- [ ] Dedicated health-check endpoint, independent of debug/docs tooling
- [ ] Deploy config committed to the repo (`render.yaml` or host equivalent)
- [ ] One service if frontend/backend can reasonably be one
- [ ] Design decisions written down as a small set of named rules, not ad hoc per screen
- [ ] Live/integration verification for anything timing- or network-dependent, distinct from unit tests
- [ ] A named, honest "here's what's NOT verified yet" note somewhere visible, kept current
- [ ] Background cleanup for any resource that accumulates over server uptime
