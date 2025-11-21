"""
Tests for Issue #10: Downloader Error Handling

Validates that all downloaders raise exceptions on failure instead of returning None.
Uses static code analysis since ffmpeg may not be available in all environments.
"""

# Standard library imports
from pathlib import Path

# Third-party imports
import pytest


class TestDownloaderConsistency:
    """Test that all downloaders have consistent error handling."""

    def test_mixcloud_imports_download_error(self):
        """Test MixcloudDownloader imports DownloadError."""
        mixcloud_file = Path("src/tracklistify/downloaders/mixcloud.py")

        with open(mixcloud_file) as f:
            content = f.read()

        assert "from tracklistify.core.exceptions import DownloadError" in content, (
            "MixcloudDownloader should import DownloadError from core.exceptions"
        )

    def test_mixcloud_download_returns_str_not_optional(self):
        """Test MixcloudDownloader.download has correct return type."""
        mixcloud_file = Path("src/tracklistify/downloaders/mixcloud.py")

        with open(mixcloud_file) as f:
            content = f.read()

        # Should have return type annotation of str, not Optional[str]
        assert "async def download(self, url: str) -> str:" in content, (
            "MixcloudDownloader.download should return str, not Optional[str]"
        )

    def test_downloaders_raise_exceptions_not_return_none(self):
        """Verify download methods don't explicitly return None on error."""
        mixcloud_file = Path("src/tracklistify/downloaders/mixcloud.py")

        with open(mixcloud_file) as f:
            content = f.read()

        # Check for problematic pattern: catching exception and returning None
        # After the fix, this pattern should not exist in error handlers
        lines = content.split("\n")
        in_except_block = False
        for i, line in enumerate(lines):
            if "except" in line and "Exception" in line:
                in_except_block = True
            elif in_except_block:
                if line.strip().startswith("return None"):
                    pytest.fail(
                        f"mixcloud.py:{i+1} returns None in exception handler - should raise"
                    )
                # Exit except block on new function/class/unindented
                if line.strip() and not line.startswith(" ") and not line.startswith("\t"):
                    in_except_block = False

    def test_mixcloud_raises_download_error_on_failure(self):
        """Test that MixcloudDownloader raises DownloadError in error handlers."""
        mixcloud_file = Path("src/tracklistify/downloaders/mixcloud.py")

        with open(mixcloud_file) as f:
            content = f.read()

        # Check that DownloadError is raised in the exception handler
        assert "raise DownloadError(" in content, (
            "MixcloudDownloader should raise DownloadError on failure"
        )

    def test_ytdlp_raises_on_failure(self):
        """Test that YtDlpDownloader raises exceptions on failure."""
        ytdlp_file = Path("src/tracklistify/downloaders/ytdlp.py")

        with open(ytdlp_file) as f:
            content = f.read()

        # Check that it raises rather than returns None
        lines = content.split("\n")
        in_except_block = False
        for i, line in enumerate(lines):
            if "except" in line:
                in_except_block = True
            elif in_except_block:
                if "raise" in line:
                    # Good - it raises
                    break
                if line.strip().startswith("return None"):
                    pytest.fail(
                        f"ytdlp.py:{i+1} returns None in exception handler - should raise"
                    )
                if line.strip() and not line.startswith(" ") and not line.startswith("\t"):
                    in_except_block = False
