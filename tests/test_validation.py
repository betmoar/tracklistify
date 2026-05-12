from pathlib import Path

from tracklistify.utils.validation import clean_url, validate_input


def test_http_url_valid():
    url = "https://example.com/watch?v=123"
    result = validate_input(url)
    assert result == (url, False)


def test_https_url_with_whitespace():
    url = "  https://example.com/path?q=1  "
    result = validate_input(url)
    assert result == (url.strip(), False)


def test_uppercase_scheme_url():
    url = "HTTP://example.com/resource"
    result = validate_input(url)
    # urlparse lower-cases scheme internally; we return original string
    assert result == (url, False)


def test_invalid_url_missing_netloc():
    assert validate_input("https:///just-path") is None
    assert validate_input("http:") is None


def test_non_string_or_empty():
    assert validate_input(None) is None
    assert validate_input("") is None
    assert validate_input("   ") is None


def test_local_file_valid(tmp_path: Path):
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"\x00\x01")
    validated_path, is_local = validate_input(str(f))
    assert is_local is True
    assert Path(validated_path).exists()
    assert Path(validated_path).is_file()
    # Should be absolute (resolved)
    assert Path(validated_path).is_absolute()


def test_local_file_nonexistent(tmp_path: Path):
    missing = tmp_path / "missing.mp3"
    assert validate_input(str(missing)) is None


def test_directory_is_not_file(tmp_path: Path):
    assert validate_input(str(tmp_path)) is None


def test_file_uri_valid(tmp_path: Path):
    f = tmp_path / "clip.wav"
    f.write_text("x")
    uri = f.as_uri()  # file://...
    validated_path, is_local = validate_input(uri)
    assert is_local is True
    assert Path(validated_path).resolve() == f.resolve()


def test_file_uri_nonexistent(tmp_path: Path):
    f = tmp_path / "nope.flac"
    uri = f.as_uri()
    assert validate_input(uri) is None


class TestCleanUrl:
    def test_strips_query_and_fragment(self):
        assert (
            clean_url("https://open.spotify.com/track/abc?si=xyz#frag")
            == "https://open.spotify.com/track/abc"
        )

    def test_lowercases_scheme_and_host(self):
        assert (
            clean_url("HTTPS://Open.Spotify.COM/track/abc")
            == "https://open.spotify.com/track/abc"
        )

    def test_strips_trailing_slash(self):
        assert (
            clean_url("https://open.spotify.com/track/abc/")
            == "https://open.spotify.com/track/abc"
        )

    def test_returns_empty_for_blank(self):
        assert clean_url("") == ""

    def test_returns_input_for_unparseable(self):
        assert clean_url("not a url") == "not a url"

    def test_strips_userinfo_credentials(self):
        """clean_url() output is frequently logged; never propagate
        ``user:pass@`` credentials into the normalized form."""
        assert (
            clean_url("https://alice:secret@youtube.com/watch?v=abc")
            == "https://youtube.com/watch"
        )

    def test_preserves_explicit_port(self):
        """Stripping userinfo must not also strip ports."""
        assert (
            clean_url("https://user:pw@host.example:8443/p")
            == "https://host.example:8443/p"
        )


class TestPlatformURLScheme:
    """Regression: _is_platform_url must reject non-HTTP(S) schemes."""

    def test_ftp_youtube_rejected(self):
        from tracklistify.utils.validation import is_youtube_url

        assert is_youtube_url("ftp://youtube.com/watch?v=abc") is False

    def test_file_uri_rejected(self):
        from tracklistify.utils.validation import is_youtube_url

        assert is_youtube_url("file:///etc/passwd") is False

    def test_javascript_scheme_rejected(self):
        from tracklistify.utils.validation import is_soundcloud_url

        assert is_soundcloud_url("javascript:alert(1)//soundcloud.com") is False

    def test_http_still_accepted(self):
        from tracklistify.utils.validation import is_youtube_url

        assert is_youtube_url("http://youtube.com/watch?v=abc") is True

    def test_https_still_accepted(self):
        from tracklistify.utils.validation import is_youtube_url

        assert is_youtube_url("https://www.youtube.com/watch?v=abc") is True
