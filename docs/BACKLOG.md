# Residual Risk Register & Backlog

From the 2026-07 handoff audit. Ordered by priority. Each item has enough
context to be picked up cold. "Fixed" items are listed at the bottom so
nobody re-audits them from scratch.

---

## Open unknowns

The items below are blocked on something other than effort. Without this
register the distinction is invisible — the blocker kind (measurement /
decision / external) determines whether a P3 item is one evening's work or
blocked indefinitely on someone outside the project saying yes. U1–U5
(the enrichment unknowns) are resolved in v0.10.0 and retained as
recorded measurements; U6–U10 remain open.

Three kinds of blocker: **measurement** (nobody has the number yet),
**decision** (nobody has chosen yet), **external** (someone outside the project
has to say yes).

Structural findings from the 2026-08 code-quality review are filed separately
as **Q1–Q9** below — those are not blocked on anything, only on effort.

| ID  | Question                                                                                                                              | Kind        | Blocks                                                | How it gets resolved                                                                                                                                                                                                         |
| --- | ------------------------------------------------------------------------------------------------------------------------------------- | ----------- | ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| U1  | What is the overall ISRC presence rate in Shazam responses?                                                                           | measurement | ~~Sizes both enrichment items~~                       | **Resolved 2026-08-04 (v0.10.0).** Measured ~94% on a commercial set (31/33) and ~70% on underground (26/36, 29/30) via the shipped per-run isrc/search/none counter + MusicBrainz enrichment |
| U2  | What fraction of ISRCs resolve to a Spotify track?                                                                                    | measurement | ~~P2 Spotify payoff estimate~~                        | **Resolved 2026-08-04 (v0.10.0).** MusicBrainz resolves ~23-25% of ISRCs to a Spotify URL (underground/EDM) and ~33% on commercial material. The Spotify-source estimate (~95%) is not separately measurable until a Premium-backed dev app exists |
| U3  | How often does title/artist search return the _wrong_ track for underground techno?                                                   | measurement | ~~Trusting the P2 Spotify fallback path~~             | **Resolved (instrumented) 2026-08-04 (v0.10.0).** `spotify_match: "isrc"\|"search"\|"musicbrainz"` is recorded per track, so fuzzy hits are auditable in real output instead of silently presented as fact. The wrong-match rate is now derivable from any real run |
| U4  | Flat per-platform keys or a nested `links` object in `Track.metadata`?                                                                | decision    | ~~P3 schema item~~                                    | **Decided 2026-08-02, shipped 2026-08-04 (v0.10.0) — nested `metadata.links`** (flat keys removed, `links.spotify` canonical-only, search URLs keep `*_search` keys) |
| U5  | How well does MusicBrainz cover underground-electronic ISRCs?                                                                         | measurement | ~~P3 MusicBrainz~~                                    | **Resolved 2026-08-04 (v0.10.0).** Measured by live probe over 117 real ISRCs: ~26% resolve, ~23-25% yield a Spotify URL. Thin for underground (the spec's caveat held), higher on commercial — additive, not exclusive |
| U6  | Is the non-distinguishing title-suffix allowlist complete?                                                                            | measurement | P2 dedup                                              | Not resolvable up front, and deliberately so: the dedup spec defaults to _keep_, so an incomplete allowlist costs a visible duplicate row, never a silent deletion. Widen it from observed output over time                  |
| U7  | RapidAPI Shazam: PCM conversion cost, metadata parity with shazamio, per-request price at ~216 segments/run, bot-defender reliability | external    | P3 RapidAPI                                           | Needs a paid key to answer any of it                                                                                                                                                                                         |
| U8  | Will Beatport grant partner access?                                                                                                   | external    | ~~P3 Beatport~~ (unblocked 2026-08-05)                | Still open — commercial-use review through the Partner Portal, a long waitlist. **No longer blocking:** the 2026-08-05 decision ships no client ID and no scraper; the user supplies their own credentials, opt-in and off by default (see the P3 Beatport section). If access is granted later, only the credential source changes |
| U9  | What is the real scope of the Spotify authorization-code + PKCE flow?                                                                 | decision    | Playlist export (`exporters/spotify.py`)              | Unscoped. Client-credentials tokens can never reach `/me/playlists`, so this is a feature project, not a wiring task                                                                                                         |
| U10 | Should a `download_quality` / `download_format` change invalidate the download cache?                                                 | decision    | P4 cache debt                                         | Unowned behavior decision. Today those fields are not wired through the factory and are absent from the cache key, so a re-run at a different quality serves the old file                                                    |
| U11 | Does `GET /v4/catalog/tracks/?isrc=` actually filter by ISRC?                                                                          | measurement | Beatport ISRC path (not the feature)                  | One live call with real credentials. Beatport track objects carry an `isrc` field, but nothing public says the list endpoint *filters* on it. `lookup_isrc` ships a returned-ISRC mismatch guard, so a "no" costs that path only — every match then arrives via gated search, with no code change |
| U12 | What is the Beatport match rate on underground techno, split isrc/search/none?                                                        | measurement | Sizing Beatport against MusicBrainz as a link source  | Read `beatport_match` counts out of one real run's `tracklist.json`. Compare against the measured ~23–25% MusicBrainz rate (U5)                                                                                              |
| U13 | Real Beatport token lifetime, and does the refresh-token grant work with the swagger-ui client ID?                                     | measurement | Whether the pasted-token path is one-off or a chore   | Read `expires_at` from `cache_dir/beatport_token.json` after a run. The refresh grant is deliberately **not implemented** until this is answered (spec §5.2 amendment) — an unverifiable fallback path is speculation         |
| U14 | How do we verify live-only behavior at all — recorded cassettes, an opt-in `integration` suite, or permanently-manual probes?          | decision    | Q8 below, and every future provider                   | Unowned. The `integration` pytest marker is registered but nothing uses it. Every provider so far was verified by an ad-hoc manual run whose result survives only in this file                                                |

**Unblocked right now:** the MusicBrainz item shipped in v0.10.0 (keyless, no
external gate). The Spotify client-credentials source also shipped but is
blocked behind a Premium-backed developer app for *live* use (Spotify's
late-2024 Web API policy) — the code is correct and degrades cleanly to a
no-op without it. Everything else in this table is waiting on a measurement,
an external decision, or someone outside the project.

---

## 2026-08 code-quality review (Q1–Q9)

A structural read of the codebase taken while building the Beatport source —
config, providers, identification, `core/track.py`, cache, factory, limiter,
tests, CI. Every claim below was verified against the tree on 2026-08-05; the
verification command is included so nobody has to re-derive it.

**The two-line summary:** the discipline in this project lives in
documentation and error-handling, not in type-safety or architecture. That
works while one person holds the whole model in their head, and degrades under
handoff — which is what the playbooks and the invariant tests exist to slow
down. The dominant risk is not bugs; it is **surface accumulating faster than
anything that validates it** (config fields, metadata keys). The second is that
the behaviors that matter most are invisible to the test suite by construction.

Three corrections to the first draft of this review, recorded so they are not
repeated: CI *does* install ffmpeg (Q6 is a testability point, not a CI
failure); the defensive `getattr` pattern is 15 sites, not "everywhere"; and
`BaseCache.get`'s rewrite-on-hit is conditional on the strategy mutating
metadata, not unconditional.

### Q1 (P1) — the cache subsystem is where "documented" replaced "fixed"

The known defects are already listed under "P4 — misc" below and have survived
several releases there. Promoting them: this is the one subsystem where the
project's own docs describe behavior nobody intends to keep.

Verify: `grep -rn "cache_cleanup_enabled\|cache_cleanup_interval" src/`
→ only `core/types.py:62-63` (a Protocol declaration). **No behavioral reader
exists.** `config/base.py` says so in a comment and ships the knobs anyway.

- `cache_cleanup_enabled` / `cache_cleanup_interval` are dead config: settable,
  documented in `.env.example`, read by nothing. Either wire a janitor or
  delete them — a knob that does nothing is worse than a missing feature,
  because someone will set it and believe it.
- `BaseCache.get()` rewrites the entry whenever `update_metadata` returns a
  changed dict (`cache/base.py:91-99`). Under `TTLStrategy` that is most hits:
  a read path doing a write, per hit.
- `SizeStrategy` treats the byte budget as per-entry; there is no aggregate
  eviction. The identification cache grows unbounded in practice.
- Compression is detected by sniffing zlib magic rather than reading the stored
  flag.
- `_stats["entries"]` over-counts overwrites.
- The download cache has no TTL and no eviction (v1), and `cache_max_size` is
  1 MB — meaningless for audio. Cleanup is `rm -rf cache_dir/downloads`.

**Done looks like:** every knob either drives behavior or is gone; one decision
recorded on aggregate eviction; U10 answered.

### Q2 (P2) — `Track.metadata` is a growing dict with no schema

`Dict[str, Any]` carrying an informal, expanding contract: `isrc`, `album`,
`label`, `release_date`, `genres`, `shazam_id`, `apple_music_id`,
`artwork_url`, `links.{shazam,spotify,spotify_search,deezer_search,deezer,
tidal,apple,beatport}`, `spotify_id`, `spotify_match`, and — as of this branch
— `beatport_id`, `bpm`, `key`, `genre`, `sub_genre`, `remixers`,
`catalog_number`, `beatport_match`.

Nothing validates any of it. `_extra_metadata` writes some keys, three
enrichment passes write others, and the JSON exporter emits whatever is there
via `default=str`. The M3U and markdown exporters read by convention. A typo in
a writer is invisible until someone reads the output.

This branch added eight keys and made the problem measurably worse.

**Done looks like:** a `TypedDict` (or small dataclass) that names every key
with its type, one place that documents them, and writers that go through it.

### Q3 (P2) — three near-duplicate enrichment passes

`_enrich_spotify`, `_enrich_musicbrainz`, `_enrich_beatport` are ~60 lines each
with the same skeleton: resolve provider → return if None → limiter loop →
acquire/`finally` release → `record_result` → counts → summary log. They differ
in the provider call and the write policy.

The `_enrich_tracks` docstring justifies this: *"the charter forbids a registry
for two implementations."* That was correct at two. At three it is
copy-paste, and the next source makes it four. The `getattr(factory,
"get_X_provider", None)` fallback is now repeated three times too.

**Done looks like:** one runner parameterized by (provider accessor, lookup
callable, write policy, pacing interval, counter labels). Not a registry — a
function with four arguments.

### Q4 (P2) — `TrackIdentificationConfig` is a god object

~40 flat fields spanning directories, logging, segmentation, six providers,
circuit breaker, cache, downloads, output and enrichment. Every feature bolts
on more; this branch added three. There is no grouping, and `_load_from_env`
reflects over every field with a type switch.

The companion smell is the defensive read: `getattr(self.config, "field",
default)` at 15 sites (`grep -rn "getattr(.*config" src/ | wc -l`). Against a
dataclass whose fields are statically known, that pattern only ever hides
typos — a misspelled attribute silently takes the default. That is the exact
shape of the `min_confidence` bug that already shipped once (config knob wired
at 0–1, property setter unscaled).

**Done looks like:** nested config sections (or grouped mixins), and direct
attribute access wherever the field is guaranteed to exist.

### Q5 (P2) — no type checking in CI

CI runs `lint`, `drift`, `test` (3.11/3.12/3.13) and CodeQL. Ruff catches
style, not attribute typos, not metadata-key drift, not `Optional` misuse —
i.e. not this codebase's actual failure mode (Q2, Q3, Q4 are all things a type
checker would have pushed back on).

