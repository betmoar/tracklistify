# CLAUDE.md

Instructions for Claude working on **Tracklistify** — automatic tracklist generator for DJ mixes (Shazam, ACRCloud, Spotify providers; YouTube/Mixcloud/SoundCloud downloaders).

Stack: Python 3.11–3.13, `uv` package manager, `pytest` (asyncio strict), `ruff` for lint + format. ffmpeg required at runtime. **Deno also required for YouTube downloads** — the `yt-dlp-ejs` solver scripts (pulled in via the `yt-dlp[default]` extras) run inside Deno to handle YouTube's signature / n-param challenges.

---

## Commands

| Task | Command |
|---|---|
| Install deps | `uv sync` |
| **Run tests** | `uv run python -m pytest -q` |
| Run one test | `uv run python -m pytest tests/test_x.py::test_y -v` |
| Coverage | `uv run python -m pytest --cov=tracklistify --cov-report=html tests/` |
| Lint | `uv run ruff check src/ tests/ scripts/` |
| Format | `uv run ruff format src/ tests/ scripts/` |
| Format check | `uv run ruff format --check src/ tests/ scripts/` |
| Run CLI | `uv run tracklistify <input>` |
| Dead-code scan | `uv run vulture src/tracklistify` |
| Regenerate `.env.example` | `uv run python scripts/generate_env_example.py` (`--check` in CI) |

CI (`.github/workflows/ci.yml`) runs lint, format check, the `.env.example`
drift check, and the test suite on Python 3.11–3.13. Keep it in sync with
this table.

**Always use `uv run python -m pytest`, not bare `pytest`.** A pyenv-ambient pytest 7.x will shadow the venv's pytest 8.x and silently break async-mode strict.

---

## Project-specific gotchas

- **`uv run pytest` picks up pyenv's pytest 7.4** instead of the venv's 8.x — always `uv run python -m pytest`.
- **`get_config()` is a module-level singleton.** Tests that mutate env must call `get_config(force_refresh=True)` *and* `monkeypatch.delenv("TRACKLISTIFY_*", raising=False)` for any vars they don't want bleeding in from local `.env`.
- **Providers are async context managers.** Always `async with provider:` — bare `with` silently breaks cleanup.
- **Rate-limiter release in `finally`.** `await limiter.acquire(...)` must always be matched by `limiter.release(provider)` or tokens leak. Report request outcomes via `limiter.record_result(provider, success)` or the circuit breaker never learns and never opens.
- **Logger naming:** `get_logger(__name__)` — never a literal module string, so log lines attribute to the right module and the third-party noise caps (symphonia) stay scoped.
- **Singletons are thread-safe via `threading.Lock`.** Don't add a parallel lock for "extra safety"; double-checked locking is already in place (`get_config`, cache factory, `get_global_rate_limiter`).
- **`audioop-lts` is the 3.13 dep.** PEP 594 removed stdlib `audioop`; `pyproject.toml` has the conditional `python_version >= '3.13'` marker. Pydub imports `audioop` directly, so the shim is required.
- **Ruff `include` path is `src/tracklistify/**/*.py`** (not `tracklistify/**/*.py`). Wrong glob silently lints zero files — burned us once.
- **Env-var truthiness:** use lowercase `true`/`false`. `True` may not parse depending on type-coercion path.
- **`Track` is a `@dataclass` with `__post_init__` validation.** Don't write a manual `__init__` — it overrides the generated one and breaks `field(default_factory=dict)` semantics for `metadata`.
- **Spotify `_api_request` accepts any 2xx and handles 204.** Don't narrow to `== 200`; mutation endpoints return 201, DELETEs return 204 with empty body.
- **Spotify wrappers must re-raise `RateLimitError` / `AuthenticationError` unchanged.** Catch them before the generic `except Exception` or callers lose retry-after timing and 401-driven token refresh.
- **`--stream-copy` (`-sc`) keeps the source codec end-to-end.** yt-dlp skips its MP3 transcode and segments stream-copy whatever YouTube served (opus/webm or m4a). Shazamio decodes via pydub/ffmpeg so any format works; ACRCloud historically prefers MP3 — if identification rates drop with `-sc` + ACRCloud, drop the flag for that run.
- **Provider secrets are env-only, never config-dataclass fields** — keeps them out of `repr()` and validation error messages. ACRCloud: `TRACKLISTIFY_ACR_ACCESS_KEY`/`_SECRET` (+ optional `_HOST`), read in `providers/factory.py`. Follow this pattern for new providers.
- **`config.min_confidence` (0–1) and `Track.confidence` (0–100) are different scales**: the config knob is wired (`TrackMatcher.__init__` scales it `* 100`), but the property **setter does not scale** — `matcher.min_confidence = config.min_confidence` silently means 0.8%, not 80%. Default is `0.0` (keep all). The `mock_config` fixture must stay at `0.0` or it filters the whole suite.
- **Dedup lives in `get_unique_tracks` only** (`add_track` just gates+appends). The two cluster axes anchor on opposite ends and neither may be "any member" — that form chains transitively and silently deletes distinct plays. **Proximity** is anchored on `cluster[-1]` (the most recent detection), so an unbroken step cadence can extend past the window; anchoring it on `cluster[0]` bounds the span and splits long tracks. **Identity** is anchored on `cluster[0]`, so membership cannot drift — artist Jaccard is not transitive, and a collaboration credit will otherwise bridge two distinct artists. `_rep_key` must never read confidence (Shazam jitter → unstable output). Before touching any of it, read `docs/playbooks/changing-dedup.md`.
- **The cache is wired into identification.** `IdentificationManager.identify_tracks` consults `get_cache()` before each provider call (key `f"{provider}:{sha256(segment_bytes)}"`) and stores successful responses. All cache I/O is best-effort (failures degrade to live identification, never abort). Gated by `config.cache_enabled`.
- **The download cache is URL-keyed and per-provider canonicalized.** `AsyncApp.process_input` checks `DownloadCache` (`cache_dir/downloads/<sha256>` + `.meta.json` sidecar) before downloading; on hit the network is skipped and metadata flows from the sidecar. Key is `sha256(f"{canonicalize_url(url)}|stream_copy={stream_copy}")` — `downloaders/cache_key.py` collapses YouTube URL variants to `yt:<video_id>`, SoundCloud to `sc:<host><path>`, Mixcloud to `mc:<user>_<slug>`. Separate from `BaseCache` (rejects binary blobs); no TTL/eviction in v1. Gated by `config.download_cache_enabled`.
- **Output is self-contained per set.** `output/[date] Artist - Title/` holds `tracklist.{json,md,m3u}` + the source audio (copied by `_copy_audio_to_output`). The M3U uses VLC `#EXTVLCOPT:start-time` for per-track seeking against the single audio file. `TracklistOutput.__init__` creates the subfolder; files use fixed `tracklist.{ext}` names (folder is the identity). The uploader must flow into `mix_info["artist"]` or folder names say "Unknown Artist".
- **`mix_info` is load-bearing for output.** `save_output` populates it: `title` (from `self.original_title`), `artist` (`self.uploader`), `total_duration` (`self.duration`), and `audio_filename` (set by `_copy_audio_to_output`). The M3U reads `total_duration` for the last track's EXTINF and `audio_filename` for the playable URI — missing either degrades the playlist but doesn't break the run.
- **`tests/test_handoff_invariants.py` locks the load-bearing invariants** (validation enforced, positive segmentation step, provider constructibility, fallback chain, circuit-breaker wiring, cache TTL/index persistence). If one fails, read docs/ARCHITECTURE.md before "fixing" the test.

