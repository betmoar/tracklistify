"""Live-network probes — opt-in via ``--live``, never run in CI (Q8).

These hit real external services with real credentials. They exist so a
developer can locally verify the pacing/regression shapes the cassette-locked
tests approximate, and to validate identification quality against a known set.
Run with::

    TRACKLISTIFY_MUSICBRAINZ_CONTACT=you@example.com \\
        uv run python -m pytest tests/test_live_probes.py --live -v

Without ``--live`` every test here is skipped (see conftest.py). CI never
passes ``--live``.
"""

import pytest

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_musicbrainz_live_resolves_a_known_isrc(monkeypatch):
    """MusicBrainz resolves a known-good ISRC to at least one streaming URL.

    This is the live counterpart to the cassette-locked 503-retry test: it
    confirms the provider resolves against the real API today. A failure here
    is either a real outage or a regression the cassette couldn't catch (a
    response-shape change). Not a gate — a manual signal.
    """
    import os

    if not os.getenv("TRACKLISTIFY_MUSICBRAINZ_CONTACT"):
        pytest.skip("TRACKLISTIFY_MUSICBRAINZ_CONTACT not set")

    from tracklistify.providers.musicbrainz import MusicBrainzProvider

    provider = MusicBrainzProvider()
    try:
        # Despacito — universally resolvable.
        links = await provider.lookup_isrc("USUM71703861")
        assert links, "MusicBrainz returned no links for a known-good ISRC"
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_youtube_download_still_works(tmp_path):
    """yt-dlp can still fetch audio bytes from YouTube today.

    This is the probe for the failure class in #91: the lock file drifts a
    month behind, YouTube retires the player client that version reaches
    for, and every download 403s. Nothing offline catches it -- the
    dependency resolves, imports, and passes its own tests; only the live
    fetch fails.

    Two things this probe has to get right, both learned by measuring
    rather than assuming:

    1. **It must download real bytes.** On the version that broke,
       metadata extraction SUCCEEDED and only the media fetch returned
       403. A probe that stops at ``extract_info`` reports green.

    2. **The video must be one that actually fails.** "Me at the zoo"
       (jNQXAC9IVRw) was the obvious pick -- 19 seconds, oldest video on
       the platform -- and it downloads fine on the BROKEN version. Short
       and old apparently means less aggressively protected. It would have
       been a probe that could never fail. This ID was verified to 403 on
       yt-dlp 2026.7.4 and to download on 2026.8.19.
    """
    import yt_dlp

    # Verified discriminating: 403 on 2026.7.4, 3.4 MB on 2026.8.19.
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(tmp_path / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    downloaded = list(tmp_path.iterdir())
    assert downloaded, (
        f"yt-dlp {yt_dlp.version.__version__} wrote no file. If the log "
        "above shows a 403, the pinned version is behind YouTube's current "
        "player clients -- run `uv lock --upgrade-package yt-dlp`."
    )
    # The audio stream is ~3.4 MB. Anything tiny is a truncated body or an
    # error page rather than audio.
    size = downloaded[0].stat().st_size
    assert size > 500_000, f"{downloaded[0].name} is only {size} bytes"


@pytest.mark.asyncio
async def test_youtube_js_challenge_solver_available():
    """The Deno-backed JS challenge solver is reachable.

    YouTube's signature / n-param challenges are solved by the yt-dlp-ejs
    scripts, which run inside Deno. Without a working Deno the newer
    clients fall back to paths that 403 -- the same symptom as a stale
    lock, but a different cause, so the two are worth separating.
    """
    import shutil
    import subprocess

    deno = shutil.which("deno")
    assert deno, (
        "deno is not on PATH. YouTube downloads need it for the yt-dlp-ejs "
        "signature solver (see CLAUDE.md)."
    )

    proc = subprocess.run(  # noqa: S603
        [deno, "--version"], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, f"deno --version failed: {proc.stderr}"
