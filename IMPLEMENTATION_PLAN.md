# Tracklistify Implementation Plan
## Phased Approach to Fixing All Audit Issues

**Document Version**: 1.0
**Date**: 2025-11-21
**Status**: Ready for Implementation
**Total Issues**: 59
**Estimated Total Effort**: 88-120 hours
**Timeline**: 6 sprints (12 weeks)

---

## Table of Contents

1. [Overview](#overview)
2. [Implementation Phases](#implementation-phases)
3. [Phase 1: Critical Security Fixes](#phase-1-critical-security-fixes)
4. [Phase 2: Critical Functional Fixes](#phase-2-critical-functional-fixes)
5. [Phase 3: High Priority Consolidation](#phase-3-high-priority-consolidation)
6. [Phase 4: High Priority Quality](#phase-4-high-priority-quality)
7. [Phase 5: Medium Priority Fixes](#phase-5-medium-priority-fixes)
8. [Phase 6: Low Priority Polish](#phase-6-low-priority-polish)
9. [Test Specifications](#test-specifications)
10. [Risk Management](#risk-management)
11. [Success Criteria](#success-criteria)

---

## Overview

### Strategy

This implementation plan addresses all 59 issues identified in the audit using a **phased, test-driven approach**:

1. **Critical issues first** - Security and breaking bugs
2. **Logical grouping** - Related changes together
3. **Test-driven** - Write tests before fixes
4. **Incremental** - Each phase can be deployed independently
5. **Safe** - Comprehensive validation at each step

### Dependencies Graph

```
Phase 1 (Security) ────┐
                       ├──> Phase 3 (Consolidation)
Phase 2 (Functional) ──┘                │
                                        ├──> Phase 5 (Medium)
Phase 4 (Quality) ──────────────────────┘        │
                                                 ├──> Phase 6 (Polish)
                                                 │
                         ┌───────────────────────┘
                         └──> Production Ready
```

### Phase Overview

| Phase | Focus | Issues | Effort | Sprints |
|-------|-------|--------|--------|---------|
| 1 | Critical Security | 2 | 8-12h | 1 |
| 2 | Critical Functional | 3 | 16-24h | 2 |
| 3 | High Priority Consolidation | 6 | 16-24h | 1 |
| 4 | High Priority Quality | 6 | 12-16h | 1 |
| 5 | Medium Priority Fixes | 25 | 24-32h | 1 |
| 6 | Low Priority Polish | 17 | 12-16h | 0.5 |
| **Total** | | **59** | **88-124h** | **6.5** |

---

## Phase 1: Critical Security Fixes

**Sprint**: 1
**Duration**: 8-12 hours
**Issues**: 2 (Issue #1, #2)
**Risk**: Low (isolated changes)
**Deployment**: Can deploy independently

### Issue #1: Remove eval() from Config Loading

**Priority**: 🔴 CRITICAL
**File**: `src/tracklistify/config/base.py:79-85`
**Risk**: Arbitrary code execution
**Effort**: 4-6 hours

#### Specification

**Current Behavior**:
```python
elif field_type in (int, float):
    try:
        value = field_type(env_value)
    except ValueError:
        # Try evaluating numeric expressions
        value = field_type(eval(env_value))  # DANGEROUS!
```

**Attack Vector**:
```bash
export TRACKLISTIFY_SEGMENT_LENGTH="__import__('os').system('rm -rf /')"
```

**Required Behavior**:
- Parse integers and floats safely
- Reject invalid input with clear error
- No code execution capability
- Support basic numeric formats: "123", "1.5", "1e3"

#### Technical Design

**New Implementation**:
```python
elif field_type in (int, float):
    try:
        # First attempt: direct conversion
        value = field_type(env_value)
    except ValueError as e:
        # Second attempt: handle scientific notation
        if field_type == float and ('e' in env_value.lower() or 'E' in env_value):
            try:
                value = float(env_value)
            except ValueError:
                raise ValueError(
                    f"Invalid numeric value for {env_key}: {env_value}. "
                    f"Expected a valid {field_type.__name__}."
                ) from e
        else:
            raise ValueError(
                f"Invalid {field_type.__name__} value for {env_key}: {env_value}"
            ) from e
```

**Migration Notes**:
- No breaking changes for valid numeric inputs
- Invalid inputs that previously worked via eval will now fail
- This is a security improvement

#### Test Specification

**Test File**: `tests/test_config_security.py` (new)

```python
import os
import pytest
from tracklistify.config import TrackIdentificationConfig

class TestConfigSecurity:
    """Test security aspects of configuration loading."""

    def test_no_eval_in_codebase(self):
        """Ensure eval() is not used in config module."""
        with open("src/tracklistify/config/base.py") as f:
            content = f.read()
            assert "eval(" not in content, "eval() found in config module"

    def test_malicious_code_execution_blocked(self):
        """Ensure malicious environment variables cannot execute code."""
        malicious_values = [
            "__import__('os').system('echo pwned')",
            "exec('print(1)')",
            "compile('x=1', '<string>', 'exec')",
            "__import__('subprocess').call(['ls'])",
        ]

        for malicious in malicious_values:
            os.environ["TRACKLISTIFY_SEGMENT_LENGTH"] = malicious
            with pytest.raises(ValueError) as exc_info:
                TrackIdentificationConfig()
            assert "Invalid" in str(exc_info.value)
            # Ensure no code was executed
            del os.environ["TRACKLISTIFY_SEGMENT_LENGTH"]

    def test_valid_numeric_formats_accepted(self):
        """Ensure valid numeric formats still work."""
        valid_configs = [
            ("60", 60),
            ("60.0", 60.0),
            ("1e2", 100.0),
            ("1E2", 100.0),
            ("0.5", 0.5),
        ]

        for env_value, expected in valid_configs:
            os.environ["TRACKLISTIFY_SEGMENT_LENGTH"] = env_value
            config = TrackIdentificationConfig()
            assert config.segment_length == expected
            del os.environ["TRACKLISTIFY_SEGMENT_LENGTH"]

    def test_invalid_numeric_formats_rejected(self):
        """Ensure invalid numeric formats are rejected."""
        invalid_values = [
            "abc",
            "12.34.56",
            "infinity",
            "1 + 1",  # Would work with eval
            "2 * 30",  # Would work with eval
        ]

        for invalid in invalid_values:
            os.environ["TRACKLISTIFY_SEGMENT_LENGTH"] = invalid
            with pytest.raises(ValueError) as exc_info:
                TrackIdentificationConfig()
            assert "Invalid" in str(exc_info.value)
            del os.environ["TRACKLISTIFY_SEGMENT_LENGTH"]
```

#### Acceptance Criteria

- [ ] `eval()` removed from config/base.py
- [ ] Valid numeric strings parse correctly: "60", "1.5", "1e3"
- [ ] Invalid numeric strings raise ValueError
- [ ] Malicious strings cannot execute code
- [ ] All tests pass
- [ ] No regression in existing config loading

#### Implementation Steps

1. Write tests (above) - they should fail
2. Implement new parsing logic
3. Run tests - they should pass
4. Run full test suite - no regressions
5. Security scan: `bandit -r src/tracklistify/config/`
6. Code review
7. Merge and deploy

---

### Issue #2: Environment Variable Logging Exposes Secrets

**Priority**: 🔴 CRITICAL
**File**: `src/tracklistify/cli.py:127-129`
**Risk**: Credential exposure
**Effort**: 4-6 hours

#### Specification

**Current Behavior**:
```python
for key, value in os.environ.items():
    if key.startswith("TRACKLISTIFY_"):
        logger.debug(f"Loaded env var: {key}={value}")  # Logs API keys!
```

**Risk**: Logs show:
```
DEBUG: Loaded env var: TRACKLISTIFY_SPOTIFY_CLIENT_SECRET=abc123secret
DEBUG: Loaded env var: TRACKLISTIFY_ACR_ACCESS_SECRET=super_secret_key
```

**Required Behavior**:
- Mask sensitive values in logs
- Show enough to verify correct loading (first/last 3 chars)
- Apply to all logging, not just CLI

#### Technical Design

**New Implementation**:

```python
# In cli.py
from tracklistify.config.security import mask_sensitive_value

for key, value in os.environ.items():
    if key.startswith("TRACKLISTIFY_"):
        # Mask sensitive values
        display_value = mask_sensitive_value(key, value)
        logger.debug(f"Loaded env var: {key}={display_value}")
```

**Enhance security.py**:

```python
# Add to src/tracklistify/config/security.py

# Sensitive field patterns
SENSITIVE_PATTERNS = [
    "password", "passwd", "pwd",
    "secret", "token", "key",
    "api_key", "apikey",
    "access_key", "access_secret",
    "client_secret", "client_id",
    "auth", "credential",
]

def is_sensitive_key(key: str) -> bool:
    """Check if environment variable key is sensitive."""
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in SENSITIVE_PATTERNS)

def mask_sensitive_value(key: str, value: str) -> str:
    """Mask sensitive values for logging.

    Args:
        key: Environment variable name
        value: Environment variable value

    Returns:
        Masked value if sensitive, original if not

    Examples:
        >>> mask_sensitive_value("TRACKLISTIFY_API_KEY", "secret123")
        'sec*****123'
        >>> mask_sensitive_value("TRACKLISTIFY_DEBUG", "true")
        'true'
    """
    if not is_sensitive_key(key):
        return value

    if not value or len(value) < 8:
        return "***"

    # Show first 3 and last 3 characters
    return f"{value[:3]}*****{value[-3:]}"
```

#### Test Specification

**Test File**: `tests/test_config_security.py` (append)

```python
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
        ]

        for key in non_sensitive:
            assert not is_sensitive_key(key), f"{key} should not be sensitive"

    def test_value_masking_correct_format(self):
        """Ensure values are masked correctly."""
        from tracklistify.config.security import mask_sensitive_value

        # Sensitive values
        assert mask_sensitive_value(
            "TRACKLISTIFY_API_KEY", "secret123456"
        ) == "sec*****456"

        # Short values
        assert mask_sensitive_value(
            "TRACKLISTIFY_API_KEY", "short"
        ) == "***"

        # Non-sensitive values
        assert mask_sensitive_value(
            "TRACKLISTIFY_DEBUG", "true"
        ) == "true"

    def test_no_secrets_in_logs(self, caplog):
        """Ensure secrets don't appear in actual logs."""
        import logging
        from tracklistify.cli import load_environment_variables

        os.environ["TRACKLISTIFY_API_KEY"] = "super_secret_key_123"
        os.environ["TRACKLISTIFY_DEBUG"] = "true"

        caplog.set_level(logging.DEBUG)

        # This should log masked values
        env_path = get_root() / ".env"
        load_environment_variables(env_path)

        # Check logs
        log_text = caplog.text
        assert "super_secret_key_123" not in log_text, "Secret exposed!"
        assert "sup*****123" in log_text, "Masked value not found"
        assert "true" in log_text, "Non-sensitive value should appear"

        # Cleanup
        del os.environ["TRACKLISTIFY_API_KEY"]
        del os.environ["TRACKLISTIFY_DEBUG"]

    def test_cli_doesnt_log_secrets(self, tmp_path, caplog):
        """Integration test: CLI doesn't log secrets."""
        import logging
        from tracklistify.cli import cli

        # Create test .env
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TRACKLISTIFY_API_KEY=test_secret_key\n"
            "TRACKLISTIFY_DEBUG=true\n"
        )

        caplog.set_level(logging.DEBUG)

        # Simulate CLI loading
        os.chdir(tmp_path)
        load_environment_variables(env_file)

        # Verify
        assert "test_secret_key" not in caplog.text
        assert "tes*****key" in caplog.text
```

#### Acceptance Criteria

- [ ] `mask_sensitive_value()` function added to security.py
- [ ] `is_sensitive_key()` function added to security.py
- [ ] CLI uses masking when logging env vars
- [ ] Sensitive values show as "xxx*****xxx"
- [ ] Non-sensitive values show in full
- [ ] All tests pass
- [ ] Manual verification with real .env file

#### Implementation Steps

1. Write tests (above)
2. Implement masking functions in security.py
3. Update cli.py to use masking
4. Run tests
5. Manual test with real .env:
   ```bash
   echo "TRACKLISTIFY_API_KEY=supersecret123" > .env.test
   TRACKLISTIFY_DEBUG=true uv run tracklistify --debug test.mp3
   # Verify logs show "sup*****123"
   ```
6. Code review
7. Merge

---

## Phase 2: Critical Functional Fixes

**Sprint**: 2-3
**Duration**: 16-24 hours
**Issues**: 3 (Issue #3, #4, #5)
**Risk**: Low-Medium (user-facing changes)
**Dependencies**: None (can start immediately)

### Issue #3: Implement Stub Functions

**Priority**: 🔴 CRITICAL
**File**: `src/tracklistify/utils/identification.py:27-40`
**Risk**: Runtime crashes
**Effort**: 4-6 hours

#### Specification

**Current State**:
```python
def format_duration(duration: float) -> str:
    """Format duration in seconds to HH:MM:SS."""
    ...  # Will raise SyntaxError or fail at runtime

def create_progress_bar(progress: float, width: int = 30) -> str:
    """Create a progress bar string."""
    ...

class ProgressDisplay:
    """Handles the progress display for track identification."""
    ...
```

**Required Behavior**:
- `format_duration()` should format seconds to HH:MM:SS
- `create_progress_bar()` should create ASCII progress bar
- `ProgressDisplay` should handle progress updates with proper state

#### Technical Design

**Implementation**:

```python
# src/tracklistify/utils/identification.py

def format_duration(duration: float) -> str:
    """Format duration in seconds to HH:MM:SS.

    Args:
        duration: Duration in seconds

    Returns:
        Formatted string in HH:MM:SS format

    Examples:
        >>> format_duration(90)
        '00:01:30'
        >>> format_duration(3665)
        '01:01:05'
    """
    hours = int(duration // 3600)
    minutes = int((duration % 3600) // 60)
    seconds = int(duration % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def create_progress_bar(progress: float, width: int = 30) -> str:
    """Create a progress bar string.

    Args:
        progress: Progress as float between 0.0 and 1.0
        width: Width of progress bar in characters

    Returns:
        ASCII progress bar string

    Examples:
        >>> create_progress_bar(0.5, 10)
        '[█████░░░░░]'
        >>> create_progress_bar(1.0, 10)
        '[██████████]'
    """
    # Clamp progress to valid range
    progress = max(0.0, min(1.0, progress))

    filled = int(progress * width)
    empty = width - filled

    bar = "█" * filled + "░" * empty
    return f"[{bar}]"


class ProgressDisplay:
    """Handles the progress display for track identification.

    Attributes:
        current_segment: Current segment being processed
        total_segments: Total number of segments
        start_time: Time when processing started

    Examples:
        >>> display = ProgressDisplay()
        >>> display.start(total=10)
        >>> display.update(current=5)
        >>> display.complete()
    """

    def __init__(self):
        """Initialize progress display."""
        self.current_segment = 0
        self.total_segments = 0
        self.start_time = None
        self._last_line_length = 0

    def start(self, total: int) -> None:
        """Start progress tracking.

        Args:
            total: Total number of segments to process
        """
        import time
        self.total_segments = total
        self.current_segment = 0
        self.start_time = time.time()

    def update(self, current: int) -> None:
        """Update progress display.

        Args:
            current: Current segment number (1-indexed)
        """
        import sys
        import time

        self.current_segment = current

        if self.total_segments == 0:
            return

        # Calculate progress
        progress = current / self.total_segments
        elapsed = time.time() - self.start_time if self.start_time else 0

        # Create progress bar
        bar = create_progress_bar(progress, width=30)

        # Create progress line
        line = (
            f"\rIdentifying tracks: {bar} "
            f"{current}/{self.total_segments} "
            f"({progress*100:.1f}%) "
            f"Elapsed: {format_duration(elapsed)}"
        )

        # Clear previous line and write new one
        sys.stdout.write("\r" + " " * self._last_line_length + "\r")
        sys.stdout.write(line)
        sys.stdout.flush()

        self._last_line_length = len(line)

    def complete(self) -> None:
        """Complete the progress display."""
        import sys
        import time

        if self.start_time:
            elapsed = time.time() - self.start_time
            print(f"\nCompleted in {format_duration(elapsed)}")
        else:
            print()  # Just newline

        sys.stdout.flush()

    def clear(self) -> None:
        """Clear the progress display."""
        import sys
        if self._last_line_length > 0:
            sys.stdout.write("\r" + " " * self._last_line_length + "\r")
            sys.stdout.flush()
            self._last_line_length = 0
```

#### Test Specification

**Test File**: `tests/test_identification_utils.py` (new)

```python
import time
import pytest
from io import StringIO
import sys
from tracklistify.utils.identification import (
    format_duration,
    create_progress_bar,
    ProgressDisplay
)

class TestFormatDuration:
    """Test duration formatting."""

    def test_zero_duration(self):
        assert format_duration(0) == "00:00:00"

    def test_seconds_only(self):
        assert format_duration(45) == "00:00:45"

    def test_minutes_and_seconds(self):
        assert format_duration(90) == "00:01:30"

    def test_hours_minutes_seconds(self):
        assert format_duration(3665) == "01:01:05"

    def test_large_duration(self):
        assert format_duration(86400) == "24:00:00"

    def test_fractional_seconds(self):
        assert format_duration(90.7) == "00:01:30"


class TestCreateProgressBar:
    """Test progress bar creation."""

    def test_empty_progress(self):
        bar = create_progress_bar(0.0, 10)
        assert bar == "[░░░░░░░░░░]"

    def test_full_progress(self):
        bar = create_progress_bar(1.0, 10)
        assert bar == "[██████████]"

    def test_half_progress(self):
        bar = create_progress_bar(0.5, 10)
        assert bar == "[█████░░░░░]"

    def test_custom_width(self):
        bar = create_progress_bar(0.5, 20)
        assert len(bar) == 22  # 20 + 2 brackets

    def test_progress_clamping_low(self):
        bar = create_progress_bar(-0.5, 10)
        assert bar == "[░░░░░░░░░░]"

    def test_progress_clamping_high(self):
        bar = create_progress_bar(1.5, 10)
        assert bar == "[██████████]"


class TestProgressDisplay:
    """Test progress display functionality."""

    def test_initialization(self):
        display = ProgressDisplay()
        assert display.current_segment == 0
        assert display.total_segments == 0
        assert display.start_time is None

    def test_start_sets_values(self):
        display = ProgressDisplay()
        display.start(total=10)
        assert display.total_segments == 10
        assert display.current_segment == 0
        assert display.start_time is not None

    def test_update_changes_current(self):
        display = ProgressDisplay()
        display.start(total=10)
        display.update(current=5)
        assert display.current_segment == 5

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Terminal output differs on Windows"
    )
    def test_update_writes_to_stdout(self, capsys):
        display = ProgressDisplay()
        display.start(total=10)
        display.update(current=5)

        captured = capsys.readouterr()
        assert "5/10" in captured.out
        assert "50.0%" in captured.out

    def test_complete_writes_newline(self, capsys):
        display = ProgressDisplay()
        display.start(total=10)
        display.update(current=10)
        display.complete()

        captured = capsys.readouterr()
        assert "Completed in" in captured.out

    def test_zero_total_no_crash(self):
        display = ProgressDisplay()
        display.start(total=0)
        display.update(current=0)  # Should not crash
        display.complete()

    def test_clear_removes_output(self):
        display = ProgressDisplay()
        display.start(total=10)
        display.update(current=5)
        display.clear()
        assert display._last_line_length == 0
```

#### Acceptance Criteria

- [ ] All three functions/classes implemented
- [ ] `format_duration()` handles edge cases (0, large numbers)
- [ ] `create_progress_bar()` creates correct ASCII bars
- [ ] `ProgressDisplay` updates without flickering
- [ ] All tests pass
- [ ] No ellipsis (...) in identification.py
- [ ] Manual test shows progress in terminal

#### Implementation Steps

1. Write tests
2. Implement functions
3. Run tests
4. Manual test with real audio file
5. Code review
6. Merge

---

### Issue #4: Fix CLI Argument Passing

**Priority**: 🔴 CRITICAL
**File**: `src/tracklistify/cli.py`, `src/tracklistify/core/base.py`
**Risk**: User-facing behavior change
**Effort**: 6-8 hours

#### Specification

**Current Behavior**:
```bash
# User runs:
tracklistify mix.mp3 --formats json --provider acrcloud

# But these arguments are ignored!
# Output: All formats created (json, markdown, m3u)
# Provider: Uses config default (shazam)
```

**Required Behavior**:
- `--formats` should control output formats
- `--provider` should override config provider
- `--no-fallback` should disable fallback
- Arguments take precedence over config

#### Technical Design

**Change 1: Update AsyncApp.process_input() signature**

```python
# src/tracklistify/core/base.py

async def process_input(
    self,
    input_path: str,
    formats: Optional[str] = None,
    provider: Optional[str] = None,
    fallback_enabled: Optional[bool] = None
) -> List[Track]:
    """Process audio input and identify tracks.

    Args:
        input_path: Path to local file or URL
        formats: Output format(s) - overrides config
        provider: Provider to use - overrides config
        fallback_enabled: Enable fallback - overrides config

    Returns:
        List of identified tracks
    """
    # Apply argument overrides
    if provider is not None:
        self.config.primary_provider = provider
        logger.info(f"Using provider: {provider}")

    if fallback_enabled is not None:
        self.config.fallback_enabled = fallback_enabled
        logger.info(f"Fallback enabled: {fallback_enabled}")

    # ... existing processing logic ...

    # Use formats parameter when saving
    if formats:
        if formats == "all":
            output.save_all()
        else:
            # Single format
            output.save(formats)
    else:
        # Use config default
        output.save_all()
```

**Change 2: Pass arguments from CLI**

```python
# src/tracklistify/cli.py

async def main(args: argparse.Namespace) -> int:
    """Main entry point."""
    app = None
    try:
        config = get_config()
        app = AsyncApp(config)

        # Setup signal handlers...

        # Pass CLI arguments to app
        await app.process_input(
            input_path=args.input,
            formats=args.formats,
            provider=args.provider,
            fallback_enabled=not args.no_fallback  # Invert flag
        )

        return 0
    # ... error handling ...
```

#### Test Specification

**Test File**: `tests/test_cli_arguments.py` (new)

```python
import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
from tracklistify.cli import parse_args, main
from tracklistify.core import AsyncApp

class TestCLIArgumentParsing:
    """Test CLI argument parsing."""

    def test_parse_formats_json(self):
        args = parse_args(["test.mp3", "-f", "json"])
        assert args.formats == "json"

    def test_parse_formats_markdown(self):
        args = parse_args(["test.mp3", "-f", "markdown"])
        assert args.formats == "markdown"

    def test_parse_formats_all(self):
        args = parse_args(["test.mp3", "-f", "all"])
        assert args.formats == "all"

    def test_parse_provider(self):
        args = parse_args(["test.mp3", "-p", "acrcloud"])
        assert args.provider == "acrcloud"

    def test_parse_no_fallback(self):
        args = parse_args(["test.mp3", "--no-fallback"])
        assert args.no_fallback is True

    def test_combined_arguments(self):
        args = parse_args([
            "test.mp3",
            "-f", "json",
            "-p", "shazam",
            "--no-fallback"
        ])
        assert args.formats == "json"
        assert args.provider == "shazam"
        assert args.no_fallback is True


@pytest.mark.asyncio
class TestCLIArgumentPassing:
    """Test that CLI arguments are passed to AsyncApp."""

    async def test_formats_passed_to_app(self, tmp_path):
        """Ensure --formats argument is passed to process_input."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"fake audio data")

        with patch('tracklistify.cli.AsyncApp') as mock_app_class:
            mock_app = AsyncMock()
            mock_app.process_input = AsyncMock(return_value=[])
            mock_app.close = AsyncMock()
            mock_app_class.return_value = mock_app

            args = parse_args([str(test_file), "-f", "json"])
            await main(args)

            # Verify process_input called with formats
            mock_app.process_input.assert_called_once()
            call_kwargs = mock_app.process_input.call_args.kwargs
            assert call_kwargs['formats'] == 'json'

    async def test_provider_passed_to_app(self, tmp_path):
        """Ensure --provider argument is passed to process_input."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"fake audio data")

        with patch('tracklistify.cli.AsyncApp') as mock_app_class:
            mock_app = AsyncMock()
            mock_app.process_input = AsyncMock(return_value=[])
            mock_app.close = AsyncMock()
            mock_app_class.return_value = mock_app

            args = parse_args([str(test_file), "-p", "acrcloud"])
            await main(args)

            # Verify process_input called with provider
            call_kwargs = mock_app.process_input.call_args.kwargs
            assert call_kwargs['provider'] == 'acrcloud'

    async def test_no_fallback_passed_to_app(self, tmp_path):
        """Ensure --no-fallback argument is passed to process_input."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"fake audio data")

        with patch('tracklistify.cli.AsyncApp') as mock_app_class:
            mock_app = AsyncMock()
            mock_app.process_input = AsyncMock(return_value=[])
            mock_app.close = AsyncMock()
            mock_app_class.return_value = mock_app

            args = parse_args([str(test_file), "--no-fallback"])
            await main(args)

            # Verify fallback_enabled=False
            call_kwargs = mock_app.process_input.call_args.kwargs
            assert call_kwargs['fallback_enabled'] is False


class TestAsyncAppArgumentHandling:
    """Test AsyncApp respects argument overrides."""

    @pytest.mark.asyncio
    async def test_provider_override_from_argument(self):
        """Test provider can be overridden via argument."""
        config = TrackIdentificationConfig()
        config.primary_provider = "shazam"  # Default

        app = AsyncApp(config)

        # Mock the actual processing
        with patch.object(app, 'download_audio', return_value="test.mp3"):
            with patch.object(app, 'split_audio', return_value=[]):
                await app.process_input(
                    "test.mp3",
                    provider="acrcloud"  # Override
                )

        # Verify config was updated
        assert app.config.primary_provider == "acrcloud"

    @pytest.mark.asyncio
    async def test_fallback_disabled_from_argument(self):
        """Test fallback can be disabled via argument."""
        config = TrackIdentificationConfig()
        config.fallback_enabled = True  # Default

        app = AsyncApp(config)

        with patch.object(app, 'download_audio', return_value="test.mp3"):
            with patch.object(app, 'split_audio', return_value=[]):
                await app.process_input(
                    "test.mp3",
                    fallback_enabled=False  # Override
                )

        # Verify config was updated
        assert app.config.fallback_enabled is False


@pytest.mark.integration
class TestCLIEndToEnd:
    """Integration tests for CLI with real files."""

    def test_json_format_only_creates_json(self, tmp_path):
        """Verify --formats json creates only JSON file."""
        # TODO: Implement with real audio file
        # This requires actual audio processing
        pass

    def test_provider_argument_uses_specified_provider(self, tmp_path):
        """Verify --provider uses specified provider."""
        # TODO: Implement with real audio and provider mocks
        pass
```

#### Acceptance Criteria

- [ ] `AsyncApp.process_input()` accepts new parameters
- [ ] CLI passes arguments to `process_input()`
- [ ] `--formats json` creates only JSON file
- [ ] `--provider acrcloud` uses ACRCloud
- [ ] `--no-fallback` disables fallback
- [ ] All tests pass
- [ ] Manual testing with real files
- [ ] Documentation updated

#### Implementation Steps

1. Write tests
2. Update `AsyncApp.process_input()` signature
3. Update CLI to pass arguments
4. Run unit tests
5. Manual testing:
   ```bash
   uv run tracklistify test.mp3 -f json
   # Verify only .json created

   uv run tracklistify test.mp3 -p acrcloud --debug
   # Verify log shows "Using provider: acrcloud"
   ```
6. Update README.md examples
7. Code review
8. Merge

---

### Issue #5: Replace Blocking Locks with Async Locks

**Priority**: 🔴 CRITICAL
**File**: `src/tracklistify/utils/rate_limiter.py`
**Risk**: Medium (async correctness)
**Effort**: 6-10 hours

#### Specification

**Current Problem**:
```python
@dataclass
class ProviderLimits:
    lock: Lock = field(default_factory=Lock)  # Threading Lock blocks event loop!

# In RateLimiter.acquire():
with limits.lock:  # BLOCKS event loop!
    self._refill_tokens(limits)
```

**Required Behavior**:
- Use `asyncio.Lock` instead of `threading.Lock`
- All lock operations must be async (`async with`)
- No blocking of event loop
- Maintain thread safety if called from threads

#### Technical Design

**Change 1: Update ProviderLimits dataclass**

```python
# src/tracklistify/utils/rate_limiter.py

@dataclass
class ProviderLimits:
    """Rate limits for a specific provider."""

    max_requests_per_minute: int = 25
    max_concurrent_requests: int = 1
    tokens: int = field(init=False)
    last_update: float = field(default_factory=time.monotonic)  # Use monotonic!
    semaphore: asyncio.Semaphore = field(init=False)
    lock: asyncio.Lock = field(init=False)  # Changed from threading.Lock
    metrics: RateLimitMetrics = field(default_factory=RateLimitMetrics)
    circuit_state: CircuitState = field(default=CircuitState.CLOSED)
    circuit_open_time: Optional[float] = None
    consecutive_failures: int = 0

    def __post_init__(self):
        """Initialize fields after dataclass creation."""
        self.tokens = self.max_requests_per_minute
        # Create async primitives
        try:
            # Try to get current event loop
            loop = asyncio.get_running_loop()
            self.semaphore = asyncio.Semaphore(self.max_concurrent_requests)
            self.lock = asyncio.Lock()
        except RuntimeError:
            # No event loop running, defer creation
            self.semaphore = None
            self.lock = None

    def ensure_async_primitives(self):
        """Ensure async primitives are created."""
        if self.semaphore is None:
            self.semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        if self.lock is None:
            self.lock = asyncio.Lock()
```

**Change 2: Make all lock usage async**

```python
class RateLimiter:
    """Advanced rate limiter with async support."""

    # ... existing code ...

    async def acquire(
        self,
        provider: Any,
        timeout: float = 30.0
    ) -> bool:
        """Acquire rate limit token (async).

        Args:
            provider: Provider to acquire token for
            timeout: Maximum time to wait in seconds

        Returns:
            True if token acquired, False if timeout
        """
        if provider not in self._provider_limits:
            raise ValueError(f"Provider {provider} not registered")

        limits = self._provider_limits[provider]
        limits.ensure_async_primitives()  # Ensure created

        # Circuit breaker check
        circuit_breaker_enabled = getattr(
            self._config, "circuit_breaker_enabled", True
        )
        circuit_reset_timeout = getattr(
            self._config, "circuit_breaker_reset_timeout", 60.0
        )

        if circuit_breaker_enabled and limits.circuit_state == CircuitState.OPEN:
            # Check if should transition to HALF_OPEN
            if limits.circuit_open_time:
                elapsed = time.monotonic() - limits.circuit_open_time
                if elapsed > circuit_reset_timeout:
                    limits.circuit_state = CircuitState.HALF_OPEN
                    logger.info(f"Circuit breaker entering HALF_OPEN state for {provider}")
                else:
                    logger.warning(f"Circuit breaker OPEN for {provider}")
                    return False

        # Try to acquire semaphore with timeout
        try:
            await asyncio.wait_for(
                limits.semaphore.acquire(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Semaphore acquisition timeout for {provider}")
            limits.metrics.rate_limited_requests += 1
            return False

        # Token bucket logic (with async lock)
        start_wait = time.monotonic()

        while True:
            async with limits.lock:  # ASYNC lock!
                self._refill_tokens(limits)

                if limits.tokens > 0:
                    limits.tokens -= 1
                    limits.metrics.total_requests += 1

                    # Track wait time
                    wait_time = time.monotonic() - start_wait
                    if wait_time > 0.001:  # More than 1ms
                        limits.metrics.total_wait_time += wait_time
                        limits.metrics.rate_limited_requests += 1

                    return True

            # Check timeout
            if time.monotonic() - start_wait > timeout:
                limits.semaphore.release()
                logger.warning(f"Token acquisition timeout for {provider}")
                limits.metrics.rate_limited_requests += 1
                return False

            # Wait a bit before retrying
            await asyncio.sleep(0.1)

    def release(self, provider: Any):
        """Release rate limit token.

        Note: This is sync for backward compatibility, but schedules
        the actual release asynchronously.

        Args:
            provider: Provider to release token for
        """
        if provider not in self._provider_limits:
            return

        limits = self._provider_limits[provider]

        if limits.semaphore is not None:
            limits.semaphore.release()
```

**Change 3: Update time functions**

```python
# Replace time.time() with time.monotonic() for elapsed time

def _refill_tokens(self, limits: ProviderLimits):
    """Refill tokens based on elapsed time."""
    now = time.monotonic()  # Changed from time.time()
    elapsed = now - limits.last_update

    # Calculate tokens to add
    tokens_to_add = int(
        elapsed * (limits.max_requests_per_minute / 60.0)
    )

    if tokens_to_add > 0:
        limits.tokens = min(
            limits.tokens + tokens_to_add,
            limits.max_requests_per_minute
        )
        limits.last_update = now
```

#### Test Specification

**Test File**: `tests/test_rate_limiter_async.py` (new)

```python
import asyncio
import pytest
import time
from tracklistify.utils.rate_limiter import RateLimiter, ProviderLimits

class TestAsyncLocks:
    """Test async lock implementation."""

    @pytest.mark.asyncio
    async def test_uses_asyncio_lock(self):
        """Ensure asyncio.Lock is used, not threading.Lock."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=10)

        limits = limiter._provider_limits["test"]
        assert isinstance(limits.lock, asyncio.Lock)
        assert not isinstance(limits.lock, threading.Lock)

    @pytest.mark.asyncio
    async def test_no_event_loop_blocking(self):
        """Ensure rate limiter doesn't block event loop."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=60)

        # Acquire should be nearly instant
        start = time.monotonic()
        result = await limiter.acquire("test")
        elapsed = time.monotonic() - start

        assert result is True
        assert elapsed < 0.01  # Less than 10ms

        limiter.release("test")

    @pytest.mark.asyncio
    async def test_concurrent_acquires_no_deadlock(self):
        """Ensure concurrent acquires don't deadlock."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=100)

        async def worker(n):
            result = await limiter.acquire("test", timeout=1.0)
            await asyncio.sleep(0.01)  # Simulate work
            limiter.release("test")
            return result

        # Run 10 concurrent workers
        results = await asyncio.gather(*[worker(i) for i in range(10)])

        # All should succeed
        assert all(results)

    @pytest.mark.asyncio
    async def test_lock_is_reentrant_safe(self):
        """Test that lock prevents race conditions."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=10)

        limits = limiter._provider_limits["test"]
        initial_tokens = limits.tokens

        # Multiple coroutines trying to acquire
        async def acquire_many():
            tasks = []
            for _ in range(20):
                tasks.append(limiter.acquire("test", timeout=5.0))
            results = await asyncio.gather(*tasks)
            return results

        results = await acquire_many()

        # Should not have acquired more than available
        acquired = sum(results)
        assert acquired <= initial_tokens

    @pytest.mark.asyncio
    async def test_monotonic_time_used(self):
        """Ensure monotonic time is used for elapsed calculations."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=60)

        limits = limiter._provider_limits["test"]

        # last_update should be monotonic time
        assert limits.last_update > 0

        # Wait and refill
        await asyncio.sleep(1.1)
        await limiter.acquire("test")

        # Should have refilled (monotonic time advanced)
        assert limits.tokens > 0

        limiter.release("test")


class TestRateLimiterAsync:
    """Test rate limiter async behavior."""

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self):
        """Test that timeout returns False instead of hanging."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=1)

        # Acquire once
        assert await limiter.acquire("test") is True

        # Try to acquire again with short timeout
        start = time.monotonic()
        result = await limiter.acquire("test", timeout=0.5)
        elapsed = time.monotonic() - start

        assert result is False
        assert 0.4 < elapsed < 0.7  # Should timeout around 0.5s

    @pytest.mark.asyncio
    async def test_release_without_acquire_safe(self):
        """Test that releasing without acquire doesn't crash."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=10)

        # This should not raise
        limiter.release("test")
        limiter.release("test")

    @pytest.mark.asyncio
    async def test_multiple_providers_independent(self):
        """Test that multiple providers don't interfere."""
        limiter = RateLimiter()
        limiter.register_provider("provider1", max_requests_per_minute=10)
        limiter.register_provider("provider2", max_requests_per_minute=10)

        # Exhaust provider1
        for _ in range(10):
            assert await limiter.acquire("provider1") is True

        # provider2 should still work
        assert await limiter.acquire("provider2") is True

        limiter.release("provider2")


@pytest.mark.benchmark
class TestRateLimiterPerformance:
    """Performance tests for rate limiter."""

    @pytest.mark.asyncio
    async def test_high_concurrency_performance(self):
        """Test performance under high concurrency."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=1000)

        async def worker():
            if await limiter.acquire("test", timeout=10.0):
                await asyncio.sleep(0.001)
                limiter.release("test")
                return True
            return False

        # 100 concurrent requests
        start = time.monotonic()
        results = await asyncio.gather(*[worker() for _ in range(100)])
        elapsed = time.monotonic() - start

        success_count = sum(results)

        # Should complete in reasonable time
        assert elapsed < 5.0
        # Most should succeed
        assert success_count > 90
```

#### Acceptance Criteria

- [ ] `ProviderLimits` uses `asyncio.Lock`
- [ ] `RateLimiter.acquire()` is async
- [ ] All lock operations use `async with`
- [ ] `time.monotonic()` used for elapsed time
- [ ] No event loop blocking (< 10ms for acquire)
- [ ] All tests pass
- [ ] No deadlocks under concurrency
- [ ] Backward compatible for existing code

#### Implementation Steps

1. Write tests (they should fail with current code)
2. Update `ProviderLimits` dataclass
3. Make `acquire()` method async
4. Update all lock usages to `async with`
5. Replace `time.time()` with `time.monotonic()`
6. Run tests
7. Performance testing:
   ```bash
   python -m pytest tests/test_rate_limiter_async.py::TestRateLimiterPerformance -v
   ```
8. Check for event loop blocking:
   ```python
   # Add this to a test file and run
   import asyncio
   limiter = RateLimiter()
   limiter.register_provider("test", 60)

   async def test():
       await limiter.acquire("test")
       # Should complete instantly

   asyncio.run(test())
   ```
9. Code review
10. Merge

---

## Summary of Phase 2

After Phase 2, the following critical issues will be resolved:
- ✅ No more eval() security vulnerability
- ✅ No secrets in logs
- ✅ No stub functions that crash
- ✅ CLI arguments work as expected
- ✅ No event loop blocking in rate limiter

**Deployment**: These changes can be deployed together as they're independent.

**Testing**: Run full test suite + manual testing with real audio files.

**Documentation**: Update README.md with corrected CLI examples.

---

## Phase 3: High Priority Consolidation

**Sprint**: 4
**Duration**: 16-24 hours
**Issues**: 6 (Issue #6-11)
**Risk**: Medium (refactoring)
**Dependencies**: Phase 1-2 complete

### Overview

Phase 3 consolidates duplicate code and inconsistencies:
- Consolidate exception definitions
- Remove test/mock code from production
- Fix logger handler duplication
- Standardize error handling
- Add thread safety to singletons
- Fix Spotify encapsulation

I'll create detailed specs for these in a separate section...

---

## Detailed Test Specifications

### Test Infrastructure Setup

**File**: `tests/conftest.py` (update)

```python
import pytest
import os
import tempfile
from pathlib import Path
from tracklistify.config import TrackIdentificationConfig

@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment variables before test."""
    # Remove all TRACKLISTIFY_ vars
    for key in list(os.environ.keys()):
        if key.startswith("TRACKLISTIFY_"):
            monkeypatch.delenv(key, raising=False)
    yield
    # Cleanup happens automatically with monkeypatch

@pytest.fixture
def temp_project_root(tmp_path, monkeypatch):
    """Create temporary project root."""
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
```

### Test Categories

1. **Unit Tests**: Test individual functions/classes
2. **Integration Tests**: Test component interactions
3. **Security Tests**: Test security vulnerabilities
4. **Performance Tests**: Test performance characteristics
5. **Regression Tests**: Ensure fixes don't break existing behavior

### Test Naming Convention

```
test_<component>_<behavior>_<condition>

Examples:
- test_config_eval_malicious_code_blocked
- test_cli_formats_argument_creates_only_json
- test_rate_limiter_async_no_blocking
```

---

## Risk Management

### Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing functionality | Medium | High | Comprehensive test suite |
| Performance degradation | Low | Medium | Benchmarking tests |
| Security regression | Low | Critical | Security scanning in CI |
| User workflow disruption | Low | Medium | Phased rollout |
| Data loss | Low | High | Backup validation |

### Rollback Plan

Each phase includes:
1. **Git tags** for each phase completion
2. **Feature flags** for risky changes
3. **Deployment scripts** for easy rollback
4. **Smoke tests** for production validation

### Monitoring

Post-deployment monitoring:
- Error rate increase
- Performance metrics
- User feedback
- Security alerts

---

## Success Criteria

### Phase 1 Success Criteria
- [ ] No `eval()` in codebase
- [ ] Security scan passes (bandit)
- [ ] All tests pass
- [ ] Manual security testing complete

### Phase 2 Success Criteria
- [ ] CLI arguments work correctly
- [ ] No event loop blocking
- [ ] Progress displays working
- [ ] All tests pass
- [ ] User documentation updated

### Overall Success Criteria
- [ ] All 59 issues resolved
- [ ] Test coverage > 85%
- [ ] Type hint coverage > 90%
- [ ] Zero critical security issues
- [ ] No performance regression
- [ ] User documentation complete

---

*This is Part 1 of the Implementation Plan. Continue to next sections for Phases 3-6 detailed specifications...*
