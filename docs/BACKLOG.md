# Residual Risk Register & Backlog

From the 2026-07 handoff audit. Ordered by priority. Each item has enough
context to be picked up cold. "Fixed" items are listed at the bottom so
nobody re-audits them from scratch.

---

## Open unknowns

The items below are blocked on something other than effort. Without this
register the distinction is invisible — it is buried in prose inside the P2/P3
entries, so "MusicBrainz enrichment" and "Spotify enrichment" look like the
same size of job when only one of them is actually unblocked.

Three kinds of blocker: **measurement** (nobody has the number yet),
**decision** (nobody has chosen yet), **external** (someone outside the project
has to say yes).

| ID | Question | Kind | Blocks | How it gets resolved |
|---|---|---|---|---|
| U1 | What is the overall ISRC presence rate in Shazam responses? | measurement | Sizes both enrichment items | The per-run isrc/search/none counter shipped by the Spotify spec. Current evidence is n=1 set: 7 of the 8 link-less tracks in a 20-track run carried an ISRC — that is a rate among *link-less* tracks, not the overall rate |
| U2 | What fraction of ISRCs resolve to a Spotify track? | measurement | P2 Spotify payoff estimate (the 12/20 → ~19/20 claim) | Same counter |
| U3 | How often does title/artist search return the *wrong* track for underground techno? | measurement | Trusting the P2 Spotify fallback path | Not resolvable up front. The Spotify spec records `spotify_match: "isrc"\|"search"` per track, so fuzzy hits are auditable in real output instead of silently presented as fact |
| U4 | Flat per-platform keys or a nested `links` object in `Track.metadata`? | decision | P3 schema item | **Decided 2026-08-02 — nested `metadata.links`.** See `docs/dev/2026-08-02-spotify-link-enrichment-spec.md` unit E |
| U5 | How well does MusicBrainz cover underground-electronic ISRCs? | measurement | P3 MusicBrainz — if coverage is low this buys little | Offline probe over a real `tracklist.json` once U1/U2 have produced ISRCs to probe with. Cheap, keyless, and worth doing before writing any MusicBrainz code |
| U6 | Is the non-distinguishing title-suffix allowlist complete? | measurement | P2 dedup | Not resolvable up front, and deliberately so: the dedup spec defaults to *keep*, so an incomplete allowlist costs a visible duplicate row, never a silent deletion. Widen it from observed output over time |
| U7 | RapidAPI Shazam: PCM conversion cost, metadata parity with shazamio, per-request price at ~216 segments/run, bot-defender reliability | external | P3 RapidAPI | Needs a paid key to answer any of it |
| U8 | Will Beatport grant partner access? | external | P3 Beatport | Commercial-use review through the Partner Portal. No code path exists without it, and the known public-client-ID workaround is not shippable |
| U9 | What is the real scope of the Spotify authorization-code + PKCE flow? | decision | Playlist export (`exporters/spotify.py`) | Unscoped. Client-credentials tokens can never reach `/me/playlists`, so this is a feature project, not a wiring task |
| U10 | Should a `download_quality` / `download_format` change invalidate the download cache? | decision | P4 cache debt | Unowned behavior decision. Today those fields are not wired through the factory and are absent from the cache key, so a re-run at a different quality serves the old file |

**Unblocked right now:** the two P2 items. Both have specs in `docs/dev/`.
Everything else in this table is waiting on a measurement that those specs
produce, or on someone outside the project.

---

## P2 — bracketed/parenthetical title variants survive dedup as separate rows

**Status: Fixed.** `_strip_title_variant` rewrites bracketed suffixes before
normalization, comparison-only (representative keeps its raw title): it drops
non-distinguishing version/live tags (`(Mixed)`, `(Club Mix)`, `[Live At …]`,
…) and **canonicalizes** `feat.`/`ft.`/`featuring` markers to `feat` while
**keeping the credited artist** (a credit identifies a specific recording, so
it is not dropped — that would merge different featured artists and swallow
`Ft. <Place>` abbreviations). The analysis below is retained as historical
record; note the `feat.` handling diverged from its "Suggested approach"
(canonicalize, not strip) for the reasons above.

**Spec:** `docs/dev/2026-08-02-dedup-title-variants-spec.md`

Identity requires titles to be **exactly equal** after normalization
(`_tracks_match`), so a track detected under two title spellings emits two
rows. Confirmed on real output, not hypothetical:

| Time | Title A | Title B |
|---|---|---|
| 08:20 / 09:10 | `Meet Her At The Love Parade (feat. Kiki Solvej)` | `Meet Her At The Love Parade (Mixed)` |
| 57:30 / 58:20 | `Outside World (Club Mix)` | `Outside World` |

