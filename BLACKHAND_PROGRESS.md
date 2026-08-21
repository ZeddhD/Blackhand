# Blackhand Build Progress

Read this file first in any new session before touching code. It tracks
status against `BLACKHAND.md`'s 15-phase build plan so a fresh session
with no memory of prior conversations can pick up correctly instead of
re-deriving state or silently disagreeing with an earlier decision.

**Current status: Phase 6 complete. Phase 7 not started.**

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

## Phases 7 through 15: not started
