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
    sv = SecretVersion(
        value="abc123", created_at=datetime.now() - timedelta(days=45)
    )
    assert loader.needs_rotation(sv) is True
