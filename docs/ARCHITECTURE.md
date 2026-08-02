# Architecture & Handoff Map

Written during the 2026-07 handoff audit. This is the mental model of the
system: what carries load, what assumptions the code makes without checking,
and where the landmines are. Read this before changing anything under
`src/tracklistify/`. Recurring change procedures live in
[PLAYBOOKS.md](PLAYBOOKS.md); known debt lives in [BACKLOG.md](BACKLOG.md).

## The pipeline in one paragraph

`tracklistify <input>` → `cli.py::cli()` parses args, checks ffmpeg exists,
loads `.env`, then `asyncio.run(main(args))` → `AsyncApp.process_input()`:
validate the input (`utils/validation.py::validate_input` — URL or local
file), download via `DownloaderFactory` (yt-dlp for YouTube/SoundCloud,
Mixcloud variant) into a per-run temp dir, slice into overlapping segments
with ffmpeg stream-copy (`AsyncApp.split_audio`, thread pool), identify each
segment via `IdentificationManager.identify_tracks` (provider chain with
rate limiting + circuit breaker), dedup via `TrackMatcher`, write
json/markdown/m3u via `TracklistOutput`, clean up the temp dir.

## Load-bearing inventory (ranked by blast radius)

| # | Component | Why it's load-bearing |
|---|---|---|
| 1 | `core/base.py::AsyncApp.process_input` | The only orchestration path. Every run goes through it. |
| 2 | `utils/identification.py::IdentificationManager.identify_tracks` | Provider chain, rate-limiter acquire/release pairing, circuit-breaker reporting. Break the release pairing and every run deadlocks after N segments. |
| 3 | `config/base.py` + `config/factory.py::get_config` | Module-level singleton. Everything reads config from here; many objects capture it at construction. |
| 4 | `core/base.py::split_audio` | ffmpeg segmentation. The `step = segment_length - overlap_duration` arithmetic MUST stay positive (guarded twice: config validation + a runtime check here). |
| 5 | `utils/rate_limiter.py::RateLimiter` | Token bucket + semaphore + circuit breaker. `acquire()` must always be paired with `release()` in a `finally`. |
| 6 | `core/track.py::Track` / `TrackMatcher` | Track validation (`__post_init__`) and dedup. Output quality lives here. |
| 7 | `providers/factory.py` | Provider name → instance. `KNOWN_PROVIDERS` is the registry; invariant test I3 keeps every entry constructible. |
| 8 | `providers/shazam.py` | The only provider that works with zero setup; the default path virtually every user takes. |
| 9 | `downloaders/ytdlp.py` | All YouTube/SoundCloud input. Requires ffmpeg and (for YouTube) Deno for yt-dlp-ejs challenge solving. |
| 10 | `exporters/tracklist.py` | The only output path (`save_all` / `save`). |

## Invariants (each is locked by `tests/test_handoff_invariants.py`)

- **I1** Config validation rules run at construction (`BaseConfig._validate`
  feeds dataclass fields to `ConfigValidator`). This was dead code until
  2026-07 — the rules were registered and never executed.
- **I2** `segment_length - overlap_duration > 0`, enforced at config load
  AND at the top of `split_audio` (config attributes are mutable after
  load — CLI overrides mutate them — so the config-time check alone is
  insufficient). Violation = infinite while-loop.
- **I3** Every name in `providers.factory.KNOWN_PROVIDERS` constructs via
  the factory or raises `ConfigError` naming the env vars to set. Never a
  bare `TypeError`.
- **I4** Providers take an `AudioSegment` (object with `file_path`) in
  `identify_track` and return `{"metadata": {"music": [{title, artists,
  score}]}}` with score on a **0–100** scale, or `None`/empty music list
  for no-match.
- **I5** Fallback: `fallback_providers` are tried in order only when
  `fallback_enabled` is true and the primary yielded no usable track.
- **I6** Every provider request outcome is reported to
  `RateLimiter.record_result` so the circuit breaker actually learns.
- **I7/I8** Cache TTL expiry works and the cache index is persisted on
  every mutation. The cache is consulted in `identify_tracks` (see landmine
  2 for the keying contract).

## Implicit contracts (assumed, not checked — tread carefully)

- `limiter.acquire(name)` / `limiter.release(name)` are paired per name,
  release in `finally`, and `release` is only called when `acquire`
  returned True. `acquire` itself releases its semaphore on all
  non-True exits.