**Done looks like:** mypy in CI, however loose to start, with a ratchet.

### Q6 (P3) — ffmpeg is required to *construct* a downloader

`YTDLPDownloader.__init__` calls `get_ffmpeg_path()` (`downloaders/ytdlp.py:161`,
`mixcloud.py:42`), which raises `FileNotFoundError` when the binary is absent.
So a unit test asserting `ydl_opts["verbose"] is False` needs a media binary
installed. CI works around this by installing ffmpeg
(`.github/workflows/ci.yml`, "Install ffmpeg"), so this is **not** a CI
failure — but it is 21 tests that cannot run in a plain checkout, and it
means the class cannot be constructed for inspection.

**Done looks like:** ffmpeg path resolution injectable or lazy, so options can
be built without the binary. The fail-fast check in `cli.py` stays.

### Q7 (P3) — `dev_cli/` has no tests at all

`testpaths = ["tests"]` and nothing under `tests/` covers it; it is also
excluded from coverage (`pyproject.toml:122`) and from bandit
(`exclude_dirs`). The 2026-08 cheap batch fixed two real bugs in it
(`run.py` argv mangling, `config.py` unreachable fallback) — both verified by
hand, because there was no other way.

**Done looks like:** a decision. Either it earns a test file, or it leaves
`src/`.

