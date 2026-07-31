"""Tests for Step 2: per-provider URL canonicalization for the download cache.

The download cache keys on a per-provider canonical ID (not the raw URL)
so that URL variants of the same media resolve to one cache entry. The
canonicalizer must be offline (no network) and deterministic.
"""

from tracklistify.downloaders.cache_key import canonicalize_url


class TestYouTubeCanonicalization:
    """All YouTube URL shapes for one video collapse to yt:<video_id>."""

    def test_watch_url(self):
        assert (
            canonicalize_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            == "yt:dQw4w9WgXcQ"
        )

    def test_short_url(self):
        assert canonicalize_url("https://youtu.be/dQw4w9WgXcQ") == "yt:dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert (
            canonicalize_url("https://www.youtube.com/shorts/dQw4w9WgXcQ")
            == "yt:dQw4w9WgXcQ"
        )

    def test_embed_url(self):
        assert (
            canonicalize_url("https://www.youtube.com/embed/dQw4w9WgXcQ")
            == "yt:dQw4w9WgXcQ"
        )

    def test_live_url(self):
        assert (
            canonicalize_url("https://www.youtube.com/live/dQw4w9WgXcQ")
            == "yt:dQw4w9WgXcQ"
        )

    def test_music_url(self):
        assert (
            canonicalize_url("https://music.youtube.com/watch?v=dQw4w9WgXcQ")
            == "yt:dQw4w9WgXcQ"
        )

    def test_extra_query_params_ignored(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120s&feature=share"
        assert canonicalize_url(url) == "yt:dQw4w9WgXcQ"

    def test_mobile_subdomain(self):
        assert (
            canonicalize_url("https://m.youtube.com/watch?v=dQw4w9WgXcQ")
            == "yt:dQw4w9WgXcQ"
        )

    def test_http_scheme(self):
        assert canonicalize_url("http://youtu.be/dQw4w9WgXcQ") == "yt:dQw4w9WgXcQ"

    def test_all_variants_collapse_to_same_key(self):
        variants = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/live/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=30s",
        ]
        keys = {canonicalize_url(v) for v in variants}
        assert keys == {"yt:dQw4w9WgXcQ"}, f"variants did not collapse: {keys}"


class TestSoundCloudCanonicalization:
    def test_basic_path(self):
        url = "https://soundcloud.com/user/track"
        assert canonicalize_url(url) == "sc:soundcloud.com/user/track"

    def test_www_stripped(self):
        url = "https://www.soundcloud.com/user/track"
        assert canonicalize_url(url) == "sc:soundcloud.com/user/track"

    def test_query_stripped(self):
        url = "https://soundcloud.com/user/track?in=user/sets/foo&t=120"
        assert canonicalize_url(url) == "sc:soundcloud.com/user/track"

    def test_trailing_slash_stripped(self):
        url = "https://soundcloud.com/user/track/"
        assert canonicalize_url(url) == "sc:soundcloud.com/user/track"

    def test_sets_path_preserved(self):
        """``/sets/`` URLs are a distinct cache key from the unwrapped track.

        Canonicalization is path-verbatim: the container URL
        ``user/sets/foo`` does not collapse to the track URL ``user/track``.
        This is intentional — the download cache is keyed on the original
        URL, and the downloader unwraps the container at fetch time (see
        test_ytdlp.py). A version stamp in the cache key material
        (cache/download.py) handles invalidation across metadata-shape
        changes rather than collapsing the URL here.
        """
        url = "https://soundcloud.com/user/sets/foo"
        assert canonicalize_url(url) == "sc:soundcloud.com/user/sets/foo"


class TestMixcloudCanonicalization:
    def test_basic_slug(self):
        url = "https://www.mixcloud.com/user/mix/"
        assert canonicalize_url(url) == "mc:user_mix"

    def test_url_encoded_slug(self):
        url = "https://www.mixcloud.com/user/my-mix-à/"
        # yt-dlp unquotes path segments; canonical form unquotes too.
        assert canonicalize_url(url) == "mc:user_my-mix-à"


class TestUnknownUrlFallback:
    def test_unknown_scheme_uses_raw_prefix(self):
        url = "https://example.com/some/audio.mp3"
        result = canonicalize_url(url)
        assert result.startswith("raw:"), f"unexpected canonical form: {result}"
