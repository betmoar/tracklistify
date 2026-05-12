"""Tests for tracklistify.config.security."""

from tracklistify.config.security import is_sensitive_field


def test_is_sensitive_field_uppercase_envvar():
    """Regression: SENSITIVE_FIELDS contained uppercase entries (e.g. 'ACR_ACCESS_KEY')
    that could never match because the function lowercases the input. After the fix
    we keep only lowercase substrings; matching against either case works via the
    .lower() normalisation."""
    assert is_sensitive_field("ACR_ACCESS_KEY") is True
    assert is_sensitive_field("SPOTIFY_CLIENT_SECRET") is True
    assert is_sensitive_field("acr_access_key") is True
    assert is_sensitive_field("OUTPUT_DIR") is False
    assert is_sensitive_field("verbose") is False
