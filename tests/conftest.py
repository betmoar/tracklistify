"""Pytest configuration and shared fixtures."""

import pytest
import os
from pathlib import Path
from tracklistify.config import TrackIdentificationConfig
from tracklistify.config.paths import get_root


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment variables before test.

    Removes all TRACKLISTIFY_ environment variables to ensure
    clean test state.
    """
    # Remove all TRACKLISTIFY_ vars
    for key in list(os.environ.keys()):
        if key.startswith("TRACKLISTIFY_"):
            monkeypatch.delenv(key, raising=False)
    yield
    # Cleanup happens automatically with monkeypatch


@pytest.fixture
def temp_project_root(tmp_path, monkeypatch):
    """Create temporary project root for testing."""
    monkeypatch.setenv("TRACKLISTIFY_PROJECT_ROOT", str(tmp_path))
    yield tmp_path


@pytest.fixture
def mock_config():
    """Create mock configuration for testing."""
    config = TrackIdentificationConfig()
    config.segment_length = 60
    config.min_confidence = 0.8
    return config


@pytest.fixture
def sample_audio_file(tmp_path):
    """Create a sample audio file for testing."""
    audio_file = tmp_path / "test.mp3"
    # Create fake MP3 file (minimal valid MP3 header)
    audio_file.write_bytes(
        b'\xff\xfb\x90\x00'  # MP3 header
        + b'\x00' * 1000     # Data
    )
    return audio_file
