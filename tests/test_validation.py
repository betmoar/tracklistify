from pathlib import Path

from tracklistify.utils.validation import validate_input


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
