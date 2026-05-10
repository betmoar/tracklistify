"""Tests for tracklistify.config.security."""

from datetime import datetime, timedelta

from tracklistify.config.security import SecureConfigLoader, SecretVersion


def test_needs_rotation_true_when_older_than_interval():
    loader = SecureConfigLoader()
    sv = SecretVersion(
        value="abc123",
        created_at=datetime.now() - loader._rotation_interval - timedelta(days=1),
    )
    assert loader.needs_rotation(sv) is True


def test_needs_rotation_false_when_fresh():
    loader = SecureConfigLoader()
    sv = SecretVersion(value="abc123", created_at=datetime.now())
    assert loader.needs_rotation(sv) is False


def test_needs_rotation_respects_custom_interval():
    loader = SecureConfigLoader()
    loader._rotation_interval = timedelta(days=30)
    sv = SecretVersion(value="abc123", created_at=datetime.now() - timedelta(days=45))
    assert loader.needs_rotation(sv) is True


def test_is_sensitive_field_uppercase_envvar():
    """Regression: SENSITIVE_FIELDS contained uppercase entries (e.g. 'ACR_ACCESS_KEY')
    that could never match because the function lowercases the input. After the fix
    we keep only lowercase substrings; matching against either case works via the
    .lower() normalisation."""
    from tracklistify.config.security import is_sensitive_field

    assert is_sensitive_field("ACR_ACCESS_KEY") is True
    assert is_sensitive_field("SPOTIFY_CLIENT_SECRET") is True
    assert is_sensitive_field("acr_access_key") is True
    assert is_sensitive_field("OUTPUT_DIR") is False
    assert is_sensitive_field("verbose") is False
