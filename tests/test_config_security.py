"""Security tests for configuration loading and logging.

Tests for Phase 1 of implementation plan:
- Issue #1: Remove eval() from config loading
- Issue #2: Mask secrets in environment variable logging
"""

import pytest
import logging
from pathlib import Path
from tracklistify.config import TrackIdentificationConfig


class TestConfigSecurity:
    """Test security aspects of configuration loading."""

    def test_no_eval_in_codebase(self):
        """Ensure eval() is not used in config module."""
        config_file = Path("src/tracklistify/config/base.py")
        with open(config_file) as f:
            lines = f.readlines()

        # Check each line for eval() calls (excluding comments)
        for i, line in enumerate(lines, 1):
            # Remove comments
            code_part = line.split("#")[0]
            # Check for eval( in actual code
            if "eval(" in code_part:
                pytest.fail(
                    f"eval() found in config module at line {i}: {line.strip()}"
                )

    def test_malicious_code_execution_blocked(self, monkeypatch, clean_env):
        """Ensure malicious environment variables cannot execute code."""
        malicious_values = [
            "__import__('os').system('echo pwned')",
            "exec('print(1)')",
            "compile('x=1', '<string>', 'exec')",
            "__import__('subprocess').call(['ls'])",
            "open('/etc/passwd').read()",
        ]

        for malicious in malicious_values:
            monkeypatch.setenv("TRACKLISTIFY_SEGMENT_LENGTH", malicious)
            with pytest.raises(ValueError) as exc_info:
                TrackIdentificationConfig()
            assert "Invalid" in str(exc_info.value), (
                f"Expected ValueError for: {malicious}"
            )

    def test_valid_numeric_formats_accepted(self, monkeypatch, clean_env):
        """Ensure valid numeric formats still work."""
        valid_configs = [
            ("60", 60),
            ("120", 120),
            ("30", 30),
        ]

        for env_value, expected in valid_configs:
            monkeypatch.setenv("TRACKLISTIFY_SEGMENT_LENGTH", env_value)
            config = TrackIdentificationConfig()
            assert config.segment_length == expected, (
                f"Expected {expected}, got {config.segment_length}"
            )

    def test_valid_float_formats_accepted(self, monkeypatch, clean_env):
        """Ensure valid float formats work."""
        valid_configs = [
            ("0.8", 0.8),
            ("0.5", 0.5),
            ("1.0", 1.0),
        ]

        for env_value, expected in valid_configs:
            monkeypatch.setenv("TRACKLISTIFY_MIN_CONFIDENCE", env_value)
            config = TrackIdentificationConfig()
            assert config.min_confidence == expected, (
                f"Expected {expected}, got {config.min_confidence}"
            )

    def test_invalid_numeric_formats_rejected(self, monkeypatch, clean_env):
        """Ensure invalid numeric formats are rejected."""
        invalid_values = [
            "abc",
            "12.34.56",
            "1 + 1",  # Would work with eval
            "2 * 30",  # Would work with eval
            "sixty",
            "1e999",  # Too large
        ]

        for invalid in invalid_values:
            monkeypatch.setenv("TRACKLISTIFY_SEGMENT_LENGTH", invalid)
            with pytest.raises(ValueError) as exc_info:
                TrackIdentificationConfig()
            assert "Invalid" in str(exc_info.value), (
                f"Expected ValueError for: {invalid}"
            )

    def test_scientific_notation_not_needed(self, monkeypatch, clean_env):
        """Scientific notation should not be needed for our use case."""
        # We removed support for scientific notation since it's not needed
        # and could be a security concern
        monkeypatch.setenv("TRACKLISTIFY_SEGMENT_LENGTH", "1e2")
        with pytest.raises(ValueError):
            TrackIdentificationConfig()


