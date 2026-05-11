# CLAUDE.md

Instructions for Claude working on **Tracklistify** — automatic tracklist generator for DJ mixes (Shazam, ACRCloud, Spotify providers; YouTube/Mixcloud/SoundCloud downloaders).

Stack: Python 3.11–3.13, `uv` package manager, `pytest` (asyncio strict), `ruff` for lint + format. ffmpeg required at runtime.

---

## Commands

| Task | Command |
|---|---|
| Install deps | `uv sync` |
| **Run tests** | `uv run python -m pytest -q` |
| Run one test | `uv run python -m pytest tests/test_x.py::test_y -v` |
| Coverage | `uv run python -m pytest --cov=tracklistify --cov-report=html tests/` |
| Lint | `uv run ruff check src/ tests/` |
| Format | `uv run ruff format src/ tests/` |
| Format check | `uv run ruff format --check src/ tests/` |
| Run CLI | `uv run tracklistify <input>` |
| Dead-code scan | `uv run vulture src/tracklistify` |

**Always use `uv run python -m pytest`, not bare `pytest`.** A pyenv-ambient pytest 7.x will shadow the venv's pytest 8.x and silently break async-mode strict.

---

## Project-specific gotchas

- **`uv run pytest` picks up pyenv's pytest 7.4** instead of the venv's 8.x — always `uv run python -m pytest`.
- **`get_config()` is a module-level singleton.** Tests that mutate env must call `get_config(force_refresh=True)` *and* `monkeypatch.delenv("TRACKLISTIFY_*", raising=False)` for any vars they don't want bleeding in from local `.env`.
- **Providers are async context managers.** Always `async with provider:` — bare `with` silently breaks cleanup.
- **Rate-limiter release in `finally`.** `await limiter.acquire(...)` must always be matched by `limiter.release(provider)` or tokens leak.
- **Logger naming:** `get_logger(__name__)` — never a literal module string. The package logger config inspects `__name__` for per-module level overrides.
- **Singletons are thread-safe via `threading.Lock`.** Don't add a parallel lock for "extra safety"; double-checked locking is already in place (`get_config`, cache factory, `get_global_rate_limiter`).
- **`audioop-lts` is the 3.13 dep.** PEP 594 removed stdlib `audioop`; `pyproject.toml` has the conditional `python_version >= '3.13'` marker. Pydub imports `audioop` directly, so the shim is required.
- **Ruff `include` path is `src/tracklistify/**/*.py`** (not `tracklistify/**/*.py`). Wrong glob silently lints zero files — burned us once.
- **Env-var truthiness:** use lowercase `true`/`false`. `True` may not parse depending on type-coercion path.
- **`Track` is a `@dataclass` with `__post_init__` validation.** Don't write a manual `__init__` — it overrides the generated one and breaks `field(default_factory=dict)` semantics for `metadata`.
- **Spotify `_api_request` accepts any 2xx and handles 204.** Don't narrow to `== 200`; mutation endpoints return 201, DELETEs return 204 with empty body.
- **Spotify wrappers must re-raise `RateLimitError` / `AuthenticationError` unchanged.** Catch them before the generic `except Exception` or callers lose retry-after timing and 401-driven token refresh.

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

- **Add a provider:** subclass `TrackIdentificationProvider` from `providers/base.py`, register in `providers/factory.py::get_identification_provider`, add config fields to `TrackIdentificationConfig`, add tests with mocked `_api_request`.
- **Add an output format:** add a method to `exporters/tracklist.py::TracklistOutput`, wire it into `save_all`, extend the `cli.py` `--formats` choices.
- **Add a config option:** add a field to `TrackIdentificationConfig` (`config/base.py`) with a default; add validation in `__post_init__` if it has bounds; assign the field to a section in `scripts/generate_env_example.py::FIELD_SECTIONS`; run `uv run python scripts/generate_env_example.py` to refresh `.env.example`.

For everything else, read the surrounding code — it's the source of truth, not this file.

---

## What goes here vs. elsewhere

- **Here:** rules that prevent repeated mistakes, project-specific gotchas, command pointers.
- **In `docs/`:** tutorials, architecture deep-dives, CHANGELOG, contribution guidelines.
- **In `.env.example`:** every config field with its env var.
- **In code:** anything explanatory about how the code works.

Keep this file **under 200 lines** (current target). If a rule isn't preventing a repeated mistake, it doesn't belong here.