---

## Architecture pointers

Read the code; line counts rot too fast to document. Key entry points:

| Concern | Module |
|---|---|
| Main orchestrator | `src/tracklistify/core/base.py::AsyncApp` |
| CLI entry | `src/tracklistify/cli.py::main` |
| Provider factory | `src/tracklistify/providers/factory.py` |
| Cache singleton | `src/tracklistify/cache/factory.py::get_cache` |
| Rate limiter singleton | `src/tracklistify/utils/rate_limiter.py::get_global_rate_limiter` |
| Config dataclasses | `src/tracklistify/config/base.py` |
| Type protocols | `src/tracklistify/core/types.py` |
| Constants (timeouts, thresholds, magic numbers) | `src/tracklistify/utils/constants.py` |

Patterns in use: Factory, Strategy (cache invalidation), Protocol (structural typing), Singleton (with `threading.Lock`), Circuit Breaker (rate limiter), async context manager (providers).

---

## Configuration

All config lives in `TrackIdentificationConfig` (`config/base.py`). Every field has a `TRACKLISTIFY_<UPPER>` env-var override. See `.env.example` for the complete list — don't duplicate it here.

Access via `from tracklistify.config import get_config; cfg = get_config()`. Use `force_refresh=True` in tests.

---

## Testing conventions

- `pytest-asyncio` in **strict mode** — every async test needs `@pytest.mark.asyncio`.
- Prefer `tmp_path` fixture over building paths manually.
- For provider tests, monkeypatch `_api_request` or `_ensure_session`; don't hit the network.
- For config tests touching env, `monkeypatch.delenv("TRACKLISTIFY_*", raising=False)` first.
- Coverage source is `src/` (see `[tool.coverage.run]` in `pyproject.toml`); `dev_cli/` is excluded.

---

## Git / commits

- **Conventional Commits via commitizen.** Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`.
- Pre-commit hooks: trailing whitespace, EOF, YAML check, ruff (lint + format), commitizen message validation.
- Pre-push hook validates branch names.
- Install hooks once: `pre-commit install && pre-commit install --hook-type pre-push`.

Don't commit unless explicitly asked. When asked, use heredoc commit messages for multi-line bodies.

---

## Doing common tasks

**Follow `docs/PLAYBOOKS.md`** — it has the full step-by-step procedures with
the traps spelled out (add a provider, add a config option, add an output
format, touch split_audio / rate limiter / config loading, debug "no tracks
identified"). The load-bearing map and landmines are in
`docs/ARCHITECTURE.md`; known debt in `docs/BACKLOG.md`.

Quick reminders (the playbooks have the detail):
- **Provider:** `identify_track` takes an `AudioSegment` (not bytes), returns score on 0–100, registers in `KNOWN_PROVIDERS`; missing creds → `ConfigError` naming the env vars.
- **Config option:** must be assigned in `generate_env_example.py::FIELD_SECTIONS` (CI drift job fails otherwise) — and something must actually *read* the field, or don't add it.
- **Output format:** method on `TracklistOutput`, wire into `save()` + `save_all()`, extend `--formats` choices.

For everything else, read the surrounding code — it's the source of truth, not this file.

---

## What goes here vs. elsewhere

- **Here:** rules that prevent repeated mistakes, project-specific gotchas, command pointers.
- **In `docs/`:** tutorials, architecture deep-dives, CHANGELOG, contribution guidelines.
- **In `.env.example`:** every config field with its env var.
- **In code:** anything explanatory about how the code works.

Keep this file **under 200 lines** (current target). If a rule isn't preventing a repeated mistake, it doesn't belong here.