### Q8 (P2) — the behaviors that matter most are unverifiable by the suite

This is the highest-leverage item and the one that keeps recurring.

The MusicBrainz pacing bug was an **8× yield regression** (3% → 25%) that every
mocked test passed. The Beatport pacing constant (`_BEATPORT_REQUEST_INTERVAL
= 0.5`) is sitting in exactly the same position right now: asserted by a test
that counts `asyncio.sleep` calls, verified against reality by nothing. Same
for U11, and for identification quality in general.

The `integration` marker is registered in `pyproject.toml` and unused.

**Done looks like:** U14 decided, then built — recorded cassettes, an opt-in
live suite, or a `scripts/probe_*` family whose output lands in this file.
Manual-forever is a legitimate answer; leaving it undecided is not.

### Q9 (P4) — test file names no longer describe their contents

`tests/test_spotify_factory.py` holds the Spotify, MusicBrainz *and* Beatport
factory-accessor tests (I added the third rather than splitting, to keep them
next to their siblings). Cheap to fix, worth doing before a fourth source.

**Done looks like:** `test_provider_factories.py`, or one file per accessor.

---

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
  is ~216 segments _per run_, times the fallback chain. Price a realistic
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

## P3 — Beatport links + DJ metadata — specced 2026-08-05 (U8 stance changed)