- Providers are async context managers; `close()` must be re-entrable
  (the factory caches instances and `close_all()` may close them again).
  ACRCloud/Spotify recreate their aiohttp session lazily after close.
- `split_audio` returns segments sorted by `start_time`; identification
  and the "time in mix" output depend on that ordering.
- `Track.time_in_mix` is **elapsed** `H+:MM:SS` (hours unbounded, so a
  25-hour mix offset parses); never use `strptime("%H:%M:%S")` on it.
- `get_config()` is process-wide. Objects capture it at construction, so
  "refresh" only affects objects created afterwards. Tests must use
  `get_config(force_refresh=True)` *and* clear `TRACKLISTIFY_*` env vars.
- Confidence is 0–100 on `Track`, but `config.min_confidence` is 0.0–1.0.
  **These scales are different.** See landmine below.
- **`get_unique_tracks` is the sole dedup authority.** `add_track` only
  confidence-gates and appends; it does not dedup. Two tracks are "the
  same" iff their titles are equal after `_strip_title_variant` (drops
  non-distinguishing version/live tags, canonicalizes `feat.`/`ft.`/
  `featuring` markers while keeping the credited name; comparison-only —
  the representative keeps its raw title) AND normalization, AND their
  artist token sets overlap with Jaccard ≥ `_ARTIST_THRESHOLD` (0.34) —
  this collapses Shazam's collaboration-string noise (`"A & B & C"` vs
  `"B, C"`) without merging genuinely different artists (Jaccard 0.0).
- **Clusters chain on the gap to the last member.** A track joins a cluster
  only if it is within `_dedup_window()` of that cluster's **most recent**
  detection (`cluster[-1]`). Gap continuity — not total span — is what
  separates the two real cases: a long track keeps producing detections one
  segmentation step apart (observed: `Hands Up` at 18:20/19:10/20:00/20:50,
  span 150s, one continuous play), while two distinct plays are separated by
  minutes of other music. Testing against `cluster[0]` instead bounds the
  span and wrongly splits long tracks; testing against *any* member is
  transitively unbounded and silently deletes distinct plays. The window is
  `2 * (segment_length - overlap_duration)` (100s default), or
  `config.time_threshold` when set (floored at the derived value).
- **`_rep_key` never reads confidence.** It is `(time, name, artist)` —
  earliest detection wins. All cluster members are the same track, so
  preferring a higher-confidence one buys nothing, while any
  confidence-derived term reintroduces run-to-run instability (Shazam
  scores identical audio differently per run). A 5-point quantization was
  tried and still flipped on bucket-edge straddles (84.9 vs 85.0).
  **Full procedure: `docs/playbooks/changing-dedup.md`.**
- Segment filenames encode `start_time` and live in a per-run temp subdir
  named `<pid>-<hex8>`; the stale-dir sweeper (`_sweep_stale_run_dirs`)
  assumes that shape and kills only dirs whose PID is dead.

## Landmines (non-obvious, will bite)

1. **`config.min_confidence` is wired, with a scale gotcha.**
   `TrackMatcher.__init__` scales it `config.min_confidence * 100` (config
   is 0–1, Track confidence is 0–100). Default `0.0` keeps all tracks; the
   default was lowered from `0.5` to `0.0` so output is unchanged until a
   user turns the knob. Dedup itself is **not** here — `get_unique_tracks`
   is the sole dedup authority (token-set artist Jaccard + proximity), so
   see the dedup section. Raising `min_confidence` filters at `add_track`
   time. Note the `mock_config` fixture must stay `0.0` or it filters the
   whole suite.
2. **The cache is keyed by content, not path.** `identify_tracks` caches
   every successful provider response under
   `f"{provider_name}:{sha256(segment_bytes)}"`. Temp segment paths are
   per-run, so the path is unhashable; the bytes are stable for identical
   audio. Cache I/O failures (get/set) are swallowed at debug level and
   degrade to live identification — never abort the run. No-match responses
   (provider returned `None` or empty music) are not cached. Gated by
   `config.cache_enabled`. (The data-loss bugs that made wiring dangerous
   were fixed in the 2026-07 audit: TTL disabled by stored `None`, index
   never persisted — locked by tests I7/I8.)
