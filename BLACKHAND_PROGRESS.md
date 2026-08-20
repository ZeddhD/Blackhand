# Blackhand Build Progress

Read this file first in any new session before touching code. It tracks
status against `BLACKHAND.md`'s 15-phase build plan so a fresh session
with no memory of prior conversations can pick up correctly instead of
re-deriving state or silently disagreeing with an earlier decision.

**Current status: Phase 2 complete. Phase 3 not started.**

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

## Phases 3 through 15: not started