> **Update 2026-08-05.** No longer blocked. Partner access is still a long
> waitlist (U8 unresolved), so the decision taken is narrower than the
> workaround this entry originally rejected: **ship no client ID and no
> scraper** — `TRACKLISTIFY_BEATPORT_CLIENT_ID` is env-only with no default,
> the feature is opt-in and off by default, and the user supplies their own
> Beatport account. Development uses the `beets-beatport4` public client ID
> the same way a user would: in a local `.env`, never committed. Spec:
> `docs/dev/2026-08-05-beatport-enrichment-spec.md`. New unknowns U11 (does
> `/v4/catalog/tracks/?isrc=` actually filter?), U12 (match rate on
> underground techno), U13 (token lifetime / refresh viability).
>
> **Implementation landed 2026-08-05** (plan:
> `docs/dev/2026-08-05-beatport-enrichment-plan.md`, tasks 1–5): config +
> limiter branch, `providers/beatport.py` (auth, token cache, catalog
> lookup/search/extraction), the env-only factory accessor, and the
> `_enrich_beatport` pass with its acceptance gate. 46 offline tests.
>
> **Verified live 2026-08-06** (two Tomorrowland sets, real creds via the
> password flow + cached token), each track gaining BPM/key/label + the
> canonical `www.beatport.com` link alongside the Shazam/Spotify/Deezer links.
> Match breakdown (isrc / search / none):
> - **Meduza WE1** (mainstream house): 14/19 = **74%** (12 isrc / 2 search /
>   5 none).
> - **Dyen b2b Maddix WE2** (hard techno): 16/20 = **80%** (11 isrc / 5
>   search / 4 none).
> Resolves all three open unknowns:
> - **U11** — `/v4/catalog/tracks/?isrc=` does filter (23 ISRC hits across the
>   two sets, no spurious mismatch-guard rejects); the ISRC-miss → search
>   fallback fired correctly (7 search hits).
> - **U12** — techno recall holds, not just house: **80%** on the Dyen/Maddix
>   hard-techno set vs 74% on Meduza house. Both ~3× the ~23–25% MusicBrainz
>   Spotify-link baseline. The search path carried a third of the techno
>   matches (5/16), so the acceptance gate earns its keep on the noisier
>   catalog.
> - **U13** — access tokens live **600 s**; no refresh flow is wired, so
>   expiry falls back to full username/password re-login (the cached token
>   makes a normal run a single login). Refresh-token use remains a gap.
> Also landed same day: an error-posture hardening pass
> (`fix(providers): harden Beatport enrichment error posture`) — OAuth
> misconfig now disables the pass instead of re-running login per track,
> transient 5xx stays per-track, auth 429s carry Retry-After, the
> zero-match summary logs unconditionally, and the metadata-write +
> cache-corruption paths can no longer abort a run.
>
> The original entry is kept below verbatim as the record of why the
> unqualified workaround was rejected — that reasoning still stands.

### Original entry (2026-07): blocked on partner approval, not on code

<https://api.beatport.com/v4/docs/>. The best metadata source for this
project's actual genre — Beatport's label, remixer, BPM and musical-key
data for techno/hard techno is materially better than Spotify's, and a
Beatport link is what a DJ reading a tracklist actually wants.

**It is an application, not a coding task.** v4 is OAuth 2.0
authorization-code with PKCE, gated to approved partners through the
Beatport Partner Portal, with no client-credentials or self-serve public
tier (verified 2026-08-01; v3 is dead). Approval involves a commercial-use
review. Apply with the same account used to buy music on Beatport —
developers report the portal returning "No Access" otherwise.

**Do not ship the known workaround.** Several open-source projects
(`beets-beatport4` among them) reuse the public client ID from Beatport's
own docs frontend. It is fragile and near-certainly outside Beatport's
terms; not something to build a user-facing feature on.

