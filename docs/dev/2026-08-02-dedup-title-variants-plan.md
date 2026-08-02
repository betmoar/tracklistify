# Plan — dedup: merge non-distinguishing title variants (SDD execution)

> **Superseded by the spec.** This plan documents an *earlier* design that
> DROPPED `feat`/`ft`/`featuring` groups. The shipped design canonicalizes
> them (keeps the credited artist) — see the spec, not the reference impl or
> rule set below. Retained as the execution record of how the work was done;
> the spec is the binding source of truth.

**Derived from spec:** `docs/dev/2026-08-02-dedup-title-variants-spec.md`
(read it — it is the binding source of truth; this plan only sequences the
work into SDD tasks).
**Required reading before implementing:** `docs/playbooks/changing-dedup.md`
**Branch:** `claude/backlog-unknowns-feature-spec-y1xk6r` (do NOT push/merge).
**Baseline (recorded before any change):**
- `uv run python -m pytest -q` → **509 passed**, 1 warning
  (pydub `audioop` DeprecationWarning — pre-existing third-party noise).
- `ruff check` / `ruff format --check` / `generate_env_example.py --check` → clean.
- Scale probe (repeated detections, before): **4.8 / 21.7 / 45.1 ms**
  at n = 216 / 1000 / 2000.

---

## Global Constraints

These bind every task. Copied verbatim from the spec so a subagent never has
to round-trip to it:

- **D1 — Strip on the RAW title, before normalizing.** `_normalize_token`
  (`track.py:64`) maps `[^\w\s]` to spaces, so after it runs there are no
  delimiters to anchor on. The helper matches `\(([^()]*)\)` and
  `\[([^\[\]]*)\]` on the raw string and the remainder is normalized after.
- **D2 — Default is KEEP.** Only allowlisted suffixes are stripped. An
  incomplete allowlist produces a visible duplicate row, never a silent
  deletion.
- **D3 — Comparison only.** `_rep_key`, `is_similar_to`'s output,
  `_artists_match`, and every output path keep reading raw `song_name`. The
  displayed name stays exactly what the provider returned. `_rep_key` is NOT
  modified.
- **D4 — Empty-result fallback.** If stripping leaves nothing but whitespace,
  return the ORIGINAL title. Without this, `(Mixed)` and `(Club Mix)` both
  reduce to empty and merge.
- **Exact rule set, checked in this order per bracketed group:**
  1. **Never strip** — normalized inner text contains any of:
     `remix`, `bootleg`, `edit by`, `vip`
  2. **Strip** — normalized inner text is exactly one of:
     `mixed`, `club mix`, `extended mix`, `original mix`, `radio edit`,
     `radio mix`, `extended`, `original`
  3. **Strip** — normalized inner text starts with any of:
     `live at `, `feat `, `ft `, `featuring `
  4. **Otherwise keep.** An empty group (`"Foo ()"`) is dropped as noise.
- **`_tracks_match`'s title clause becomes:**
  `_normalize_token(_strip_title_variant(t1.song_name)) == _normalize_token(_strip_title_variant(t2.song_name))`.
  The artist clause is **untouched**.
- **Do not touch the artist axis.** `_ARTIST_THRESHOLD` stays `0.34`. No change
  to `_artists_match`, `_rep_key`, `get_unique_tracks`, or any exporter.
- **Gate (all four must pass):** `uv run python -m pytest -q`,
  `uv run ruff check src/ tests/ scripts/`,
  `uv run ruff format --check src/ tests/ scripts/`,
  `uv run python scripts/generate_env_example.py --check`.

---

## Task 1: `_strip_title_variant` + `_tracks_match` wiring + all tests (TDD)

Add `_strip_title_variant(title: str) -> str` to
`src/tracklistify/core/track.py`, placed **after `_normalize_token`
(`track.py:55-65`)**. It is consumed by `_tracks_match` (`track.py:86-95`)
and by nothing else.

### Reference implementation (semantics binding; style not)

```python
_TITLE_GROUP_RE = re.compile(r"\(([^()]*)\)|\[([^\[\]]*)\]")

_SUFFIX_KEEP_MARKERS = ("remix", "bootleg", "edit by", "vip")

_SUFFIX_DROP_EXACT = frozenset({
    "mixed", "club mix", "extended mix", "original mix",
    "radio edit", "radio mix", "extended", "original",
})

_SUFFIX_DROP_PREFIXES = ("live at ", "feat ", "ft ", "featuring ")


def _strip_title_variant(title: str) -> str:
    def _decide(m: "re.Match[str]") -> str:
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        inner = _normalize_token(raw)
        if not inner:
            return ""
        if any(marker in inner for marker in _SUFFIX_KEEP_MARKERS):
            return m.group(0)
        if inner in _SUFFIX_DROP_EXACT or inner.startswith(_SUFFIX_DROP_PREFIXES):
            return ""
        return m.group(0)

    stripped = _TITLE_GROUP_RE.sub(_decide, title)
    return stripped if stripped.strip() else title
```

`_tracks_match`'s title clause becomes
`_normalize_token(_strip_title_variant(t1.song_name)) == _normalize_token(_strip_title_variant(t2.song_name))`.
The artist clause is untouched.

### TDD — write the failing tests first, then implement

