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

## Add an enrichment source

Enrichment (Spotify, MusicBrainz, Beatport) is a *separate* path from
identification — it runs post-dedup in
`utils/identification.py::_enrich_tracks`, adding canonical links + extra
metadata to already-identified tracks. Each source has its own
`_enrich_<name>` pass and a `get_<name>_provider` accessor on
`ProviderFactory` (cached under a non-colliding `_`-prefixed key so it never
shadows an identification provider).

- **Credentials env-only** (same rule as identification providers), read in
  the factory accessor, never on the config dataclass.
- **Best-effort contract:** enrichment never fails a run. The per-track hook
  (`_enrich_one_<name>`) wraps the lookup in try/except, reports outcomes via
  `limiter.record_result`, and degrades a failure to a per-track miss; a
  `ProviderError` (structural, e.g. auth config broken) disables the whole
  pass once rather than retrying per track.
- **Beatport auth specifics** (the load-bearing detail): use the **docs**
  OAuth client (`app:docs`, scraped from `/v4/docs/` JS at runtime — it
  rotates), not the storefront `app:prostore` id (401s on `/catalog/`). The
  login POST enforces a CSRF `Referer` check; the token-exchange POST needs
  `Referer: /auth/o/authorize/`. The docs client supports the refresh-token
  grant (the storefront one does not). See `providers/beatport.py` and the
  P3 entry in `docs/BACKLOG.md`.
- **The enrichment title gate** (`_enrichment_title_match` in `core/track.py`)
  is intentionally looser than the dedup gate (recall for matching, precision
  for dedup). It gates on **remixer identity**: `_extract_mix_info` pulls
  remixer names and generic mix types out of the title's bracketed suffixes,
  and `_any_remixer_in` / `_mix_type_matches` compare them against Beatport's
  `remixers` / `mix_name`. **It rejects only on data it can verify** — when
  Beatport supplies neither field there is nothing to contradict, so the
  match falls through to the `_title_stem` comparison instead of failing.
  Rejecting on absent data is a recall regression that has been introduced
  (and caught in review) once per branch. See U15 in `docs/BACKLOG.md` and
  `scripts/measure_beatport_remix_matches.py` for the live probe.

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
   assuming; this codebase has shipped documented config knobs that were
   no-ops (`min_confidence`, `fallback_*` pre-2026-07,
   `overlap_strategy`, `min_segment_length`). A config option nobody
   reads is a lie to the user — if you can't wire it now, don't add it.

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
- **Tag chain is `v0.7.0`→HEAD, all `v`-prefixed.** `v0.7.0` (2025-09
  clean-slate squash) and `v0.8.0` (2026-05 audit) were reconstructed as
  back-dated annotated tags; `changelog_start_rev = "v0.7.0"` is the oldest
  commitizen sees. If a tag is missing or lacks the `v` prefix, `cz` silently
  mis-ranges or aborts — create back-dated annotated tags (`git tag -a` with
  `GIT_COMMITTER_DATE`) to match.
- **Never let `cz` auto-regenerate the changelog.** `update_changelog_on_bump`
  is `false` because `cz bump` runs the *non-incremental* generator, which
  regenerates from `changelog_start_rev` and overwrites curated history
  (observed: it replaced a hand-written `### Added` section with a wrong
  duplicate `### Fix`). The repeatable flow is two steps:
  1. `cz changelog --incremental` — adds one section for the new version,
     preserves the rest. Then hand-curate it to match the existing
     narrative style (bold lead-ins, one fix per bullet).
  2. `cz bump` — bumps `pyproject.toml`, commits, and tags `v$version`.
     Changelog untouched.
- Back-dating a tag at a past commit:
  `GIT_COMMITTER_DATE="2025-09-15T21:07:03+02:00" git tag -a v0.7.0 <sha>
  -m "Release …"`. Use the commit's author date (`git log -1 --format=%ci`).

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
