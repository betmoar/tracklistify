# Beatport link + DJ-metadata enrichment — spec

**Date:** 2026-08-05
**Backlog item:** `docs/BACKLOG.md` → "P3 — Beatport links: blocked on partner
approval, not on code" (unknown **U8**)
**Status:** spec, pre-plan (Gate A)
**Tier:** L — new provider, new auth flow, new config surface, new enrichment
pass. ~5 plan tasks.

---

## 1. Goal

Add a third post-dedup enrichment source that resolves, per unique track:

- a canonical **Beatport track URL** (`metadata.links.beatport`), and
- the DJ-relevant fields Beatport has and Spotify/MusicBrainz do not:
  **BPM**, **musical key**, **label**, **genre / sub-genre**, **remixers**,
  **release date**, **catalog number**.

For techno / hard techno — this project's actual genre — that is the metadata a
DJ reading a tracklist wants, and Beatport's is materially better than
Spotify's.

## 2. What changed since the backlog entry said "do not build this"

The backlog blocked this on **U8: "Will Beatport grant partner access?"** and
explicitly said *"Do not ship the known workaround"* — the public client ID
that `beets-beatport4` reuses from Beatport's own swagger-ui frontend.

The decision taken on 2026-08-05 is narrower than the thing that was rejected,
and it is what this spec builds:

