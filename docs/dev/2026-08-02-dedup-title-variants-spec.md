# Spec — dedup: merge non-distinguishing title variants

**Date:** 2026-08-02
**Backlog item:** `docs/BACKLOG.md` → "P2 — bracketed/parenthetical title
variants survive dedup as separate rows"
**Status:** specified, not implemented
**Required reading before implementing:** `docs/playbooks/changing-dedup.md`

---

## Goal

Two detections of the same recording, one segmentation step apart with matching
artists, must emit **one** row when the only difference between their titles is
a non-distinguishing bracketed suffix — and must still emit **two** rows when
the suffix names a different recording. A `feat.`/`ft.`/`featuring` credit is
**distinguishing** (the featured artist identifies a specific recording), so
it is canonicalized — not dropped — and distinct credits stay separate.

Confirmed on real output (backlog table):

| Time | Title A | Title B | Wanted |
|---|---|---|---|
| 08:20 / 09:10 | `Meet Her At The Love Parade (feat. Kiki Solvej)` | `Meet Her At The Love Parade (Mixed)` | **2 rows** *(revised — see below)* |
| 57:30 / 58:20 | `Outside World (Club Mix)` | `Outside World` | 1 row |
| — | `Stereo Murder [Live At Tomorrowland]` | `Stereo Murder` | 1 row |
| — | `Berghain` | `Berghain (Remix)` | 2 rows |
| — | `Track (ft. Carl Cox)` | `Track (feat. Carl Cox)` | 1 row (canonicalized) |
| — | `Hit (ft. Snoop Dogg)` | `Hit (feat. Pharrell)` | 2 rows (distinct credit) |

The first row was the original motivating case ("wanted 1 row"). It is
**revised to 2 rows**: `feat.` is a credit marker, and the credited artist is
distinguishing information per the streaming-metadata standard. Treating it
as droppable merged different featured artists and collided with `Ft. <Place>`
abbreviations; the canonicalize-don't-drop rule fixes both at the cost of this
pair separating (a visible duplicate — the recoverable direction). The other
merge pairs (~50 s apart, matching artists) still merge; only the title check
split them.

## Non-goals

- Fuzzy title similarity ratios. See "Why not a threshold" below.
- Any change to the artist axis or to `_ARTIST_THRESHOLD`.
- Any change to what is *displayed*. This is a comparison-only change.
- Markdown / M3U / JSON output changes.

---

## Why not a threshold

No single similarity ratio separates the merge cases from the separate cases.
`"Berghain"` vs `"Berghain (Remix)"` (must split) and `"Outside World"` vs
`"Outside World (Club Mix)"` (should merge) are the same edit distance;
`docs/playbooks/changing-dedup.md:149-156` records that `"Berghain (Remix)"`
vs `"Berghain (Radio Edit)"` and `"Berghain"` vs `"Berghain (Remix)"` both
score 0.727 with opposite correct answers.

The distinguishing information is **semantic**, not metric: `(Mixed)`,
`(Club Mix)`, `(Radio Edit)`, `(Extended Mix)`, `(feat. X)`, `[Live At …]` are
usually the same recording under different Shazam spellings, while `(Remix)`
and a named `(Someone Remix)` are a genuinely different track. So the rule is a
curated allowlist, not a tuned number.

---

## Approach

Add `_strip_title_variant(title: str) -> str` to
`src/tracklistify/core/track.py`, placed after `_normalize_token`
(`track.py:55-65`). It is consumed by `_tracks_match` (`track.py:86-95`) and by
nothing else.

### Four load-bearing decisions

**D1 — Strip on the raw title, before normalizing.**
`_normalize_token` maps punctuation to spaces at `track.py:64`
(`re.sub(r"[^\w\s]", " ", s)`), so after it has run there are no delimiters
left to anchor on:

```
"Stereo Murder [Live At Tomorrowland]" -> "stereo murder live at tomorrowland"
"Outside World (Club Mix)"             -> "outside world club mix"
```

A post-normalize stripper would have to substring-match, which eats a track
genuinely titled `Club Mix`. The helper therefore matches `\(([^()]*)\)` and
`\[([^\[\]]*)\]` on the raw string and normalizes the remainder afterwards.
This mirrors the ordering invariant `_artist_tokens` already relies on at
`track.py:68-74` (split before normalize, so separators survive).

**D2 — Default is KEEP.**
Only suffixes on the allowlist are stripped; anything unrecognized is retained.
An incomplete allowlist therefore produces a *visible duplicate row*, never a
silent deletion — the direction `docs/playbooks/changing-dedup.md` rule 1b
always chooses.