6. **Download cache is URL-keyed and per-provider canonicalized.** Before
   downloading, `process_input` checks a `DownloadCache`
   (`cache_dir/downloads/<sha256>` + `.meta.json` sidecar) keyed by
   `sha256(f"{canonicalize_url(url)}|stream_copy={stream_copy}")`.
   Canonicalization (`downloaders/cache_key.py`) is offline and
   per-provider: YouTube URLs collapse to `yt:<video_id>` (all shapes —
   watch?v=, youtu.be/, /shorts/, /embed/, /live/); SoundCloud to
   `sc:<host><path>`; Mixcloud to `mc:<user>_<slug>`; unknown to
   `raw:<clean_url>`. On a hit the network is skipped and metadata flows
   from the sidecar. Separate from `BaseCache` (which rejects binary
   blobs). No TTL/eviction in v1. Gated by `config.download_cache_enabled`.
7. **Output is self-contained per set.** Each run produces
   `output/[date] Artist - Title/` containing `tracklist.{json,md,m3u}`
   **and the source audio** (copied in via `_copy_audio_to_output`). The
   folder is movable — the M3U references the audio by relative filename,
   not absolute path. The M3U uses VLC `#EXTVLCOPT:start-time` for
   per-track seeking (single source file; the standard DJ-mix pattern);
   EXTINF duration is the inter-track gap, last track uses
   `total_duration − last_start`.
3. **`downloaders/spotify.py` and `exporters/spotify.py` are dead ends.**
   No factory routes Spotify URLs, and the exporter needs a user-auth
   token while `SpotifyProvider` only does client-credentials (which can
   never call `/me/*` endpoints — playlist creation would 401). Don't
   "just wire them up"; the auth model is wrong. BACKLOG P2/P3.
4. **Secrets live in env vars, not the config dataclass** — deliberately,
   so `repr(config)` and validation errors can't leak them. ACRCloud creds:
   `TRACKLISTIFY_ACR_ACCESS_KEY` / `_SECRET` / optional `_HOST`, read in
   `providers/factory.py`. Follow that pattern for new providers.
5. **Provider instances are cached and shared** (`ProviderFactory.providers`
   dict, module-level factory singleton). A provider that keeps per-run
   state would leak it across runs in long-lived processes.
6. **`get_root()` falls back to CWD when installed as a package** (no
   pyproject.toml above `site-packages`), and it's captured at import time
   as `BaseConfig.project_root`. Installed CLI users get `.tracklistify/*`
   under whatever directory they launched from. Env override:
   `TRACKLISTIFY_PROJECT_ROOT`.
7. **Env parsing strips `#` comments** (`_load_from_env` splits on `#`).
   A secret containing `#` set via a dataclass-backed env var would be
   truncated. Credentials avoid this (read raw via `os.getenv`), but keep
   it in mind for new string fields.
8. **shazamio decodes via pydub/ffmpeg** — a missing ffmpeg breaks
   identification too, not just segmentation. `cli()` fail-fasts on this;
   don't remove that check.

## "If you touch X, also update Y" couplings

| You changed | You must also |
|---|---|
| Added/removed a field on `TrackIdentificationConfig` | Add it to a section in `scripts/generate_env_example.py::FIELD_SECTIONS`, run the script (CI `drift` job fails otherwise); add a range/type rule in `_setup_validation` if it has bounds. |
| Added a provider | Update `providers/factory.py` (branch + `KNOWN_PROVIDERS`), rate limits in `RateLimiter.register_provider` + config fields, `.env.example` credentials block if it needs secrets, and the I3 invariant test will then cover it. Full procedure in PLAYBOOKS.md. |
| Changed provider response shape | `IdentificationManager._track_from_info` is the single parse point; keep score 0–100. |
| Renamed/moved a CLI flag | `tests/test_cli_arguments.py` and README examples. |
| Changed segment naming or temp-dir layout | `_sweep_stale_run_dirs` (PID parsing) and `cleanup()`. |
| Changed `pre-commit` hooks or commands | Mirror in `.github/workflows/ci.yml` and CLAUDE.md's command table. |

## What the architecture gets right (don't "fix" these)

- Segmentation stream-copies (`-c:a copy`) instead of re-encoding — that's
  why splitting a 2-hour mix takes seconds. Don't add a transcode step.
- `-ss` before `-i` in the ffmpeg command is an input-seek; moving it after
  `-i` makes each segment decode from the file start (quadratic total work).
- Rate limiter uses `asyncio.Lock`/`Semaphore`, not threading primitives —
  the identify loop runs on the event loop and must not block it.
- Singletons use double-checked locking with `threading.Lock`; don't add a
  second layer of locking.