Revisit only if partner access is granted. If it is, the token refresh
and PKCE flow make it closer in shape to the Spotify _playlist export_
problem than to the simple client-credentials enrichment above.

## P3 — config/docs.py accuracy

The doc generator works now (`scripts/generate_config_docs.py` was calling
a method that never existed; fixed), but: `_field_to_schema` parses
constraint strings like "Must be >= 10" by inspecting the wrong token, so
min/max never reach the JSON schema; `generate_schema` marks every field
required; `field.__doc__` is the `dataclasses.Field` class docstring, not a
field description. Low value — consider generating from
`_setup_validation` rules directly instead of parsing prose.

## P4 — misc

- ~~`tests/test_cli_arguments.py` uses an unregistered `integration` pytest
  mark~~ — registered in `pyproject.toml:112`. Its declared meaning ("hit live
  external services") and its only use disagree, though:
  `test_cli_to_app_integration` (`test_cli_arguments.py:371`) is an in-process
  CLI→app test that touches nothing external. Either the description or the
  usage is wrong; resolving it is part of Q8/U14.
- `pytest-asyncio` will eventually require `asyncio_default_fixture_loop_scope`;
  set it explicitly in `[tool.pytest.ini_options]` when upgrading.
- **Cache debt (identification + download):** **promoted to Q1 above (P1)** —
  the full defect list, the dead `cache_cleanup_*` knobs, and what "done"
  means live there now. One item stays here because it is a decision, not a
  defect: `download_quality`/`download_format` are not wired through the
  factory and so are absent from the download cache key, meaning a re-run at
  a different quality serves the old file (U10).

---

## Fixed

### 2026-08 cheap batch: dead code + dev_cli + security polish (`chore/cheap-batch-*`)

Closed the cheapest unblocked backlog items in one pass. No end-user behavior
change for the main `tracklistify` CLI.

| Fix                                                                                                   | Where                                                                                                  | Test / verify                                                                  |
| ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------ |
| Dead `downloaders/spotify.py` (405 lines, no factory route, internally broken)                        | deleted; `test_imports` pins ytdlp, `test_type_hints` drops the path                                   | 590 passed                                                                     |
| `utils/decorators.py::memoize` — unused `ttl`, unbounded, no production callers                        | deleted + its 2 test files + `utils/__init__` re-export + 3 stale static-inspection test methods       | suite                                                                          |
| `core/types.Downloader` Protocol — incompatible with the real ABC; orphaned TypedDicts + TypeVar       | deleted Protocol, `DownloaderT`, `DownloadResult`/`DownloadProgress` (no consumers); typing imports trimmed | suite                                                                          |
| `ACRCLOUD_SUCCESS_CODE = 2000` — unused, and actually ACRCloud's auth-error code                       | deleted from constants                                                                                  | vulture                                                                        |
| `core/run._cleanup_tasks` — registry never populated                                                  | removed; `cleanup()` is now an explicit no-op                                                           | suite                                                                          |
| `dev_cli/execution/executor.py` — zero callers, timeout never enforced                                | deleted; `execution/__init__` re-exports removed                                                        | suite + import probe                                                           |
| `RunCommand` join-then-shlex-split mangled spaced/quoted args                                          | `run.py` threads list-form end-to-end; `run_shell_command` accepts `Union[str, List[str]]`             | manual: `'arg with spaces'` survives as one argv element                       |
| `dev_cli/config.py` — missing `tools.json` crashed (FileNotFoundError fallback unreachable)            | early `ConfigurationError` removed so the fallback fires; redundant module-level `load_default_config` dropped | manual: missing tools.json → defaults                                          |
| `mask_sensitive_value` threshold 8 → 12 (8-char secret leaked 6/8 chars)                              | `config/security.py`; two tests updated to ≥12-char partial-mask values                                 | `test_config_security.py`, `test_config.py`                                    |
| Two divergent sensitive predicates (`is_sensitive_key` / `is_sensitive_field`)                         | collapsed to one `SENSITIVE_PATTERNS` source; `SENSITIVE_FIELDS` removed (additive only — no field un-masks) | existing assertions hold                                                      |
| `cache/storage.py` — on-disk index `filename` trusted without basename check (path traversal)         | `_safe_cache_path` rejects directory components; get()→miss+drop, delete()→no-op                        | `test_storage_rejects_traversal_filename`                                      |

**Design:** dev_cli has no test coverage (excluded from the suite via
`exclude_dirs`), so the `run.py` arg-fix and `config.py` fallback are verified
manually (logged above), not by a unit test. The `metadata.links` schema and
enrichment work are untouched. **Out of scope, noted by vulture:** pre-existing
`downloaders/factory._downloaders` and `ytdlp` unreachable-code findings — not
introduced here.

### 2026-08 P2/P3 Spotify + MusicBrainz link enrichment (`feat/spotify-link-enrichment` #72, `feat/musicbrainz-enrichment` #73, v0.10.0)

Two post-dedup link sources for canonical streaming URLs, plus the nested
`metadata.links` schema (resolves unknowns U1–U5). Both additive, opt-in,
best-effort (never fail a run).

| Fix                                                                                                   | Where                                                                                                        | Test                                                                              |
| ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| `SpotifyProvider` search/enrich existed but no pipeline stage called it                               | `utils/identification.py::_enrich_spotify` hook after `get_unique_tracks()` (ISRC-first, search fallback)   | `tests/test_spotify_enrichment.py`                                               |
| `search_track` lacked `external_urls`/`isrc`; no exact ISRC lookup                                    | `providers/spotify.py` (+`search_by_isrc`)                                                                   | `tests/test_providers_spotify.py`                                                |
| No keyless link source reachable without a Premium-backed Spotify app                                 | `providers/musicbrainz.py::MusicBrainzProvider.lookup_isrc` (free, keyless, `isrc/<isrc>?inc=url-rels`)      | `tests/test_providers_musicbrainz.py`                                            |
| MusicBrainz bursts a full token bucket and 503-storms → ~3% yield                                     | `utils/identification.py::_enrich_musicbrainz` explicit 1.1s pacing + bounded 503 retry (provider)          | `tests/test_musicbrainz_enrichment.py` + live (3 runs: 25/23/23%, was 3%)        |
| Flat per-platform `*_url` metadata keys don't scale past four                                         | `utils/identification.py::_extra_metadata` nests under `links.{shazam,spotify_search,deezer_search}` (U4)   | `tests/test_identification_utils.py`                                             |
| `enrichment_enabled` / `musicbrainz_enabled` + rate-limit config                                       | `config/base.py`, `utils/rate_limiter.py` (musicbrainz branch), `scripts/generate_env_example.py`           | `tests/test_config.py`, `tests/test_rate_limiter.py`                             |

**Design:** two independent sources run in sequence (Spotify client-credentials
first, then MusicBrainz keyless), first-writer-wins per `links` key. The
Spotify source needs a Premium-backed developer app (Spotify's late-2024 Web
API policy) for live use and degrades to a clean no-op without it; the
MusicBrainz source needs no external account and works today. Each matched
track records `spotify_match` (`"isrc"` | `"search"` | `"musicbrainz"`) so the
underground-techno wrong-match rate is auditable from real output (U3).
Measured coverage (U5): ~23–25% Spotify links on underground/EDM ISRCs, ~33%
on commercial material. The explicit MB pacing is load-bearing — the rate
limiter's full-token-bucket seed permits a burst; removing the 1.1s sleep
regresses yield ~8× (3% → 25%), and unit tests mocking HTTP cannot catch it.
Specs: `docs/dev/2026-08-02-spotify-link-enrichment-spec.md`,
`docs/dev/2026-08-04-musicbrainz-enrichment-spec.md` (local-only).

### 2026-08 changelog + tag reconstruction (`docs/changelog-tag-reconstruction`)

The changelog and git tags disagreed with the real release history, so
commitizen could not generate reliably. Three real releases had no changelog
section; this reconstructs them.

| Fix                                                                                                      | Where                                                                        | Test |
| -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ---- |
| `0.7.0` (clean-slate modular restructure, 2025-09-15) had no changelog section                          | `docs/CHANGELOG.md` — added `[0.7.0]` from `f847c83` + #26–#35 commit bodies | —    |
| `0.8.0` (the 2026-05 multi-phase audit) had no changelog section — its work was misfiled under `[0.8.2]` | `docs/CHANGELOG.md` — added `[0.8.0]` from `86fa9fc` body                     | —    |
| `0.8.1` (the #53 handoff-audit hardening) had no changelog section — misfiled under `[0.8.2]`            | `docs/CHANGELOG.md` — added `[0.8.1]` from `40af3e9` body (I1–I8)             | —    |
| `[0.8.2]` over-bundled 0.8.0/0.8.1 work (importability, ABC, CryptoManager)                             | `docs/CHANGELOG.md` — trimmed to PR #65's actual scope                       | —    |
| `0.7.0` was never tagged                                                                                | created back-dated annotated `v0.7.0` at `f847c83`                           | —    |
| `0.8.0` tag lacked the `v` prefix `tag_format` requires                                                 | recreated as back-dated annotated `v0.8.0` at `86fa9fc`                      | —    |
| `changelog_start_rev = "v0.8.1"` made cz blind to all pre-0.8.1 history                                 | `pyproject.toml` — moved to `v0.7.0`                                         | —    |

**Design:** cz now sees a consistent `v0.7.0 → HEAD` tag chain and generates
end-to-end (`cz changelog --dry-run` and `cz bump --dry-run` both exit 0).
The `[0.1.0]`–`[0.6.0]` + "Phase 1–4" sections are the genuine pre-squash
record (the old branch's work, consolidated into the 0.7.0 clean slate) and
are kept verbatim below `v0.7.0`. `update_changelog_on_bump` stays `false`
(full regen is off-limits; the repeatable flow is `cz changelog
--incremental` then `cz bump`). This item was itself only recoverable from
the session transcript — it had never been recorded in the backlog.

### 2026-08 P2 dedup title-variants + download fixes (`feat/dedup`, PR #68)

| Fix                                                                                                                                                                  | Where                                                                                                                               | Test                                                                         |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Bracketed title variants (`(Club Mix)`, `[Live At …]`, `feat.`/`ft.`/`featuring` spellings) survived dedup as duplicate rows — titles compared exact-after-normalize | `core/track.py::_strip_title_variant` + `_comparison_title` (canonicalize trailing-suffix groups before normalize; comparison-only) | `tests/test_track_matcher.py::TestDedupInvariants` d1–d21                    |
| `config.download_max_retries` was dead config (declared, never read) — transient YouTube 403 aborted the run                                                         | `downloaders/ytdlp.py` wires it into yt-dlp's native `retries` option                                                               | `tests/test_ytdlp.py::test_download_max_retries_is_wired_into_ydl_opts`      |
| YouTube `&list=RD…` (auto-mix) URLs 403'd — yt-dlp descended into the playlist before `playlist_items='1'` bounded the download (non-retryable)                      | `downloaders/ytdlp.py::_strip_youtube_playlist_params` strips playlist params for YouTube                                           | `tests/test_ytdlp.py::test_youtube_playlist_params_stripped_before_download` |
| `ydl_opts['verbose']` was `True` with a comment saying "Always set to False" — flooded the log with a yt-dlp traceback on every download failure                     | `downloaders/ytdlp.py` (`verbose: False`)                                                                                           | `tests/test_ytdlp.py::test_ydl_opts_verbose_is_false`                        |

**Design:** the feat-credit marker is canonicalized, not dropped — keeping
both the marker word and the credited artist (a credit identifies a specific
recording). Accepted trade-off: a `feat. X` credit and a `(Mixed)` tag of the
same audio now separate (visible duplicate — the recoverable direction). The
full rule set, allowlist/keep-list trade-offs, and representative-selection
invariants are in `docs/playbooks/changing-dedup.md`. Survived 3 review
passes (2× `/code-review max`, 4-agent PR-review) + code-simplifier polish.

### 2026-07 P2 correctness batch (`fix/p2-dedup-confidence-downloader`)

| Fix                                                                                                                                                           | Where                                                                                                                           | Test                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Dedup missed artist-string variants (`Berghain (Remix)` twice, 50s apart) — the shipping `get_unique_tracks` keyed on exact `artist\|song` and was time-blind | `core/track.py::TrackMatcher.get_unique_tracks`                                                                                 | `tests/test_track_matcher.py::test_artist_variant_merge_berghain` |
| Representative `time_in_mix` flipped between runs (strict `>` on noisy confidence)                                                                            | `core/track.py::_rep_key` (earliest time; confidence excluded outright — bucketing was tried and still flipped at bucket edges) | `test_representative_is_deterministic_under_confidence_noise`     |
| `config.min_confidence` was a no-op (hardcoded 0); default 0.5 → 0.0 so output is unchanged until the knob is turned                                          | `core/track.py::TrackMatcher.__init__`, `config/base.py`                                                                        | `test_min_confidence_filters_low_confidence`                      |
| `TrackMatcher` re-resolved the global config, ignoring an injected one                                                                                        | `utils/identification.py` passes `self.config`                                                                                  | `tests/test_track_matcher.py` fixture                             |
| SoundCloud `/sets/` container metadata propagated (wrong title/duration/filename)                                                                             | `downloaders/ytdlp.py::download` unwraps `_type == "playlist"` → `entries[0]`                                                   | `tests/test_ytdlp.py`                                             |
| Output path reconstructed via `prepare_filename` missed muxing ext changes                                                                                    | prefer `requested_downloads[0]["filepath"]`                                                                                     | `tests/test_ytdlp.py`                                             |
| Stale pre-fix `/sets/` metadata served forever (cache has no TTL)                                                                                             | `cache/download.py::KEY_VERSION` in key material                                                                                | `tests/test_download_cache.py`                                    |

**Design:** the matching rule (canonicalize-then-normalize via
`_strip_title_variant`: drop non-distinguishing version/live tags,
canonicalize `feat.`/`ft.`/`featuring` to `feat` keeping the credited artist,
default keep), the allowlist-vs-keep-list trade-off, representative selection
(jitter-proof earliest-time), and the accepted over-merges
(`(Original Mix)` vs `(Radio Edit)` merge by design; two _named-different_
`Live At …` venues collapse — a real over-merge class awaitable against real
output) are all specified canonically in
`docs/playbooks/changing-dedup.md`. The keep-list beats a drop-list because
`(Someone Remix)` and a bare `(Remix)` must stay separate rows; no fuzzy
ratio is used.

**Dead code removed:** `merge_nearby_tracks` + its six helpers
(`_create_track_group`, `_should_add_to_group`, `_add_to_group`,
`_get_best_track`, `_is_unique_track`, `_add_to_merged_list`). These had zero
production callers — the original backlog framing of the dedup bug described
_these_, not the shipping `get_unique_tracks`, which is why the proposed
levers (fuzzy `is_similar_to`, raise `time_threshold`) would not have fixed
anything. `add_track` no longer dedups; it confidence-gates and appends.

### 2026-07 cache + output work (`feat/wire-cache-identification`, PR #65)

| Fix                                                                                  | Where                                                 | Test                                                            |
| ------------------------------------------------------------------------------------ | ----------------------------------------------------- | --------------------------------------------------------------- |
| Identification cache never called by production code                                 | `utils/identification.py::IdentificationManager`      | `tests/test_cache_wiring.py`                                    |
| Downloaded audio re-fetched every run                                                | `cache/download.py`, `core/base.py::process_input`    | `tests/test_download_cache*.py`                                 |
| Output was a flat dir; M3U emitted comments only (no playable URI, EXTINF always -1) | `exporters/tracklist.py`, `core/base.py::save_output` | `tests/test_output_subfolders.py`, `tests/test_m3u_playable.py` |
| Mixcloud stored no metadata (`get_last_metadata()` returned None)                    | fixed via download-cache sidecar                      | `tests/test_download_cache_wiring.py`                           |
| Folder names said "Unknown Artist" (uploader never wired into output)                | `core/base.py::save_output` → `mix_info["artist"]`    | `tests/test_output_subfolders.py`                               |

### Fixed in the 2026-07 audit (do not re-fix; locked by tests)

| Fix                                                                                                | Where                                           | Test      |
| -------------------------------------------------------------------------------------------------- | ----------------------------------------------- | --------- |
| Config validation rules were never executed                                                        | `config/base.py::_validate`                     | I1        |
| `overlap >= segment` → infinite segmentation loop                                                  | config cross-check + `split_audio` guard        | I2        |
| ACRCloud unconstructible (missing ctor args) + wrong `identify_track` signature                    | `providers/factory.py`, `providers/acrcloud.py` | I3, I4    |
| `--no-fallback` / `fallback_*` config were no-ops                                                  | `IdentificationManager` provider chain          | I5        |
| Circuit breaker never received outcomes                                                            | `RateLimiter.record_result` + identify loop     | I6        |
| Cache TTL disabled by stored `None`                                                                | `cache/base.py::set`                            | I7        |
| Cache index never saved on set/delete (cross-process data loss + orphan deletion of valid entries) | `cache/storage.py`                              | I8        |
| Cache index rename without fsync                                                                   | `cache/index.py::save`                          | —         |
| ffmpeg absence surfaced as cryptic per-segment errors                                              | `cli.py` fail-fast + `split_audio` log          | CLI tests |
| `TracklistOutput` mkdir without `parents=True`                                                     | `exporters/tracklist.py`                        | —         |
| Spotify 429 lost structured `retry_after`                                                          | `providers/spotify.py`                          | —         |
| `cz bump` broken (`version_provider = "poetry"` post-uv-migration)                                 | `pyproject.toml`                                | —         |
| `scripts/generate_config_docs.py` called a nonexistent method                                      | fixed to use `ConfigDocGenerator`               | —         |
| Dead + broken module-level `identify_tracks(audio_path)` (iterated a string as segments)           | removed from `utils/identification.py`          | —         |
