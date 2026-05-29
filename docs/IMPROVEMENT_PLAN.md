# Optimization & Improvement Plan

Technical companion to PR #44 (*Lightweight optimizations, latent bug fixes, and
circuit-breaker wiring*). It documents the changes that shipped in this PR and
lays out a prioritized, risk-classified backlog for follow-up work.

The guiding constraint for everything in **Part A** was **no behavioral
regression**: each change is either behavior-identical, or repairs a path that
was already broken. Items deferred because they *do* change behavior are
captured in **Part B** so the trade-offs are explicit rather than lost.

- Tests: `uv run python -m pytest -q` → **382 passed** (pytest 9.0.3, asyncio strict)
- Lint/format: `uv run ruff check src/ tests/` + `ruff format --check` → clean
- Dead code: `uv run vulture src/tracklistify` → no new findings

---

## Risk / effort legend

| Tag | Meaning |
|-----|---------|
| 🟢 Low | Behavior-identical or repairs a broken path; covered by tests |
| 🟡 Medium | Observable behavior change, but bounded and config-gated |
| 🔴 High | Changes concurrency / ordering / public semantics; needs design + new tests |

---

## Part A — Delivered in PR #44

### A1. Performance (behavior-preserving) — `perf:`

| Change | File(s) | Notes |
|--------|---------|-------|
| **O(n) track de-duplication** | `core/track.py::TrackMatcher.get_unique_tracks` | Replaced an O(n²) `next()`-scan + `list.remove()` + double-sort with a single dict pass keyed by `artist|song`, then one sort. Tie-break preserved: earliest occurrence wins among equal confidence; highest confidence wins overall. |
| **Cache size reuse** | `cache/invalidation.py::SizeStrategy.update_metadata`, `cache/base.py` | Reuse the `size` computed at set-time instead of re-running `json.dumps(value)` on every cache access. `SizeStrategy` returns the entry unchanged when size is known, so it no longer forces a storage rewrite (access-time updates from `LRUStrategy` are a separate concern — see B5). |
| **Shazam cooldown hoist** | `providers/shazam.py` | The inter-request cooldown was re-read from config (with a `try/except`) on every segment; now resolved once in `__init__`. |
| **Magic number → constant** | `core/base.py` | Segment-size validation uses `MIN_SEGMENT_FILE_SIZE` (already in `utils/constants.py`) instead of the literal `1000`. |
| **Precompiled regexes** | `exporters/tracklist.py` | Filename-sanitization patterns compiled once at module level. |
| **Parallel Spotify enrichment** | `providers/spotify.py::get_track_details` | The independent `tracks/{id}` and `audio-features/{id}` requests now run via `asyncio.gather`. |
| **Dead code removal** | `downloaders/ytdlp.py` | Removed unused `get_ydl_opts()` (download builds opts inline) and the now-unused `tempfile` import. |

### A2. Correctness fixes (repair broken paths) — `fix:`

- **ACRCloud factory** (`providers/factory.py`): `ACRCloudProvider()` was constructed
  with no arguments, raising `TypeError` the moment `acrcloud` was selected. The
  factory now reads `TRACKLISTIFY_ACR_ACCESS_KEY` / `_ACCESS_SECRET` (and optional
  `_HOST`) from the environment — the documented credential design — and raises a
  clear `ProviderError` when they're absent.
- **ACRCloud protocol mismatch** (`providers/acrcloud.py`): `identify_track` expected
  raw `bytes`, but the identification loop and the base provider protocol pass an
  `AudioSegment`. It now accepts a segment (reading bytes from `file_path`, using
  its `start_time`) while still accepting raw bytes for direct/back-compat use.
  Together with the factory fix, ACRCloud can now run end-to-end.
- **Spotify downloader event-loop crash** (`downloaders/spotify.py`): `_set_metadata`
  called `asyncio.run()` while already inside the running `download()` loop —
  `RuntimeError` whenever a track had cover art. `_set_metadata` is now `async` and
  awaits the cover fetch; the call site awaits it.

### A3. Reliability — `feat:`