**D3 — Comparison only.**
`_rep_key` (`track.py:98-120`) and every output path keep reading raw
`track.song_name`. The displayed name stays exactly what the provider returned.
`_rep_key` is not modified.

**D4 — Empty-result fallback.**
If rewriting leaves nothing but whitespace, return the original title. Without
this, a track titled `(Mixed)` and one titled `(Club Mix)` both reduce to the
empty string and merge.

**D5 — Credits are distinguishing; canonicalize, don't drop.**
A `feat.`/`ft.`/`featuring` credit names a specific collaborator, which
identifies a specific recording (`Song Title (feat. Artist Name)` is the
streaming-metadata standard). Dropping the whole group merges different
featured artists and, because casing is normalized away, also swallows `Ft.
<Place>` US abbreviations. The marker is therefore rewritten to a single
canonical `feat ` form (so spelling variants collapse) while the credited
name is retained (so distinct credits separate). This overrides the earlier
"strip the feat prefix" draft in every section below.

### Exact rule set

Each bracketed group's inner text is normalized with `_normalize_token`, then
the group is transformed by **exactly one** of these rules, tested in order.

1. **Never touch** — inner text contains any of:
   `remix`, `bootleg`, `edit by`, `vip`
   (these are title-distinguishing; the group is kept verbatim)
2. **Drop** — inner text is exactly one of:
   `mixed`, `club mix`, `extended mix`, `original mix`, `radio edit`,
   `radio mix`, `extended`, `original`
   (non-distinguishing version tags; the group is removed)
3. **Canonicalize the feat-marker** — inner text starts with any of:
   `feat `, `ft `, `featuring `
   The marker is rewritten to `feat ` and the **credited name is kept**: the
   group becomes `(feat <credited name>)`. So `(ft. Carl Cox)`,
   `(Ft. Carl Cox)`, and `(Featuring Carl Cox)` all reduce to the same key.
   **The credit is NOT dropped** — it is distinguishing information per the
   streaming-metadata standard (`Song Title (feat. Artist Name)`; the
   featured artist identifies a specific recording). Dropping it would merge
   `(feat. Snoop Dogg)` with `(feat. Pharrell)`. Canonicalizing lets
   spelling-variant duplicates collapse while keeping distinct credits apart.
4. **Drop** — inner text starts with `live at `
   (a live-recording tag; non-distinguishing for dedup)
5. **Otherwise keep** the group verbatim.

(Prefixes are written post-normalization: `"feat. Kiki Solvej"` normalizes to
`"feat kiki solvej"`, so the prefix to match is `"feat "`, not `"feat. "`.
Case does not matter — `_normalize_token` lowercases first, so `Ft.`,
`FEAT`, `Featuring` all match.)

An empty group (`"Foo ()"`) is dropped — it is noise under either reading.

**Why canonicalize feat instead of dropping it.** `feat.`, `ft.`, and
`featuring` are all standard spellings of the same credit marker, and Shazam
returns them inconsistently for the same recording. But the *credited name*
after the marker is onderscheidend — `(feat. Snoop Dogg)` and
`(feat. Pharrell)` are different tracks. Canonicalizing the marker (so
spelling variants of the same credit merge) while keeping the name (so
different credits separate) is correct on both. Dropping the whole group, as
an earlier draft did, merged different featured artists and also collided
with `Ft. <Place>` US place abbreviations (`Ft. Lauderdale`) — canonicalizing
fixes both: `Sunrise (Ft. Lauderdale Session)` keeps `feat lauderdale
session` and correctly does not merge with a bare `Sunrise`.

**Trade-off accepted.** A detection tagged `(feat. X)` and one tagged
`(Mixed)` of the *same* audio now separate (the feat-credit is retained, the
`(Mixed)` tag drops, so the keys differ). This is the cost of treating the
featured artist as distinguishing — a visible duplicate on that real pair,
which is the recoverable direction this feature always chooses.

### Reference implementation shape

Not binding on style, but the semantics below are binding.