Both pairs are ~50s apart (one segmentation step) with matching artists —
the proximity and artist gates already agree they belong together; only
the title check splits them. A reader sees one track played once and gets
two lines.

**Suffixes appear in `[...]` as well as `(...)`** — e.g. `Stereo Murder
[Live At Tomorrowland]` in the same run. Handle both bracket styles or
the fix covers half the cases.

**Why this was left alone during the dedup rewrite:** the suffixes are not
uniformly noise. `(Mixed)`, `(Club Mix)`, `(Radio Edit)`, `(Extended
Mix)`, `(feat. X)` are usually the *same* recording under different
Shazam spellings, but `(Remix)` and a named `(Someone Remix)` are a
genuinely different track that must stay separate. No single similarity
ratio separates `"Berghain"` vs `"Berghain (Remix)"` (must split) from
`"Outside World"` vs `"Outside World (Club Mix)"` (should merge) — they
are the same edit distance. This needs a **semantic** rule, not a fuzzier
threshold.

**Suggested approach:** strip a curated allowlist of non-distinguishing
suffixes before comparison (`mixed`, `club mix`, `extended mix`, `radio
edit`, `original mix`, `live at …`, `feat.`/`ft.`/`featuring …`) and keep
everything else — notably anything containing `remix`, `bootleg`,
`edit by`, `vip` — as title-distinguishing. Strip for the *comparison
only*; the representative must keep its original title, since the
displayed name should be what Shazam actually returned.

**Implementation constraint — strip BEFORE normalizing.** `_normalize_token`
maps punctuation to spaces, so by the time it has run the delimiters are
already gone and the suffix is indistinguishable from part of the title:

```
"Stereo Murder [Live At Tomorrowland]" -> "stereo murder live at tomorrowland"
"Outside World (Club Mix)"             -> "outside world club mix"
```

A stripper that runs after normalization has no brackets left to anchor
on and would have to substring-match, which will eat legitimate titles
(a track actually called `Club Mix`). Operate on the raw title, matching
`\((...)\)` and `\[(...)\]`, then normalize the remainder.

Guard both directions with tests, as with the chaining rule: a merge case
and a must-not-merge case. Do **not** attack this by loosening the artist
Jaccard threshold — that is a different axis and would reintroduce the
collab-bridge data loss (see `docs/playbooks/changing-dedup.md` rule 1b).

## P2 — Spotify enrichment is built but unreachable

**Spec:** `docs/dev/2026-08-02-spotify-link-enrichment-spec.md` (also decides
the P3 link-schema item below — unknown U4)

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

**Concrete goal, now that links are the driver:** a canonical Spotify
track URL per track. Shazam already gives us a *search* URL for free
(`spotify_search_url`, shipped 2026-08-01) — this item is what upgrades it
to a real `https://open.spotify.com/track/<id>`. `search_track` already
returns `spotify_id`, so the URL is string construction, not another API
call. Note `search_track` does **not** return `external_urls` even though
`get_track_details` does (`spotify.py:227`) — add the field there rather
than making a second request per track.

**Measured payoff (fresh-cache run, 2026-08-01, 20-track Tomorrowland
set):** Shazam supplied a Spotify search URL for only **12/20** tracks —
`hub.providers` is simply absent from ~40% of responses, and it varies
between calls for the same audio (one track had no link on the first run
and one on the next). But **7 of the 8 tracks missing a link do carry an
ISRC**. An ISRC-first lookup would take link coverage from 12/20 to
roughly 19/20, which is the concrete argument for doing this.

**Hook after `get_unique_tracks()`, not per segment.** Dedup runs first,
so a 3h mix enriches ~22 unique tracks instead of ~216 raw detections —
a 10x cut in API calls, and it keeps the rate limiter out of the
identification hot path. Also decide match confidence: Spotify's search
returns a best-effort top hit, and for underground techno it will
sometimes confidently return the wrong track. Prefer ISRC lookup
(`search?q=isrc:<isrc>`) when Shazam gave us one — exact, not fuzzy —
and fall back to title/artist search only when it didn't.

No wiring path exists yet: `KNOWN_PROVIDERS` is `("shazam", "acrcloud")`
and the factory has no Spotify branch. Rate-limiter fields *are* already
present (`spotify_max_rpm`, `spotify_max_concurrent` in `config/base.py`),
but credentials are not — add them env-only
(`TRACKLISTIFY_SPOTIFY_CLIENT_ID`/`_SECRET`, read in
`providers/factory.py`), never as config-dataclass fields, following the
ACRCloud pattern.

## P3 — MusicBrainz link enrichment via ISRC (no auth, no key)