- **Circuit breaker wired into the request path**
  (`utils/identification.py`, `utils/rate_limiter.py`). The breaker was implemented
  but never invoked in production, so `circuit_state` never opened. The
  identification loop now reports each provider request outcome via the new public
  `RateLimiter.record_result(provider, success)`:
  - a `None`/no-match result still counts as **success** (resets the failure streak);
  - an exception from `identify_track` counts as **failure**.

  After `circuit_breaker_threshold` consecutive failures (default 5), `acquire`
  short-circuits and segments are skipped until `circuit_breaker_reset_timeout`
  (default 60s). Config-gated via `circuit_breaker_enabled`.
- **Bounded metrics** (`utils/rate_limiter.py`): `rate_limit_windows` is capped at
  `MAX_RATE_LIMIT_WINDOWS` so long runs don't grow the list without bound.

### A4. Refactors — `refactor:`

- `core/base.py`: extracted `_build_identification_manager()` (removing duplicated
  construction); declared `original_title` / `uploader` / `duration` /
  `_output_formats` in `__init__` (removing scattered `getattr` fallbacks); replaced
  two duplicated duration `try/float/except` blocks with `_coerce_float()`. The
  `_output_formats → config.output_format` fallback is preserved via `or`.
- `providers/acrcloud.py`: collapsed a confusing nested `try/except` (the outer
  handler re-wrapped the `ProviderError` the inner one raised) into a single
  `JSONDecodeError` handler.

### A5. Dependency maintenance

Merged 5 Dependabot `chore(deps)` PRs into `main` after verifying the full set
together against the test suite (notably the **pytest 8 → 9** major bump):
`aiohttp 3.13.4`, `urllib3 2.7.0`, `python-dotenv 1.2.2`, `idna 3.15`,
`pytest 9.0.3` (+ `pytest-httpx 0.36.2`). The suite is green on pytest 9.0.3.

### A6. Test coverage added

- `tests/test_provider_factory.py` — ACRCloud credential wiring (missing/partial
  creds raise, env creds construct, host override, caching, unknown provider).
- `tests/test_providers_acrcloud.py` — `identify_track` response handling (success,
  no-result code → empty music, HTTP 401/429 → typed errors, invalid JSON, and the
  `AudioSegment` input path).
- `tests/test_identification_circuit_breaker.py` — breaker trips after repeated
  failures (and stops calling the provider); `record_result` resets the streak.

---

## Part B — Forward improvement plan (prioritized backlog)

### B1. 🟡 Shazam error semantics & circuit-breaker accuracy
**Problem.** `providers/shazam.py::identify_track` returns `None` on *all* errors,
including genuine network/provider failures. With the breaker now wired, those
failures are recorded as **success** (no exception is raised), so the breaker
never trips for Shazam — the most-used provider.
**Approach.** Distinguish "no match" (return `None`) from "request failed" (raise
`ProviderError`/`RateLimitError`), matching ACRCloud/Spotify. The loop already maps
an exception to a breaker failure.
**Files.** `providers/shazam.py`; tests in `tests/`.
**Risk.** 🟡 Changes what the loop sees on Shazam errors; add tests for both paths.

### B2. 🔴 Parallelize per-segment identification
**Problem.** `utils/identification.py` processes segments strictly sequentially even
when the rate limiter permits concurrency (`max_concurrent_requests > 1`).
**Approach.** Dispatch `identify_track` calls under an `asyncio.gather` bounded by
the existing limiter/semaphore; preserve result ordering and per-call breaker
accounting; keep the Shazam cooldown semantics intact.
**Files.** `utils/identification.py`, `utils/rate_limiter.py`.
**Risk.** 🔴 Interacts with rate limiting, cooldown, ordering, and the breaker.
Needs careful design and new concurrency tests.

### B3. 🟡 Rate limiter: event-driven token wait
**Problem.** `RateLimiter.acquire` polls every `TOKEN_REFILL_SLEEP` (10 ms) while
waiting for tokens — a busy-wait that wakes ~100×/s per waiter.
**Approach.** Replace the poll loop with an `asyncio.Condition` notified by
`_refill_tokens`, or compute the exact sleep-until-next-token interval.
**Files.** `utils/rate_limiter.py`.
**Risk.** 🟡 Core timing path; existing rate-limiter tests must stay green, add
tests for wakeup correctness.