```python
_TITLE_GROUP_RE = re.compile(r"\(([^()]*)\)|\[([^\[\]]*)\]")

_SUFFIX_KEEP_MARKERS = ("remix", "bootleg", "edit by", "vip")

_SUFFIX_DROP_EXACT = frozenset({
    "mixed", "club mix", "extended mix", "original mix",
    "radio edit", "radio mix", "extended", "original",
})

_SUFFIX_DROP_PREFIXES = ("live at ",)

# A feat-credit marker at the start of a bracketed group. Matched on the
# NORMALIZED inner text (already lowercased), so it covers feat/ft/featuring
# and every casing variant. The credited name that follows is KEPT.
_FEAT_MARKER_RE = re.compile(r"^(feat|ft|featuring)\b\s*")


def _strip_title_variant(title: str) -> str:
    def _decide(m: "re.Match[str]") -> str:
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        inner = _normalize_token(raw)
        if not inner:
            return ""  # empty group is noise
        if any(marker in inner for marker in _SUFFIX_KEEP_MARKERS):
            return m.group(0)  # title-distinguishing: keep verbatim
        # Canonicalize the feat-marker, KEEP the credited name.
        if _FEAT_MARKER_RE.match(inner):
            credit = _FEAT_MARKER_RE.sub("", inner)
            return f"({credit})" if credit else m.group(0)
        if inner in _SUFFIX_DROP_EXACT or inner.startswith(_SUFFIX_DROP_PREFIXES):
            return ""  # non-distinguishing version/live tag: drop
        return m.group(0)  # unrecognized: keep verbatim (default is keep)

    rewritten = _TITLE_GROUP_RE.sub(_decide, title)
    return rewritten if rewritten.strip() else title
```

`_tracks_match`'s title clause becomes
`_normalize_token(_strip_title_variant(t1.song_name)) == _normalize_token(_strip_title_variant(t2.song_name))`.
The artist clause is untouched.

### Worked cases

| Input | After rewrite + normalize |
|---|---|
| `Track (ft. Carl Cox)` | `track carl cox` |
| `Track (feat. Carl Cox)` | `track carl cox` |
| `Track (Featuring Carl Cox)` | `track carl cox` |
| `Hit (ft. Snoop Dogg)` | `hit snoop dogg` |
| `Hit (feat. Pharrell)` | `hit pharrell` (distinct credit → distinct key) |
| `Sunrise (Ft. Lauderdale Session)` | `sunrise lauderdale session` (no longer drops → no place collision) |
| `Outside World (Club Mix)` | `outside world` |
| `Outside World` | `outside world` |
| `Stereo Murder [Live At Tomorrowland]` | `stereo murder` |
| `Berghain (Remix)` | `berghain remix` |
| `Berghain` | `berghain` |
| `Outside World (Adam Beyer Remix)` | `outside world adam beyer remix` |
| `Foo (Kiki's Extended Remix)` | `foo kiki s extended remix` (keep-list beats everything) |
| `Club Mix` (real title, no brackets) | `club mix` (no group to match) |
| `(Mixed)` | `mixed` (D4 fallback) |
| `Meet Her At The Love Parade (feat. Kiki Solvej)` | `meet her at the love parade kiki solvej` |
| `Meet Her At The Love Parade (Mixed)` | `meet her at the love parade` (**now separates** — trade-off) |

Nested parentheses are not handled by `[^()]*`; a non-match falls through to
"keep", which is the safe default.

---

## Do not touch the artist axis

`_ARTIST_THRESHOLD = 0.34` (`track.py:38`) sits in an empirical gap — all
observed merge cases score ≥ 0.50, all separate cases 0.00 — and existing tests
bracket it to within 0.067 (`tests/test_track_matcher.py:217` must-not-merge at
0.333, `:232` must-merge at 0.40). Loosening it to reach these cases
reintroduces the collab-bridge data loss described in
`docs/playbooks/changing-dedup.md` rule 1b, where a collaboration credit
transitively bridges two distinct artists and a later distinct play is deleted
outright. The backlog rules this out explicitly (lines 60–62).

---

## Performance requirement

`_tracks_match` runs once per active cluster per candidate track. This change
adds one regex pass and one extra `_normalize_token` per side per call.

The implementation **must** run the scale probe from
`docs/playbooks/changing-dedup.md` (verification section) and record the
before/after delta. Expected budget: ~1.5 / 7 / 13 ms at n = 216 / 1000 / 2000.
Over ~100 ms at n = 2000 means identity matching is scanning cluster members
instead of anchoring on `cluster[0]` — a different bug.

**The probe must use repeated detections.** The playbook records an earlier
probe that generated all-distinct titles, left every cluster at size 1, and
certified a quadratic implementation as linear.

If the probe regresses beyond the budget, memoize the strip+normalize composite
with a bounded `functools.lru_cache` keyed on the raw title. Do not memoize
speculatively — measure first.

---

## Tests

All in `tests/test_track_matcher.py::TestDedupInvariants`. Build tracks with
the existing `_t(name, artist, secs, conf=80.0)` helper
(`test_track_matcher.py:269-278`). The `config` fixture pins
`segment_length = 60`, `overlap_duration = 10`, `time_threshold = 0`, so the
derived window is 100 s and 50 s apart is exactly one step.

Both poles are mandatory — `docs/playbooks/changing-dedup.md`, "procedure for a
rule change", step 2.

### Must merge (1 row)