The cheapest breadth we can get, and the only option needing no
commercial relationship. We already extract `isrc` from Shazam; the
MusicBrainz `isrc/<isrc>?inc=url-rels` lookup is free, keyless, and
returns cross-platform URL relations — frequently including purchase and
streaming links across services we will never integrate directly.

Fits the same post-dedup hook as the Spotify item above, so build them
together if both are wanted. Rate limit is ~1 req/s with a required
descriptive `User-Agent` (they block generic agents), which is fine
against ~22 unique tracks but would not be against ~216 raw detections.

Coverage caveat worth measuring before committing: ISRC presence in
Shazam responses is good for label releases and patchy for the
white-label/promo end of a techno set, and MusicBrainz's own coverage of
underground electronic is thinner than its rock/pop catalog. Sample a
real tracklist's ISRC hit rate first — if it is low, this buys little.

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

## P3 — Beatport links: blocked on partner approval, not on code

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
and PKCE flow make it closer in shape to the Spotify *playlist export*
problem than to the simple client-credentials enrichment above.

## P3 — decide the `metadata` link schema before more platforms land

**Decided 2026-08-02 (unknown U4): nested `metadata.links`.** Specified in
`docs/dev/2026-08-02-spotify-link-enrichment-spec.md` unit E, which lands it
alongside the Spotify enrichment as this entry recommends. The flat keys are
removed rather than aliased, and `links.spotify` is canonical-only — the
Shazam-supplied search URLs keep distinct `spotify_search` / `deezer_search`
keys so a consumer can tell a resolved track link from a search. The rest of
this entry is retained as the rationale.

`Track.metadata` currently carries flat, per-platform keys: `shazam_url`,
`apple_music_id`, `spotify_search_url`, `deezer_search_url`. That is fine
at four and gets ugly at eight, and every consumer of the JSON has to
know each key by name.

Proposed, if a third link source is ever added:

```json
"metadata": {
  "isrc": "USABC1234567",
  "links": {"shazam": "...", "spotify": "...", "apple": "..."}
}
```

Cheap now, a consumer-visible migration later — `_save_json`'s output is
the public surface. Decide when the Spotify enrichment item lands, since
that is the change that would make it worth doing. Not worth churning the
schema for its own sake.

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

**Known limitation (narrowed, not fully fixed):** the matching rule is now
canonicalize-then-normalize (not exact-after-normalize): `_strip_title_variant`
drops non-distinguishing version/live tags (`(Mixed)`, `(Club Mix)`,
`(Extended Mix)`, `(Original Mix)`, `(Radio Edit)`, `(Radio Mix)`,
`(Extended)`, `(Original)`, `Live At …`, in both `(...)` and `[...]`) and
canonicalizes `feat.`/`ft.`/`featuring` markers to `feat` while keeping the
credited artist. The **specific** `"Berghain"` vs `"Berghain (Remix)"` case
this note cites **still will not merge**: `remix` is on the keep-list, and
the default is keep (anything unrecognized stays too). What *did* open up is
the allowlisted set — e.g. `Outside World` vs `Outside World (Club Mix)` now
merges. No fuzzy ratio is used; the keep-list beats a drop-list because
`(Someone Remix)` and a bare `(Remix)` must stay separate rows.

**Known over-merge (accepted, awaits more data):** two *named-different* live
recordings collapse because `Live At …` is a drop-prefix.
`Song (Live At Wembley 95)` and `Song (Live At Madison Square Garden 98)` by
the same artist both drop to `Song` and merge into one row (verified
end-to-end). The spec's `Live At …` case was bare-title-vs-live
(`Stereo Murder [Live At Tomorrowland]` vs `Stereo Murder`); it did not
consider live-vs-live with different venues. In a DJ-mix context two live
recordings 50s apart by the same artist are usually the same track Shazam
spelled differently, not two genuinely different plays — but two *named*
venues/years is a real over-merge class that can only be sized against real
output over time.

**By design (not a limitation):** the drop-exact version tags
(`(Original Mix)`, `(Radio Edit)`, `(Extended)`, `(Extended Mix)`, etc.) are
*deliberately* treated as non-distinguishing — the spec's premise is that
these are "usually the same recording under different Shazam spellings." So
`(Original Mix)` vs `(Radio Edit)`, or a bare title vs `(Original Mix)`,
merge by design. They are *sometimes* different masters; that is the accepted
cost of the allowlist, not an undocumented over-merge. Likewise the accepted
trade-off of treating `feat.` credits as distinguishing: a `feat. X` credit
and a `(Mixed)` tag of the *same* audio now separate (a visible duplicate —
the recoverable direction).

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
