# Playbook: changing track dedup safely

`core/track.py` decides which tracks reach the user. Get it wrong and the
failure is **silent** — a tracklist that looks fine but is missing a track the
DJ played. This playbook exists because two separate rewrites of this file
shipped bugs that the tests at the time did not catch.

Read this before touching `get_unique_tracks`, `_tracks_match`,
`_artists_match`, `_rep_key`, or `_dedup_window`.

---

## The one-paragraph mental model

Identification produces one detection per segment. A 4-minute track spans
several 60s segments, so the *same* track is detected repeatedly, ~50s apart
(the segmentation step), each time with a slightly different artist string and
confidence from Shazam. Dedup's whole job: collapse those repeats into one row
without collapsing two genuinely different plays.

```
add_track()          -> confidence-gate + append. Does NOT dedup.
get_unique_tracks()  -> THE dedup authority. Cluster, then pick one per cluster.
  _dedup_window()    -> how close in time counts as "the same play"
  _tracks_match()    -> is this the same track? (title + artist identity)
  _rep_key()         -> which detection represents the cluster
```

---

## The four rules that must not be broken

### 1. A cluster's span is bounded by the window — anchor, never chain

Proximity is measured against `cluster[0]` (the anchor), **not** against any
member.

```python
if t_secs - cluster[0].time_to_seconds() > window:   # correct
if any(abs(t_secs - m.time_to_seconds()) <= window for m in cluster):  # WRONG
```

The `any`-member form makes the relation transitively chaining: each join
extends the cluster's reach, so a run of near-neighbours swallows an
arbitrarily long stretch. Measured: 41 detections 90s apart spanning an hour
collapsed into **1 track**, silently deleting a distinct play. With the anchor
form the same input yields 21.

**Guardrail:** `test_c3_cluster_span_is_bounded_by_the_window`.

### 2. Representative selection never reads confidence

`_rep_key` is `(time, name, artist)`. Confidence is deliberately absent.

Every cluster member is the same track by construction, so a "better"
detection buys nothing — while *any* confidence-derived term reintroduces
run-to-run instability, because Shazam scores the same audio differently each
run. A previous attempt quantized confidence into 5-point buckets to absorb
the jitter; two detections straddling a bucket edge (84.9 vs 85.0) still
flipped. Earliest time is jitter-proof. Don't "improve" this by preferring
high confidence.

**Guardrail:** `test_c5_representative_stable_across_deadband_boundary`,
`test_representative_selection_is_time_based_not_confidence_based`.

### 3. Both scales, always: config is 0–1, `Track.confidence` is 0–100

`TrackMatcher.__init__` multiplies by 100. The property setter does **not**.
`matcher.min_confidence = config.min_confidence` is therefore a bug: 0.8 means
0.8%, silently disabling the filter. Scale it, or let `__init__` do it.

**Guardrail:** `test_c4_constructor_scales_config_min_confidence`.

### 4. Read mutable config per call, not at construction

`config.segment_length` / `overlap_duration` / `time_threshold` are mutated
after load by CLI overrides. `_dedup_window()` reads them each call for that
reason. Caching them in `__init__` yields a stale window. (This is the same
class of bug as ARCHITECTURE.md invariant I2.)

---

## Changing the matching rule

The predicate is: **normalized titles equal AND artist Jaccard ≥ 0.34.**

- **Titles are exact-after-normalize, deliberately.** No fuzzy ratio. A ratio
  cannot separate `"Berghain"` vs `"Berghain (Remix)"` (should merge, 0.727)
  from `"Berghain (Remix)"` vs `"Berghain (Radio Edit)"` (should NOT merge,
  also 0.727). Same score, opposite correct answers. Exact-after-normalize is
  the only rule correct on both. The cost is a known false-negative: a bare
  title and a parenthetical variant won't merge. Accepted.
- **The 0.34 threshold sits in an empirical gap**, not a tuned constant: real
  merge cases score ≥ 0.50, real separate cases score 0.00. Before moving it,
  re-run the numbers; if your new case lands between 0.34 and 0.50 you are
  changing behavior for every existing case too.
- **Artist tokenization splits before normalizing** so separators survive.
  `\bx\b` uses word boundaries — it splits `MGMT x Tame Impala` but leaves
  `Charli XCX` intact. Verify any separator you add against a name that
  *contains* it.

### Procedure for a rule change

1. Write the failing test first, with the real strings you observed. Put it in
   `TestDedupInvariants` and name the contract.
2. Check your change against **both** poles:
   `test_artist_variant_merge_berghain` (must still merge) and
   `test_similar_song_different_artist` (must still separate). A change that
   only satisfies one is not a fix.
3. Run the scale probe below — unit tests use handfuls of tracks and will not
   reveal a complexity regression.
4. Full suite. Dedup changes have shown fallout in `test_config.py` and
   fixtures, not just in `test_track_matcher.py`.

---

## Verification commands

```bash
# The gate. Run all four.
uv run python -m pytest -q
uv run ruff check src/ tests/ scripts/
uv run ruff format --check src/ tests/ scripts/
uv run python scripts/generate_env_example.py --check

# Just the dedup surface
uv run python -m pytest tests/test_track_matcher.py -v

# Scale probe — clustering must stay ~linear. Regression here means the
# early-exit `break` in get_unique_tracks was lost.
uv run python -c "
import os, time
os.environ['TRACKLISTIFY_SEGMENT_LENGTH']='60'; os.environ['TRACKLISTIFY_OVERLAP_DURATION']='10'
from tracklistify.config.factory import get_config
from tracklistify.core.track import Track, TrackMatcher
cfg = get_config(force_refresh=True)
def T(n,a,s):
    h,r=divmod(s,3600); m,sec=divmod(r,60)
    return Track(song_name=n,artist=a,time_in_mix=f'{h}:{m:02d}:{sec:02d}',confidence=80.0)
for n in [216, 1000, 2000]:
    m=TrackMatcher(cfg); m.tracks=[T(f'S{i}',f'A{i}',i*50) for i in range(n)]
    t0=time.perf_counter(); u=m.get_unique_tracks(); dt=time.perf_counter()-t0
    print(f'n={n:5} -> {len(u)} unique in {dt*1000:7.1f}ms')
"
# Expected: ~1.4ms / ~7ms / ~14ms (linear). If n=1000 is >100ms, you have
# reintroduced the quadratic scan.
```

## The trap that is not in the code

`tests/test_track_matcher.py`'s `config` fixture sets `time_threshold = 0`
**on purpose**, so tests exercise the derived window. It previously set `30`,
which was inert while the field was dead — the moment `time_threshold` became
a live override, that fixture silently narrowed the window to 30s and split
the 50s Berghain pair. If you make another config field live, grep the
fixtures for it first.
