# Residual Risk Register & Backlog

From the 2026-07 handoff audit. Ordered by priority. Each item has enough
context to be picked up cold. "Fixed" items are listed at the bottom so
nobody re-audits them from scratch.

## P2 — Spotify enrichment is built but unreachable

`SpotifyProvider` (search/enrich, client-credentials auth) works but no
pipeline stage calls `enrich_metadata`. The natural hook: after
`TrackMatcher.get_unique_tracks()` in `identify_tracks`, enrich each track's
`metadata` dict when Spotify creds are configured. Keep it strictly optional
(no creds → skip silently).

`exporters/spotify.py` (playlist export) is a different story: it calls
`/me/playlists`, which client-credentials tokens can NEVER access. Wiring it
requires implementing the authorization-code flow (user consent, token
refresh). Don't attempt as a drive-by; it's a feature project.

**Scope note (from the 2026-07 exploration):** ~~the hook alone is invisible.
No exporter serializes `Track.metadata`~~ — **resolved 2026-08-01** (PR #57,
folded into `fix/p2-dedup-confidence-downloader`): `_save_json` now emits
`metadata` per track and `_extra_metadata` threads provider extras into
`Track.metadata`, so an enrichment hook is now visible without further
exporter work. Markdown and M3U still build their own strings and ignore
`metadata` — extend them only if a user asks. Also:
`enrich_metadata` takes a plain dict keyed on `title`/`artist` (a `Track`
uses `song_name`), mutates in place, and deliberately re-raises
`RateLimitError`/`AuthenticationError` — the caller must catch those two.
Keep Spotify **out** of `KNOWN_PROVIDERS` (it has no `identify_track`, so
`-p spotify` would crash); use a separate `Optional[SpotifyProvider]`
accessor that returns `None` when creds are absent.

## P3 — evaluate RapidAPI Shazam as a `shazamio` alternative/fallback

<https://rapidapi.com/apidojo/api/shazam> (apidojo). A hosted HTTP Shazam
API, versus `shazamio` which reverse-engineers the mobile endpoints
directly. Worth evaluating because shazamio's approach is the fragile part
of the current stack: it carries a `shazam_cooldown_seconds` knob
(default 2.25s) and a `shazam_proxy` escape hatch specifically because
Shazam throttles and blocks, and an upstream protocol change breaks
identification with no vendor recourse. A paid, documented API trades
that fragility for cost and a rate cap.

**Evaluate before committing to it:**

- **Input format is the real cost.** `songs/detect` (and `songs/v2/detect`)
  take base64-encoded **raw PCM: 44100Hz, mono, signed 16-bit
  little-endian**, under 500KB (~3–5s is enough). Not mp3/wav. Our
  segments come out of `split_audio` as `AudioSegment` and go to
  providers as such, so this needs a pydub/ffmpeg conversion step in the
  provider — not a drop-in swap. An empty result usually means wrong
  input format, not "no match", so the provider must distinguish those or
  it will silently report every segment as unidentified.
- **Metadata parity.** The PR #57 extraction (`isrc`, `genres.primary`,
  `sections[].metadata` for Album/Label/Released, `hub.actions` for the
  Apple Music id, `images.coverarthq`) is shaped around shazamio's
  payload. Confirm the RapidAPI response carries the same fields before
  assuming `_extra_metadata` works unchanged.
- **Cost model.** RapidAPI tiers are per-request. A 3h mix at a 50s step
  is ~216 segments *per run*, times the fallback chain. Price a realistic
  run before wiring it as primary; it may only make sense as a fallback
  for when shazamio breaks.
- Some apidojo endpoints carry a "bot-defender" warning in their own docs
  — verify `songs/detect` specifically is reliable, not just listed.

**If it proceeds:** it's a normal provider add — follow
`docs/PLAYBOOKS.md`. `identify_track` takes an `AudioSegment`, returns a
0–100 score, registers in `KNOWN_PROVIDERS`, and raises `ConfigError`
naming the env var when the key is missing. Key is env-only
(`TRACKLISTIFY_RAPIDAPI_KEY`), never a config-dataclass field — same rule
as ACRCloud.

## P3 — delete or rescue `downloaders/spotify.py`