| Rejected in the backlog | What this spec does |
| --- | --- |
| Vendor a client ID in the repo (or scrape it from Beatport's docs page at runtime) so the feature "just works" for every user | **Ship no client ID and no scraper.** `TRACKLISTIFY_BEATPORT_CLIENT_ID` is required, has no default, and the source tree never contains the literal value |
| Present Beatport enrichment as a first-class always-on feature | **Opt-in, default off** (`beatport_enabled = false`), and a silent no-op when unconfigured |
| Ship Beatport access on the project's behalf | **The user supplies their own Beatport account and client ID.** Requests are made as that user, under their own relationship with Beatport |

During development the `beets-beatport4` client ID is used the same way any
user would use it: set in a local `.env`, never committed.

**Recorded caveat (not a blocker, per the 2026-08-05 decision):** the public
swagger-ui client ID is not an official self-serve credential, and Beatport
could invalidate it or object to its use at any time. The design contains that
risk rather than removing it — the credential is the user's to supply, the
feature is off by default, and every failure path degrades to a clean no-op
(§7). If partner access is ever granted (U8), only the credential source
changes; §4–§6 hold unchanged.

## 3. Requirements

Each is testable.

- **R1** — With `beatport_enabled = false` (the default), no Beatport code
  runs, no network request is made, and output is byte-identical to today.
- **R2** — With `beatport_enabled = true` but no `TRACKLISTIFY_BEATPORT_CLIENT_ID`
  in the environment, the pass logs one debug line and returns. Not an error,
  not a warning, no traceback — the Spotify-enrichment "absent creds are a
  skip" posture (`providers/factory.py::get_spotify_provider`).
- **R3** — Given a client ID plus **either** username+password **or** a pasted
  access token, the provider obtains a usable bearer token and authenticates
  API calls with it.
- **R4** — A matched track gains `metadata.links.beatport` (canonical
  `https://beatport.com/track/<slug>/<id>`) plus `beatport_id`, `bpm`,
  `key`, `label`, `genre`, `sub_genre`, `remixers`, `catalog_number`, and
  `beatport_match` provenance (`"isrc"` | `"search"`). Empty values are
  dropped, never stored as `None` (`_extra_metadata` convention).
- **R5** — A track is only written to when the match passes the acceptance
  gate in §5.3. A search result that fails the gate leaves the track
  untouched and counts as `none`.
- **R6** — `links.beatport` merges **first-writer-wins**: a URL MusicBrainz
  already resolved survives. The non-link fields (bpm/key/label/…) are written
  by this pass regardless, since no other source supplies them.
- **R7** — Best-effort, exactly as the two shipped sources: no Beatport
  failure — auth, transport, 4xx, 5xx, rate limit, malformed JSON — ever fails
  a run or loses an identified track.
- **R8** — Every `limiter.acquire("beatport")` is matched by a
  `release("beatport")` in `finally`, and every outcome is reported via
  `record_result` (invariant I6).
- **R9** — No Beatport secret (client ID, password, access token, refresh
  token, authorization code) is ever a config-dataclass field, and none
  appears in a log line at any level — including `--debug`. Account
  username/email are redacted in debug output.
- **R10** — The whole unit test suite runs offline: no test performs a network
  call or requires a Beatport account.

## 4. Non-goals

Struck deliberately; each would be its own item.

- **No album art** fetching/embedding (beets-beatport4 has it; we have no
  consumer for it).
- **No release/album import** — Beatport is consulted per identified *track*.
- **No client-ID scraping** from `api.beatport.com/v4/docs/`, and no vendored
  default value. See §2.
- **No Beatport as an identification provider.** It has no audio fingerprint
  API; it never enters `KNOWN_PROVIDERS` or the fallback chain.
- **No markdown / M3U output changes.** The new fields ride in
  `Track.metadata`, which `_save_json` already emits in full. Surfacing BPM
  and key in `tracklist.md` is a separate, easy follow-up once we have real
  output to look at.
- **No partner-portal application** and no PKCE authorization-code flow with a
  local redirect listener (that is the shape of the Spotify *playlist export*
  problem, U9).
- **No writes of any kind** — no cart, no playlist, no library mutation.
  Read-only catalog access.

## 5. Design

### 5.1 Components

```
utils/identification.py::IdentificationManager._enrich_tracks
    ├── _enrich_spotify      (shipped)
    ├── _enrich_musicbrainz  (shipped)
    └── _enrich_beatport     (NEW — unit C)
              │
              ▼
providers/factory.py::get_beatport_provider()   (NEW — unit B)
              │  reads env, returns None when unconfigured
              ▼
providers/beatport.py::BeatportProvider          (NEW — unit A)
    _authenticate() → bearer token
    lookup_isrc(isrc)         → dict | {}
    search_track(title, artist) → dict | {}
```

Unit boundaries mirror the MusicBrainz work exactly: the provider knows HTTP
and Beatport's payload shape and nothing about `Track`; the hook knows
`Track`, the limiter and the counters and nothing about Beatport's JSON. Two
existing sources plus this one is still not a registry — three sibling methods
sharing shape, per the charter (`_enrich_tracks` docstring).

### 5.2 Authentication (unit A)

All inputs are **env-only** (R9), following the ACRCloud rule:

| Env var | Required | Purpose |
| --- | --- | --- |
| `TRACKLISTIFY_BEATPORT_CLIENT_ID` | yes | OAuth client ID. No default shipped |
| `TRACKLISTIFY_BEATPORT_USERNAME` | one of the two paths | Beatport account |
| `TRACKLISTIFY_BEATPORT_PASSWORD` | with username | Beatport account |
| `TRACKLISTIFY_BEATPORT_TOKEN` | alternative path | Access token pasted from the browser |

**Path 1 — username + password** (verbatim from `beets-beatport4`'s
`Beatport4Client._authorize`, verified against the source on 2026-08-05):

1. `POST https://api.beatport.com/v4/auth/login/` with JSON
   `{"username": …, "password": …}` → session + CSRF cookies. A response body
   without `username`/`email` keys is an auth failure, even on HTTP 200.
2. `GET https://api.beatport.com/v4/auth/o/authorize/?response_type=code&client_id=<id>&redirect_uri=https://api.beatport.com/v4/auth/o/post-message/`
   with redirects **disabled** → the authorization code is the `code` query
   parameter of the `Location` header.
3. `POST https://api.beatport.com/v4/auth/o/token/?code=<code>&grant_type=authorization_code&redirect_uri=<same>&client_id=<id>`
   → `{"access_token", "expires_in", "refresh_token", …}`.

**Path 2 — pasted token:** `TRACKLISTIFY_BEATPORT_TOKEN` is used directly as
the bearer. No login, no password on disk. When it is expired or rejected
(401), and no username/password are configured, the pass warns **once** and
disables itself for the run (§7) with an actionable message naming the env var
and the devtools recipe.

**Token cache:** the obtained token is written to
`config.cache_dir / "beatport_token.json"` with mode `0600`, storing
`{access_token, refresh_token, expires_at}`. On the next run a non-expired
cached token skips the login entirely; expiry uses a 30 s safety buffer
(beets-beatport4's `TOKEN_EXPIRY_BUFFER_SECONDS`). The stored
`refresh_token` is kept but **not yet used**. The token file is validated as
an ordinary JSON dict — a corrupt or unreadable file is a cache miss, never an
exception (best-effort, R7).

**Amended 2026-08-05, after implementation.** Two behaviors this section
originally specified were cut during implementation rather than built. Recorded
here so nobody reads the spec and relies on them:

- *Refresh-token grant preferred over a full re-login* — **not implemented.**
  Whether the grant works at all with the swagger-ui client ID is exactly
  unknown U13, and building an unverifiable fallback path ahead of the
  measurement is speculation. An expired cached token falls straight through
  to the username/password flow, or (token-only mode) disables the pass with
  an actionable message. Revisit once U13 has an answer.
- *`GET /v4/my/account` probe before the first catalog call* — **not
  implemented.** It costs a request per run to learn what the first catalog
  call reveals anyway: a dead token returns 401, which clears the cached token
  and disables the pass. The redaction rule it carried still stands and is
  tested (`test_secrets_never_appear_in_logs`) — nothing logs an account
  username or email.

### 5.3 Matching and the acceptance gate

Beatport has no fingerprint; every match is by text or by ISRC. U3's lesson
(fuzzy search silently presenting the wrong track as fact) applies directly,
so provenance is recorded and a gate is mandatory.

1. **ISRC path (preferred, exact).** When `track.metadata["isrc"]` is present,
   `GET /v4/catalog/tracks/?isrc=<isrc>&per_page=1`. Beatport track objects do
   carry an `isrc` field; whether the list endpoint *filters* on it is
   **unverified** (unknown U11, §9) — the first plan task is a live probe. If
   the filter is unsupported the path is dropped and everything falls to (2)
   with no other design change.
   Provenance: `beatport_match = "isrc"`. No gate needed — an ISRC match is
   exact. As a cheap sanity check, a returned track whose own `isrc` differs
   from the queried one is rejected (guards against the endpoint silently
   ignoring an unsupported filter and returning an arbitrary page-1 track —
   the exact failure mode U11 is about).
2. **Search path (fallback, fuzzy).**
   `GET /v4/catalog/search/?q=<artist> <title>&type=tracks&per_page=5`.
3. **Acceptance gate (R5).** A search candidate is accepted only when **both**
   hold, reusing `core/track.py`'s existing comparison helpers
   (`_comparison_title`, `_artists_match`) so there is exactly one definition
   of "same title" and "same artist" in the codebase — the hook already
   imports from `core.track`:
   - `_comparison_title(candidate_title) == _comparison_title(track.song_name)`
     (that helper is `_normalize_token(_strip_title_variant(...))`, so it
     already canonicalizes `(Original Mix)` / `feat.` / bracket-suffix
     variants). Beatport splits a title into `name` plus a separate
     `mix_name`, so `candidate_title` is `f"{name} ({mix_name})"` when
     `mix_name` is present and is not `"Original Mix"`, else `name`;
   - `_artists_match(candidate_artists_joined, track.artist)` — the same
     token-set Jaccard `≥ _ARTIST_THRESHOLD` that dedup identity uses.
   Candidates are tested in API rank order; first acceptance wins, and a page
   where nothing is accepted counts as `none`.
   Provenance: `beatport_match = "search"`.

The gate deliberately trades recall for precision: a missing Beatport link is
invisible, a wrong BPM/key/label presented as fact is worse than no data for
someone building a set.

### 5.4 Field extraction (unit A)

From the v4 track object (shapes verified against `beets-beatport4`'s
`models.py`, 2026-08-05):

| Our key | Beatport field | Note |
| --- | --- | --- |
| `links.beatport` | `https://www.beatport.com/track/{slug}/{id}` | first-writer-wins (R6) |
| `beatport_id` | `id` | as `str` |
| `bpm` | `bpm` | `int` |
| `key` | `key.name` | Beatport's own spelling, verbatim — no Camelot conversion (non-goal) |
| `label` | `release.label.name` | only written when absent (Shazam may have set it) |
| `genre` / `sub_genre` | `genre.name` / `sub_genre.name` | strings, distinct from Shazam's `genres` list |
| `remixers` | `remixers[].name` | list of names |
| `catalog_number` | `release.catalog_number` | |
| `release_date` | `release.publish_date` | only written when absent |

All reads are defensive (`.get`, no bare subscripts): a payload shape change
yields fewer keys, never an exception (`_extra_metadata` convention).

### 5.5 Pacing and rate limiting

New limiter branch `beatport` in `utils/rate_limiter.py`, alongside `spotify`
and `musicbrainz`, reading `beatport_max_rpm` (default **60**) and
`beatport_max_concurrent` (default **1**).

Beatport publishes no official rate limit; community guidance is ~500 ms
between requests. Following the MusicBrainz lesson — where the token bucket's
full-bucket seed permitted a burst and cost an 8× yield regression that no
mocked unit test could catch — the hook paces explicitly at
`_BEATPORT_REQUEST_INTERVAL = 0.5` s between tracks, and that constant is
load-bearing, not decoration. At ~22 unique tracks that is ~11 s per run.

### 5.6 Ordering

`_enrich_tracks` runs Spotify → MusicBrainz → **Beatport**. Last, because it
is the only opt-in-by-default-off source and the only one that can be skipped
per-track: a track that already carries `links.beatport` (MusicBrainz resolved
it) still gets queried, because the API call is what supplies BPM/key/label —
the URL is the cheap part.

## 6. Configuration surface

Config dataclass (`config/base.py`) — **non-secret fields only**:

| Field | Default | Meaning |
| --- | --- | --- |
| `beatport_enabled` | `False` | Opt-in. §2 |
| `beatport_max_rpm` | `60` | limiter |
| `beatport_max_concurrent` | `1` | limiter; serialize |

Each needs a `FIELD_SECTIONS` entry in `scripts/generate_env_example.py`
(`beatport_enabled` under "Enrichment", the two limits under "Per-provider
rate limits") or the CI drift check fails. The four secrets are env-only and
appear in `.env.example` only as commented-out documentation, in the
credentials block next to Spotify's — including the one-paragraph explanation
of where a client ID comes from and the ToS caveat from §2.

## 7. Error handling

| Condition | Behavior |
| --- | --- |
| `beatport_enabled = false` | Pass not called at all (R1) |
| No client ID, or neither credential path configured | One `debug` line, return (R2) |
| Login rejected / 401 / token expired with no refresh path | One `warning` naming the env vars and the fix, `record_result(success=False)`, disable for the rest of the run (the `"disabled"` sentinel `_enrich_one` already uses) |
| 429 | `warning`, stop enriching, keep everything enriched so far |
| 5xx / transport error on one track | `debug`, count `none`, continue to the next track |
| Candidate fails the acceptance gate | Silent, count `none`, track untouched |
| Corrupt token cache file | Treated as a miss; re-authenticate |
| `asyncio.CancelledError` | Re-raised unchanged (never swallowed) |

Summary line at the end of a pass, mirroring the other two sources:
`Beatport enrichment: N tracks matched (isrc=…, search=…, none=…)`.

## 8. Testing

Offline (R10), `pytest-asyncio` strict, monkeypatching `_api_request` /
`_ensure_session` per the provider-test convention.

- `tests/test_providers_beatport.py` — auth flow against a fake session
  (login → authorize `Location` parse → token exchange), token-cache
  read/write/expiry/corruption, ISRC lookup hit + miss + wrong-ISRC rejection,
  search parse, field extraction from a captured payload fixture, missing-key
  degradation, 401/429/5xx mapping to `AuthenticationError` / `RateLimitError`
  / `ProviderError`.
- `tests/test_beatport_enrichment.py` — hook behavior: disabled → zero calls;
  no creds → no calls, no warning; gate accept/reject; first-writer-wins on
  `links.beatport`; `beatport_match` provenance; limiter acquire/release
  pairing and `record_result` on every path (R8); the `"disabled"` sentinel
  halting the loop; a raising provider leaves all tracks intact (R7).
- `tests/test_config.py` — the three new fields, env overrides, defaults.
- Secret hygiene: assert no secret value appears in `repr(config)` or in
  captured log output at debug level (R9).
- **Not covered by unit tests, and stated as such:** that the 0.5 s pacing is
  correct, and that the ISRC filter works (U11). Both need a live run against
  a real account, logged in the backlog like the MusicBrainz measurement was.

## 9. Success criteria and new unknowns

Ship criteria: R1–R10 hold, the suite is green against baseline, and one live
run against a real DJ mix produces a JSON tracklist whose Beatport-matched
tracks carry a URL that resolves to the right track and a BPM/key that match
the audio.

Measurements to record in `docs/BACKLOG.md` after that run (new unknowns,
resolved the way U1–U5 were):

- **U11** — Does `GET /v4/catalog/tracks/?isrc=` actually filter by ISRC?
  *(measurement; blocks §5.3 path 1; resolved by the plan's first probe task)*
- **U12** — Beatport match rate on underground techno, split isrc/search/none,
  compared against the ~23–25 % MusicBrainz Spotify-link rate.
  *(measurement)*
- **U13** — Real access-token lifetime, and whether the refresh-token grant
  works with the swagger-ui client ID or a full re-login is required every
  run. *(measurement — decides whether path 2 is a one-off paste or a chore)*

## 10. Assumptions

Stated rather than asked, per §2's decision:

1. The user supplies their own client ID; the repo ships none, and dev uses
   the `beets-beatport4` value from a local `.env` only.
2. Default is **off** — Beatport needs a personal account, unlike MusicBrainz.
3. Beatport's `key` is stored as Beatport spells it; no Camelot/OpenKey
   conversion.
4. BPM and key are **not** surfaced in `tracklist.md` in this change (§4);
   JSON carries them for free.
5. Enrichment stays post-dedup and sequential — ~22 tracks, no gather.

## 11. References

- `beets-beatport4` — <https://github.com/Samik081/beets-beatport4>
  (auth flow, endpoint shapes, and field mappings in §5.2/§5.4 were read from
  `beetsplug/beatport4/{client,models,constants}.py` on 2026-08-05)
- Beatport v4 API docs — <https://api.beatport.com/v4/docs/>
- `docs/PLAYBOOKS.md` → "Add a provider", "Add a config option"
- Prior art in this repo: `docs/dev/2026-08-04-musicbrainz-enrichment-spec.md`
  (local-only), `providers/musicbrainz.py`, `utils/identification.py`