### B4. 🟡 Cache storage: bounded per-key locks
**Problem.** `cache/storage.py` allocates one `asyncio.Lock` per unique key and never
evicts, so the lock dict grows with the key space.
**Approach.** Use a bounded pool of locks (hash key → fixed-size lock array) or an
LRU of locks. Evicting a lock that's in use must be impossible — design carefully.
**Files.** `cache/storage.py`.
**Risk.** 🟡–🔴 Concurrency-correctness sensitive.

### B5. 🟡 Cache: avoid write-on-every-hit for access metadata
**Problem.** `cache/base.py::get` rewrites the entry to storage whenever
`update_metadata` changes `last_accessed`, i.e. on most hits — disk I/O on the hot
read path.
**Approach.** Sample/throttle access-time updates (e.g. only persist every Nth hit
or after a time delta), or keep access metadata in memory and flush periodically.
**Files.** `cache/base.py`, `cache/invalidation.py`.
**Risk.** 🟡 Slightly staler LRU/access stats; behavior otherwise unchanged.

### B6. 🟢 Spotify `enrich_metadata` silent no-op
**Problem.** When `search_track` finds no match, the input dict is returned
unchanged with no signal — callers can't tell "enriched" from "not found".
**Approach.** Log at debug and/or annotate the result (e.g. `enriched: False`).
**Files.** `providers/spotify.py`.
**Risk.** 🟢 Additive.

### B7. 🔴 Spotify `add_tracks_to_playlist` batch concurrency
**Problem.** 100-track batches are added sequentially.
**Caveat.** Parallelizing with `asyncio.gather` can **reorder** tracks in the
playlist — a behavior change. Only pursue if order-preservation is guaranteed
(e.g. position indices) or order is deemed unimportant.
**Files.** `providers/spotify.py`.
**Risk.** 🔴 Ordering semantics.

### B8. 🟡 Decouple CLI overrides from config mutation
**Problem.** `core/base.py::process_input` mutates the shared config singleton
(`self.config.primary_provider = ...`) and rebuilds the manager mid-run.
**Approach.** Pass overrides explicitly or use a per-run config copy, so the global
singleton isn't mutated.
**Files.** `core/base.py`, `config/`.
**Risk.** 🟡 Touches config lifecycle; singleton tests must stay green.

### B9. 🟢 Non-blocking audio metadata probe
**Problem.** `core/base.py::split_audio` calls synchronous `mutagen.File()` on the
event loop. (An earlier attempt was reverted because `split_audio` is synchronous.)
**Approach.** Make `split_audio` async and `await asyncio.to_thread(File, ...)`, or
provide an async wrapper; update its single caller and tests.
**Files.** `core/base.py` and tests calling `split_audio`.
**Risk.** 🟢–🟡 Mechanical but ripples into the caller/tests.

### B10. 🟢 Circuit breaker HALF_OPEN re-open
**Problem.** `_update_circuit_breaker` only transitions `CLOSED → OPEN`; a failure
while `HALF_OPEN` doesn't re-open the circuit (it waits for the next success or
another full threshold from CLOSED).
**Approach.** On failure in `HALF_OPEN`, transition straight back to `OPEN` and
reset `circuit_open_time`.
**Files.** `utils/rate_limiter.py`; extend breaker tests.
**Risk.** 🟢 Small, well-scoped state-machine fix.

---

## Part C — Verification & conventions

```bash
uv sync
uv run python -m pytest -q                 # full suite (use `python -m`, not bare pytest)
uv run ruff check src/ tests/              # lint
uv run ruff format --check src/ tests/     # format gate
uv run vulture src/tracklistify            # dead-code scan
```

Conventions when picking up a backlog item:
- One change per concern; Conventional Commits (`feat`/`fix`/`perf`/`refactor`/…).
- Add or extend tests **in the same change**; prefer mocking `_api_request` /
  `_get_session` over network access.
- For config-touching tests, `get_config(force_refresh=True)` and
  `monkeypatch.delenv("TRACKLISTIFY_*", raising=False)`.
- Keep behavior changes (Part B 🟡/🔴) gated/flagged and called out in the PR.
