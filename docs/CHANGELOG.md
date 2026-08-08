# Changelog

All notable changes to Tracklistify will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Release dates are in YYYY-MM-DD format.

## [0.11.1] - 2026-08-08

### Added

- **`dev_cli` test suite + coverage enablement.** `tests/test_dev_cli.py`
  (16 tests) covers `config.py`, `commands/run.py` (via
  `DevCommand.run_shell_command`), and `logging.py`. `dev_cli/` is removed
  from both the `[tool.coverage.run]` and `[tool.coverage.report]` `omit`
  lists in `pyproject.toml`, so it is now measured (still excluded from
  bandit and mypy — deliberate, out of scope).
- **Mypy type-checking in CI (ratchet).** `mypy` runs as a CI gate with a
  baseline of pre-existing errors (`.mypy-baseline`); CI fails only on *new*
  type errors, so the existing debt is chipped away without blocking merges.
  `scripts/check_mypy_baseline.py` (`--update` to re-baseline after fixes).
- **Cassette-locked + live verification.** vcrpy cassettes replay recorded
  HTTP so pacing/retry shapes (the MusicBrainz 503→retry regression class)
  are locked offline. An opt-in `@pytest.mark.live` suite (run via `--live`)
  and `scripts/probe_*.py` cover the live signals cassettes can't.

### Changed

- **Lazy ffmpeg resolution in downloaders (Q6).** `get_ffmpeg_path()` moved
  from `__init__` to `download()` in `downloaders/ytdlp.py` and
  `downloaders/mixcloud.py`; `self.ffmpeg_path` starts `None` and is
  resolved once on first download, then cached. Downloaders are now
  constructible without ffmpeg installed — the `cli.py` fail-fast check is
  unchanged.
- **`dev_cli` config degrades instead of erroring or silently defaulting.**
  `ToolsConfiguration` now loads to an EMPTY config when `tools.json` is
  missing or malformed (previously: missing → loaded 4 built-in defaults;
  malformed → raised `ConfigurationError`). The now-dead
  `load_default_config` was deleted.
- **`Track.metadata` is now a typed schema.** A `TrackMetadata` TypedDict
  names every metadata key + type (plus a nested `TrackLinks`); a typo'd key
  is a mypy error instead of a silent JSON field.
- **One enrichment runner.** The three near-identical enrichment passes
  (Spotify/MusicBrainz/Beatport) share one parameterized runner; behavior
  unchanged.
- **Config reads are direct, not defensive.** The 14 `getattr(config, ...)`
  reads that could hide a typo are now direct attribute access — a
  misspelled field is a mypy error (the shape of the `min_confidence` bug).

### Fixed

- **Beatport wrong-remix gate (U15).** `_enrichment_title_match` fell back
  to `_title_stem`, which strips remix markers, so distinct remixes
  collapsed to one stem and the enrichment gate attached the wrong remix's
  BPM/key/label/catalog# to a track. Replaced with a hybrid
  remixer-identity gate in `core/track.py` (`_extract_mix_info`,
  `_any_remixer_in`, `_mix_type_matches`) that compares remixer names and
  mix types pulled from Beatport's own data. Governing principle: gate only
  when Beatport actually supplies `remixers`/`mix_name` to verify against —
  when both are absent there is nothing to contradict, so the match falls
  through to the stem comparison rather than being rejected. Rejecting on
  absent data was a recall regression caught in review and fixed before
  merge. 39 new tests in `tests/test_track_matcher.py`. The live acceptance
  probe (`scripts/measure_beatport_remix_matches.py`) has not been re-run
  against these changes — unit-level behavior is locked by tests, but live
  re-verification is still outstanding.
