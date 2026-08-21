# Blackhand Build Progress

Read this file first in any new session before touching code. It tracks
status against `BLACKHAND.md`'s 15-phase build plan so a fresh session
with no memory of prior conversations can pick up correctly instead of
re-deriving state or silently disagreeing with an earlier decision.

**Current status: Phase 12 complete (Phase 11's human listening pass still pending). Phase 13 not started.**

**Push policy, confirmed by the user: commit locally after every phase,
but do not `git push` at all until the frontend is far enough along that
the live deployed site works end to end again.** The engine and server
vocabulary migration in Phase 1 already broke the live site's ability to
start a game (the deployed frontend still sends old role names like
`mafia`/`godfather`, which no longer match anything). Pushing mid-migration
would just put that broken state on the public URL. Hold every push,
across every phase, until a frontend phase (6+) restores a working
end-to-end flow. Only push once that's true, and confirm with the user
first regardless.

---

## Phase 0: Audit (done)

Full read-only audit of the existing repo delivered and reviewed. Every
open question resolved with the user before Phase 1 began, per the
document's "Stop. Report. Wait." rule. Decisions made during this phase
that affect later phases:

- **Recruitment reuses the existing shared-kill-target mechanism.** One
  shared "tonight's Hand action" state (mode: kill or offer, plus a
  target), settable by any living Hand, visible live to the team. Not a
  new voting system.
- **A Marked player stays revealed as Hand at The Reading even if killed
  later.** Faction flips permanently on acceptance; death doesn't undo it.
- **Offer targets must be validated server-side as living Table players**,
  not just restricted in the UI.
- **Show Your Hands ties resolve as HOLD wins** (game continues). No
  majority reached means the affirmative "end the game" act didn't happen.
- **Watchman self-heal rules are unchanged.** Recruitment explicitly
  doesn't interact with protection at all.
- **The player-count table in section 3.1 (6-12) supersedes all prior
  guidance wholesale.**
- **No external assets, ever.** The hand mark (Phase 7) will be an
  original SVG built from scratch, not sourced art. All sound (Phase 11)
  will be synthesized via Web Audio, the same technique the current
  `sound.js` already uses, not recorded/sourced audio files. This is a
  hard constraint from the user, not a placeholder-pending-assets choice.
- **Balance logging (Phase 15) goes to stdout only.** No new persistent
  storage gets introduced. This means the 45-55% win-rate target cannot
  be tracked automatically across server restarts/redeploys; whoever
  wants that data has to copy it out of the log dashboard periodically.

## Phase 1: Engine, vocabulary migration (done)

**Files touched:** `engine/models.py`, `engine/actions.py`, `engine/game.py`,
`engine/__init__.py`, `tests/test_engine.py`. Plus one necessary one-line
fix in `server/rooms.py` (`mafia_team()` renamed to `hand_team()` in the
engine, so the one call site had to follow or the server would not
import). This was outside Phase 1's stated file list but was unavoidable;
flagged rather than silently done.

**What changed:**
- `Role`: `VILLAGER/DETECTIVE/DOCTOR/MAFIA/GODFATHER` -> `CIVILIAN/INSPECTOR/WATCHMAN/HAND`.
  Godfather has no replacement; the role and its entire promotion mechanic
  (`_check_succession`) are deleted, not renamed.
- `Team` -> `Faction`, members `TOWN/MAFIA` -> `TABLE/HAND`.
- `role_team()` -> `faction_of()`, `detective_reads_as()` -> `inspector_reads_as()`
  (and simplified, since there's no more Godfather-reads-innocent exception
  to special-case).
- `mafia_team()` -> `hand_team()`, `mafia_kill_target/actor` ->
  `hand_kill_target/actor`, `_doctor_self_heal_used/_doctor_last_target` ->
  `_watchman_self_heal_used/_watchman_last_target`, `mafia_ready()` ->
  `hand_ready()`.
- `view_for()` output keys renamed: `mafia_kill_target_id/name` ->
  `hand_kill_target_id/name`, `mafia_reveal` -> `hand_reveal`. `allies`
  keeps its name (already faction-neutral). The old `known_mafia` key is
  gone entirely, there is no Godfather-equivalent hidden-teammate concept
  in Blackhand.
- `GameConfig.validate()` error copy updated to match section 7.3's exact
  given strings ("The game needs at least one Hand", "The Black Hand
  already holds the table", "{n} roles assigned for {m} players").
- Win/lynch/night-resolution event copy updated (Watchman/Inspector/Black
  Hand naming, "They were a Hand" / "They were not a Hand", "The Table
  wins!" / "The Black Hand wins!").

**Acceptance criteria, all verified:**
- 33 tests pass (was 36; 5 Godfather-specific tests deleted since the role
  no longer exists: promotion-via-night-kill, promotion-via-lynch,
  Inspector-reads-Godfather-innocent, and two ally/known-list leak tests
  whose entire premise was hiding one evil role from another; 2 new tests
  added to preserve equivalent coverage that isn't Godfather-specific:
  `test_inspector_sees_civilian_as_innocent`, `test_view_for_hand_shows_allies`).
- `grep -riE "godfather|mafia|detective|doctor|villager" engine/ tests/`
  returns nothing (verified live).
- No behavior change other than Godfather removal, confirmed by review:
  win-condition math, night-resolution stage order, protection/self-heal
  rules, and the shared-kill-target mechanic are all mechanically
  identical to before, only renamed.
- `server.main:app` still imports successfully after the one forced
  cross-file rename.

**Deliberately NOT done in Phase 1** (would have exceeded "no behavior
change other than Godfather removal"):
- Player-count min/max (6-12) validation from section 7.3 is not yet
  added. `GameConfig.validate()` still has no floor or ceiling on player
  count.
- `Phase` enum is untouched: still `LOBBY/ASSIGN_ROLES/NIGHT/RESOLVE_NIGHT/
  DAY_DISCUSSION/VOTING/RESOLVE_LYNCH/GAME_OVER`, not the beat-structure
  names from Part 1.3's vocabulary table (`Phase.TABLE`, `Phase.SHOW_HANDS`,
  `Phase.READING`). Deferred to whichever phase actually builds the round
  structure (Phase 2 for Recruitment/Offer resolution, Phase 3 for Show
  Your Hands, and the frontend phases for the full 11-beat sequence).
- The night resolution pipeline is still the old 6-stage shape
  (protections / kills / investigations / win-check). The 7-stage version
  with "Kills, or the Offer" and a dedicated "Offer resolution" stage is
  Phase 2 work.
- `server/`, `frontend/` are functionally untouched except the one forced
  rename. **The live deployed site will not reflect Blackhand rules or
  vocabulary until later phases land** (server: Phase 5+, frontend: Phase
  6+). Expect it to look and behave inconsistently with this document
  until then. That's expected, not a regression.

## Phase 2: Engine, Recruitment (done)

**Files touched:** `engine/game.py`, `engine/models.py`, `engine/actions.py`,
`engine/resolution.py` (new file, as the build plan specified),
`engine/__init__.py`, `tests/test_recruitment.py` (new file, 16 tests).

**A genuinely new engine concept had to be introduced: `Phase.OFFER`.**
Recruitment can't resolve atomically like a kill does, because the
recipient needs a real response window (accept, refuse, or a timeout the
server enforces) before the pipeline can continue into investigations and
the win check. `resolve_night()` now stops after stage 3 and enters
`Phase.OFFER` when the Black Hand chose to offer instead of kill; two new
methods finish the job once an answer exists: `respond_to_offer(player_id,
accepted)` for the recipient's real answer, and `resolve_offer_timeout()`
for the server-driven timeout path (no player identity check, since
nobody submitted it). This wasn't optional scope, Recruitment cannot be
modeled correctly without a way to represent "waiting on one specific
player's answer" as distinct from "waiting on night actions in general."

**Design decisions made while implementing, not fully specified in the
document itself:**
- **A Marked player's literal `role` never changes**, only `player.marked
  = True` flips, exactly as the vocabulary table's code column specifies.
  Every faction/team check in the engine that used to read `role` directly
  now goes through `effective_faction(player)` (role, or Marked), so a
  recruit is correctly treated as Hand everywhere (win check, `hand_team()`,
  ally list, endgame reveal, investigation results) without their stored
  role ever lying about their original assignment. This matters for The
  Reading later (Phase 13), which is supposed to show who was recruited as
  a distinct fact from who started as Hand.
- **`inspector_reads_as` now reflects the target's current effective
  faction at the moment of investigation, not a frozen snapshot.** This is
  what actually makes a stale clear "decay" per section 3.4: an
  Inspector's OLD result doesn't retroactively change, but a NEW
  investigation of a since-recruited player now correctly reads guilty.
  Investigations are also deferred behind an active offer (pipeline stage
  5 waits on stage 4), so an Inspector who targeted the recruit the same
  night gets the post-answer result, confirmed by
  `test_investigations_wait_behind_offer_resolution`.
- **The "byte identical" message is now a single constant,
  `NO_VISIBLE_DEATH_MESSAGE = "Nobody was killed last night."`,** used for
  all three silent outcomes: no target chosen, a kill blocked by the
  Watchman, and an accepted offer. The Phase 1 messages ("Nothing happened
  last night." and "The Watchman saved X last night.") both leaked
  information and had to change, this was flagged as a known conflict in
  the Phase 0 audit and is now fixed. Verified with a direct string-equality
  test across all three cases, per the document's own instruction that this
  is "the most important test in this project."
- **A refusal or timeout death is not distinguished from a normal kill** in
  either the public event or the round log's public-facing parts, only the
  detailed round log (dead/post-game only) says an offer was involved.
- **Offer targets are validated engine-side**, not just left to the UI:
  `submit_night_action` rejects an `OFFER` aimed at anyone already
  effectively Hand.
- **`recruitment_used` is only set `True` at actual resolution** (when
  `resolve_night()` commits to opening `Phase.OFFER`), not at submission.
  A Hand can freely switch back to a kill before night resolves without
  spending the one-time offer, verified by
  `test_switching_from_offer_back_to_kill_before_resolution_does_not_spend_it`.
- **`hand_kill_target`/`hand_kill_actor` renamed to `hand_target_id`/
  `hand_target_actor_id`** since the same shared field now serves both kill
  and offer targeting, per the confirmed Phase 0 answer that Recruitment
  reuses the kill-target live-sync mechanism directly.

**Acceptance criteria, all verified:** every item in Phase 2's stated list
is covered by a dedicated test in `tests/test_recruitment.py` (49 tests
total pass across both files). One item, "Marked player's Ledger history
is unchanged," is only partially testable right now since the Ledger
itself doesn't exist until Phase 4; the current test verifies identity and
pre-existing state are untouched by recruitment, full verification is
deferred and noted here so it isn't forgotten.

**Deliberately not done in Phase 2:**
- No lobby toggle for enabling/disabling Recruitment (section 7.1). Phase
  2's acceptance list didn't ask for it and `GameConfig` doesn't have a
  `recruitment_enabled` field yet. Worth deciding explicitly before the
  Lobby phase (14) needs it.
- No player-count validation changes (still deferred from Phase 1).
- `server/`, `frontend/` still untouched beyond what already didn't need
  changes (the generic `ActionType(msg.get("action_type"))` pass-through
  in `server/main.py` already handles `"offer"` automatically once a
  frontend sends it, no server code change was needed for this phase).
  **Not pushed**, per the confirmed policy above.

## Phase 3: Engine, Show Your Hands (done)

**Files touched:** `engine/game.py`, `engine/models.py`, `tests/test_show_hands.py`
(new file, 16 tests). Also fixed `tests/test_engine.py` and
`tests/test_recruitment.py`'s shared `make_game()` helpers to disable Show
Your Hands by default, since the default threshold (6) meant most of
those pre-existing tests' small player counts would otherwise trigger it
unexpectedly and break assumptions written before this phase existed.

**New engine state:** `Phase.SHOW_HANDS` (the vocabulary table names this
one explicitly, unlike Offer). A new `_begin_round()` method is now the
real entry point for starting a round, called everywhere `_begin_night()`
used to be called directly (`start_game()`, `resolve_lynch()`). It checks
`_show_hands_eligible()` (enabled, occurrence count under 3, living
players at or below the configured threshold) and opens `Phase.SHOW_HANDS`
instead of Night when eligible. Resolving it with a HOLD majority or a tie
calls `_begin_night()` directly, not `_begin_round()` again, so eligibility
isn't re-checked mid-transition the same round.

**A real bug in Phase 2's work was caught and fixed while building this
phase.** Several places still checked literal `actor.role != Role.HAND`
instead of `effective_faction(actor) != Faction.HAND`: `hand_ready()`, the
`KILL`/`OFFER` eligibility checks in `submit_night_action()`, and the
`night_actions_total`/`done` progress calculation in `view_for()`. This
meant a Marked player who had accepted an offer could not actually
participate in choosing the next kill or offer target, directly
contradicting section 2.3's "gains... the shared kill target." All four
call sites now use `effective_faction`. Caught by re-reading Phase 2's own
code while wiring Show Your Hands into the same win-check paths, not by a
failing test, worth being more careful about going forward: **any new
literal `p.role is Role.HAND` check anywhere in the engine should be
treated as a probable bug** unless it's specifically about original role
assignment (like `GameConfig.hand_count()`, which is correctly role-based
since it describes the lobby's role configuration, not runtime status).

**Decisions made, not fully specified in the document:**
- **Show Your Hands can end early once everyone's voted**, same
  early-completion pattern as Night and day Voting
  (`show_hands_votes_complete()`). The document only states a flat 15
  second duration for this beat; extending the established pattern here
  was a judgment call, not an explicit instruction, flagged in case it's
  wrong.
- **Non-voters simply don't count toward the tally** (majority is of votes
  actually cast, not of all living players), consistent with how the day
  lynch tally already treats skipped/missing votes. No death penalty for
  not voting, unlike the Offer.
- **Individual votes are never exposed to anyone but the voter themselves**,
  not even after resolution; only the final aggregate counts become a
  public event (`"Show Your Hands: 4 HOLD, 2 CALL IT"`) and round log
  entry. Verified by `test_results_expose_counts_only_never_names` and
  `test_own_vote_is_visible_only_to_self`.
- **A successful CALL IT bypasses the normal parity win check entirely**:
  it's a direct binary read (any Hand alive at all means Black Hand wins,
  regardless of how lopsided the numbers are), not the usual `hand_count
  >= table_count` math. Verified by
  `test_black_hand_wins_even_at_bad_parity_once_called`.

**Acceptance criteria, all verified:**
- Only available at or below the configured threshold, and the threshold
  is itself configurable (`show_hands_threshold`)
- Majority CALL IT ends the game
- All Hands dead + CALL IT means Table wins; any Hand alive + CALL IT
  means Black Hand wins, confirmed even at parity that would never
  normally trigger a win
- Maximum 3 occurrences per game enforced (tested with a 3-player game
  where every round is eligible, confirming the 4th round is skipped)
- Results expose counts only through `view_for`, never names or a
  per-player breakdown

**Deliberately not done in Phase 3:**
- The private Black Hand channel is not yet gated off during Show Your
  Hands ("Hands vote individually and are forbidden from coordinating this
  vote in their private channel. Enforce it in the interface: the channel
  is disabled during Show Your Hands"). The engine phase value
  (`Phase.SHOW_HANDS`) is directly inspectable and sufficient for the
  server layer to enforce this, but the actual gating is server work
  (`server/rooms.py`'s `mafia_channel_ids`/chat broadcast), which is Phase
  5. Noting this explicitly so it isn't forgotten when Phase 5 starts.
- No lobby-facing threshold validation range (5-7 per section 7.1) is
  enforced yet; `show_hands_threshold` currently accepts any integer. Left
  for whichever phase actually builds lobby input validation.
- `server/`, `frontend/` untouched. **Not pushed**, per the confirmed
  policy.

## Phase 4: Engine, Ledger data (done)

**Files touched:** `engine/game.py`, `tests/test_ledger.py` (new file, 13
tests). No new module needed, the build plan didn't name one for this
phase, so the Ledger lives as plain fields on `Game` (`vote_history`,
`losing_side_counts`, `speaking_seconds`) plus a handful of methods, not a
separate class.

**A real gap was surfaced and resolved with the user before writing any
code:** section 6.12 wants a "speaking time" accretion mark, but this
project has zero Discord API integration and no microphone access
anywhere, so there is currently no way to actually know who's talking.
Confirmed approach: `record_speaking_time(player_id, seconds)` is a dumb
accumulator with no opinion on where the seconds come from. The real
measurement mechanism (browser mic detection, a push-to-talk button, or
something else) is an explicit open decision for whichever phase actually
builds live discussion UI (Phase 9, The Room). Noting it here again so it
isn't lost.

**Key design choices:**
- **Every vote cast is appended to `vote_history` the moment
  `submit_vote()` is called, not just the final vote per round.** A
  changed vote produces a second history entry rather than overwriting
  the first, matching "every vote every player casts is public and
  permanent" literally rather than only keeping the vote that ended up
  mattering. `self.votes` (the live tally dict) is unchanged and still
  holds only the current/final choice per round, `vote_history` is the
  permanent record layered on top.
- **A Stand Aside (`SKIP_VOTE`) is recorded in history as `target_id:
  None`**, distinct both from a real vote and from the raw `SKIP_VOTE`
  sentinel string, so a Ledger consumer can't confuse "voted for a player
  named None" with "chose not to vote."
- **"Losing side of a lynch" is computed only when a lynch actually
  resolves with a single clear leader.** Every living player whose final
  vote that round was for someone other than the person actually lynched
  gets a losing-side increment; a Stand Aside counts as no side at all,
  not a loss. Ties and no-votes produce no losing-side records for that
  round, since nothing was actually resolved to be wrong about.
- **`votes_received(player_id)` is a plain filter over `vote_history`**,
  not a separately stored/maintained data structure, since it's fully
  derivable and keeping two copies in sync would just be a bug waiting to
  happen.
- **The Ledger is exposed unconditionally in `view_for`**, not gated by
  phase, alive/dead status, or Hand/Table membership like most other
  fields, since section 2.5 is explicit that it's public and permanent
  for everyone at all times.
- **No scoring, ranking, or suspicion-computation function exists
  anywhere in the engine**, verified by an actual automated test
  (`test_no_scoring_or_ranking_function_exists_in_the_engine`) that greps
  `engine/*.py` for the exact terms the document names, not just a manual
  one-time check. Had to reword two of my own explanatory comments that
  were incidentally tripping this same grep pattern while describing the
  absence of scoring, worth remembering that comments count too, not just
  code.

**Acceptance criteria, all verified:**
- Every vote recorded with round, voter, and target
- Stand asides recorded distinctly from votes
- Losing side of lynch computed per player per round
- Speaking time accumulated per player (mechanism deferred, storage done)
- No scoring function exists anywhere in the engine (grep returns zero
  matches, enforced by a real test now, not just a one-time check)

**Deliberately not done in Phase 4:**
- No actual speaking-time measurement mechanism, confirmed deferred, see
  above.
- No frontend accretion-mark rendering (section 6.7's directional marks,
  filled bars, etc.) -- that's Phase 9, The Room. This phase only built
  the data those marks will eventually be drawn from.
- `server/`, `frontend/` untouched. **Not pushed**, per the confirmed
  policy.

## Phase 5: Server protocol (done)

**Files touched:** `server/rooms.py`, `server/main.py`, plus one necessary
cross-phase fix in `engine/game.py` (see below) and one new test in
`tests/test_recruitment.py`. This is the first phase to touch `server/`
at all -- everything before this was engine-only.

**The room loop (`run_room`) now drives two more phases**, inserted in
the correct cascade position so a single pass can fall through multiple
transitions the way NIGHT to DAY_DISCUSSION already did:
`SHOW_HANDS -> NIGHT -> OFFER -> DAY_DISCUSSION -> VOTING`. Show Your
Hands reuses the existing `_countdown`/`early_end_event` pattern exactly
like Voting does (real timer, early exit once everyone's voted). The
Offer also reuses `_countdown`/`early_end_event`, but needs one extra
guard Voting/Discussion never needed: a response can pre-empt the timer
entirely (`respond_to_offer` transitions the phase away from `Phase.OFFER`
before the natural 30s elapses), so `run_room` only calls
`resolve_offer_timeout()` if the phase is *still* `Phase.OFFER` after the
countdown returns, otherwise it was already resolved by an actual answer.

**Two new WebSocket message types:** `offer_response` (`{"accepted":
bool}`, calls `respond_to_offer`) and `show_hands_vote` (`{"choice":
"hold"|"call_it"}`, calls `submit_show_hands_vote`). No new message type
was needed for *submitting* an offer -- `night_action` with
`action_type: "offer"` already worked automatically once Phase 2 added
`ActionType.OFFER`, since `server/main.py`'s handler was already generic.

**The Black Hand channel is disabled during Show Your Hands** by making
`Room.mafia_channel_ids()` return an empty set during `Phase.SHOW_HANDS`,
rather than adding a separate check. This one change correctly blocks
both sending (the existing `mafia_chat` handler already checks membership
against this set) and the broadcast recipient list, with no separate
code path to keep in sync. A slightly more specific error message
("disabled during Show Your Hands" instead of the generic "not in the
channel") was added on top for a sender who tries anyway. One
acknowledged, minor, unhandled edge case: a Hand who reconnects *during*
Show Your Hands won't get their chat history re-synced until the phase
ends or a new message is sent, since the reconnect-sync call also goes
through the now-empty `mafia_channel_ids()`. Not fixed, spec doesn't ask
for it, rare enough to accept.

**A real hang bug was found and fixed in the engine while wiring this
in, not caught by any existing test:** if the offer *recipient*
disconnects during their own 30-second response window, the generic
`handle_disconnect_removal` path would have just marked them dead without
ever calling `_resolve_offer`, leaving `game.phase` stuck at `Phase.OFFER`
forever -- nothing in `run_room` would ever move it again, since the
timeout guard only fires from inside the room's own countdown loop, and
that loop had already moved on. Fixed: `handle_disconnect_removal` now
special-cases this one situation and resolves the offer as a refusal
(same as a timeout) instead of taking the generic path. Covered by
`test_recipient_disconnecting_during_offer_resolves_it_as_a_timeout` in
`tests/test_recruitment.py`. This is a second example (after Phase 3's
`effective_faction` gap) of a real correctness bug surfacing only once a
later phase actually exercised a code path the way a live client would,
not from the original phase's own tests -- worth staying alert for more
of these as Phase 6+ starts exercising the engine from an actual browser.

**Verified live against a running server, then the scripts were deleted
per the phase's own acceptance criteria:**
- Offer delivered only to the recipient: every other player's view
  (bystanders, the offering Hand, the other Hand) confirmed to never
  contain `offer_pending`.
- The Black Hand channel is genuinely disabled during Show Your Hands: a
  Hand's `mafia_chat` attempt during that phase gets the specific error
  message, then succeeds normally once the phase ends.
- Marked player gains channel access on acceptance: confirmed both
  structurally (`allies` list) and functionally (an actual chat message
  sent and received after accepting).
- The offer timeout path specifically (nobody answers, server's own
  30-second countdown fires `resolve_offer_timeout()`): confirmed with
  `OFFER_SECONDS` temporarily shrunk for the test, then reverted. Two
  bugs were found and fixed in the *test scripts themselves* while
  chasing this down (a stale queued message being misread as the
  resolution, and an unbuffered per-socket backlog), not in the server --
  worth remembering that a `night`-phase-looking result right after
  submitting an offer is almost always the leftover pre-transition
  broadcast, not a real regression, given how fast `resolve_night`
  transitions into `Phase.OFFER` once the shared target is set.

**Deliberately not done in Phase 5:**
- No lobby-side way to configure `show_hands_enabled`/`show_hands_threshold`
  from the client yet; `start_game` still only reads `role_counts` and the
  two existing timer fields. The engine defaults (on, threshold 6) already
  match section 7.1's stated defaults, so this isn't broken, just not yet
  host-configurable over the wire. Left for Phase 14 (the Lobby).
- No `recruitment_enabled` toggle either, consistent with it being
  deferred since Phase 2.
- `frontend/` still completely untouched. **Not pushed**, per the
  confirmed policy -- the live site still can't start a game at all with
  the current deployed frontend's stale role names, and this phase adds
  two more message types the frontend doesn't know about yet either.

## Phase 6: Design tokens (done)

**Files touched:** `frontend/index.html`, `frontend/src/index.css` (full
rewrite), `frontend/src/components/Avatar.jsx` (full rewrite),
`frontend/src/components/Timer.jsx` (full rewrite),
`frontend/src/components/PlayerRow.jsx` (full rewrite),
`frontend/src/components/RoleConfig.jsx`, `frontend/src/components/MafiaChat.jsx`,
`frontend/src/roles.js` (full rewrite), `frontend/src/App.jsx` (full rewrite).

**The token system (section 4), verified by grep:** exactly four hex
colors exist (`--room #0f1216`, `--paper #e4dfd3`, `--ink #14171b`, `--lamp
#c9a227`) plus exactly five documented `color-mix()` derivatives
(`--paper-edge`, `--ink-quiet`, `--ink-faint`, `--room-lift`,
`--lamp-quiet`). No hex color exists anywhere outside `index.css`. Every
`border-radius` is `0`, every `box-shadow` is a flat 2px offset or `none`
(no blur term), zero gradients. Two font families (Newsreader serif for
testimony, Space Mono for the record) loaded via Google Fonts, split
strictly by the type-scale classes (`.t-whisper` through `.t-verdict`).
Spacing is entirely gated through `--tension` (0 today, no round-aware
component sets it yet -- noted below). Four motion keyframes
(`bh-placed/stamped/unfolded/taken`) exist as utility classes with a
`prefers-reduced-motion` override. Lamp appears in exactly three places:
the timer's last-10-seconds state, and the two Black Hand private-surface
rules in `.mafia-chat`.

**A real functional bug was found and fixed that went beyond this
phase's stated CSS-only scope, for the same reason Phase 1 needed one
forced cross-file rename: the frontend had never been touched by Phases
1-5 at all.** `roles.js` and `RoleConfig.jsx`'s `CONFIGURABLE_ROLES` still
used the pre-migration role keys (`villager/detective/doctor/mafia/godfather`).
Since the server's `ROLE_BY_NAME` only recognizes
`civilian/inspector/watchman/hand` (Phase 1), the host's role-count
config UI was silently sending a payload the server would filter down to
nothing -- no game could ever be started from the live frontend, at all,
regardless of styling. Fixed: `roles.js` rewritten with the correct role
keys and Blackhand labels/text (Civilian/Inspector/Watchman/Hand, no
Godfather), `RoleConfig.jsx`'s `CONFIGURABLE_ROLES` updated to
`["hand", "inspector", "watchman"]`. `App.jsx` was audited and fixed the
same way: `your_role === "mafia"` checks now read `"hand"`,
`mafia_kill_target_id/name` reads now read `hand_target_id/name`,
`mafia_reveal` reads now read `hand_reveal`, `winner === "mafia"` now
reads `winner === "hand"`, the dead `known_mafia` field (no Godfather
equivalent exists) was removed entirely, and the default lobby role-count
state changed from `{ mafia, detective, doctor, godfather }` to
`{ hand, inspector, watchman }`. Verified live: a full
create-room-through-role-assignment round trip against a running server
with the new role-count keys correctly produces `hand`/`inspector`/
`watchman`/`civilian` roles and a working `allies` list for both Hand
players, then the disposable verification script was deleted per
established practice.

**Also removed as part of the same necessary-for-function pass:** every
`<div className="card-tab tab-*">` label in every component (those
classes were deliberately deleted from the new `index.css`, since the new
system has no per-card colored-tab concept). Each card's existing `<h2>`
now serves as its own header (the type-scale/border-bottom styling on
`h2` already does this job); cards that only had a tab and no separate
`h2` (Join, Your Role, Lobby) got a plain `h2` added in the tab's place.
`PlayerRow`'s `danger` prop (a kill/protect/vote color-severity variant)
was deleted along with its one remaining CSS hook, per section 4.2's "no
red anywhere, the weight of a choice comes from context and copy, never a
color" rule -- confirmed via grep that no `danger` prop reference remains
anywhere in `frontend/src`.

**Decisions made, not fully specified in the document:**
- **The lobby's minimum player-count gate stayed at 4**, not the 6 from
  section 3.1's player-count table. That table's floor/ceiling was already
  flagged as not-yet-enforced back in Phase 1 (`GameConfig.validate()` has
  no floor/ceiling), and adding it here would be scope creep into
  server-side validation this phase doesn't touch. Left as a known,
  pre-existing gap, not a new one.
- **No placeholder UI was built for `Phase.SHOW_HANDS` or `Phase.OFFER`.**
  Both phases exist in the engine and the room cascade (Phases 2, 3, 5)
  and the live verification round actually entered `show_hands` directly
  (6 players hits the default threshold), but there is deliberately no
  vote-casting or offer-response panel yet -- that's Phase 9/10's Show
  Your Hands beat and Phase 12's Offer UI, not this phase's file list.
  During those phases today, a player sees their role card and the event
  log but no action panel, which is an accurate "not built yet" state, not
  a crash: nothing in `App.jsx` throws or renders blank/broken markup for
  those phase values, confirmed by the live round above landing on
  `show_hands` without error. Deliberately not papered over with "coming
  soon" placeholder copy, per the standing "no half-finished
  implementations" rule -- an honest gap beats a fake one.
- **`--tension` is defined and consumed but nothing sets it away from 0
  yet.** No component in the current tree is round-number-aware in a way
  that would justify writing that wiring now; the token chain
  (`--tension` -> `--tension-scale` -> every `-t` spacing variable and
  `--motion-duration`) is verified live end-to-end by construction (it's
  plain CSS `calc()`, not JS), just inert until some later phase's
  component actually assigns `--tension` from `night_number`/round count.

**Acceptance criteria, all verified:**
- `npm run build` succeeds with zero errors.
- Exactly 4 hex colors and exactly 5 `color-mix()` derivatives exist in
  the whole tree, both confirmed by grep, with zero hex colors outside
  `index.css`.
- Zero non-`0` `border-radius`, zero blurred `box-shadow`, zero gradients.
- Zero occurrences of `godfather|villager|mafia|detective|doctor` as
  role/display vocabulary anywhere in `frontend/src` (protocol-plumbing
  strings that must match the server's existing WebSocket message
  contract unchanged -- `mafia_chat` the message type, `mafiaChat`/
  `MafiaChat` the existing component/prop names, `mafia_room_code`/
  `mafia_player_id` the localStorage keys -- were deliberately left alone,
  since renaming them is a protocol change with no visible-copy benefit
  and out of this phase's scope).
- Zero em dashes anywhere in `frontend/src`.
- Zero references to the deleted `card-tab`/`tab-brass`/`tab-blood`/
  `tab-steel` classes anywhere in `frontend/src`.
- `tests/` still 79/79 passing (no engine changes this phase).
- Live verification: a full 6-player game created and started against a
  running server using the new role-count vocabulary correctly assigns
  `civilian`/`inspector`/`watchman`/`hand` roles and populates `allies`
  for Hand players, landing in `Phase.SHOW_HANDS` without any client-side
  error.

**Deliberately not done in Phase 6:**
- The hand-mark logo/wordmark treatment (Phase 7).
- Any beat-specific component (Letter, Room, Crossing, Table, Offer UI,
  Reading, Lobby redesign) -- Phases 8-14. The current tree is still the
  pre-Blackhand structural shape (`Lobby`/`NightPanel`/voting/day/game-over
  panels), now correctly tokened and vocabulary-correct, not yet
  reorganized into the 11-beat sequence.
- Sound (Phase 11) -- `sound.js` is untouched.
- Any Show Your Hands or Offer interactive UI, per above.
- Player-count floor/ceiling validation (still deferred from Phase 1).
- **Not pushed**, per the confirmed policy. This is the first frontend
  phase, and while a game can now genuinely be started and played through
  night/day/voting/game-over with correct vocabulary, Show Your Hands and
  Offer -- both of which the engine can enter under normal play at typical
  player counts -- still have no interactive UI at all, so the frontend is
  not yet "far enough along to actually work end to end." Hold continues.

## Phase 7: The logo (done)

**Files touched:** `frontend/src/components/Mark.jsx` (new), `frontend/public/favicon.svg`
(replaced), `frontend/index.html` (added the `<link rel="icon">` that was
missing entirely, so the favicon was previously unused dead weight),
`frontend/src/index.css` (`.mark-lockup`/`.mark-lockup-stacked`/
`.mark-lockup-horizontal`/`.mark-on-paper`/`.wordmark` rules), `frontend/src/App.jsx`
(mark wired into the Lobby).

**Context note:** the actual `BLACKHAND.md` text had gone missing from
this session's recoverable context between Phase 6 and Phase 7 (an
earlier compaction dropped the original paste and it wasn't in either
session's stored transcript). Per the document's own "ask before
deviating" rule, this was flagged and the user re-pasted the full
document rather than letting Phase 7 proceed from a guessed
reconstruction of section 5 and Phase 7's acceptance list.

**Building the mark itself was the real work of this phase.** Hand
authoring a single closed SVG path for an asymmetric five finger hand
by typing raw bezier coordinates blind was judged too error prone to
trust without a way to actually see the result, so a disposable Python
pipeline was built in the scratchpad (not committed, per the document's
own "no external assets" and "single SVG path" rules, only the tooling
used to arrive at one honestly): `shapely` to construct the palm, wrist,
and five digits as a union of capsule polygons with deliberately uneven
finger lengths, angles, and a distinctly angled thumb, `cairosvg` (tried,
unusable, no native Cairo library on this machine) then `svglib` +
`reportlab` (usable, rendering to PDF rather than PNG sidesteps the same
missing Cairo dependency) to actually see intermediate results and catch
a real defect: the first two geometry attempts produced a visible
self-intersecting crack at the thumb-to-palm join, confirmed to be a
genuine geometry gap (not a smoothing artifact) by rendering the raw
unsmoothed union polygon directly. Fixed by widening the thumb's base
overlap into the palm rather than by disguising it with heavier
smoothing. The final path was fit as a closed Catmull-Rom spline through
34 simplified anchor points (a `poly.simplify()` pass, not the raw ~76
point capsule-union boundary), producing a compact, genuinely curved
(`C` commands, not a dense polyline of `L` segments) path, 1266 characters,
one `<path>`, one `d` attribute, no groups, no strokes. Legibility at
24px and asymmetry at 200px were both verified by rasterizing the exact
same curve-fit data (not a separate approximation) with Pillow at 24x24
and 200x200 before the path was ever written into a component.

**Design decisions made, not fully specified in the document:**
- **The mark is rendered via `fill="currentColor"`**, not a hardcoded
  hex, so a single `Mark.jsx` works in both the `--room`-on-`--paper` and
  `--paper`-on-`--room` cases the document requires (section 5.5) by
  inheriting whatever color the caller sets, the same pattern
  `Avatar.jsx` already established in Phase 6. `favicon.svg` is the one
  necessary exception: a static file outside any React color context, so
  its fill is hardcoded to `--paper` on a `--room` background (visible
  against a light or dark browser tab chrome either way).
- **Hand geometry: normalized to occupy exactly 78% of a 100-unit square
  viewBox height, centered on the shape's centroid rather than its
  bounding box**, a literal reading of "optically centered rather than
  mathematically centered." Bounds after normalization: x 13.1-80.8, y
  9.6-87.6, confirming it clears the viewBox edges with margin at every
  size.
- **Wordmark size capped at `--t-said` (24px, at the low end of that
  scale), not `--t-event`**, because the Waiting Room already uses
  `--t-event` for the room code, and section 4.3 is explicit that only
  one element above `--t-said` may exist on screen at once. The wordmark
  in the stacked lockup deliberately stays secondary to the room code.
- **Where it's actually wired in Phase 7 is narrower than section 5.6's
  full list, because three of the four listed locations don't have a
  component yet.** The Waiting Room placement (stacked lockup, above the
  room code mention, inside the current `Lobby` function since Phase 14
  hasn't rebuilt it into its own beat component) and the favicon are both
  live today. The Crossing (mark only, 40% opacity, under a Crossing
  component that is Phase 10's work) and The Reading's closing frame
  (Phase 13's work) do not exist as components yet, so the mark
  necessarily doesn't appear there yet either, exactly the same kind of
  gap Phase 6 left for Show Your Hands and Offer UI. "Page title" from
  the same bullet is satisfied by the existing `<title>Blackhand</title>`
  text (unchanged); "share card" doesn't apply, no social-card
  generation exists anywhere in this project.
- **A real, unrelated contrast bug was found and fixed one line away from
  where the mark was placed:** `.room-code` hardcoded `color: var(--paper)`,
  which is correct in the topbar (room ground) but made the room-code
  mention inside the Lobby's `.card` (paper ground) paper-on-paper,
  invisible. The mark's placement directly above that exact line is what
  surfaced it. Fixed by removing the hardcoded color and letting it
  inherit from context (`--paper` from `body` in the topbar, `--ink` from
  `.card` inside the Lobby), the same currentColor pattern used
  throughout this phase.

**Acceptance criteria, all verified:**
- Single SVG path, no groups, no strokes: confirmed by grep on both
  `Mark.jsx` and `favicon.svg` (`<g` and `stroke=` both return nothing,
  exactly one `<path` in each file).
- Visibly asymmetric at 200px: confirmed via a direct Pillow raster of
  the final curve-fit path at 200x200, reviewed directly (uneven finger
  lengths, a thumb set at a clearly different angle and base position
  than the fingers, a bent pinky).
- Still legible at 24px: confirmed via a direct Pillow raster of the same
  path at 24x24, reviewed directly, still unambiguously an open hand with
  a distinct thumb.
- Three lockups implemented: `lockup="mark"`, `"stacked"`, `"horizontal"`
  all exist in `Mark.jsx` with the document's exact gaps (24px stacked,
  16px horizontal). Only `"mark"` (favicon) and `"stacked"` (Waiting
  Room) have a live call site today, `"horizontal"` has no caller yet
  since nothing in section 5.6's list needing it (header, share card) is
  built, consistent with the rule that it should appear nowhere outside
  those four locations.
- Renders in `--room` and `--paper` only, never `--lamp`: confirmed by
  grep, `--lamp`/lamp does not appear anywhere in `Mark.jsx` or
  `favicon.svg` except in an explanatory code comment.
- Appears in exactly the four locations in 5.6 and nowhere else: grep
  confirms exactly one import and one render call site (`App.jsx`'s
  Lobby) plus the favicon file, both accounted for above; no header,
  navigation, or in-play watermark usage exists anywhere in the tree.
- `npm run build` succeeds with zero errors. `tests/` still 79/79 passing
  (no engine changes this phase). Zero em dashes anywhere touched this
  phase, confirmed by grep.

**Deliberately not done in Phase 7:**
- The mark does not yet appear at The Crossing or The Reading, since
  neither component exists yet (Phases 10 and 13).
- No share card / Open Graph image generation exists to put a horizontal
  lockup on, consistent with nothing in this codebase producing social
  cards at all.
- The disposable geometry-construction script (shapely/svglib/Pillow
  pipeline) was not committed, per the same "verify live, then delete
  the script" discipline used for Phase 5's WebSocket verification
  scripts. Only the resulting path data and the shipped `Mark.jsx`/
  `favicon.svg` are part of the repository.
- **Not pushed**, per the confirmed policy. The frontend still has no
  Show Your Hands or Offer UI (Phase 6's carried-over gap).

## Phase 8: The Letter component (done)

**Files touched:** `frontend/src/components/Letter.jsx` (new), `frontend/src/index.css`
(`.letter`/`.letter-table`/`.letter-hand`/`.letter-page` rules and the
`bh-letter-unfold` keyframe), `frontend/src/App.jsx` (role reveal and
investigation results now render through `Letter`).

**The component itself is small and does not own any dismissal
judgment.** `Letter({ faction, children })` renders whatever it's given
inside a `.letter` shell; there is no built-in close button, no outside
click handling, nothing that could close it. That satisfies "does not
close on outside click" by construction rather than by a guard, verified
by grep finding zero click-outside/dismiss code in the file at all. Any
future beat that needs a deliberate dismiss (Delivery's self-closing 4
seconds, the Reading's final frame) adds that behavior itself, on top of
this component, when that beat is actually built.

**The deckle edge is a fixed CSS `clip-path: polygon()`,** not a
per-instance computation, so "identical on every letter" is true by
construction rather than by convention: there is exactly one polygon
definition in `index.css` and every `.letter` uses it. Depth stays within
the document's stated 3px. The right edge is untouched (100% straight).

**The unfold animation is 420ms, `var(--ease-soft)`, hardcoded rather
than reading `--tension`,** matching both the literal number in section
4.5 and the existing `.motion-unfolded` utility Phase 6 already built
under the same name from section 4.7's motion vocabulary table (Phase 6
evidently anticipated this component). The "4px seam" detail is
approximated with a `scaleY(0.02)` starting keyframe rather than a
height-based animation: a height-based version could hit exactly 4px,
but only by animating to a guessed oversized `max-height` target, which
visibly finishes well before the nominal 420ms for typical content and
would fail "matches spec exactly" on duration. `scaleY` keeps duration
and easing exact at the cost of the starting sliver being an
approximation of 4px rather than a guaranteed one, true for a roughly
150-250px tall letter and noted here as a judgment call, not hidden.
`.letter` was added to the same `prefers-reduced-motion` block that
already disables `.motion-unfolded`, so it also snaps open instantly
under reduced motion.

**No border, no shadow**, per section 4.5's explicit exception to the
general "paper gets a 2px offset shadow" rule (`.card`'s convention):
Letters sit directly on `--room` and contrast alone does the separation.

**The Black Hand variant (`faction="hand"`) is `--room` ground, `--lamp`
text, permanently**, matching section 4.2's "the Black Hand never gets
paper" rule. Its `.muted`/`h2` treatment was folded into the same rule
`.mafia-chat` already used in Phase 6 (`color: var(--lamp-quiet)`), plus
one fix applied to both surfaces at once: `h2`'s `border-bottom` is
hardcoded to `--ink-faint` globally, which read as a pale, off-theme line
on a `--room` background. Both `.mafia-chat h2` and `.letter-hand h2` now
override it to `--lamp-quiet`. This exact inconsistency already existed
in `.mafia-chat` since Phase 6, unnoticed until building the letter-hand
variant surfaced the same pattern; fixed for both together rather than
just the new one.

**"Role reveal, investigation result, and offer all use this single
component" was verified as three real integration points, not just
component-API compatibility, with one honest exception:**
- **Role reveal**: the persistent "Your Role" card (still always-visible
  for the whole round, since no round-beat orchestration exists yet to
  drive Delivery's actual 4-second self-closing behavior) now renders
  inside a `Letter`, `faction` computed from `effective_faction` (role is
  `"hand"` or `marked` is true), not literal role, matching the pattern
  established in the engine since Phase 3.
- **Investigation result**: this is a real, and previously unnoticed,
  violation of section 4.5 fixed by this phase, not a preexisting
  correct thing that just needed a new wrapper. `state.private_log`
  entries were rendered as plain `<p className="private-log">` lines
  bundled inside the same shared `.card.log` container as public events,
  literally the "feed line" the document explicitly forbids for private
  information. `EventLog` now handles only public `events`; a new
  `InvestigationLetters` component renders each `private_log` entry as
  its own `Letter` (`faction="table"`, since only the Inspector, a Table
  role, ever receives one). Verified live against a running server: a
  7-player game, an Inspector's investigation submitted alongside a
  Watchman protect and a Hand kill so night actually resolves, and
  `private_log` confirmed to arrive as `["Investigation of X: INNOCENT"]`
  exactly as `InvestigationLetters` expects, then the script was deleted.
- **The offer**: intentionally NOT wired to any live UI this phase. There
  is no Offer beat screen anywhere in the app (Phase 6 already deferred
  this entirely, and building one now would duplicate Phase 12's exact
  stated scope: the fully-black room, verbatim copy, 30 second timer,
  Take it/Refuse, the struck wire, the permanent interface conversion on
  accept). `Letter.jsx`'s `faction="hand"` variant is exactly the visual
  surface Phase 12 will need, and that readiness was confirmed by the
  existing role-reveal integration already exercising the hand variant
  live, but no offer-specific screen exists yet. This is the one
  acceptance line met only partially, said outright here rather than
  glossed over.

**Verification note:** the visual result (deckle notches, the unfold
motion, the two color variants) was reasoned through and grep-verified
for structural correctness, but not seen rendered in an actual browser.
No screenshot or headless-browser tool is available in this environment,
unlike Phase 7's hand mark, which had a working SVG-to-raster pipeline
built specifically to get real visual feedback before the path was
committed. Said here rather than implied by silence.

**Acceptance criteria:**
- Unfold animation: 420ms, `var(--ease-soft)` (`cubic-bezier(0.16, 1,
  0.3, 1)`, matching the document's literal curve), scaleY approximation
  of the 4px seam. Duration and easing exact; starting pixel height an
  approximation, noted above.
- Deckle edge on left only, identical across instances: confirmed by
  construction, one static `clip-path: polygon()` shared by every
  `.letter`, right edge untouched.
- Does not close on outside click: confirmed by grep, no dismiss/outside
  click code exists in `Letter.jsx` at all.
- Black Hand variant renders room ground with lamp text: `.letter-hand`
  sets `background: var(--room)`, `color: var(--lamp)`, confirmed live
  via the role-reveal integration for a Hand-role player during the same
  verification run.
- Role reveal and investigation result both genuinely use this component
  in the running app, confirmed live. Offer does not yet, confirmed
  honestly above rather than claimed.
- `npm run build` succeeds. `tests/` still 79/79 (no engine changes this
  phase). Zero em dashes, confirmed by grep across every file touched.

**Deliberately not done in Phase 8:**
- No Offer beat screen, per above (Phase 12).
- No Delivery-beat orchestration (role reveal appearing once at round
  start and self-closing after 4 seconds per section 6.2). The build
  plan's Part 8 phase list does not name a dedicated phase for Delivery
  or First Light at all (only Phases 8 Letter, 9 Room, 10
  Crossing/Table, 12 Offer, 13 Reading are listed); this is a real gap in
  the stated plan worth surfacing to the user rather than silently
  picking a phase to fold it into.
- No sound (`"Sound: one paper unfold, 380ms"`), consistent with Phase
  11 owning all audio and nothing else in this codebase playing sound
  yet either.
- **Not pushed**, per the confirmed policy. Same standing gap as
  Phases 6 and 7: Show Your Hands and Offer still have no interactive
  UI.

## Phase 9: The Room (done)

**Files touched:** `frontend/src/phases/Room.jsx` (new, first file in a new
`frontend/src/phases/` directory, the location the build plan specifies
for beat components from here on), `frontend/src/index.css`
(`.room-feed`/`.room-feed-timer`/`.room-feed-list`/`.marks`/`.mark`/
`.mark-bar` rules), `frontend/src/App.jsx` (the old inline
`day_discussion` block replaced with `<Room>`, and the shared header
timer now skips rendering during `day_discussion` since Room owns its
own).

**Room.jsx replaces the pre-Blackhand discussion screen's plain
`PlayerRow` roster with a vertical column of `Letter`s**, one per player,
each carrying that player's accumulated marks, per section 6.6's literal
"player letters in a column." Living and dead players both appear (a
dead player's mark for eliminated is part of the same accretion strip,
not a separate panel), consistent with 6.12's "player letters start
blank and are never cleaned."

**Accretion marks (section 6.12) are computed live from the real Ledger
data already built in Phase 4**, not placeholders: votes cast, votes
received, stand asides, and times on the losing side of a lynch all come
straight from `state.ledger.votes` and `state.ledger.losing_side_counts`.
Verified live against a running 7-player game that `state.ledger`
actually reaches the client with the exact shape `Room.jsx` expects
(`votes: []`, `losing_side_counts: {}`, `speaking_seconds: {}` this
early in a fresh game, all populated once real play generates them,
confirmed both by this run and by reading `submit_vote()`'s literal dict
shape in `engine/game.py`).

**One mark in the spec's list is intentionally approximated, said
outright rather than faked:** "votes cast, as directional marks toward
the target's seat position" needs a seat angle for every player, and
seats do not exist until The Crossing assigns them (Phase 10, which
hasn't run yet at this point in the round). Votes cast render as a plain
count (`→3`) instead of a compass-style mark toward a seat. This will
become literal once Phase 10 exists and a real seat layout can be passed
down.

**Speaking time renders as a filled bar already**, per section 6.12's
"filled bar" instruction, scaled against the current discussion timer's
total duration, but will read as empty for every player until some
phase actually calls `record_speaking_time` from a live measurement
source, which per Phase 4's notes is still an explicitly open decision
(no Discord integration, no mic access anywhere in this project).

**The Room's own Timer, not the shared header one, satisfies "top right,
quiet until 10 seconds remain, then lamp":** `Room.jsx` now renders its
own `<Timer>` at the top of its feed, reusing the exact `Timer.jsx`
component and `colorFor()` threshold Phase 6 already built
(`seconds <= 10 ? var(--lamp) : var(--ink-quiet)`), and `App.jsx`'s
shared header timer was given one extra condition
(`state.phase !== "day_discussion"`) so the countdown isn't shown twice.
"Audible" (the ticking sound) is Phase 11's job; nothing in this project
plays sound yet.

**Spacing responds to `--tension` because it uses the same tension-scaled
tokens every other phase already uses**, not a new mechanism: `.room-feed`
and `.room-feed-list` both gap on `var(--space-2-t)`. No new tension
wiring was needed or added; this was true by using the existing system
correctly, which is itself worth confirming rather than assuming.

**Acceptance criteria:**
- Vertical feed, scrollable: confirmed structurally. The whole app is a
  normally-scrolling page (`#root` has no `overflow: hidden` anywhere),
  and `Room.jsx` adds no fixed-height or scroll-trapping container of its
  own, so this is true by not fighting the page's default behavior.
- Player letters carry marks: confirmed live, using real Ledger data
  reaching the client in the exact shape expected, verified via a live
  7-player run, not just a build check.
- Timer goes lamp and audible at exactly 10 seconds: the lamp threshold
  is exact (reusing Phase 6's already-correct `Timer.jsx`), confirmed
  present in `Room.jsx`'s own render tree rather than only the shared
  header. Audible is not yet true, Phase 11 owns sound entirely and
  nothing in this codebase plays audio yet, said here rather than
  claimed.
- Spacing responds to `--tension`: confirmed, `.room-feed`/
  `.room-feed-list` use the tension-scaled spacing tokens.
- `npm run build` succeeds. `tests/` still 79/79 (no engine changes this
  phase). Zero em dashes, confirmed by grep.

**Deliberately not done in Phase 9:**
- Directional (seat-position) vote marks: plain counts for now, per
  above, until Phase 10 gives seats an angle to point toward.
- Sound (the audible tick at 10 seconds, ambient bed): Phase 11.
- No live speaking-time source exists yet to actually fill the speaking
  bar, consistent with the Phase 4 gap.
- **Not pushed**, per the confirmed policy. Same standing gap as
  Phases 6 through 8: Show Your Hands and Offer still have no
  interactive UI.

## Phase 10: The Crossing and The Table (done)

**Files touched:** `frontend/src/phases/Crossing.jsx` (new), `frontend/src/phases/Table.jsx`
(new), `frontend/src/index.css` (`.crossing*`/`.table-*`/`.stand-aside*`
rules and three new keyframes), `frontend/src/App.jsx` (seat-order
capture, the client-side Crossing timer, and a full-takeover early return
for both beats that bypasses the normal header/screen wrapper entirely).

**The Crossing has no engine phase of its own, and this phase's file
list is frontend-only, so it is implemented as a client-side timed
overlay, not a server-driven beat.** The engine goes straight from
`day_discussion` to `voting`; there is no `Phase.CROSSING`. `App.jsx`
detects that exact transition (a dedicated `prevPhaseForCrossing` ref,
kept separate from the existing `prevPhase` ref used for chimes so the
two effects can't race on which one updates first) and holds a local
`showCrossing` flag true for a flat 3000ms `setTimeout` before revealing
the real Table. This is a deliberate scope reading, not an oversight:
adding a genuine `Phase.CROSSING` would mean touching `engine/` and
`server/`, neither of which this phase's stated files include, and the
document's own "ask before deviating" rule cuts toward not doing that
without being asked, not toward doing it. **The real cost of this
choice, stated plainly:** the server's 45 second voting countdown starts
the instant `Phase.VOTING` begins, underneath the Crossing overlay, so a
player's usable voting window is the configured duration minus the 3
seconds they spend looking at the Crossing, not the full configured
number. The timer that eventually appears is accurate to what it shows,
it just starts a few seconds into an already-running clock. A fully
correct implementation needs a real `Phase.CROSSING` engine state and
belongs to a future phase, flagged here rather than silently absorbed.

**Both beats render as a full takeover.** `App.jsx` now has an early
return, before the normal `.screen`/`header`/`EventLog` render tree,
that fires whenever a living player is in `voting`: it renders only
`Crossing` or `Table`, nothing else, satisfying "no chat, no back, no
tabs, no side panel, the rest of the application does not exist while
you are here" by construction rather than by hiding elements with CSS.
The one deliberate exception is the `sr-only` live announcement region,
duplicated into this branch rather than restructured around, since an
invisible screen-reader channel isn't "the rest of the application" in
the sense the document means. A dead player still sees the existing
`DeadPanel` with normal chrome during voting, unchanged from before this
phase; nothing in the document describes spectator-specific behavior
here, so this scope was left alone.

**Seats never reorder, and this is a real per-game guarantee, not a
per-render one:** `App.jsx` captures `state.players.map(p => p.id)` into
`seatOrderRef` exactly once, the first time a non-lobby state is seen
after the game starts, and both `Crossing` and `Table` are handed that
frozen array rather than reading `state.players`' order directly. A
dead player's angle in the ring stays reserved and renders as an empty
dashed marker (`table-seat-empty`) rather than letting the remaining
seats close the gap, matching "seats never reorder... reordering
destroys the spatial memory that makes the ring a place" literally.

**Honest limit on verification: "seats never reorder... verified across
a full 5 round game" could not be fully verified the way the document
asks.** Seat position is a pure client-rendering property with no
server-observable signal, and this environment has no browser or
screenshot tool (the same gap noted in Phase 8). What was actually done:
a live 7-player game was run through night, discussion, and voting
against a real server to confirm `state.players`, `state.votes`, and the
transition sequence all arrive in the shape `Table.jsx` and `Crossing.jsx`
assume; and the seat-stability guarantee itself was verified by code
reading, not pixel comparison, confirming `seatOrderRef` is written
exactly once (guarded by `if (!seatOrderRef.current)`) and never
consulted from `state.players`' own order anywhere in either component.
That is a real guarantee by construction, but it is not the same thing
as watching five actual rounds render in a browser and confirming no
seat visibly moved, and this document's own discipline is to say that
difference out loud rather than let "verified" imply more than it does.

**Votes land staggered at 220ms, driven by a real reveal queue, not a
CSS delay trick:** `Table.jsx` diffs incoming `state.votes` against a
`knownRef` set of voter ids already seen, queues any new ones, and pops
the queue on a 220ms `setTimeout` chain, only counting a vote toward a
seat's visible tally once it's been popped. Confirmed live that
`state.votes` itself arrives as the plain `{voter_id: target_id}` dict
the queue logic assumes. The tally badge remounts on each count change
(`key={count}`) to retrigger the existing `.motion-stamped` utility from
Phase 6, satisfying "with the wooden stamp" visually; the sound itself
is Phase 11's job.

**Pulse tempo is tied to remaining time using absolute thresholds**, the
same pattern `Timer.jsx`'s lamp-at-10-seconds cutoff already established
in Phase 6, not a percentage of whatever voting duration the host
configured: linear from a 3000ms period at 45 seconds or more remaining
down to a 500ms period at 8 seconds or less. "Nearly inaudible at 45,
impossible to ignore at 8" is audio language describing what Phase 11
will layer onto this same pulse; this phase only owns the visual rate.

**The Table inverts** (`--ink` ground, `--paper` text) via a dedicated
`.table-screen` rule, matching section 4.9's explicit statement that this
is the only Table-facing surface that looks like the Black Hand's own,
never explained in copy and none was added here either.

**Acceptance criteria:**
- Crossing runs 3 seconds with no skip control present in the DOM:
  confirmed by grep, `Crossing.jsx` contains no `button`, `<a>`, or
  `onClick` at all, and the 3000ms hold is enforced by `App.jsx`'s own
  `setTimeout`, not anything inside the component that could be
  bypassed.
- Ring assembles at 220ms per seat: confirmed, `animationDelay: i * 220ms`
  on each `.crossing-seat`.
- Table ground is inverted: confirmed, `.table-screen` sets `--ink`
  background and `--paper` text.
- Seats never reorder across rounds: guaranteed by construction
  (captured once, never re-derived), not independently confirmed by
  browser observation, stated honestly above.
- Votes land staggered at 220ms with sound: the 220ms stagger is real
  and queue-driven, confirmed live against real `state.votes` data.
  Sound is Phase 11's, not built or claimed here.
- No chat, no navigation, no side panel reachable while at the Table:
  confirmed structurally, the full-takeover early return in `App.jsx`
  renders nothing else during a living player's `voting` phase.
- Pulse tempo tied to remaining time: confirmed, `pulseDurationMs()`
  reads `timer.secondsLeft` directly and drives `--pulse-duration`.
- `npm run build` succeeds. `tests/` still 79/79 (no engine changes this
  phase, confirmed deliberately, since this phase's whole point was
  proving the Crossing needs none). Zero em dashes, zero non-zero
  `border-radius`, confirmed by grep across every file touched.

**Deliberately not done in Phase 10:**
- No genuine `Phase.CROSSING` engine state, per above; the client-side
  timing shim costs roughly 3 seconds of the configured voting window on
  every round, a real and permanent trade-off until a later phase adds
  the engine-side beat properly.
- No sound anywhere in either component (the placement sounds, the
  chairs/footsteps/door ambience, the wooden vote stamp, the pulse's
  audible layer): Phase 11 owns all of it.
- Directional vote marks in `Room.jsx` (Phase 9's stated gap) still
  render as counts, not compass headings toward a seat, even though
  seats now exist here in Phase 10. Wiring `Room.jsx` to the same
  `seatOrderRef` so its marks can finally point at a real angle was not
  done this phase, since Phase 9's file list didn't include it and this
  phase's didn't either; noted as a natural follow-up, not silently
  abandoned.
- No true visual/browser verification of seat stability, per the honest
  limitation stated above.
- **Not pushed**, per the confirmed policy. Show Your Hands and Offer
  still have no interactive UI.

## Phase 11: Sound (done, pending human verification)

**Files touched:** `frontend/src/audio/` (new directory: `context.js`,
`noise.js`, `effects.js`, `ambient.js`, `index.js`), `frontend/src/sound.js`
(deleted, fully replaced), `frontend/src/App.jsx` (every old chime call
site rewired to the new event table, plus the ambient bed's lifecycle),
`frontend/src/components/Letter.jsx` (the letter-unfold sound moved onto
the component itself, per section 4.5), `frontend/src/phases/Table.jsx`
(the vote stamp wired into the existing 220ms reveal queue from Phase
10).

**The one honest, unavoidable limit on this phase: I cannot hear.** This
environment has no audio playback or listening tool. Every sound in this
phase was designed from audio-engineering reasoning (what filtered noise
through what kind of filter, at what envelope, produces a percept close
to "paper," "wood," or "room tone") and verified structurally (every
exported function actually runs against a full mock Web Audio API
without throwing, including the deferred 2-second death-silence
callbacks actually firing), but the document's own acceptance line for
this phase is explicit: **"votes countable by ear, verified by a human
listening with the screen off."** That is stated as done here only in
the sense that the mechanism exists and is wired correctly; the
perceptual verification itself needs the user to actually listen. Said
plainly rather than claimed. Worth an explicit ask: please play a round
with sound on and confirm the four ambient layers, the stamp, and the
struck wire (see below) actually read the way the document intends,
since I have no way to check that myself.

**The old `sound.js` was a direct, if unintentional, violation of this
phase's own rule 1 and had to be fully replaced, not extended.** It
played melodic sine/triangle/square note sequences (a two-note "night
chime," an ascending "day chime," a "resolving triad" for game over)
exactly the "musical stings" and "synths" section 4.10 explicitly bans.
It also had no concept of the actual event table at all (there was no
letter-open sound, no vote stamp, no pen stroke, no phase-slide, no
ambient bed, no death silence, no struck wire), since it predates
Blackhand entirely. This phase did not add sound to an existing correct
system; it replaced a same-name but thematically wrong one.

**Every sound is synthesized from filtered noise, generated at runtime,
matching the confirmed "no external assets" constraint from Phase 0:**
`noise.js` provides white, brown (simple leaky integration), and pink
(Paul Kellett's economy filter) noise buffer generators, the only raw
material anything in this module uses. `effects.js`'s `woodKnock()`
helper excites a narrow resonant bandpass filter with a noise impulse,
the same principle a struck solid object's own resonance works on, used
for the vote stamp and the Crossing's footsteps and door. Confirmed by
grep: the only `createOscillator()` calls in the whole module are the
struck wire (the document's one deliberate exception) and one inaudible
LFO inside the lobby ambient that modulates a noise layer's gain
parameter and is never itself connected to any audio output, explained
in a comment at that exact line since it would otherwise look like a
second, unexplained exception to the no-synths rule.

**The ambient bed is four independent looping noise layers** (a low
brown-noise rumble, a pink-noise mid hum, a high white-noise hiss, and a
second pink-noise texture layer), each through its own filter and gain
node into a shared master. `crossfadeBedTo(phaseKey)` ramps each
surviving layer's gain to a small per-phase target over 1.4 seconds
(section 4.10 rule 1: cross faded, never a hard cut), using a fixed
per-phase mix table that stays close across phases on purpose, since
this is still room tone throughout, not a different soundscape per
screen.

**Death is driven by the server's true dead count, not by locally
diffing individual state updates**, the same reconciliation pattern the
Phase 10 write-up flagged as the correct approach and finally builds
here: `reconcileDeadCount(deadCount)` compares against the last count
this client has seen. The very first observation in a session (a fresh
join, or a reconnect mid-game) catches up silently, no drama, since
those deaths already happened before this client was listening; any
later increase plays the real ritual live. That ritual: every surviving
layer ramps to zero over 50ms (fast enough to read as silence rather
than a fade), holds there, and after a flat 2000ms the newly-dead
player's layer is permanently zeroed and the survivors return to
whatever the current phase's mix calls for. **One precision note on
"exactly 2000ms":** the total window from the first sign of quiet to the
bed's return is 2050ms (the 50ms ramp-down plus the 2000ms hold), not a
literal instantaneous cut into a 2000ms void, since an instant gain cut
to zero on a live audio node would itself produce an audible click. This
was a deliberate, small, click-avoiding trade-off, not an oversight, and
is called out here rather than silently rounded up to "exactly."
Layer removal is capped at 4: a fifth or later death changes nothing
further, matching "the room sounds hollow by the final round," not
silent, since a 6-12 player game routinely has more than 4 deaths.

**The Waiting Room's ambient (section 6.1) is a genuinely separate
system**, not one of the four layers and not eroded by death: a single
band-passed pink-noise layer with a slow, irregular LFO-driven amplitude
wobble approximating a room of voices too quiet to make out, started
when a player first sees the lobby and stopped, permanently for that
game, the moment the game actually starts.

**Event wiring, replacing every old call site:**
- Letter opens -> `letterUnfold()`, now called from `Letter.jsx` itself
  on mount (matches section 4.5's own stated ownership of this sound),
  not from whatever screen happens to render one.
- Vote lands -> `voteStamp()`, called from `Table.jsx`'s existing
  Phase-10 reveal queue at the exact moment a vote is popped and
  revealed, so the sound and the visible stamp are the same event, not
  two separately-timed things that might drift apart.
- Night action submitted -> `penStroke()`, called from `NightPanel`'s
  target `onClick`, alongside the existing `nightAction()` call.
- Phase change -> `phaseChange()`, called from the existing phase-change
  effect in `App.jsx` for every transition except day_discussion ->
  voting, which gets `theCrossing()` instead (from the dedicated Crossing
  effect built in Phase 10), so a round never plays two different
  transition sounds for the same beat.
- Timer under 10s -> `clockTick()`, the exact same call site and
  threshold Phase 6 already built for the lamp color change, just
  renamed from the old `playTick()`.
- Death -> `reconcileDeadCount()`, per above, replacing both of the old
  `playEliminated()`/`playDeathToll()` call sites with the one
  server-truth-driven mechanism.
- The struck wire -> `struckWire()` exists, is exported, and is
  deliberately oscillator-based so it resembles nothing else in the
  module, but **has no live call site yet**, consistent with every prior
  phase's Offer gap: there is still no Offer beat screen anywhere in this
  app (Phase 12's job). "Used only for the offer" holds vacuously today,
  the same honest partial-credit situation Phase 8 already flagged for
  the Black Hand letter variant.

**Verified without hearing anything, the parts that could be:**
- A disposable Node smoke test (not committed, deleted after the run,
  same practice as every live-verification script in prior phases)
  bundled `audio/index.js` with esbuild and ran every exported function,
  including idempotent repeat calls, muted-state calls, and the full
  `reconcileDeadCount` sequence (initial catch-up, no change, a live
  increase, jumping straight to the 4-layer cap, and a death past the
  cap), against a full mock Web Audio API. All 32 checks passed with no
  exceptions, and the deferred 2-second death-silence `setTimeout`
  callbacks were also awaited and confirmed to run cleanly, not just
  scheduled and abandoned.
- `npm run build` succeeds. `tests/` still 79/79 (no engine changes this
  phase). Zero em dashes, confirmed by grep across every file touched.

**Acceptance criteria:**
- Every sound sourced from paper, wood, or room tone, no synths:
  confirmed by construction and by grep (only two `createOscillator`
  call sites total, one the deliberate wire exception, one an inaudible
  modulator explained inline). Whether the *result* actually sounds like
  paper, wood, or room tone rather than just "filtered noise" is the
  part only a human ear can confirm.
- 4 layer ambient bed, one layer permanently removed per death:
  implemented and smoke-tested through catch-up, live-increase, cap, and
  beyond-cap cases.
- Death produces exactly 2000ms of silence: 2000ms of true silence, plus
  a 50ms click-avoiding ramp into it, noted above rather than rounded up.
- Cross fades between phases, never hard cuts: confirmed, every gain
  change in `ambient.js` is a `linearRampToValueAtTime`, never a
  `setValueAtTime` jump, except the two places a genuine instant value is
  correct (the very first silent frame of the death ramp's start point,
  and permanently zeroing an already-silenced removed layer).
- The struck wire exists, is used only for the offer, resembles nothing
  else: exists and is structurally distinct (oscillator-based, the only
  one in the module). No live call site yet, said outright above.
- Votes countable by ear, verified by a human listening with the screen
  off: **not verified by me, cannot be**. The mechanism (the same
  220ms-staggered stamp from Phase 10, now with an actual sound behind
  it) is in place and ready for that listening pass.

**Deliberately not done in Phase 11:**
- No live call site for the struck wire, per above (Phase 12).
- No sound for Show Your Hands' own results reveal or the Ledger's UI,
  since neither has dedicated sound cues named anywhere in section 4.10's
  table; nothing was invented beyond what the table specifies.
- The actual human listening verification this phase's own acceptance
  criteria require. Flagged clearly rather than assumed or skipped
  silently.
- **Not pushed**, per the confirmed policy. Show Your Hands and Offer
  still have no interactive UI.

## Phase 12: The Offer (done)

**Files touched:** `frontend/src/phases/Offer.jsx` (new), `frontend/src/useGameSocket.js`
(new `respondToOffer` sending `{type: "offer_response", accepted}`, the
one message type Phase 5's server protocol already defined but the
frontend never had a function for), `frontend/src/index.css`
(`.offer-screen`/`.offer-letter`/`.offer-timer`/`.offer-controls`
rules), `frontend/src/App.jsx` (a new full-takeover branch for the
recipient, and three real correctness fixes described below).

**The Offer screen itself reuses `Letter.jsx` directly** rather than
building its own paper surface: `<Letter faction="hand">` already
renders exactly `--room` ground and `--lamp` text, so the "one letter
unfolds centered" requirement needed only a centering wrapper
(`.offer-screen`, the same negative-margin full-bleed technique Phases
10 and the rest of this phase reuse) and the verbatim copy as children.

**"Fully black, not dimmed" is `--room` at its own full, undiminished
value, not a fifth color.** Section 4.2 closes the palette to four
values and their five documented mixes; introducing an actual `#000`
for this one screen would break that rule for a single phase. `--room`
(`#0F1216`) already reads as near-black, and "not dimmed" is read here
as "not one of this document's own fractional-opacity treatments" (The
Dark's 60%, Last Words' 20%): the Offer's room is just `--room` at full
strength, no overlay, no dimming math applied on top of it.

**Copy is verbatim, confirmed by grep against the document's exact
text**, including the internal line breaks section 6.4 shows within the
second and third paragraphs (rendered as `<br />` inside single `<p>`
elements, since those are the same sentence group breaking mid-thought,
not separate paragraphs).

**The 30 second timer and timeout-as-refusal were already correct
server-side work from Phase 5** (`OFFER_SECONDS = 30`,
`resolve_offer_timeout()`); this phase only had to display it, always in
`--lamp` (not the generic `Timer.jsx`'s under-10-seconds-only lamp
threshold, since section 4.2 explicitly allows lamp for "the Black
Hand's private surfaces" throughout, not just the last 10 seconds here).
A small dedicated countdown was built in `Offer.jsx` rather than reusing
`Timer.jsx`, since the two components' lamp rules are genuinely
different, not just differently themed.

**The struck wire plays exactly once**, from a plain `useEffect` with an
empty dependency array on `Offer.jsx`'s mount, matching "when the letter
opens," and has no repeat path anywhere in the component.

**"On accept, the interface converts fully and permanently" surfaced a
real, pre-existing frontend bug, the third instance of the same class of
mistake this project has now caught** (after Phase 3's `hand_ready()`
literal-role bug and Phase 5's disconnect-during-Offer hang, both in the
engine): `NightPanel`'s `actionByRole` lookup and the Black Hand chat's
render condition both checked `state.your_role === "hand"` directly.
Since a Marked player's literal `role` never changes (only
`effective_faction` does), a player who accepted the Offer would have
correctly seen the Hand-faction role card (Phase 8 already got this
right) but then hit "STAY SILENT" and no chat access on every
subsequent night, unable to actually act as Hand at all through the UI.
Both fixed to key off a new `isHandFaction` value
(`your_role === "hand" || marked`), computed once in `App.jsx` and
threaded into `NightPanel` as a prop rather than recomputed. **Given
this fix, no bespoke "second letter with the names" needed to be built**:
the existing role-reveal `Letter` from Phase 8 already renders the
"Fellow Hand: ..." line the instant `state.allies` populates, which
happens naturally the moment the server processes acceptance and broadcasts
the next state. Verified live rather than assumed (see below).

**"No other player's interface changes in any way" is enforced by never
mounting `Offer.jsx` for anyone but the recipient**, not by hiding
something after the fact: `App.jsx` renders it only when
`state.offer_pending` is true, a field `view_for` only ever sets for the
one player the offer was actually sent to (confirmed in Phase 5). Every
other player's `state.phase` does read `"offer"` too, since the server
broadcasts the same phase value to everyone, so a `displayPhase` value
was added that quietly treats `"offer"` as still `"night"` for anyone
who isn't the recipient, meaning they keep seeing whatever night UI they
were already looking at (their `NightPanel`, their Black Hand chat if
they're a Hand) with zero visible change, exactly as if nothing had
happened yet. A bystander whose own night action would technically be
rejected server-side during this pause (the engine requires
`Phase.NIGHT` to submit one) is an accepted, narrow edge case: the
document asks for no *visible* change, not for disabling controls that
would already have nothing left to do in this ~30 second window in
ordinary play.

**Verified live against a running server, then the script was deleted,
per established practice:** a 7-player game, a Hand offering instead of
killing, and three separate connections read simultaneously during the
same live Offer: the recipient correctly showed `offer_pending: true`;
an ordinary Table bystander showed `phase: "offer"` with no
`offer_pending` field at all; the *other* Hand member (the one who did
not send the offer) also showed `phase: "offer"`, no `offer_pending`,
and an `allies` list that correctly did not yet include the recipient.
After the recipient accepted: `marked: true`, `allies` now including
both original Hands, `offer_pending` gone, and `phase` already advanced
to `day_discussion`, confirming the whole handoff chain end to end
exactly as designed, not just each piece in isolation.

**Acceptance criteria:**
- Room goes fully black, not dimmed: `.offer-screen` sets `background:
  var(--room)` at full strength, no overlay or opacity treatment.
- Copy matches 6.4 verbatim, character for character: confirmed by grep.
- 30 second timer, timeout treated as refusal: the timer displays the
  server's own `OFFER_SECONDS = 30` countdown; the timeout path was
  already correct engine/server behavior from Phase 5, confirmed still
  intact by this phase's live run reaching the accept path without
  needing any change there.
- Struck wire plays once, does not repeat: confirmed by reading the
  component, one `useEffect(..., [])` call site, no interval, no replay
  trigger anywhere.
- On accept the interface converts fully and permanently: confirmed
  live, `marked` and `allies` both update correctly and the NightPanel/
  chat bug that would have silently broken this for real play is fixed.
- No other player's interface changes in any way: confirmed live for
  both an ordinary bystander and the other Hand member in the same run.
- `npm run build` succeeds. `tests/` still 79/79 (no engine changes this
  phase). Zero em dashes, confirmed by grep across every file touched.

**Deliberately not done in Phase 12:**
- No audio-quality verification of the struck wire "resembling nothing
  else," the same human-listening gap Phase 11 already flagged and
  still hasn't been closed; this phase just gave it its first real call
  site.
- No visual/browser confirmation of "fully black," consistent with the
  no-screenshot-tool gap noted in Phases 8 and 10.
- **Not pushed**, per the confirmed policy. Show Your Hands still has no
  interactive UI anywhere in this app, and unlike the Offer (this phase)
  or Delivery, Part 8's 15-phase list never names a dedicated phase for
  it at all, the same kind of build-plan gap already flagged for
  Delivery back in Phase 8. Worth deciding explicitly before Phase 15's
  full playtest needs it to actually work.

## Phases 13 through 15: not started