Dead (no factory route) and internally broken: `asyncio.run()` inside a
running loop (`_set_metadata`), enum-vs-string filename bug, and
`_get_stream_url` is called with a track id where a file id is expected.
Deleting ~400 lines + adjusting `test_imports.py`/`test_type_hints.py` is
the cheap option; rescuing it means rewriting its download flow against a
Spotify CDN API that may not be stable. Recommendation: delete.

## P3 — dev_cli cleanup

- `dev_cli/execution/executor.py` is unused (commands use `subprocess.run`
  directly); its timeout parameter is also never enforced. Delete.
- `dev_cli/config.py`: missing `tools.json` crashes at import (the
  `FileNotFoundError` fallback can never fire because a manual
  `ConfigurationError` is raised first); `load_default_config()` is called
  redundantly after construction.
- `RunCommand._run_tool` joins args into a string then re-splits with
  shlex — args containing spaces/quotes get mangled.

## P3 — config/docs.py accuracy

The doc generator works now (`scripts/generate_config_docs.py` was calling
a method that never existed; fixed), but: `_field_to_schema` parses
constraint strings like "Must be >= 10" by inspecting the wrong token, so
min/max never reach the JSON schema; `generate_schema` marks every field
required; `field.__doc__` is the `dataclasses.Field` class docstring, not a
field description. Low value — consider generating from
`_setup_validation` rules directly instead of parsing prose.

## P3 — security polish

- `mask_sensitive_value` reveals first/last 3 chars of secrets ≥ 8 chars;
  an 8-char secret leaks 6/8 characters. Raise the full-mask threshold to
  ~12.
- Two divergent sensitivity predicates (`is_sensitive_key` vs
  `is_sensitive_field`) — currently consistent, fragile on divergence.
  Collapse to one.
- `cache/storage.py` trusts `filename` from the on-disk index without a
  basename check; a tampered index could point delete/read at arbitrary
  paths. Add `os.path.basename(filename) == filename` validation on load.

## P4 — misc

- `utils/decorators.py::memoize` has an unused `ttl` param and unbounded
  growth, and no callers. Delete or finish.
- `core/types.py` declares a `Downloader` Protocol incompatible with the
  real `downloaders/base.py` ABC (different signature/return). Delete the
  Protocol.
- `core/run.py` cleanup-task registry is never populated; `ACRCLOUD_SUCCESS_CODE = 2000`
  in constants is actually ACRCloud's *auth error* code and is unused.
- `tests/test_cli_arguments.py` uses an unregistered `integration` pytest
  mark (warning noise); register it in pyproject or drop it.
- `pytest-asyncio` will eventually require `asyncio_default_fixture_loop_scope`;
  set it explicitly in `[tool.pytest.ini_options]` when upgrading.
- **Cache debt (identification + download):** the download cache has no
  TTL or eviction (v1 unbounded; `cache_max_size` is 1MB and too small for
  audio — manual `rm -rf cache_dir/downloads`). `download_quality`/
  `download_format` are not wired through the factory, so they're excluded
  from the download cache key (re-runs at different quality serve the old
  file until the key is extended). On the identification cache,
  `SizeStrategy` treats the byte budget as per-entry (no aggregate
  eviction); compression detection sniffs zlib magic instead of the stored
  flag; `BaseCache.get()` rewrites the entry on every hit (write
  amplification); `_stats["entries"]` over-counts overwrites.

---

## Fixed

### 2026-07 P2 correctness batch (`fix/p2-dedup-confidence-downloader`)