All tests in `tests/test_track_matcher.py::TestDedupInvariants`. Build tracks
with the existing `_t(name, artist, secs, conf=80.0)` helper
(`test_track_matcher.py:269-278`). The `config` fixture pins
`segment_length=60`, `overlap_duration=10`, `time_threshold=0`, so the derived
window is 100 s and 50 s apart is exactly one step. **Both poles are
mandatory** for every case.

**Must merge (1 row):**
1. `Meet Her At The Love Parade (feat. Kiki Solvej)` @ 08:20 vs
   `Meet Her At The Love Parade (Mixed)` @ 09:10, same artist. (50 s apart:
   use secs 500 and 550, same artist.)
2. `Outside World (Club Mix)` vs `Outside World`, same artist, 50 s apart
   (secs 3450/3500).
3. `Stereo Murder [Live At Tomorrowland]` vs `Stereo Murder`, same artist,
   50 s apart — **square brackets**, a paren-only stripper fails this.

**Must separate (2 rows):**
4. `Berghain` vs `Berghain (Remix)`, same artist, 50 s apart. **This pole does
   not exist in the suite today** — every existing `"Berghain (Remix)"`
   literal carries the suffix on BOTH sides.
5. `Outside World (Club Mix)` vs `Outside World (Adam Beyer Remix)` — a named
   remix, the keep-list's main job.
6. A track titled `Club Mix` vs one titled `Mixed` (no brackets on either) —
   proves the stripper anchors on delimiters and does not substring-match.
7. `(Mixed)` vs `(Club Mix)` — the D4 fallback.

**Non-regression (must keep passing, do not modify):**
8. Representative keeps its raw title: for case 1, the earlier detection wins
   by `_rep_key`, so the emitted `song_name` is
   `Meet Her At The Love Parade (feat. Kiki Solvej)`, NOT a stripped form.
9. These must still pass unchanged: `test_artist_variant_merge_berghain`,
   `test_similar_song_different_artist`, the two Jaccard-bound tests
   (`test_artist_jaccard_threshold_lower_bound`, `..._upper_bound`), and
   `test_f07_is_similar_to_agrees_with_dedup_predicate` (`Track.is_similar_to`
   delegates to `_tracks_match` and must keep agreeing with it).

### Reference truth table (implementer self-check)

| Input | After strip + normalize |
|---|---|
| `Meet Her At The Love Parade (feat. Kiki Solvej)` | `meet her at the love parade` |
| `Meet Her At The Love Parade (Mixed)` | `meet her at the love parade` |
| `Outside World (Club Mix)` | `outside world` |
| `Outside World` | `outside world` |
| `Stereo Murder [Live At Tomorrowland]` | `stereo murder` |
| `Berghain (Remix)` | `berghain remix` |
| `Berghain` | `berghain` |
| `Outside World (Adam Beyer Remix)` | `outside world adam beyer remix` |
| `Foo (Kiki's Extended Remix)` | `foo kiki s extended remix` (keep-list beats `extended`) |
| `Club Mix` (real title, no brackets) | `club mix` (no group to match) |
| `(Mixed)` | `mixed` (D4 fallback) |

### Scale probe (required — record before/after in the report)

Run the probe from `docs/playbooks/changing-dedup.md` (verification section),
verbatim. Expected budget ~1.5 / 7 / 13 ms at n = 216 / 1000 / 2000; over
~100 ms at n = 2000 means a bug (identity matching scanning cluster members).
**MUST use repeated detections** (few identities, big clusters) — the
playbook records an earlier probe that used all-distinct titles and certified
a quadratic implementation as linear. If the probe regresses beyond budget,
memoize strip+normalize with a bounded `functools.lru_cache` keyed on the raw
title; **measure first, do not memoize speculatively.**

Before numbers for the report: **4.8 / 21.7 / 45.1 ms** at n = 216/1000/2000.

### Acceptance

- Cases 1–8 all pass; full suite shows no new failures vs the 509-pass
  baseline.
- Gate clean (all four commands).
- Scale probe within budget, delta recorded in the report.
- No diff to `_rep_key`, `_artists_match`, `_ARTIST_THRESHOLD`,
  `get_unique_tracks`, or any exporter.

---

## Task 2: Documentation updates

Update the docs the spec invalidates (spec §"Documentation this change
invalidates"). Read each file before editing; keep changes tightly scoped.

- `docs/playbooks/changing-dedup.md:149-156` — "Titles are
  exact-after-normalize, deliberately" becomes exact-after-strip-then-normalize.
  Keep the no-fuzzy-ratio rationale (still correct). Add `_strip_title_variant`
  to the function list the playbook tells you to read before touching.
- `docs/ARCHITECTURE.md` — the implicit contract "same track iff normalized
  titles equal AND artist Jaccard ≥ 0.34" becomes strip-then-normalize.
- `CLAUDE.md` — the dedup landmine bullet (the spec cites `:50`; locate the
  current bullet about `get_unique_tracks` and update it to mention
  non-distinguishing title-variant stripping via `_strip_title_variant`).
- `docs/BACKLOG.md` — move the P2 entry to the Fixed table; the "Known
  limitation (accepted, not fixed)" note under the 2026-07 batch is
  superseded for the allowlisted suffixes and must say so.
- `docs/CHANGELOG.md` — `[Unreleased]`, user-visible output change.

### Acceptance

- All five docs updated as above.
- Gate clean (the four commands — docs changes touch no `.py`, but run the
  gate anyway; `generate_env_example.py --check` must still pass).
- No code diff in Task 2 (it is docs-only).