class TestSecretMasking:
    """Test secret masking in logging."""

    def test_sensitive_keys_detected(self):
        """Ensure sensitive keys are detected."""
        from tracklistify.config.security import is_sensitive_key

        sensitive = [
            "TRACKLISTIFY_API_KEY",
            "TRACKLISTIFY_CLIENT_SECRET",
            "TRACKLISTIFY_PASSWORD",
            "TRACKLISTIFY_ACR_ACCESS_SECRET",
            "TRACKLISTIFY_SPOTIFY_TOKEN",
            "TRACKLISTIFY_SPOTIFY_CLIENT_SECRET",
            "TRACKLISTIFY_ACRCLOUD_ACCESS_KEY",
        ]

        for key in sensitive:
            assert is_sensitive_key(key), f"{key} should be sensitive"

    def test_non_sensitive_keys_not_masked(self):
        """Ensure non-sensitive keys are not masked."""
        from tracklistify.config.security import is_sensitive_key

        non_sensitive = [
            "TRACKLISTIFY_DEBUG",
            "TRACKLISTIFY_VERBOSE",
            "TRACKLISTIFY_SEGMENT_LENGTH",
            "TRACKLISTIFY_OUTPUT_DIR",
            "TRACKLISTIFY_CACHE_DIR",
            "TRACKLISTIFY_PRIMARY_PROVIDER",
        ]

        for key in non_sensitive:
            assert not is_sensitive_key(key), f"{key} should not be sensitive"

    def test_value_masking_correct_format(self):
        """Ensure values are masked correctly."""
        from tracklistify.config.security import mask_sensitive_value

        # Sensitive values with sufficient length
        assert (
            mask_sensitive_value("TRACKLISTIFY_API_KEY", "secret123456")
            == "sec*****456"
        )

        assert (
            mask_sensitive_value("TRACKLISTIFY_CLIENT_SECRET", "abcdefghijk")
            == "abc*****ijk"
        )

        # Short values
        assert mask_sensitive_value("TRACKLISTIFY_API_KEY", "short") == "***"

        assert mask_sensitive_value("TRACKLISTIFY_API_KEY", "1234567") == "***"

        # Non-sensitive values should not be masked
        assert mask_sensitive_value("TRACKLISTIFY_DEBUG", "true") == "true"

        assert mask_sensitive_value("TRACKLISTIFY_SEGMENT_LENGTH", "60") == "60"

    def test_no_secrets_in_logs(self, monkeypatch, caplog, clean_env):
        """Ensure secrets don't appear in actual logs."""
        from tracklistify.cli import load_environment_variables

        # Set up test environment
        test_secret = "super_secret_key_123456"
        monkeypatch.setenv("TRACKLISTIFY_SPOTIFY_CLIENT_SECRET", test_secret)
        monkeypatch.setenv("TRACKLISTIFY_DEBUG", "true")

        caplog.set_level(logging.DEBUG)

        # Create temporary .env file
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(f"TRACKLISTIFY_SPOTIFY_CLIENT_SECRET={test_secret}\n")
            f.write("TRACKLISTIFY_DEBUG=true\n")
            env_path = Path(f.name)

        try:
            # Load environment variables (should log masked values)
            load_environment_variables(env_path)

            # Check logs
            log_text = caplog.text

            # Secret should NOT appear in full
            assert test_secret not in log_text, "Secret exposed in logs!"

            # Masked value should appear
            assert "sup*****456" in log_text or "SPOTIFY_CLIENT_SECRET" in log_text, (
                "Masked value or key name should appear"
            )

            # Non-sensitive value should appear
            assert "true" in log_text, "Non-sensitive value should appear"

        finally:
            # Cleanup
            env_path.unlink()

    def test_empty_values_handled(self):
        """Test that empty/None values are handled."""
        from tracklistify.config.security import mask_sensitive_value

        assert mask_sensitive_value("TRACKLISTIFY_API_KEY", "") == "***"
        assert mask_sensitive_value("TRACKLISTIFY_DEBUG", "") == ""
