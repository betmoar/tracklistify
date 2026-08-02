# Spec — Spotify canonical links + `metadata.links` schema

**Date:** 2026-08-02
**Backlog items:** `docs/BACKLOG.md` → "P2 — Spotify enrichment is built but
unreachable" and "P3 — decide the `metadata` link schema before more platforms
land" (unknown **U4**, decided here)
**Status:** specified, not implemented
**Required reading before implementing:** `docs/PLAYBOOKS.md` ("Add a config
option"), `docs/ARCHITECTURE.md` (invariant I6, load-bearing #2 and #5)

---

## Goal

Every unique track in `tracklist.json` carries a canonical
`https://open.spotify.com/track/<id>` link wherever one can be found, and
`Track.metadata` moves from flat per-platform keys to a nested `links` object
before a third link source lands.

### Why now, with numbers

Measured on a fresh-cache run, 2026-08-01, 20-track Tomorrowland set
(recorded in the backlog):

- Shazam supplied a Spotify *search* URL for **12/20** tracks. `hub.providers`
  is simply absent from ~40% of responses, and it varies between calls for the
  same audio.
- **7 of the 8** tracks missing a link **do carry an ISRC**.

An ISRC-first lookup therefore takes link coverage from 12/20 to roughly 19/20.
That is the concrete argument for building this.

`SpotifyProvider` already implements search and client-credentials auth; no
pipeline stage calls it. `_save_json` already emits `Track.metadata` per track
(`exporters/tracklist.py:159-167`, shipped 2026-08-01), so an enrichment hook is
visible without further exporter work.

## Non-goals

- **Playlist export / authorization-code + PKCE** (unknown U9).
  `exporters/spotify.py` calls `/me/playlists`, which a client-credentials token
  can never access. That is a feature project, not a drive-by.
- **MusicBrainz** (unknown U5 — gated on unmeasured coverage of
  underground-electronic ISRCs). The enricher is nonetheless shaped so a second
  source slots in later; see "Shape for a second source".
- **Adding `spotify` to `KNOWN_PROVIDERS`.** It has no `identify_track`, so
  `-p spotify` would crash and invariant I3 would fail.
- Rescuing or deleting `downloaders/spotify.py` (separate P3 item).
- Markdown / M3U rendering of metadata. Both build their own strings and ignore
  `metadata`; extend only if a user asks.
- Client-side scoring of fuzzy search results — see R7 for what replaces it.

---

## Requirements

Each is independently testable.

**R1.** `SpotifyProvider.search_track` returns `external_urls` and `isrc` in
addition to its current keys.

**R2.** `SpotifyProvider.search_by_isrc(isrc)` performs an exact ISRC lookup.

**R3.** `ProviderFactory.get_spotify_provider()` returns a configured provider,
or `None` when credentials are absent — it never raises for missing creds.

**R4.** `IdentificationManager` enriches unique tracks after dedup, ISRC-first
with a title/artist fallback.

**R5.** Enrichment never fails a run. Every error path leaves the identified
tracks intact and the run successful.

**R6.** Every rate-limiter `acquire` is matched by a `release` in a `finally`,
and every outcome is reported via `record_result`.

**R7.** Each enriched track records **how** it was matched
(`spotify_match: "isrc" | "search"`), and each run logs a summary count of
`isrc` / `search` / `none`.

**R8.** `Track.metadata` link keys move under a nested `links` object.

**R9.** Enrichment is gated by `enrichment_enabled` (default `true`) and is a
silent no-op when credentials are absent.

---

## Unit A — `search_track` returns the link fields

`src/tracklistify/providers/spotify.py:148-200`.

The return dict at lines 194–200 carries `spotify_id` but no `external_urls`.
`get_track_details` does have `external_urls` (line 227) but is the wrong route:
it names the id `id` rather than `spotify_id`, and it makes a second
`audio-features` request that Spotify deprecated for new apps in Nov 2024, so
it will 403 on any newly created client and the whole method re-raises.

Add to the returned dict:

```python
"external_urls": top.get("external_urls") or {},
"isrc": (top.get("external_ids") or {}).get("isrc"),
```

Use `.get()` for the new fields. The existing keys use bare subscripts
(`top["id"]`, `top["album"]["release_date"]`) outside the `try`, so a malformed
response already raises `KeyError`; do not widen that behavior, but do not
extend it to the new optional fields either.

Constraints:
- The `MetadataProvider` ABC signature (`providers/base.py:83-89`) must not
  change.
- `tests/test_spotify_encapsulation.py` asserts method names and parameter
  names by static analysis; adding return keys is safe, renaming is not.

## Unit B — `search_by_isrc`

New method on `SpotifyProvider`:

```python
async def search_by_isrc(self, isrc: str) -> Dict:
```

`GET search` with `params={"q": f"isrc:{isrc}", "type": "track", "limit": 1}`.
Returns the same dict shape as `search_track` (so the caller has one shape to
handle), or `{}` when there are no items.

Error posture identical to its neighbours: re-raise `RateLimitError` and
`AuthenticationError` unchanged, wrap everything else in `ProviderError`. Never
swallow them into a generic `except Exception` — callers lose retry-after
timing and 401-driven token refresh.

This is an exact lookup, not a fuzzy one. That distinction is the whole point
of preferring it (R7).

## Unit C — factory accessor

`src/tracklistify/providers/factory.py`.

```python
def get_spotify_provider(self) -> Optional["SpotifyProvider"]:
```

- Reads `TRACKLISTIFY_SPOTIFY_CLIENT_ID` and
  `TRACKLISTIFY_SPOTIFY_CLIENT_SECRET` via `os.getenv`, following the ACRCloud
  env-only pattern at `factory.py:73-97`. **Never** config-dataclass fields:
  `_load_from_env` (`config/base.py:54-104`) auto-maps every field to
  `TRACKLISTIFY_<UPPER>`, and dataclass fields leak through `repr()` and
  validation error messages.
- **Returns `None` when either credential is missing.** This is the one
  deliberate departure from the ACRCloud branch, which raises `ConfigError`:
  identification requires its provider, enrichment does not. Absent creds are a
  skip, not an error.
- Lazy-imports `SpotifyProvider` and caches the instance in `self.providers`
  under a key that cannot collide with an identification provider name, so the
  existing `close_all()` (`factory.py:106`) closes its aiohttp session. No new
  lifecycle code.
- `KNOWN_PROVIDERS` (`factory.py:17`) is **not** modified.

## Unit D — the hook

`src/tracklistify/utils/identification.py`.

Called from `identify_tracks` immediately after
`unique_tracks = self.track_matcher.get_unique_tracks()` (line 414):

```python
unique_tracks = self.track_matcher.get_unique_tracks()
await self._enrich_tracks(unique_tracks)
```

**Post-dedup by design.** A 3 h mix has ~216 raw detections but ~22 unique
tracks — a 10× cut in API calls — and it keeps the rate limiter out of the
identification hot path. The call site sits outside the `AsyncExitStack` that
wraps identification providers, so those are already closed; unrelated and
correct.

### Per-track algorithm

Sequential, not `gather` — the volume is ~22 and concurrency buys nothing worth
the added failure modes.

1. Skip if `track.metadata.get("links", {}).get("spotify")` is already set
   (idempotence; mirrors `enrich_metadata`'s own guard at `spotify.py:78`).
2. **ISRC path** — if `track.metadata.get("isrc")`, call `search_by_isrc`.
3. **Search path** — otherwise call
   `search_track(title=track.song_name, artist=track.artist)`.
   Use the **raw** `song_name`, i.e. what the provider returned. If
   `docs/dev/2026-08-02-dedup-title-variants-spec.md` has landed, its suffix
   stripping is comparison-only and must not be applied here.
4. On a hit, set:
   - `metadata["links"]["spotify"]` — prefer `result["external_urls"]["spotify"]`,
     else construct `f"https://open.spotify.com/track/{result['spotify_id']}"`
   - `metadata["spotify_id"]`
   - `metadata["spotify_match"] = "isrc"` or `"search"`
5. On no hit, leave the track untouched and count it as `none`.

`enrich_metadata` (`spotify.py:75-99`) is **not** used: it is keyed on
`title`/`artist` while a `Track` uses `song_name`, and it has no ISRC path. The
hook calls `search_by_isrc` / `search_track` directly.

### Match provenance (R7)

`spotify_match` is how unknown **U3** ("how often does fuzzy search return the
wrong track for underground techno?") gets answered without inventing a
scoring heuristic: an exact ISRC hit and a best-effort search hit are recorded
differently, so a consumer can see which links are trustworthy and the
wrong-match rate becomes auditable from real output rather than guessed.

The per-run summary log — counts of `isrc` / `search` / `none` — is the
instrumentation for unknowns **U1** (overall ISRC presence rate) and **U2**
(Spotify ISRC-lookup hit rate). Log at INFO when anything was enriched.

### Rate limiting

The wiring already exists: `spotify_max_rpm = 120` and
`spotify_max_concurrent = 20` (`config/base.py:230-232`) are consumed by
`RateLimiter.register_provider`, which already has a `spotify` branch
(`utils/rate_limiter.py:126-132`).

Follow the identification loop's pattern verbatim
(`identification.py:375-407`):

```python
acquired = False
try:
    acquired = await limiter.acquire("spotify")
    if not acquired:
        continue
    ...
    limiter.record_result("spotify", success=True)
except asyncio.CancelledError:
    raise
except Exception:
    limiter.record_result("spotify", success=False)
finally:
    if acquired:
        limiter.release("spotify")
```

Breaking the acquire/release pairing deadlocks every run after N requests
(ARCHITECTURE load-bearing #2). Skipping `record_result` means the circuit
breaker never learns and never opens (invariant I6).

Enter the provider as an async context manager (`async with provider:`) —
`MetadataProvider` defines `__aenter__`/`__aexit__` at `providers/base.py:113-117`,
and `close()` is documented re-entrable, so the later `close_all()` closing it
again is safe.

### Error handling (R5)

Same posture as the cache I/O at `identification.py:354-392`: best-effort,
degrade, never abort.

| Condition | Behavior |
|---|---|
| `AuthenticationError` | Warn once, disable enrichment for the remainder of the run |
| `RateLimitError` | Warn, stop enriching, return tracks enriched so far |
| Any other `Exception` | Debug log, continue to the next track |
| `asyncio.CancelledError` | Re-raise, never swallowed |
| No credentials | Debug log, return immediately, never touch the limiter |
| `enrichment_enabled` false | Return immediately |

### Config

New field on `TrackIdentificationConfig` (`config/base.py`):

```python
enrichment_enabled: bool = True
```

`true` is safe as a default because the feature is a no-op without credentials.

Per `docs/PLAYBOOKS.md` → "Add a config option":

1. Add the field with its default; `TRACKLISTIFY_ENRICHMENT_ENABLED` then works
   automatically.
2. Assign it to a new **"Metadata enrichment"** section in
   `scripts/generate_env_example.py::FIELD_SECTIONS`, with an `INLINE_COMMENTS`
   entry. Every public dataclass field must appear in exactly one section or the
   script and the CI `drift` job hard-fail.
3. Update `CREDENTIALS_BLOCK` in the same script — it currently tells readers
   the Spotify credentials are "consumed only by the UNWIRED Spotify
   downloader/exporter", which this change makes false.
4. Regenerate: `uv run python scripts/generate_env_example.py`.

Env-var truthiness is lowercase `true`/`false`.

### Shape for a second source

Structure `_enrich_tracks` so the per-source logic (resolve provider → look up
one track → write into `metadata["links"]`) is separable from the loop
scaffolding (gating, limiter pairing, error posture, summary counting). A
MusicBrainz enricher (unknown U5) then adds a source without touching the
scaffolding. Do not build an abstract base class or a registry for one
implementation — just keep the seam obvious.

## Unit E — `metadata.links` schema (decides U4)

In `_extra_metadata` (`utils/identification.py:81-123`), the single parse point
for provider extras.

```json
"metadata": {
  "isrc": "USABC1234567",
  "album": "...", "label": "...", "release_date": "...", "genres": ["..."],
  "shazam_id": "...", "apple_music_id": "...", "artwork_url": "...",
  "spotify_id": "...", "spotify_match": "isrc",
  "links": {
    "shazam": "...",
    "spotify": "https://open.spotify.com/track/...",
    "spotify_search": "...",
    "deezer_search": "..."
  }
}
```

Decisions:

- **`links.spotify` is canonical-only.** The Shazam-supplied search URLs keep
  distinct `spotify_search` / `deezer_search` keys rather than being conflated
  with a real track URL. A consumer must be able to tell "this resolves to the
  track" from "this runs a search".
- **Flat `shazam_url` / `spotify_search_url` / `deezer_search_url` are
  removed**, not aliased. Four flat keys is fine; eight is the problem the
  backlog flags, and migrating costs less now than after a third source lands.
- The existing falsy-drop at `identification.py:123` extends to dropping an
  empty `links` object, so a track with no links has no `links` key at all.
- **`apple_music_id` stays flat.** We hold an id, not a URL; this spec does not
  invent an Apple URL format.

Blast radius is small because `providers/shazam.py`'s payload keys
(`shazam.py:228-258`) are untouched — only the parse point changes.

Consumers to update:

- `tests/test_identification_utils.py:268,282` — asserts `spotify_search_url`
  survives `_extra_metadata`.
- `tests/test_providers_shazam.py` — the `spotify_search_url` assertions. Note
  `_web_search_url` and the provider payload keys themselves do not change.
- `docs/CHANGELOG.md` `[Unreleased]` — `tracklist.json` is the public surface,
  so this is a consumer-visible change and must be called out as such.
- `_save_json` (`exporters/tracklist.py:159-167`) emits `metadata` verbatim
  with `default=str` and needs **no** change.

---

## Tests

`tests/test_providers_spotify.py` mocks either by monkeypatching `_api_request`
(line 18) or, for `_api_request` itself, with a hand-rolled
`FakeResponse`/`FakeSession` injected over `_ensure_session` and
`_get_access_token` (lines 96-124). Never hit the network.

**Provider (Units A/B)**
1. `search_track` surfaces `external_urls` and `isrc`, and still returns `{}`
   on no items.
2. `search_track` tolerates a response with neither `external_urls` nor
   `external_ids`.
3. `search_by_isrc` sends `q=isrc:<isrc>`, `type=track`, `limit=1` — assert the
   captured params.
4. `search_by_isrc` re-raises `RateLimitError` and `AuthenticationError`
   unchanged.

**Factory (Unit C)**
5. Returns `None` with no creds (use `monkeypatch.delenv`), a `SpotifyProvider`
   with both set, and `None` when only one is set.
6. `"spotify" not in KNOWN_PROVIDERS`, and
   `tests/test_handoff_invariants.py` I3 still passes untouched.

**Hook (Unit D)**
7. ISRC path is preferred when `metadata["isrc"]` exists — assert
   `search_by_isrc` was called and `search_track` was not.
8. Search fallback is used when there is no ISRC.
9. `links["spotify"]` and `spotify_match` are set correctly on both paths, and
   `external_urls["spotify"]` wins over the constructed URL when present.
10. A track already carrying `links["spotify"]` is skipped.
11. No creds → no-op, and the rate limiter is never touched.
12. `enrichment_enabled = false` → no-op.
13. `RateLimitError`, `AuthenticationError`, and a generic `Exception` each
    leave `unique_tracks` intact and the run successful (R5).
14. The limiter is released on every path including each exception path (R6) —
    assert acquire/release call counts match.
15. The run summary reports the isrc/search/none counts (R7).

**Schema (Unit E)**
16. `_extra_metadata` emits nested `links` with the Shazam-supplied URLs under
    `shazam` / `spotify_search` / `deezer_search`.
17. `_extra_metadata` omits `links` entirely when no link is present.
18. `_save_json` round-trips a nested `links` object.

---

## Interaction with the dedup spec

`docs/dev/2026-08-02-dedup-title-variants-spec.md` strips non-distinguishing
title suffixes for **comparison only**. Enrichment therefore searches Spotify
with the raw `song_name`, never a stripped form. Both specs state this.

Order-independent: the dedup change only reduces the number of tracks reaching
this hook.

---

## Success criteria

1. All 18 tests pass; the full suite shows no new failures against the recorded
   baseline.
2. `uv run ruff check src/ tests/ scripts/`,
   `uv run ruff format --check src/ tests/ scripts/`, and
   `uv run python scripts/generate_env_example.py --check` all pass.
3. With no Spotify credentials set, a normal run's behavior and output are
   byte-identical to before the change apart from the `links` reshaping.
4. With credentials set, a real run reports the isrc/search/none summary, and
   `tracklist.json` carries `links.spotify` for the tracks that matched.
5. `KNOWN_PROVIDERS` is unchanged and no Spotify credential appears on any
   config dataclass.
