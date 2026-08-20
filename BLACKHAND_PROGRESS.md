# Blackhand Build Progress

Read this file first in any new session before touching code. It tracks
status against `BLACKHAND.md`'s 15-phase build plan so a fresh session
with no memory of prior conversations can pick up correctly instead of
re-deriving state or silently disagreeing with an earlier decision.

**Current status: Phase 1 complete. Phase 2 not started.**

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

## Phases 2 through 15: not started
