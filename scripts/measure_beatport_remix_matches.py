#!/usr/bin/env python3
"""Measure Beatport enrichment search-match remix accuracy (U15 acceptance test).

For each track that enriched via the Beatport **search** path, fetch the actual
Beatport record (by the track-id in the stored URL) and compare its `mix_name`
+ `bpm` to what Shazam identified and what we wrote. A mismatch means the
enrichment gate attached a *different remix's* metadata — distinct remixes are
separate Beatport catalog entries with different BPM/key/label/catalog#.

This is the acceptance test for backlog item **U15** (see docs/BACKLOG.md):
the enrichment title gate over-loosened and matched the wrong remix. Acceptance
criterion for a U15 fix: re-run this probe → 0 MISMATCH, with the recall bugs
(Adelphi show-ID, MEDUZA feat) and wrong-artist precision still passing in the
unit suite.

Usage:
    # Token is read from the run cache (beatport_token.json), or BP_ACCESS env:
    set -a && source .env && set +a
    uv run python scripts/measure_beatport_remix_matches.py

Scans every tracklist.json under .tracklistify/output/ for `beatport_match ==
"search"` entries. Hits the live Beatport catalog once per entry (paced ~2/s).
Read-only — fetches and compares, writes nothing.
"""

import asyncio
import glob
import json
import os
import re
import sys

import aiohttp

API = "https://api.beatport.com/v4"
# Defaults to the project's run cache; override with TRACKLISTIFY_OUTPUT_DIR.
OUTPUT_GLOB = os.environ.get(
    "TRACKLISTIFY_OUTPUT_DIR",
    ".tracklistify/output",
)
MIX_RE = re.compile(r"\(([^)]*)\)|\[([^\]]*)\]")


def _mix_tokens(title: str) -> list[str]:
    """Bracket contents (lowercased) of a title — the mix/credit info."""
    return [
        (m.group(1) or m.group(2) or "").strip().lower()
        for m in MIX_RE.finditer(title or "")
    ]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


async def _get_token() -> str:
    token = os.getenv("BP_ACCESS")
    if not token:
        cache = ".tracklistify/cache/beatport_token.json"
        if os.path.exists(cache):
            token = json.load(open(cache))["access_token"]
    if not token:
        sys.exit(
            "No Beatport token: set BP_ACCESS or run the provider once to cache "
            "beatport_token.json."
        )
    return token


async def main() -> None:
    token = await _get_token()

    # Collect every search-matched track across all output sets.
    suspects = []
    for folder in sorted(glob.glob(os.path.join(OUTPUT_GLOB, "*"))):
        path = os.path.join(folder, "tracklist.json")
        if not os.path.exists(path):
            continue
        data = json.load(open(path))
        tracks = data.get("tracks", data if isinstance(data, list) else [])
        for track in tracks:
            meta = track.get("metadata", {})
            if meta.get("beatport_match") != "search":
                continue
            url = (meta.get("links", {}) or {}).get("beatport", "")
            match = re.search(r"/track/[^/]+/(\d+)", url or "")
            if not match:
                continue
            suspects.append(
                {
                    "song": track.get("song_name", ""),
                    "shaz_mix": _mix_tokens(track.get("song_name", "")),
                    "wrote_bpm": meta.get("bpm"),
                    "bp_id": match.group(1),
                }
            )

    print(f"checking {len(suspects)} search-matches...\n")
    ok = wrong = 0
    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        for su in suspects:
            async with session.get(f"{API}/catalog/tracks/{su['bp_id']}/") as resp:
                rec = await resp.json() if resp.status == 200 else {}
            bp_mix = rec.get("mix_name", "")
            bp_bpm = rec.get("bpm")
            bp_mix_n = _norm(bp_mix)
            shaz_mixes = [_norm(x) for x in su["shaz_mix"]]
            mix_ok = (not shaz_mixes) or any(sm and sm in bp_mix_n for sm in shaz_mixes)
            bpm_match = su["wrote_bpm"] == bp_bpm
            verdict = "OK" if (mix_ok and bpm_match) else "MISMATCH"
            if verdict == "MISMATCH":
                wrong += 1
            else:
                ok += 1
            flag = "" if verdict == "OK" else "  <-- WRONG"
            print(
                f"{verdict:8} {su['song'][:34]:35} | "
                f"shaz_mix={str(su['shaz_mix'])[:22]:23} bp_mix={bp_mix[:24]:25} | "
                f"bpm wrote={su['wrote_bpm']} bp={bp_bpm}{flag}"
            )
            await asyncio.sleep(0.4)

    print(f"\nTOTAL search-matches: {len(suspects)}")
    print(f"OK (correct remix + bpm): {ok}")
    print(f"MISMATCH (wrong remix or bpm): {wrong}")


if __name__ == "__main__":
    asyncio.run(main())
