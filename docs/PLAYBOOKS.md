# Playbooks

Step-by-step procedures for the recurring changes in this codebase. Follow
them literally; each ends with the exact verification commands. The traps
listed are real failures, not hypotheticals. Background/why lives in
[ARCHITECTURE.md](ARCHITECTURE.md).

Every playbook ends the same way:

```bash
uv run ruff check src/ tests/ scripts/ && uv run ruff format src/ tests/ scripts/
uv run python -m pytest -q      # NOT `uv run pytest` — see CLAUDE.md
```

---

## Add an identification provider

1. Subclass `TrackIdentificationProvider` (`providers/base.py`) in a new
   `providers/<name>.py`.
   - `identify_track(audio_segment)` receives an `AudioSegment` (object
     with `file_path`, `start_time`, `duration`). Read the file yourself
     (use `await asyncio.to_thread(Path(...).read_bytes)` — file IO blocks
     the event loop).
   - Return `{"metadata": {"music": [{"title": str, "artists": [{"name":
     str}], "score": float}]}}`. **Score must be 0–100**, not 0–1 — Track
     construction rejects anything outside 0–100.
   - Return `None` or an empty `music` list for "no match". Raise a
     `ProviderError` subclass for real failures (this feeds the circuit
     breaker; returning None on errors hides outages).
   - Re-raise `RateLimitError` / `AuthenticationError` unchanged — never
     let a generic `except Exception` swallow them.
2. Register in `providers/factory.py::get_identification_provider`:
   - Add a branch AND add the name to `KNOWN_PROVIDERS`.
   - Credentials come from `os.getenv("TRACKLISTIFY_<NAME>_...")` — **not**
     from config dataclass fields (secrets must stay out of `repr()` and
     validation errors). Missing credentials must raise `ConfigError` with
     a message naming the exact env vars (I3 test enforces this).
3. Rate limits: add `<name>_max_rpm` / `<name>_max_concurrent` fields to
   `TrackIdentificationConfig` with sane defaults, add a branch in
   `RateLimiter.register_provider`, and map the fields to a section in
   `scripts/generate_env_example.py`, then run the script.
4. Document credentials in the `CREDENTIALS_BLOCK` of
   `scripts/generate_env_example.py` and regenerate.
5. Tests: mock the HTTP session (see
   `tests/test_handoff_invariants.py::test_acrcloud_identify_accepts_audio_segment`
   for the pattern). Never hit the network.
6. Run `uv run python -m pytest tests/test_handoff_invariants.py -q` —
   I3 picks up the new `KNOWN_PROVIDERS` entry automatically.

**The trap:** implementing `identify_track(bytes)` instead of
`identify_track(AudioSegment)`. That exact mismatch made ACRCloud dead on
arrival for its entire life pre-2026-07. The pipeline passes segments.

---

## Add a config option

1. Add the field to `TrackIdentificationConfig` (`config/base.py`) with a
   default. The env var `TRACKLISTIFY_<UPPER_NAME>` works automatically.
2. Bounds? Add a rule in `_setup_validation` (they ARE enforced now).
   Cross-field constraint? Add it to `TrackIdentificationConfig._validate`
   after `super()._validate()`.
3. Assign the field to a section in
   `scripts/generate_env_example.py::FIELD_SECTIONS` (the script — and the
   CI `drift` job — hard-fails on unmapped fields). Add an
   `INLINE_COMMENTS` entry for units/bounds.
4. `uv run python scripts/generate_env_example.py`
5. **Actually consume the field.** Grep for an existing consumer before
   assuming; this codebase already shipped `min_confidence`,
   `fallback_*` (pre-2026-07), `overlap_strategy`, `min_segment_length`,
   and most `cache_*` fields as no-ops. A config option nobody reads is a
   lie to the user — if you can't wire it now, don't add it.

**The trap:** step 5. The env example and dataclass make an option *look*
supported long before anything reads it.

---

## Add an output format

1. Add `_save_<fmt>()` to `exporters/tracklist.py::TracklistOutput`,
   returning the written `Path`.
2. Wire it into `save()`'s dispatch and add the format to `save_all()`'s
   list.
3. Add the choice to the `--formats` argparse option in `cli.py` and to
   the `output_format` inline comment in `generate_env_example.py`.
4. Filenames must go through the existing `_format_filename` /
   `clean_string` path — it strips path separators from titles (YouTube
   titles are untrusted input).

---

## Touch `split_audio`

- Keep the two guards: positive step, and ffmpeg-missing error.
- Keep `-ss` **before** `-i` (input-seek; after `-i` = decode-from-start
  per segment, quadratic total work).
- Keep `-c:a copy`; re-encoding multiplies runtime by ~100x on long mixes.
- Keep the final `segments.sort(key=...)` — `as_completed` yields out of
  order and downstream assumes chronological order.
- Segment filename shape `segment_<start>_<len><suffix>` inside
  `self.temp_dir` (per-run dir); `cleanup()` and the stale-PID sweeper
  depend on the dir layout.

## Touch the rate limiter

- Every code path out of `acquire()` after the semaphore is taken must
  either return True or release the semaphore. Check the `except
  BaseException` block still covers cancellation.
- `record_result(provider, success)` is the only sanctioned way to feed
  the circuit breaker from outside; keep the identification loop calling
  it on both outcomes.
- Only `asyncio` primitives inside acquire/release paths. A
  `threading.Lock` held across an `await` will deadlock the event loop —
  that bug was already fixed once (commit 86fa9fc); don't reintroduce it.

## Touch config loading

- Order in `__post_init__` is load-bearing:
  `_load_from_env` → `_create_directories` → `_setup_validation` →
  `_validate`. Validation must see env-loaded values; directory PathRules
  must run after dirs exist (or use `create_if_missing`).
- Tests mutating env: `monkeypatch.delenv("TRACKLISTIFY_*", ...)` first,
  `get_config(force_refresh=True)` after. A developer's local `.env`
  otherwise bleeds into CI-green-but-locally-red test failures.

## Release / version bump

- `cz bump` (commitizen) reads `[project].version` via
  `version_provider = "pep621"`. Don't set it back to `"poetry"`; the
  project migrated to uv and there is no `[tool.poetry]` table.

## Debugging a 3am "no tracks identified" report

Work down this list; each step has a distinct signature:

1. **ffmpeg missing** → the CLI now refuses to start; if running via API,
   look for the `ffmpeg not found on PATH` error log.
2. **Download failed / wrong file** → check the `Downloaded audio to:` log
   line and whether the file exists with nonzero size.
3. **Segments empty** → `Split audio into 0 segments`; usually a corrupt
   download or an ffmpeg build without the needed demuxer.
4. **Provider errors on every segment** → `<provider> identification
   failed for segment at Ns:` lines; check credentials (ACRCloud) or
   upstream throttling (Shazam). Circuit breaker opening shows up as
   `Rate limiter rejected request` after repeated failures.
5. **Everything "no match"** → genuine content problem (unreleased music,
   heavy overlays). Try `--provider acrcloud` (needs creds) or smaller
   `TRACKLISTIFY_SEGMENT_LENGTH`.
