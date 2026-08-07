#!/usr/bin/env python3
"""Probe: MusicBrainz link-resolution rate (Q8 pacing-regression sentinel).

The 2026-08-04 pacing bug was an 8× yield regression (3% -> 25% Spotify links)
that every mocked test passed, because mocks can't reproduce MusicBrainz's
503-under-burst behavior. This probe measures the real resolution rate against
a set of known ISRCs so a regression in the pacing/retry logic shows up as a
dropped rate — the same signal the live verification caught the first time.

Usage:
    TRACKLISTIFY_MUSICBRAINZ_CONTACT="you@example.com" \
        uv run python scripts/probe_musicbrainz_link_rate.py

Logs each ISRC's outcome (resolved/none/error) and a summary line. A resolution
rate far below ~20% on this known-good set is the regression signature; record
the result in docs/BACKLOG.md. This is a manual probe, not a CI gate — it hits
the live MusicBrainz API.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Known-good ISRCs (popular tracks MusicBrainz resolves to streaming URLs).
# Curated so a healthy run resolves a majority; a pacing regression drops it.
SAMPLE_ISRCS = [
    "USUM71703861",  # Despacito
    "USUM71703861",
    "GBAYE0601498",  # Crazy (Gnarls Barkley)
    "USUM71406867",  # Uptown Funk (approx)
    "GBAYE0601302",
]


async def main() -> int:
    if not os.getenv("TRACKLISTIFY_MUSICBRAINZ_CONTACT"):
        print(
            "Set TRACKLISTIFY_MUSICBRAINZ_CONTACT=you@example.com first "
            "(MusicBrainz requires a contact UA).",
            file=sys.stderr,
        )
        return 2

    # Lazy import so the arg-check runs without the venv's deps on --help.
    from tracklistify.providers.musicbrainz import MusicBrainzProvider

    resolved = none = errors = 0
    provider = MusicBrainzProvider()
    try:
        for isrc in SAMPLE_ISRCS:
            try:
                links = await provider.lookup_isrc(isrc)
            except Exception as e:  # noqa: BLE001 — probe, report everything
                errors += 1
                print(f"{isrc}: ERROR {e}")
                continue
            if links:
                resolved += 1
                services = ",".join(sorted(links))
                print(f"{isrc}: resolved [{services}]")
            else:
                none += 1
                print(f"{isrc}: none")
            # Polite pacing (the probe itself must not become the burst).
            await asyncio.sleep(1.1)
    finally:
        await provider.close()

    total = len(SAMPLE_ISRCS)
    rate = resolved / total if total else 0.0
    print(
        f"\nMusicBrainz link rate: {resolved}/{total} resolved "
        f"({rate:.0%}), {none} none, {errors} error. "
        f"A healthy run resolves a majority; a pacing/retry regression "
        f"collapses this toward 0%."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