| Fix | Where | Test |
|---|---|---|
| Dedup missed artist-string variants (`Berghain (Remix)` twice, 50s apart) — the shipping `get_unique_tracks` keyed on exact `artist\|song` and was time-blind | `core/track.py::TrackMatcher.get_unique_tracks` | `tests/test_track_matcher.py::test_artist_variant_merge_berghain` |
| Representative `time_in_mix` flipped between runs (strict `>` on noisy confidence) | `core/track.py::_rep_key` (earliest time; confidence excluded outright — bucketing was tried and still flipped at bucket edges) | `test_representative_is_deterministic_under_confidence_noise` |
| `config.min_confidence` was a no-op (hardcoded 0); default 0.5 → 0.0 so output is unchanged until the knob is turned | `core/track.py::TrackMatcher.__init__`, `config/base.py` | `test_min_confidence_filters_low_confidence` |
| `TrackMatcher` re-resolved the global config, ignoring an injected one | `utils/identification.py` passes `self.config` | `tests/test_track_matcher.py` fixture |
| SoundCloud `/sets/` container metadata propagated (wrong title/duration/filename) | `downloaders/ytdlp.py::download` unwraps `_type == "playlist"` → `entries[0]` | `tests/test_ytdlp.py` |
| Output path reconstructed via `prepare_filename` missed muxing ext changes | prefer `requested_downloads[0]["filepath"]` | `tests/test_ytdlp.py` |
| Stale pre-fix `/sets/` metadata served forever (cache has no TTL) | `cache/download.py::KEY_VERSION` in key material | `tests/test_download_cache.py` |

**Dead code removed:** `merge_nearby_tracks` + its six helpers
(`_create_track_group`, `_should_add_to_group`, `_add_to_group`,
`_get_best_track`, `_is_unique_track`, `_add_to_merged_list`). These had
zero production callers — the backlog's original framing of the dedup bug
described *these*, not the shipping `get_unique_tracks`, which is why the
proposed levers (fuzzy `is_similar_to`, raise `time_threshold`) would not
have fixed anything. `add_track` no longer dedups; it confidence-gates and
appends.

**Known limitation (accepted, not fixed):** `"Berghain"` vs
`"Berghain (Remix)"` will not merge — titles must match exactly after
normalization. No fuzzy ratio separates that case from the
correctly-separate `"(Remix)"` vs `"(Radio Edit)"` pair (both score 0.727),
so exact-after-normalize is the only rule correct on both.

### 2026-07 cache + output work (`feat/wire-cache-identification`, PR #65)

| Fix | Where | Test |
|---|---|---|
| Identification cache never called by production code | `utils/identification.py::IdentificationManager` | `tests/test_cache_wiring.py` |
| Downloaded audio re-fetched every run | `cache/download.py`, `core/base.py::process_input` | `tests/test_download_cache*.py` |
| Output was a flat dir; M3U emitted comments only (no playable URI, EXTINF always -1) | `exporters/tracklist.py`, `core/base.py::save_output` | `tests/test_output_subfolders.py`, `tests/test_m3u_playable.py` |
| Mixcloud stored no metadata (`get_last_metadata()` returned None) | fixed via download-cache sidecar | `tests/test_download_cache_wiring.py` |
| Folder names said "Unknown Artist" (uploader never wired into output) | `core/base.py::save_output` → `mix_info["artist"]` | `tests/test_output_subfolders.py` |

### Fixed in the 2026-07 audit (do not re-fix; locked by tests)

| Fix | Where | Test |
|---|---|---|
| Config validation rules were never executed | `config/base.py::_validate` | I1 |
| `overlap >= segment` → infinite segmentation loop | config cross-check + `split_audio` guard | I2 |
| ACRCloud unconstructible (missing ctor args) + wrong `identify_track` signature | `providers/factory.py`, `providers/acrcloud.py` | I3, I4 |
| `--no-fallback` / `fallback_*` config were no-ops | `IdentificationManager` provider chain | I5 |
| Circuit breaker never received outcomes | `RateLimiter.record_result` + identify loop | I6 |
| Cache TTL disabled by stored `None` | `cache/base.py::set` | I7 |
| Cache index never saved on set/delete (cross-process data loss + orphan deletion of valid entries) | `cache/storage.py` | I8 |
| Cache index rename without fsync | `cache/index.py::save` | — |
| ffmpeg absence surfaced as cryptic per-segment errors | `cli.py` fail-fast + `split_audio` log | CLI tests |
| `TracklistOutput` mkdir without `parents=True` | `exporters/tracklist.py` | — |
| Spotify 429 lost structured `retry_after` | `providers/spotify.py` | — |
| `cz bump` broken (`version_provider = "poetry"` post-uv-migration) | `pyproject.toml` | — |
| `scripts/generate_config_docs.py` called a nonexistent method | fixed to use `ConfigDocGenerator` | — |
| Dead + broken module-level `identify_tracks(audio_path)` (iterated a string as segments) | removed from `utils/identification.py` | — |
