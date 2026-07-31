# Residual Risk Register & Backlog

From the 2026-07 handoff audit. Ordered by priority. Each item has enough
context to be picked up cold. "Fixed" items are listed at the bottom so
nobody re-audits them from scratch.

## P1 — wire the cache into identification — DONE

Wired in `feat/wire-cache-identification`. `IdentificationManager.identify_tracks`
now consults `get_cache()` before each provider call (key
`f"{provider}:{sha256(segment_bytes)}"`) and stores successful responses;
all cache I/O is best-effort (failures degrade to live, never abort), gated
by `config.cache_enabled`. Covered by `tests/test_cache_wiring.py` (9 cases).

**Remaining internal cache debt (fix opportunistically):**
`SizeStrategy` treats the whole-cache byte budget as a per-entry limit and
nothing enforces aggregate size (no eviction); compression detection sniffs
zlib magic bytes instead of using the stored `compression` flag (breaks if
anyone wires `cache_compression_level` ≠ 6); `BaseCache.get()` rewrites the
entry file on every hit (write amplification); `_stats["entries"]`
over-counts overwrites.

## P2 — decide `min_confidence` semantics

`config.min_confidence` (0.0–1.0) is documented and validated but ignored:
`TrackMatcher` hardcodes 0. Options:
- (a) Wire it: `TrackMatcher.__init__` sets `self._min_confidence =
  config.min_confidence * 100`. Behavior change: default 0.5 would drop
  sub-50% matches — decide whether the default should become 0.0 to
  preserve current output.
- (b) Remove the field and its env var.
Recommendation: (a) with default lowered to 0.0, so the knob works but
nothing changes until a user turns it.

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

---

## Fixed in the 2026-07 audit (do not re-fix; locked by tests)

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
