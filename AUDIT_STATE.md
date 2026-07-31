# AUDIT_STATE — PR1 (`fix/p2-dedup-confidence-downloader`)

**Mode:** INTERACTIVE
**Target:** the PR1 diff vs `main`. Scope was the diff, not the whole repo.
**Phase cursor:** DONE — P1→P4 complete. 7/7 findings fixed and verified, no deferrals.
**Baseline → final:** `450 passed` → `457 passed` (+7 guardrails, 0 regressions).

## Verdict

PR1 fixed its target bug (the Berghain duplicate) correctly, and introduced one
silent regression of the same class (F01: chained clusters deleting distinct
plays). Both are now resolved. The dedup subsystem is in better shape than
before PR1: the guarantees in the docstrings are now the guarantees the code
actually provides, and each is locked by a named test.

## Findings ledger

| ID | Title | Sev | Status | Verified by |
|---|---|---|---|---|
| F01 | Cluster chaining unbounded — merged distinct plays | P1 | FIXED | repro 41 detections: 1 → 21 tracks; Berghain still 1 |
| F02 | Claimed early exit absent; O(n²) | P2 | FIXED | n=1000: 475ms → 7.0ms (linear) |
| F03 | `min_confidence` setter doesn't scale | P2 | FIXED (documented + locked) | `test_c4_constructor_scales_config_min_confidence` |
| F04 | Deadband straddled bucket edges | P2 | FIXED (confidence removed from `_rep_key`) | straddle stable in both input orders |
| F05 | `/sets/` truncation was debug-level | P2 | FIXED | `test_multi_entry_set_warns_about_truncation` |
| F06 | `time_threshold`/`max_duplicates` dead but documented | P3 | FIXED | `test_f06_time_threshold_overrides_the_dedup_window` |
| F07 | `is_similar_to` unreferenced, untested | P3 | FIXED (pinned) | `test_f07_is_similar_to_agrees_with_dedup_predicate` |

## Load-bearing map (post-fix)

| # | Surface | Invariant it must hold | Locking test |
|---|---|---|---|
| 1 | `get_unique_tracks` | Cluster span ≤ window (anchor, never chain) | `test_c3_cluster_span_is_bounded_by_the_window` |
| 2 | `_tracks_match` / `_artists_match` | Berghain merges, Artist1/Artist2 separates | `test_artist_variant_merge_berghain`, `test_similar_song_different_artist` |
| 3 | `_rep_key` | Never reads confidence; stable across jitter | `test_c5_representative_stable_across_deadband_boundary` |
| 4 | `_dedup_window` | Reads mutable config per call; honors override | `test_f06_time_threshold_overrides_the_dedup_window` |
| 5 | `ytdlp.download` unwrap | Multi-entry truncation is loud | `test_multi_entry_set_warns_about_truncation` |
| 6 | `TrackMatcher.__init__` | Scales 0–1 config onto 0–100 | `test_c4_constructor_scales_config_min_confidence` |

## Implicit contracts — status

- **C1** valid `time_in_mix` — holds (enforced by `Track.__post_init__`).
- **C2** `window > 0` requires `segment_length > overlap_duration` — enforced by
  config invariant I2; `_dedup_window()` now reads config **per call**, so CLI
  mutation after load can't leave a stale window. Residual: a user setting
  `time_threshold` to a negative value falls through to the derived default
  (treated as unset) — acceptable, documented in `_dedup_window`.
- **C3** cluster span bounded — **now true** (was violated; F01).
- **C4** min_confidence scale asymmetry — **documented + locked** (F03).
- **C5** representative stability — **now unconditional** (F04 removed the
  confidence term rather than trying to quantize around it).
- **C6** `/sets/` → `entries[0]` — unchanged behavior, now warns (F05).

## Decisions

- `// DECISION:` anchor on `cluster[0]` rather than capping a chained span with
  a second tunable — makes the docstring guarantee true with no new knob.
- `// DECISION:` remove confidence from `_rep_key` entirely rather than widen
  the deadband — any confidence term is jitter-exposed at some boundary.
- `// DECISION:` `time_threshold` default `30.0 → 0.0`. Making a dead knob live
  would otherwise have silently changed shipped behavior, since 30s is
  narrower than one 50s segmentation step.
- `// DECISION:` keep `max_duplicates` as a field but label it UNUSED in both
  doc surfaces rather than delete it — deletion touches config, two
  validators, the TypedDict mirror, and `.env.example`; out of scope for an
  audit of this diff. Logged in the backlog.

## Artifacts produced

- `docs/playbooks/changing-dedup.md` — the executable procedure (rules,
  change checklist, verification commands incl. a scale probe with expected
  numbers, and the fixture trap).
- `tests/test_track_matcher.py::TestDedupInvariants` — 6 guardrail tests,
  each naming its contract.
- `tests/test_ytdlp.py::test_multi_entry_set_warns_about_truncation`.
- Corrected: `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`, `CLAUDE.md`,
  `config/docs.py`, `scripts/generate_env_example.py`, `.env.example`.

## Residual risk / backlog

| Item | Sev | Note |
|---|---|---|
| `max_duplicates` is dead config | P3 | Labeled UNUSED. Delete it (config + `validation.py` + `core/types.py:39` + `docs.py` + regenerate env) or give it meaning. |
| Bare-title vs parenthetical won't merge | P3 | `"Berghain"` vs `"Berghain (Remix)"`. Accepted: no ratio separates it from `(Remix)` vs `(Radio Edit)`. Revisit only with a title-variant corpus. |
| Multi-track `/sets/` processes only track 1 | P3 | Now warns. Full multi-entry support is a feature, not a bugfix. |
| Dedup unvalidated against real audio | P2 | All evidence is synthetic + the original Berghain strings. **Only the human can close this**: re-run the Sara Landry SoundCloud mix and confirm the tracklist is correct and stable across two runs. |
| `tests/test_decorators.py::test_memoize_avg_...` order-dependent | P3 | Pre-existing on `main`, unrelated to PR1. `memoize` is dead code (BACKLOG P4). |