1. **Feat-marker spelling variants, same credit.** `(ft. Carl Cox)` vs
   `(feat. Carl Cox)` vs `(Featuring Carl Cox)`, same artist, 50 s apart —
   canonicalization collapses them to one key. (Was the feat-drop in an
   earlier draft; now the credit is kept and the marker canonicalized.)
2. `Outside World (Club Mix)` @ 57:30 vs `Outside World` @ 58:20, same artist.
3. `Stereo Murder [Live At Tomorrowland]` vs `Stereo Murder`, 50 s apart —
   square brackets, so a paren-only stripper fails this one.

### Must separate (2 rows)

4. `Berghain` vs `Berghain (Remix)`, same artist, 50 s apart.
   **This pole does not exist in the suite today.** All six
   `"Berghain (Remix)"` literals currently in the file carry the suffix on
   *both* sides of the comparison, so they merge with or without rewriting —
   the existing suite cannot catch an over-aggressive stripper.
5. `Outside World (Club Mix)` vs `Outside World (Adam Beyer Remix)` — a named
   remix, the keep-list's main job.
6. A track titled `Club Mix` vs one titled `Mixed` (no brackets on either) —
   proves the stripper anchors on delimiters and does not substring-match.
7. A track titled `(Mixed)` vs one titled `(Club Mix)` — the D4 fallback.
8. **Different featured artists.** `(ft. Snoop Dogg)` vs `(feat. Pharrell)`,
   same artist, 50 s apart — the credit is kept, so the keys differ. This is
   the canonicalize-don't-drop rule's main job.
9. **Place-name (no longer collides).** `Sunrise (Ft. Lauderdale Session)` vs
   `Sunrise`, same artist, 50 s apart — `Ft.` no longer drops, so the place
   qualifier is retained and they separate. (Was a silent over-merge when feat
   was dropped; canonicalizing fixes it.)
10. **feat-credit vs Mixed tag of the same audio (accepted trade-off).**
    `Meet Her At The Love Parade (feat. Kiki Solvej)` vs
    `Meet Her At The Love Parade (Mixed)`, same artist, 50 s apart — now
    SEPARATE. The feat-credit is distinguishing, so it is kept even though
    this is the same recording Shazam tagged two ways. A visible duplicate is
    the recoverable direction.

### Non-regression

11. The representative keeps its raw title: for case 1 the earlier detection
    wins by `_rep_key`, so the emitted `song_name` is the raw provider spelling
    `(ft. Carl Cox)` / `(feat. Carl Cox)` — never a canonicalized form.
12. These must still pass unchanged: `test_artist_variant_merge_berghain`,
    `test_similar_song_different_artist`, the two Jaccard-bound tests, and
    `test_f07_is_similar_to_agrees_with_dedup_predicate` —
    `Track.is_similar_to` delegates to `_tracks_match` and must keep agreeing
    with it.

---

## Interaction with the Spotify enrichment spec

`docs/dev/2026-08-02-spotify-link-enrichment-spec.md` enriches tracks after
`get_unique_tracks()`. Stripping is **comparison-only** (D3), so enrichment
looks up Spotify with the raw `song_name` — the provider's own spelling — not a
stripped form. Both specs state this.

The two changes compose cleanly and can land in either order: this one reduces
the number of unique tracks, which only reduces the number of enrichment calls.

---

## Documentation this change invalidates

Update at implementation time:

- `docs/playbooks/changing-dedup.md:149-156` — "Titles are exact-after-normalize,
  deliberately" becomes canonicalize-then-normalize; keep the
  no-fuzzy-ratio rationale, it is still correct.
- `docs/ARCHITECTURE.md` — implicit contract "same track iff normalized titles
  equal AND artist Jaccard ≥ 0.34".
- `CLAUDE.md:50` — the dedup landmine bullet.
- `docs/BACKLOG.md` — mark the P2 entry Fixed; the "Known limitation (accepted,
  not fixed)" note under the 2026-07 batch is superseded for the allowlisted
  suffixes. Note the accepted trade-off: a `feat. X` credit vs a `(Mixed)` tag
  of the same audio now separate.
- `docs/CHANGELOG.md` — `[Unreleased]`, user-visible output change.

---

## Success criteria

1. All twelve new tests (cases 1–12) pass; the full suite shows no new failures
   against the recorded baseline.
2. The scale probe is within budget, with the delta recorded in the PR.
3. `uv run ruff check src/ tests/ scripts/`,
   `uv run ruff format --check src/ tests/ scripts/`, and
   `uv run python scripts/generate_env_example.py --check` all pass.
4. No diff in `_rep_key`, `_artists_match`, `_ARTIST_THRESHOLD`,
   `get_unique_tracks`, or any exporter.