- **Mixcloud misdiagnosed a missing ffmpeg as "Mix not found".** The lazy
  ffmpeg resolution (Q6, above) originally sat inside `download()`'s `try:`
  block; mixcloud's broad exception handler string-matched `"not found"`
  (present in ffmpeg's own missing-binary error) and re-raised it as
  `DownloadError("Mix not found: <url>")`, telling users their link was
  dead when ffmpeg was merely absent. Both downloaders now resolve the
  ffmpeg path above the `try:`.
- **Cache defects.** A read hit no longer rewrites the entry file (was a
  write+fsync per read under `TTLStrategy`); the phantom `_stats['entries']`
  counter (tracked total writes, not live entries) is removed; reads trust
  the stored compression flag, not zlib magic-byte sniffing.
- **Dead cache knobs removed.** `cache_cleanup_enabled` / `_interval` were
  settable and documented but read by nothing — deleted from config, types,
  and `.env.example`.

## [0.11.0] - 2026-08-07

### Added

- **Beatport links + DJ-metadata enrichment.** A third enrichment source
  (after Spotify and MusicBrainz) that resolves, per identified track, a
  canonical Beatport track link plus the fields no other source carries —
  BPM, musical key, label, genre, sub-genre, remixers, catalog number.
  Opt-in (`beatport_enabled`, default off). Auth is fully headless:
  username + password run the OAuth password flow against Beatport's docs
  client (the `app:docs` client ID scraped from the docs JS bundle, not the
  storefront id which 401s on the catalog API), mints an access token plus a
  refresh token, and caches both — so every run after the first refreshes
  silently, no token babysitting. Live-verified at 70–80% recall across four
  Tomorrowland sets (~3× the MusicBrainz link rate). See `.env.example` and
  `docs/BACKLOG.md` (P3 entry).
- **Per-provider rate limits.** `shazam_max_rpm`/`_max_concurrent` etc.
  (already present for some providers) now also cover Spotify and Beatport.

### Fixed

- **Beatport enrichment error posture.** OAuth misconfig now disables the
  pass instead of re-running the login dance once per track; transient 5xx
  stays per-track; auth 429s carry `Retry-After`; the zero-match summary
  logs unconditionally (a fully-broken pass is debuggable without `--debug`);
  the metadata-write and token-cache paths can no longer abort a run.
- **Token-cache robustness.** A non-numeric `expires_at` in the cache is a
  miss, not a `ValueError` per track (honoring `_load_cached_token`'s
  "never raises" contract). `_json_or_none` no longer collapses transport
  failures (connection reset, truncated body) into a silent miss that read
  as "wrong credentials."

### Known limitation

- **Beatport search-path remix matching (U15).** The enrichment title gate
  (loosened for recall) can attach a different remix's metadata on the
  search-fallback path — distinct remixes are separate Beatport catalog
  entries. Measured 9/18 search-matches landed on a different mix (BPM is
  often coincidentally right; key/label/catalog# wrong). ISRC-path matches
  (the majority) are unaffected. Tracked in `docs/BACKLOG.md` U15 with an
  acceptance test (`scripts/measure_beatport_remix_matches.py`).

## [0.10.1] - 2026-08-05

### Fixed

- **Security: secret masking + cache path traversal.** `mask_sensitive_value`
  now fully masks secrets under 12 characters (was 8 — an 8-char secret leaked
  6/8 chars). `is_sensitive_field` delegates to the same pattern list as
  `is_sensitive_key` so the two predicates can't diverge. The on-disk cache
  index filename is now basename-validated (including a bare `..` that passed
  the original check), so a tampered index entry can't point read/delete at a
  path outside the cache directory.
- **Cache index persistence.** `set()`/`delete()`/`get()` now persist index
  changes immediately, so a normally-exited process no longer leaves entries
  invisible to the next (stale index → reported misses → orphan-deleted on the
  next cleanup). Previously the index was saved only from `cleanup()`/`clear()`.
- **Enrichment UX.** A "please wait" INFO line now precedes the ~1 req/s
  MusicBrainz enrichment pass, so the 30–60s of apparent silence between
  "Identified N unique tracks" and the resolution summary no longer reads as a
  stalled process.

### Changed

- **dev_cli: arg mangling + config fallback.** `dev run` no longer mangles
  arguments containing spaces or quotes (it threaded a list through a
  string→shlex round-trip; now list end-to-end, config default args use
  `shlex.split` too; the duplicate stdout echo is gone). A missing `tools.json`
  falls back to defaults instead of crashing at import (the fallback was
  unreachable; the redundant post-init `load_default_config` that clobbered a
  loaded config is gone).

### Removed

- **Dead code.** `downloaders/spotify.py` (405 lines, no factory route),
  `utils/decorators.memoize` (unused), the `core/types.Downloader` Protocol
  (incompatible with the real ABC), `dev_cli/execution/executor.py` (no
  callers), the unused `ACRCLOUD_SUCCESS_CODE` constant (which was actually
  ACRCloud's auth-error code), the never-populated `core/run._cleanup_tasks`
  registry, the dead `DownloaderFactory._downloaders` field, and an unreachable
  duplicate block in `ytdlp.py::_strip_youtube_playlist_params`. No production
  callers; no end-user behavior change.

## [0.10.0] - 2026-08-04

### Added

- **MusicBrainz link enrichment (keyless, free).** A second link source runs
  after the Spotify enrichment pass, resolving canonical streaming URLs
  (Spotify/Deezer/Tidal/Apple/Beatport) per unique track via MusicBrainz's
  ISRC lookup — no credentials, no Premium, no key. It needs only an ISRC
  (Shazam supplies one for most tracks) and fills link keys the Spotify source
  didn't set (first-writer-wins per key). When it supplies the Spotify link it
  records `spotify_match: "musicbrainz"`. Measured coverage on underground/EDM:
  ~25% of tracks gain a Spotify link (vs the Spotify-source ~95% estimate that
  is currently blocked behind a Premium-backed developer app). Gated by
  `musicbrainz_enabled` (default `true`); a silent no-op when disabled or when a
  track has no ISRC. Requests are serialized with bounded 503 retry —
  MusicBrainz rate-limits with 503 under burst load.

- **Canonical Spotify track links via post-dedup enrichment.** After
  deduplication, each unique track is enriched with a canonical
  `https://open.spotify.com/track/<id>` link when Spotify credentials are
  configured (`TRACKLISTIFY_SPOTIFY_CLIENT_ID`/`_SECRET`, client-credentials
  auth). The lookup is ISRC-first (exact, via `search_by_isrc`) with a
  title/artist search fallback, and each track records `spotify_match`
  (`"isrc"` | `"search"`) so a consumer can tell a trustworthy exact match
  from a best-effort search hit. A run summary logs the `isrc`/`search`/`none`
  counts. Strictly optional: a silent no-op without credentials or when
  `enrichment_enabled` (env `TRACKLISTIFY_ENRICHMENT_ENABLED`, default `true`)
  is off. Best-effort — enrichment never fails a run.

### Changed

- **`Track.metadata` platform links moved under a nested `links` object.**
  `tracklist.json` is the public surface, so this is a consumer-visible
  change. The flat `shazam_url`, `spotify_search_url`, and
  `deezer_search_url` keys are now `links.shazam`, `links.spotify_search`,
  and `links.deezer_search` respectively. `links.spotify` (canonical, set by
  the new enrichment hook) is distinct from `links.spotify_search`
  (Shazam-supplied search URL), so a consumer can tell a resolved track link
  from a search. `apple_music_id` stays flat (an id, not a URL). A track with
  no link omits `links` entirely. The MusicBrainz enrichment source may also
  add canonical `links.deezer` / `links.tidal` / `links.apple` / `links.beatport`
  keys (distinct from the Shazam-supplied `links.deezer_search`).

## [0.9.1] - 2026-08-03

### Fixed

- **YouTube `&list=` URLs no longer 403.** A URL carrying a playlist param
  (e.g. `&list=RD...` — a YouTube auto-mix/radio list) made yt-dlp descend
  into the playlist during resolution, triggering a non-retryable 403 before
  `playlist_items='1'` could bound the download. YouTube playlist params
  (`&list=`, `&index=`, `&t=`, …) are now stripped for YouTube URLs before
  download — we only ever process one video, so the playlist context is never
  wanted. The video id is extracted regardless of query-param order
  (`watch?v=…&list=…` and `watch?list=…&v=…` alike). SoundCloud/Mixcloud are
  untouched.
- **Transient download 403s are now retried.** `config.download_max_retries`
  (env `TRACKLISTIFY_DOWNLOAD_MAX_RETRIES`, default `3`) was declared but
  never read — dead config. It is now wired into yt-dlp's native `retries`
  option, so a transient YouTube HTTP 403 (bot-detection throttling — the
  case that succeeds on a manual second run ~seconds later) is retried with
  backoff instead of aborting the whole run. Genuine 403s (private/
  region-locked video) still raise `DownloadError`.
- **Download failures no longer flood the log with a yt-dlp traceback.**
  Two causes, both fixed: (1) `ydl_opts['verbose']` was `True` with a comment
  saying "Always set to False" — now `False`, suppressing yt-dlp's own
  debug-level stderr spew; (2) the CLI's generic error handler logged
  `exc_info=True` unconditionally, which printed the full exception chain —
  yt-dlp's `HTTPError` traceback deep into its internals, "during handling of
  the above exception", then the `DownloadError` — on every failure. The
  traceback is now gated on `--debug`; at default verbosity a download error
  logs one clean message (pass `--debug` for the full chain).
- **Title-variant duplicates collapse in dedup.** Two detections of the same
  recording under different bracketed spellings — `(Club Mix)` vs bare title,
  `[Live At …]`, `feat.`/`ft.`/`featuring` spelling variants of the same
  credit — no longer survive dedup as separate rows. `_strip_title_variant`
  rewrites trailing-suffix bracket groups for the comparison only: it drops
  non-distinguishing version/live tags and canonicalizes `feat.`/`ft.`/
  `featuring` markers to `feat`, keeping both the marker word and the
  credited artist (so `(feat. Snoop Dogg)` ≠ `(feat. Pharrell)`, and a
  feat-credit ≠ a bare-name bracket). It defaults to KEEP: `remix`/
  `bootleg`/`edit by`/`vip` (whole words), named remixes, and anything
  unrecognized stay title-distinguishing; leading/middle and nested brackets
  are left verbatim. The displayed `song_name` is unchanged. Accepted
  trade-off: a `feat. X` credit and a `(Mixed)` tag of the same audio now
  separate (a visible duplicate — the recoverable direction).
- **Dedup over-merge hardening.** Closed four silent data-loss paths found in
  review: bare-name vs feat-credit collision, cross-type nested brackets
  defeating the empty-collapse guard, leading-bracket collapse, and
  substring keep-marker shadowing. Comparison-only — `_rep_key`, exporters,
  cache, and Spotify enrichment all still read the raw `song_name`.

### Changed

- **Release process:** `update_changelog_on_bump` is now `false`. Commitizen's
  `cz bump` ran the non-incremental changelog generator, which regenerated
  from `changelog_start_rev` and overwrote curated history. The repeatable
  flow is now a hand-written version section + `cz bump` for version/tag only.
- **Dependencies:** bumped `uv_build`, `ruff`, and `commitizen` versions.

## [0.9.0] - 2026-08-01

### Added

- **Richer track metadata in JSON output.** `Track.metadata` existed as a
  field with nothing writing to it and nothing reading it; both ends are now
  wired. The Shazam provider surfaces ISRC, genre, album, label, release
  date, Shazam/Apple Music ids and artwork from the raw payload, and
  `_save_json` serializes them per track. Empty values are dropped rather
  than stored as `null`, and a track with no extras serializes as `null`
  rather than `{}`. Merges [#57](https://github.com/betmoar/tracklistify/pull/57)
  by @fakhavan. Markdown and M3U output are unchanged.
- **Platform search links.** Shazam ships per-platform deeplinks alongside
  every match in `hub.providers` — free, no extra API call. Surfaced as
  `spotify_search_url` / `deezer_search_url`, converted from Shazam's
  app-scheme URIs (`spotify:search:`, `deezer-query://`) to https so they
  are clickable from the JSON. Named `*_search_url` because they are
  searches: Shazam does not resolve a canonical track id. Coverage is
  partial — measured at 12/20 tracks on a real set, since `hub.providers`
  is absent from roughly 40% of responses.
- **`--no-cache`.** Re-downloads and re-identifies, ignoring stored results.
  It is a *refresh*, not a disable: cache reads are skipped while writes
  stay live, so a wrong stored identification is overwritten rather than
  stepped around. Disabling the caches instead would gate the writes too and
  leave the stale entry to be served again on the next run.

### Changed

- **`cache_ttl` 1 hour → 30 days**, with `cache_max_age` raised to match.
  The identification cache is keyed on the segment's content hash, so a
  stored response does not go stale the way a typical HTTP cache entry does
  — a provider improving its catalog is the only real staleness, and weeks
  is the right granularity. At one hour, re-running yesterday's mix re-paid
  the full identification cost. Both values must move together: they are
  independent expiry gates and the shorter one wins.
- **Logging levels reflect outcomes again.** A healthy run printed a wall of
  "No track information found in Shazam response." and nothing about the
  tracks it identified. The per-track success line is back at INFO with its
  timestamp and artist; unmatched segments — the normal case in a DJ mix —
  are now debug. A run where *no* segment matches emits a single warning,
  since a broken request pipeline is otherwise indistinguishable from a set
  of unreleased IDs.
- Running `tracklistify` with no arguments prints help and exits 0 instead
  of an argparse usage error.
- `TrackMatcher.__init__` accepts an optional config, and
  `IdentificationManager` passes its own — previously the matcher always
  re-resolved the global singleton, so an injected config never reached it.

### Fixed

- **Identity chaining could delete a whole play.** Artist Jaccard is not
  transitive, so testing cluster membership against *any* member let a
  collaboration credit bridge two distinct artists: `Artist A` and
  `Artist B` share no tokens, but `Artist A, Artist B` matches both. Each
  hop also refreshed the cluster's proximity anchor, so the chain ran
  unbounded — six detections spanning two separate plays collapsed to one
  row and the second play vanished. Identity is now anchored on `cluster[0]`
  while proximity stays anchored on `cluster[-1]`.
- **Search-URL encoding.** Deezer's deeplink embeds unescaped apostrophes,
  so term extraction truncated at the first one in the text itself
  (`Don't Stop` searched for `Don`). Separately, `quote()`'s default left
  slashes intact, so `AC/DC` injected a path segment into the search URL.
- **A malformed `hub.providers` entry no longer costs the identification.**
  A non-string `type` raised from `.strip()` inside `identify_track`'s outer
  try, escalating to `ShazamError` and discarding a match whose title,
  artist and ISRC were all valid.
- **SoundCloud `/sets/` with no downloadable entries fails loudly.** An
  empty `entries` list fell through, leaving the *set's* metadata in place —
  silently reinstating the bug the unwrap exists to fix — and built an
  output path for a file that was never written.
- **A missing downloaded file is no longer reported as success.** When the
  glob fallback found nothing, the reconstructed path was returned anyway
  and the failure first surfaced several frames later as "Could not read
  audio file".
- **JSON export cannot leave a truncated file.** `json.dump` streams, so a
  serialization error partway through wrote a partial file that looked
  complete — after the entire expensive identification pass. Serialization
  now completes in memory first, with a `default=str` fallback.
- `cz bump` aborted on a `changelog_start_rev` pointing at a tag that does
  not exist in this repository.
- **Dedup now merges artist-string variants.** The same track appeared twice
  in output when Shazam returned different collaboration artist strings on
  adjacent segments (`Berghain (Remix)` at 1900s as
  `Conrad Taylor & ROSALÍA & Björk & Yves Tumor` and at 1950s as
  `ROSALÍA, Björk & Yves Tumor`). `get_unique_tracks` — the shipping dedup
  path — keyed on exact `artist|song` strings and ignored time entirely.
  It now clusters by identity (normalized-title equality + artist token-set
  Jaccard ≥ 0.34) within a proximity window derived from the segmentation
  step (`2 * (segment_length - overlap_duration)`, 100s by default), so
  adjacent-segment detections merge while a track genuinely played twice in
  a set stays two entries. Proximity is measured as the gap to a cluster's
  most recent detection: a long track keeps arriving one segmentation step
  apart so the chain holds, while two distinct plays are separated by
  minutes of other music so it breaks. (Bounding the total span instead
  wrongly splits long tracks; testing against any member is transitively
  unbounded and silently deletes distinct plays.)
- **Stable representative selection.** Cluster representatives were chosen
  by strict `>` on confidence, so Shazam's per-run jitter could change which
  detection won — and therefore the reported `time_in_mix` — between runs of
  identical audio. Selection is now purely `(time, name, artist)`: the
  earliest detection represents the cluster and confidence is not an input,
  because every member is the same track and any confidence-derived term
  reintroduces the jitter.
- **`time_threshold` works again.** It was assigned and never read, while
  `.env.example` advertised it as controlling merge behavior. It is now the
  dedup-window override; the default drops from `30.0` to `0.0`, meaning
  "derive from the segmentation step" (the old 30s default was narrower
  than one 50s step and would have split adjacent-segment detections). Any
  override below the derived window is floored, with a warning, because a
  narrower window cannot merge adjacent detections at all.
- **Multi-track SoundCloud sets warn instead of silently truncating.** Only
  `entries[0]` is processed; previously the discarded count appeared only at
  debug level, so a set silently produced a one-track tracklist and cached
  it under the set's URL.
- **`config.min_confidence` is no longer a no-op.** `TrackMatcher` hardcoded
  a 0 threshold, so the documented (and validated) knob did nothing. It is
  now applied, scaled from the config's 0.0–1.0 range to `Track.confidence`'s
  0–100. The default drops from `0.5` to `0.0` so existing output is
  unchanged until a user raises it.
- **SoundCloud `/sets/` URLs no longer propagate container metadata.** These
  extract as a playlist whose id/ext/duration describe the *set*, not the
  track; the downloader now unwraps to `entries[0]` before anything reads the
  info dict. Previously the wrong title/duration reached the output folder
  name, the M3U, and — via the sidecar — persisted in the download cache.
- **Output path resolution prefers `requested_downloads[0]["filepath"]`**
  (the path yt-dlp actually wrote) over reconstructing it with
  `prepare_filename`, which missed extension changes made during muxing.
- **Download cache entries are version-stamped** (`KEY_VERSION` in the key
  material), invalidating stale pre-fix `/sets/` metadata that would
  otherwise be served indefinitely — the cache has no TTL or eviction.

### Removed

- **`max_duplicates` config field.** It capped how many detections one dedup
  cluster could absorb, but every value that fits a real mix is wrong: a
  track spanning several segments legitimately yields 4+ detections, so any
  low cap splits it back into duplicate rows. It had been dead (assigned,
  never read) and wiring it up broke real output, so the field, its two
  validators, its `TypedDict` mirror and its docs are gone.
- Dead `TrackMatcher.merge_nearby_tracks` and its six private helpers. They
  had no production callers; `get_unique_tracks` is now the sole dedup
  authority and `add_track` only confidence-gates and appends.

## [0.8.2] - 2026-07-31

End-to-end caching and self-contained output: wires the existing
identification cache into the pipeline, adds a URL-keyed download cache so
re-runs skip the network, restructures output into per-set subfolders
(audio + tracklist + playable M3U), and fixes Mixcloud metadata. Builds on
the audit-driven hardening of [0.8.1] (config validation, provider repair,
importability) and the [0.8.0] reliability/perf pass — see those sections.
Comprises PRs #59, #62, #63, #64, #65.

### Added

- Identification results are now cached. `IdentificationManager.identify_tracks`
  consults the cache (`get_cache()`) before each provider call, keyed by
  `f"{provider}:{sha256(segment_bytes)}"`, and stores successful responses
  for reuse across reruns. Cache I/O is best-effort (failures degrade to
  live identification, never abort the run); gated by the existing
  `cache_enabled` config flag. Closes the P1 backlog item.
- Downloaded audio is now cached. A new `DownloadCache`
  (`cache_dir/downloads/<sha256>` + `.meta.json` sidecar) keys on a
  per-provider canonical URL + `stream_copy` flag, so re-running the same
  URL skips the network entirely and reads metadata from the sidecar.
  Canonicalization is offline: YouTube URLs (watch?v=, youtu.be/, /shorts/,
  /embed/, /live/, m./music.) collapse to `yt:<video_id>`; SoundCloud to
  `sc:<host><path>`; Mixcloud to `mc:<user>_<slug>`. Also fixes Mixcloud,
  which previously stored no metadata. Gated by new
  `download_cache_enabled` (default `true`).
- Output is now self-contained per set. Each run produces
  `output/[date] Artist - Title/` containing `tracklist.{json,md,m3u}`
  **and the source audio file**, replacing the previous flat layout. The
  uploader (from yt-dlp metadata) now populates the artist slot — folder
  names no longer say "Unknown Artist". The subfolder is movable.
- The M3U playlist is now playable. It points at the real audio file in
  the subfolder and uses VLC `#EXTVLCOPT:start-time` for per-track seeking;
  EXTINF duration is the inter-track gap (last track uses
  `total_duration − last_start`). Previously it emitted only comments with
  no playable URI lines and EXTINF was always `-1`.
- `TRACKLISTIFY_SHAZAM_PROXY` config option (#63) — routes `ShazamProvider`
  identification requests through an HTTP proxy via shazamio's
  `recognize(..., proxy=...)`. Empty by default (direct connection);
  `proxy` added to the sensitive-field patterns so a credential embedded
  in the proxy URL is redacted in logs.

### Changed

- **Breaking:** output structure changed from flat
  `output/[date] Artist - Title.{json,md,m3u}` to
  `output/[date] Artist - Title/tracklist.{json,md,m3u}` (+ audio).
- `AsyncApp.save_output` now wires `self.uploader` into `mix_info["artist"]`
  and passes `total_duration`.
- CI workflow now uses least-privilege permissions (#62).
- Dependencies bumped: aiohttp 3.13, yt-dlp 2025.11, click 8.3, pytest 8.4,
  pytest-asyncio 1.3, ruff 0.14, plus minor bumps across the dev group (#59).

### Fixed

- **Shazam typed errors** (#64): a non-string `type` in `hub.providers`
  raised from `.strip()` inside `identify_track`'s outer try, escalating to
  `ShazamError` and discarding a match whose title, artist and ISRC were
  all valid.
- **Spotify async metadata** (#64): the provider's enrichment path no longer
  blocks; perf salvages applied to avoid dropping identifications.
- `uv_build` version range corrected (#62, #59).

### Deprecated

- `tracklistify.cache.run_async`: now emits `DeprecationWarning`. Prefer
  awaiting coroutines directly or using `asyncio.run`. The body is unchanged
  so existing callers continue to work; removal is deferred to a future
  release.

## [0.8.1] - 2026-07-31

The principal-architect handoff audit. Tagged `v0.8.1`. Fixes eight
production bugs (each locked by an invariant test in
`tests/test_handoff_invariants.py`, I1–I8) and adds the CI + docs missing
from the repo.

### Fixed

- **Config validation never ran.** `_validate()` was an empty body; the ~13
  declarative rules were dead code. Now executes at construction time, plus a
  cross-field `overlap < segment_length` rule (I1).
- **`split_audio` hung in an infinite loop** when `overlap >= segment_length`
  (step <= 0). Runtime guard added — the load-time check alone was
  insufficient since config is mutable post-load (I2).
- **ACRCloud was unusable since inception.** The factory called it with no
  credentials (`TypeError`), and `identify_track` took bytes while the
  pipeline passes `AudioSegment`. Factory now reads env creds with an
  actionable `ConfigError`; `identify_track` accepts both shapes (I3, I4).
- **Provider fallback was a complete no-op** — `fallback_enabled` was never
  read. `IdentificationManager` now walks a primary→fallback chain (I5).
- **Circuit breaker never received outcomes** —
  `_update_circuit_breaker` had zero callers. New public `record_result()`
  called on every provider result (I6).
- **Cache TTL was disabled:** `set()` stored `ttl=None`, shadowing the
  strategy default, so entries never expired (I7). The cache index was only
  persisted from `cleanup()`/`clear()`, so cross-process writes were
  invisible then deleted as orphans (I8).

### Added

- CI (`.github/workflows/ci.yml`): ruff lint + format, `.env.example` drift
  check, and the test suite on Python 3.11–3.13.
- `.env.example` documenting every config field with its env-var override.
- `tests/test_handoff_invariants.py` locking I1–I8 against regression.
- ffmpeg-absence fail-fast in the CLI (was a cryptic per-segment error).

## [0.8.0] - 2026-05-12

Multi-phase audit: security, concurrency/reliability, correctness,
performance, and dead-code removal. Tagged `v0.8.0` at the audit commit
`86fa9fc` (whose `pyproject.toml` still read `0.7.0` — the version string
caught up at 0.8.1; the tag marks the work, not the bump).

### Security

- Removed a shell-injection vector in `dev_cli` (dropped an unsafe
  `shell=` kwarg).
- Added `bandit` to pre-commit (`-ll` severity).
- Mask sensitive config values in error messages.
- `clean_url()` strips userinfo so credentials don't leak via logs.
- `_is_platform_url()` rejects non-HTTP(S) schemes (no
  `ftp://youtube.com`).

### Changed

- **Concurrency & reliability:** replaced the blocking `threading.Lock`
  with `asyncio.Lock` in the rate limiter; made singletons
  (`get_config`/`get_cache`/`get_global_rate_limiter`) thread-safe via
  double-checked locking with `force_refresh` for tests; always release
  rate-limiter semaphores in `finally`; per-invocation
  `.tracklistify/temp/<pid>-<hex>/` dirs so concurrent runs can't trample
  each other (with a stale-dir sweep for dead PIDs); Ctrl+C cancels the
  running task and double-press force-exits; providers used via
  `async with` so sessions close; Spotify wrappers propagate
  `RateLimitError`/`AuthenticationError` before the generic catch;
  `_api_request` accepts any 2xx incl. 204; logger closes prior handlers
  (no FD leak).
- **Correctness:** `Track.time_in_mix` validated at construction and accepts
  elapsed offsets > 23h; `time_to_seconds()` infallible; `get_cache()`
  honors `cache_dir`/`ttl`/`max_size` (previously silently dropped — always
  wrote to `~/.tracklistify/cache`); cache-size semantics reconciled to
  bytes (default 1KB → 1MB); `process_input()` preserves
  `output_format` when `--formats` omitted; CLI respects `fallback_enabled`
  when `--no-fallback` not given; `set_logger()` honors `log_level` again;
  `ProgressDisplay.clear()` blanks the rendered width; `mutagen.File`
  imported from the public API.

### Added

- **`-sc` / `--stream-copy`:** skip yt-dlp's MP3 transcode and segment with
  `-c:a copy` end-to-end (major speedup on long mixes).
- Per-segment progress logging via `concurrent.futures.as_completed`.
- `FFMPEG_SEGMENT_TIMEOUT` prevents stuck segments from hanging the run.
- Named constants in `utils/constants.py` (replacing magic numbers).

### Removed

- Dead code: `CryptoManager` + `SecureConfigLoader` (~414 lines),
  `SimpleLimiter`, four unused exception classes, the `run_async` helper,
  and the `TrackMatcher.process_file` legacy stub.
- Consolidated `Track` init into dataclass + `__post_init__`.

## [0.7.0] - 2025-09-15

The clean-slate modular restructure: the prior development branch was
squashed into a single commit (`f847c83`, "initial project restructure with
modular architecture and development tools"), giving the project a clean
base under the `0.7.0` version. Tagged `v0.7.0` in 2026-08 (it was never
tagged at release). The subsystem work consolidated by this squash —
configuration management, the cache system, Spotify integration, the rate
limiter, and the early track-identification/output phases — is recorded in
the pre-squash sections below ("Phase 1–4", "Rate Limiter Enhancements",
`[0.6.0]`–`[0.1.0]`).

### Added

- **Local file processing support** alongside URL input, with improved
  track identification (#27).
- **Metadata extraction and string sanitization** for downloaded files (#26).
- **Advanced rate limiter with circuit breaker and metrics** (#31); delay
  between Shazam API requests to avoid rate limiting (#29).
- **Cache improvements:** better stats tracking and TTL handling (#30).
- **`poetry` → `uv` migration** (`f12d4e4`) — the package manager the rest
  of this changelog assumes.
- **Project-root discovery utilities** (#35), streamlining path handling.

### Changed

- Replaced the YouTube downloader with a generic `yt-dlp` implementation
  for broader URL support (`26abfff`).
- Simplified `clear_config` and improved the track-similarity check (#28).
- Coverage configuration and test imports updated for the core-module
  refactor (#32).



### Added

- Enhanced rate limiter with metrics collection and monitoring
- Circuit breaker pattern for rate limiting
- Alert system for rate limit events
- Per-provider rate limiting configuration
- Concurrent request limiting
- Async support for rate limiting operations
- Resource cleanup mechanisms
- Comprehensive logging for rate limiter events
- Rate limit configuration validation
- Environment variables for rate limiter configuration
- Comprehensive test suite for rate limiter:
  - Basic rate limiting functionality
  - Concurrent request handling
  - Metrics tracking
  - Circuit breaker behavior
  - Alert system functionality
  - Resource cleanup verification
  - Provider registration
  - Rate limit window tracking
  - Timeout handling

### Changed

- Updated rate limiter implementation with token bucket algorithm
- Enhanced provider limits with metrics tracking
- Improved error handling with circuit breaker pattern

### Fixed

- Rate limiting resource cleanup
- Proper handling of concurrent requests
- Thread-safe rate limit operations

## [Phase 4 - Spotify Integration] - 2024-11-25

### Added

- Spotify downloader implementation:
  - Support for multiple audio qualities:
    - Vorbis: 96, 160, 320 kbps
    - AAC: 24, 32, 96, 128, 256 kbps
  - Multiple output formats (M4A/OGG/MP3)
  - Rich metadata tagging:
    - Artist and album information
    - Track and disc numbers
    - Release dates and genres
    - Cover art embedding
  - Factory method for environment-based creation
- Environment variable configuration:
  - TRACKLISTIFY_SPOTIFY_COOKIES: Browser cookie path
  - TRACKLISTIFY_SPOTIFY_QUALITY: Audio quality setting
  - TRACKLISTIFY_SPOTIFY_FORMAT: Output format selection
  - TRACKLISTIFY_OUTPUT_DIR: Download directory
  - TRACKLISTIFY_TEMP_DIR: Temporary file location
  - TRACKLISTIFY_VERBOSE: Logging verbosity
- Enhanced file management:
  - Structured .tracklistify directory:
    - /output: Downloaded files
    - /temp: Temporary processing
  - Safe filename generation
  - Home directory expansion (~)
  - Automatic directory creation

### Changed

- Project structure improvements:
  - Integrated Spotify downloader with existing base
  - Enhanced environment variable handling
  - Expanded configuration options
  - Improved directory organization
- Audio processing:
  - FFmpeg integration for format conversion
  - Quality-preserving transcoding
  - Metadata preservation during conversion
- Error handling and logging:
  - Detailed debug information
  - Operation progress tracking
  - Comprehensive error messages
  - Clean error recovery

### Fixed

- Path handling:
  - Home directory expansion
  - Illegal character sanitization
  - Unicode filename support
- Temporary file management:
  - Proper cleanup after processing
  - Unique temp file naming
  - Error state cleanup
- Cookie handling:
  - Path expansion support
  - Better error messages
  - Validation checks

## [Phase 3 - Track Identification and Output Enhancement] - 2024-11-24

### Added

- Real-time progress display for track identification:
  - Visual progress bar
  - Segment-by-segment tracking
  - Status updates with current provider
  - File size and timing information
- Multiple output format support:
  - JSON output with detailed analysis info
  - Markdown format with confidence scores
  - M3U playlist generation with timing
- YouTube and Mixcloud URL support:
  - Direct URL processing
  - Metadata extraction
  - Automatic format handling
- Enhanced command-line interface:
  - Provider selection options
  - Format selection flags
  - Verbose logging mode
  - Provider fallback control

### Changed

- Improved identification system:
  - Better provider management
  - Enhanced error handling
  - Caching and rate limiting
  - Track matching refinements
- Enhanced mix info extraction:
  - Better metadata handling
  - Special character support
  - Consistent filename formatting
- Logging system improvements:
  - Detailed debug information
  - Progress tracking
  - Analysis summaries
  - Error reporting

### Fixed

- Resource cleanup in main execution flow
- Provider fallback mechanism
- Special character handling in filenames
- Progress display overlapping

## [Phase 2 - Cache System] - 2024-11-22

### Added

- Enhanced cache management system:
  - Base cache implementation with generic type support
  - Multiple invalidation strategies:
    - TTL (Time-To-Live) based invalidation
    - LRU (Least Recently Used) strategy
    - Size-based cache limits
    - Composite strategy support
  - Asynchronous operations:
    - Async-first design
    - Non-blocking cache operations
    - Concurrent access support
  - Storage backends:
    - JSON file-based storage
    - Atomic file operations
    - Compression support
  - Cache statistics tracking:
    - Hit/miss rates
    - Invalidation counts
    - Storage efficiency metrics
  - Comprehensive test suite:
    - Unit tests for all components
    - Integration tests for cache system
    - Performance benchmarks
    - Timing-sensitive test cases
- Enhanced type system:
  - New type definitions for cache operations:
    - `CacheMetadata` TypedDict
    - `CacheStorage` Protocol
    - `InvalidationStrategy` Protocol
    - `Cache` Protocol with comprehensive type hints
  - Improved configuration types:
    - Added cache-specific configuration options
    - Enhanced type safety for cache operations

### Changed

- Improved cache entry handling:
  - Enhanced metadata management
  - Strict type checking
  - Better error handling
  - Atomic updates
- Refined invalidation logic:
  - More precise timing checks
  - Floating-point comparison fixes
  - Enhanced error recovery
- Updated test framework:
  - Async test support
  - More reliable timing tests
  - Better test isolation
- Restructured cache implementation:
  - Moved cache code to dedicated module
  - Separated concerns into distinct files
  - Improved code organization

### Fixed

- Cache invalidation timing issues
- Metadata update consistency
- Concurrent access race conditions
- File system race conditions
- Type checking in cache operations

### Security

- Implemented atomic file operations
- Added comprehensive error logging
- Enhanced metadata validation
- Secure file permissions handling

### Documentation

- Added detailed cache system documentation
- Created comprehensive testing guide (TESTING.md)
- Added performance benchmarks
- Included troubleshooting tips
- Documented best practices
- Added type hints documentation:
  - Protocol definitions
  - Generic type variables
  - Configuration types
  - Cache-specific types

## [Phase 2 - Configuration Management] - 2024-11-22

### Added

- Enhanced configuration management system:
  - Standardized directory structure:
    - `.tracklistify/output` for output files
    - `.tracklistify/cache` for cache data
    - `.tracklistify/temp` for temporary files
  - Environment variable improvements:
    - `TRACKLISTIFY_` prefix for all variables
    - Type conversion for all config values
    - Home directory expansion for paths
    - Enhanced list parsing with multiple formats support
    - Better error messages for invalid values
    - Support for single value and comma-separated lists
  - Configuration validation:
    - Comprehensive test coverage
    - Directory creation and cleanup
    - Path validation and expansion
    - Custom configuration handling
  - Security enhancements:
    - Sensitive field masking
    - Configurable rate limiting
    - Secure credential handling
- Complete configuration management system implementation:
  - Recognition configuration:
    - Confidence threshold settings
    - Segment length configuration
    - Overlap settings
    - Cache directory configuration
    - Provider configuration
  - Added \_parse_env_value helper for robust type conversion
  - Support for various boolean formats (true/1/yes/on)
  - Proper handling of Path expansion
  - Improved validation error messages
- Improved environment variable handling:
  - Enhanced list parsing with multiple formats support
  - Automatic type conversion for all config fields
  - Better error messages for invalid values
  - Support for single value and comma-separated lists
- Configuration improvements:
  - Added \_parse_env_value helper for robust type conversion
  - Support for various boolean formats (true/1/yes/on)
  - Proper handling of Path expansion
  - Improved validation error messages

## [Phase 1 Completion] - 2024-11-21

### Added

- Comprehensive development environment setup
  - Black for code formatting
  - isort for import sorting
  - flake8 for linting
  - mypy for type checking
  - pre-commit hooks configuration
- Commit message validation using commitizen
- Type system foundation in types.py
  - TypedDict definitions for configuration and metadata
  - Protocol definitions for providers and downloaders
  - Generic type variables
- Error handling framework in exceptions.py
  - Base exceptions hierarchy
  - Provider-specific exceptions
  - Downloader-specific exceptions
- Environment validation tests
  - Python version validation
  - System dependencies check
  - Virtual environment validation
  - Development tools validation

## [0.6.0] - 2024-03-21

### Added

- Modern Python packaging with pyproject.toml
- Dynamic version management using setuptools_scm
- Improved development tooling:
  - Black for code formatting
  - isort for import sorting
  - mypy for type checking
  - flake8 for linting
  - pytest for testing
  - pre-commit hooks
- Enhanced Shazam provider:
  - Updated to shazamio 0.7.0
  - Improved recognition accuracy
  - Better error handling and retries

### Changed

- Optimized track identification settings:
  - Reduced segment length to 15 seconds for faster processing
  - Set minimum confidence threshold to 50%
  - Improved duplicate handling with single track limit
- Simplified provider configuration:
  - Made Shazam the default provider
  - Streamlined fallback settings
- Enhanced environment setup process
- Updated Python requirement to 3.11+

### Fixed

- Various bug fixes and performance improvements
- Enhanced error handling in audio processing
- More reliable track identification

## [0.5.8] - 2024-01-09

### Changed

- Improved logging system across all downloaders
- Enhanced error handling for unidentified segments
- Reduced segment length to 20 seconds for better identification
- Enabled verbose and debug modes by default

### Added

- Detailed logging for YouTube and Mixcloud downloaders
- Specific error messages for common download failures
- Debug logging for download initialization and settings
- More informative success messages with track details

### Fixed

- Better handling of unidentified segments in identification process
- More appropriate log levels for different types of messages
- Simplified downloader factory implementation

## [0.5.7] - 2024-11-19

### Changed

- Refactored downloader modules into dedicated factory folder structure
- Improved code organization with proper separation of concerns
- Enhanced maintainability and extensibility for future downloaders

### Removed

- Deprecated `downloader.py` module in favor of new `downloaders` package

## [0.5.6] - 2024-11-19

### Added

- New download configuration options in `.env` file:
  - `DOWNLOAD_QUALITY`: Audio quality setting (default: 320kbps)
  - `DOWNLOAD_FORMAT`: Output audio format (default: mp3)
  - `DOWNLOAD_TEMP_DIR`: Custom temporary directory
  - `DOWNLOAD_MAX_RETRIES`: Maximum retry attempts for downloads

### Changed

- Improved downloader implementation with async support
- Enhanced YouTube downloader with better error handling
- Implemented singleton pattern for downloader instances
- Made download quality and format configurable
- Improved thread handling for non-blocking downloads

### Removed

- Redundant download code from main application
- Unused app.py module

## [0.5.5] - 2024-11-19

### Changed

- Cache implementation now uses ttl instead of duration
- Improved cache key generation with byte range support
- Better error handling in cache operations
- Added cache entry deletion method

### Fixed

- Cache configuration error with duration attribute
- Cache expiration handling
- Cache key generation for better segment isolation

## [0.5.4] - 2024-11-19

### Added

- Exponential backoff retry logic for Shazam provider
- Rate limiting with configurable intervals
- Improved session management with automatic recovery
- Better audio format handling with consistent WAV output

### Changed

- Shazam provider completely refactored for better reliability
- Output format handling now properly respects environment variables
- Session management now uses exponential backoff with jitter
- Audio processing standardized to stereo 44.1kHz WAV

### Fixed

- URL validation errors in Shazam provider
- Session expiration handling
- Output format not respecting environment variables
- Audio format inconsistencies causing recognition failures

### Security

- Added rate limiting to prevent API abuse
- Improved session handling to prevent resource leaks

## [0.5.3] - 2024-11-19

### Added

- Configurable provider fallback system
- Enhanced logging for provider selection and usage
- Output configuration with customizable directory and format
- Improved cache error handling with graceful degradation

### Changed

- Provider fallback now respects PROVIDER_FALLBACK_ENABLED setting
- Rate limiter now has configurable timeout (30s default)
- Cache operations now handle errors gracefully
- Improved logging for provider selection and track identification
- Better error messages for provider failures

### Fixed

- Cache enabled check now uses config object correctly
- Rate limiter synchronization issues
- Provider fallback logic to skip duplicate providers
- Cache key now includes provider name for better isolation

## [0.5.2] - 2024-11-17

### Changed

- Migrated ACRCloud to provider interface
- Enhanced provider factory with better configuration
- Improved error handling for providers
- Standardized provider timeouts

## [0.5.1] - 2024-11-17

### Added

- Comprehensive contributing guidelines (CONTRIBUTING.md)
- Detailed development environment setup instructions
- Code style and linting configuration
- Pre-commit hooks setup

### Changed

- Enhanced environment configuration template
- Expanded documentation for API keys and settings
- Improved project structure documentation

## [0.5.0] - 2024-11-17

### Added

- Enhanced Shazam integration:
  - Advanced audio fingerprinting with MFCCs
  - Spectral centroid analysis
  - Pre-emphasis filtering
  - Improved confidence scoring
  - Detailed audio features extraction
  - Extended metadata enrichment
- Audio landmark fingerprinting for track identification
- Advanced audio processing with librosa
- Shazam integration using shazamio package

## [0.4.0] - 2024-11-16

### Added

- Multiple provider support through provider interface
- Spotify integration for metadata enrichment
- Provider factory for managing multiple providers
- Comprehensive test suite for providers
- File-based caching system for API responses
- Token bucket rate limiter for API calls
- Memory-efficient chunk-based audio processing
- Retry mechanism with exponential backoff for API calls
- Timeout handling for long-running operations
- Enhanced logging system with colored console output
- Configurable log file output with timestamps
- Debug-level logging for development
- Custom log formatters for both console and file output
- Enhanced track identification verbosity
- Comprehensive analysis summary in output files
- Additional metadata in M3U playlists
- Modular package structure with dedicated modules
- Type hints throughout the codebase
- Factory pattern for platform-specific downloaders
- Enhanced track identification algorithm
- Cache configuration options:
  - CACHE_ENABLED for toggling caching
  - CACHE_DIR for cache location
  - CACHE_DURATION for cache expiration
- Rate limiting configuration:
  - RATE_LIMIT_ENABLED for toggling rate limiting
  - MAX_REQUESTS_PER_MINUTE for API throttling

### Changed

- Modular provider architecture
- Enhanced metadata enrichment
- Optimized memory usage during audio processing
- Improved Track class with strict validation
- Enhanced TrackMatcher with better error handling
- Refined confidence threshold handling
- More robust MP3 format validation
- Updated environment variable structure
- Enhanced error handling and logging
- Improved configuration management

### Fixed

- Track timestamp ordering
- Confidence threshold validation
- Track metadata validation
- Audio file format validation
- Memory leaks in audio processing
- API rate limiting issues

## [0.3.6] - 2024-11-16

### Fixed

- Fixed track timing calculation using MP3 metadata for accurate timestamps
- Adjusted default segment length to 60 seconds for better track identification
- Removed redundant acrcloud-py dependency in favor of pyacrcloud

### Added

- Added mutagen dependency for MP3 metadata handling
- Added total mix length display in track identification output

### Changed

- Improved segment timing calculation to use actual audio duration
- Enhanced logging with proper time formatting (HH:MM:SS)
- Updated requirements.txt for better dependency management

## [0.3.5] - 2024-11-15

### Fixed

- YouTube download functionality
- Import error handling for yt-dlp
- Downloader factory creation
- Mix information extraction order

### Changed

- Better error messages for missing dependencies
- Improved YouTube URL handling
- More robust downloader initialization
- Cleaner error handling flow

## [0.3.4] - 2024-11-15

### Added

- URL validation and cleaning functionality
- Support for various YouTube URL formats
- Automatic backslash stripping from URLs
- URL unescaping for encoded characters

### Changed

- Improved URL handling in main program
- Enhanced error messages for invalid URLs
- Better logging of URL processing steps
- Cleaner YouTube URL reconstruction

### Fixed

- Issue with backslashes in URLs
- Problems with URL-encoded characters
- Inconsistent YouTube URL formats
- Invalid URL handling

## [0.3.3] - 2024-11-15

### Added

- Comprehensive error handling system with specific exception types
- Retry mechanism with exponential backoff for API calls
- Timeout handling for long-running operations
- Custom exceptions for different error scenarios
- Detailed error logging and reporting

### Changed

- Enhanced API calls with retry logic
- Improved download operations with timeout handling
- Updated error messages with more context
- Added detailed error documentation

## [0.3.2] - 2024-11-15

### Added

- Enhanced logging system with colored console output
- Configurable log file output with timestamps
- Debug-level logging for development
- Custom log formatters for both console and file output

### Changed

- Updated logger module with comprehensive configuration options
- Improved log message formatting
- Added color-coding for different log levels
- Enhanced logging verbosity control

## [0.3.1] - 2024-11-15

### Added

- Enhanced track identification verbosity with detailed progress and status logging
- Comprehensive analysis summary in output files including confidence statistics
- Additional metadata in M3U playlists (artist and date information)

### Changed

- Modified track confidence handling to keep all tracks with confidence > 0
- Updated tracklist filename format to `[YYYYMMDD] Artist - Description.extension`
- Improved track merging process with more detailed debug logging
- Enhanced markdown output with analysis statistics section

### Fixed

- Filename sanitization to preserve spaces and valid punctuation
- Date format handling in filenames for consistency

## [0.3.0] - 2024-11-15

### Added

- Modular package structure with dedicated modules:
  - config.py for configuration management
  - logger.py for centralized logging
  - track.py for track identification
  - downloader.py for audio downloads
- Type hints throughout the codebase
- Proper package installation with setup.py
- Development environment setup
- Comprehensive logging system with file output
- Factory pattern for platform-specific downloaders

### Changed

- Restructured project into proper Python package
- Improved configuration using dataclasses
- Enhanced error handling and logging
- Updated documentation with new structure
- Improved code organization and maintainability

### Fixed

- FFmpeg path detection on different platforms
- Package dependencies and versions
- Installation process

## [0.2.0] - 2024-11-15

### Added

- Enhanced track identification algorithm with confidence-based filtering
- New track merging logic to handle duplicate detections
- Dedicated tracklists directory for organized output
- Additional configuration options in .env for fine-tuning:
  - MIN_CONFIDENCE for match threshold
  - TIME_THRESHOLD for track merging
  - MIN_TRACK_LENGTH for filtering
  - MAX_DUPLICATES for duplicate control
- Improved JSON output format with detailed track information
- Better timestamp handling in track identification

### Changed

- Updated .env.example with new configuration options
- Improved README documentation with output format examples
- Enhanced error handling in track identification process
- Optimized FFmpeg integration

### Fixed

- Duplicate track detection issues
- Timestamp accuracy in track listing
- File naming sanitization

## [0.1.0] - 2024-11-15

### Added

- Core track identification functionality
- Support for YouTube and Mixcloud platforms
- ACRCloud integration for audio recognition
- JSON export of track listings
- Command-line interface
- Configuration file support
- Detailed track information retrieval
- Timestamp tracking
- Confidence scoring
- Duplicate detection and merging
- Error handling and logging
- Documentation and usage examples

### Technical Features

- Abstract base class for stream downloaders
- Factory pattern for platform-specific downloaders
- Modular architecture for easy platform additions
- Temporary file management
- FFmpeg integration
- Configuration validation
- Progress tracking
- Error reporting

## Future Plans

### Planned Features

- Support for additional streaming platforms
- Enhanced duplicate detection algorithms
- Local audio fingerprinting
- Batch processing capabilities
- Web interface
- Playlist export to various formats
- BPM detection and matching
- DJ transition detection
- Genre classification
- Improved confidence scoring
- API rate limiting optimization
- Caching system for recognized tracks

### Technical Improvements

- Unit test coverage
- Performance optimizations
- Memory usage improvements
- Error handling enhancements
- Documentation updates
- Code refactoring
- Configuration system improvements
- Logging system enhancements
