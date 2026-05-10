# Tracklistify Implementation Plan - Phases 3-6
## Continuation: Detailed Specifications

**Document Version**: 1.0
**Date**: 2025-11-21
**Parent Document**: IMPLEMENTATION_PLAN.md

---

## Phase 3: High Priority Consolidation

**Sprint**: 4
**Duration**: 16-24 hours
**Issues**: 6 (Issues #6-11)
**Risk**: Medium
**Dependencies**: Phases 1-2 complete

### Issue #6: Consolidate Exception Definitions

**Priority**: 🟠 HIGH
**Files**: Multiple
**Effort**: 4-6 hours

#### Specification

**Current State**: Exception classes defined in multiple places:
- `TrackIdentificationError`: `core/exceptions.py` AND `core/base.py`
- `ProviderError`: `core/exceptions.py` AND `providers/base.py`
- `ConfigError`: Multiple locations

**Problem**: `isinstance()` checks fail across modules.

**Required Behavior**:
- Single source of truth in `core/exceptions.py`
- All modules import from there
- No duplicate definitions

#### Technical Design

**Step 1**: Audit all exception definitions

```bash
# Find all custom exceptions
grep -r "class.*Error.*Exception" src/tracklistify/
```

**Step 2**: Keep only in `core/exceptions.py`, remove duplicates

```python
# src/tracklistify/core/exceptions.py (authoritative)

"""Exception hierarchy for Tracklistify.

All exceptions should inherit from TracklistifyError.
All modules should import from this file.
"""

# ... keep all existing exceptions ...

# Add any missing ones
class TimeoutError(TracklistifyError):
    """Operation timeout (Note: may shadow built-in in Python 3.11+)."""
    def __init__(self, message: str, timeout: float):
        super().__init__(message)
        self.timeout = timeout
```

**Step 3**: Update all imports

```python
# src/tracklistify/core/base.py
# REMOVE lines 418-430 (duplicate definitions)

# ADD imports at top
from tracklistify.core.exceptions import (
    TracklistifyError,
    TrackIdentificationError,
    ApplicationError,
    # ... etc
)

# src/tracklistify/providers/base.py
# REMOVE exception definitions

# ADD imports
from tracklistify.core.exceptions import (
    ProviderError,
    AuthenticationError,
    RateLimitError,
)

# src/tracklistify/config/factory.py
# REMOVE ConfigError definition

# ADD import
from tracklistify.core.exceptions import ConfigError
```

#### Test Specification

**Test File**: `tests/test_exception_consistency.py` (new)

```python
import pytest
import importlib
import inspect
from pathlib import Path
from tracklistify.core import exceptions as core_exceptions

class TestExceptionConsolidation:
    """Test that exceptions are defined only in core/exceptions.py."""

    def test_no_duplicate_exception_definitions(self):
        """Ensure no exception classes defined outside core/exceptions.py."""
        src_path = Path("src/tracklistify")

        # Files allowed to define exceptions
        allowed_files = {
            "src/tracklistify/core/exceptions.py",
        }

        # Find all Python files
        for py_file in src_path.rglob("*.py"):
            if str(py_file) in allowed_files:
                continue

            with open(py_file) as f:
                content = f.read()

            # Check for exception class definitions
            if "class" in content and "Error" in content and "Exception" in content:
                # Parse more carefully
                for line in content.split("\n"):
                    if line.strip().startswith("class") and "Error" in line:
                        # Check if it inherits from Exception or another Error
                        if "(Exception)" in line or "Error)" in line:
                            pytest.fail(
                                f"Duplicate exception definition in {py_file}: {line.strip()}"
                            )

    def test_all_modules_import_from_core_exceptions(self):
        """Ensure modules import exceptions from core.exceptions."""
        # Modules that should use exceptions
        modules_to_check = [
            "tracklistify.core.base",
            "tracklistify.providers.base",
            "tracklistify.providers.shazam",
            "tracklistify.providers.acrcloud",
            "tracklistify.config.factory",
        ]

        for module_name in modules_to_check:
            module = importlib.import_module(module_name)

            # Check if module uses any exception classes
            for name in dir(module):
                obj = getattr(module, name)
                if inspect.isclass(obj) and issubclass(obj, Exception):
                    if obj.__module__ != "tracklistify.core.exceptions":
                        # Exception from this module - might be duplicate
                        if obj.__module__ == module_name:
                            pytest.fail(
                                f"{module_name} defines exception {name} "
                                f"instead of importing from core.exceptions"
                            )

    def test_isinstance_works_across_modules(self):
        """Test that isinstance() works for imported exceptions."""
        from tracklistify.core.exceptions import ProviderError
        from tracklistify.providers.shazam import ShazamProvider

        # Create a ProviderError
        error = ProviderError("Test error", provider="shazam")

        # isinstance should work
        assert isinstance(error, ProviderError)
        assert isinstance(error, Exception)

    def test_exception_hierarchy_complete(self):
        """Test that all exceptions inherit from TracklistifyError."""
        from tracklistify.core.exceptions import TracklistifyError

        # Get all exception classes from core.exceptions
        for name in dir(core_exceptions):
            obj = getattr(core_exceptions, name)
            if inspect.isclass(obj) and issubclass(obj, Exception):
                if obj is TracklistifyError:
                    continue
                if obj.__module__ == "tracklistify.core.exceptions":
                    assert issubclass(obj, TracklistifyError), (
                        f"{name} should inherit from TracklistifyError"
                    )
```

#### Acceptance Criteria

- [ ] All exceptions in `core/exceptions.py`
- [ ] No duplicate exception definitions
- [ ] All modules import from core
- [ ] `isinstance()` checks work across modules
- [ ] All tests pass

---

### Issue #7: Remove Test/Mock Code from Production

**Priority**: 🟠 HIGH
**Files**: `core/track.py:116-124, 252-287`, `cache/base.py:60-66`
**Effort**: 2-3 hours

#### Specification

**Current State**:
```python
# core/track.py lines 116-124
def some_method(self):
    print("This is a method")  # Debug code!

# core/track.py lines 252-287
if file_path == "test_mix.mp3":
    return [...]  # Mock data

# cache/base.py lines 60-66
class MockConfig:  # In production!
    ...
```

**Required Behavior**: Delete all test/mock/debug code.

#### Technical Design

Simply delete the code:

```python
# core/track.py
# DELETE lines 116-124 entirely
# DELETE lines 252-287 entirely

# cache/base.py
# DELETE lines 60-66 (MockConfig class)
```

#### Test Specification

**Test File**: `tests/test_no_debug_code.py` (new)

```python
import pytest
from pathlib import Path

class TestNoDebugCode:
    """Ensure no debug/test/mock code in production."""

    def test_no_print_statements(self):
        """Ensure no print() statements in production code."""
        src_path = Path("src/tracklistify")

        # Allowed print statements (in CLI, dev tools)
        allowed_files = {
            "src/tracklistify/cli.py",
            "src/tracklistify/dev.py",
        }

        for py_file in src_path.rglob("*.py"):
            if str(py_file) in allowed_files:
                continue

            with open(py_file) as f:
                content = f.read()
                lines = content.split("\n")

                for i, line in enumerate(lines, 1):
                    if "print(" in line and not line.strip().startswith("#"):
                        pytest.fail(
                            f"print() statement found in {py_file}:{i}\n{line}"
                        )

    def test_no_mock_classes_in_production(self):
        """Ensure no Mock classes in production code."""
        src_path = Path("src/tracklistify")

        for py_file in src_path.rglob("*.py"):
            if "test" in str(py_file):
                continue

            with open(py_file) as f:
                content = f.read()

                if "class Mock" in content:
                    pytest.fail(f"Mock class found in production: {py_file}")

    def test_no_test_specific_conditions(self):
        """Ensure no test-specific if conditions."""
        src_path = Path("src/tracklistify")

        patterns = [
            'if file_path == "test',
            'if file == "test',
            'if input == "test',
        ]

        for py_file in src_path.rglob("*.py"):
            if "test" in str(py_file):
                continue

            with open(py_file) as f:
                content = f.read()

                for pattern in patterns:
                    if pattern in content:
                        pytest.fail(
                            f"Test-specific condition found in {py_file}: {pattern}"
                        )
```

#### Acceptance Criteria

- [ ] No `print()` in production code
- [ ] No `MockConfig` classes
- [ ] No test-specific conditions (e.g., `if file == "test_mix.mp3"`)
- [ ] All tests pass

---

### Issue #8: Fix Logger Handler Duplication

**Priority**: 🟠 HIGH
**File**: `src/tracklistify/utils/logger.py:78-89`
**Effort**: 2-3 hours

#### Specification

**Current Problem**:
```python
def set_logger(...):
    logger.addHandler(console_handler)  # Adds every call!
```

**Result**: Multiple calls create duplicate log entries.

**Required Behavior**: Clear existing handlers before adding new ones.

#### Technical Design

```python
# src/tracklistify/utils/logger.py

def set_logger(
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
    verbose: bool = False,
    debug: bool = False
):
    """Configure logging with console and optional file output.

    Args:
        log_level: Base log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        verbose: Enable verbose output
        debug: Enable debug output

    Note:
        This function can be called multiple times safely.
        Existing handlers will be removed before adding new ones.
    """
    # Get root logger
    logger = logging.getLogger()

    # CLEAR EXISTING HANDLERS (FIX!)
    logger.handlers.clear()

    # Determine effective log level
    if debug:
        base_level = logging.DEBUG
    elif verbose:
        base_level = logging.INFO
    else:
        base_level = getattr(logging, log_level.upper(), logging.INFO)

    logger.setLevel(base_level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(base_level)

    # Colored formatter
    formatter = ColoredFormatter(
        "%(levelname)s - %(name)s - %(message)s"
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        ))

        logger.addHandler(file_handler)

    return logger
```

#### Test Specification

**Test File**: `tests/test_logger.py` (update or create)

```python
import pytest
import logging
from pathlib import Path
from tracklistify.utils.logger import set_logger, get_logger

class TestLoggerConfiguration:
    """Test logger configuration."""

    def test_set_logger_clears_existing_handlers(self):
        """Test that set_logger clears existing handlers."""
        # First call
        set_logger(log_level="INFO")
        logger = logging.getLogger()
        handler_count_1 = len(logger.handlers)

        # Second call should not add more handlers
        set_logger(log_level="DEBUG")
        handler_count_2 = len(logger.handlers)

        assert handler_count_1 == handler_count_2, (
            "Handlers should not duplicate"
        )

    def test_no_duplicate_log_messages(self, caplog):
        """Test that log messages don't appear multiple times."""
        caplog.set_level(logging.INFO)

        # Configure logger multiple times
        set_logger(log_level="INFO")
        set_logger(log_level="INFO")
        set_logger(log_level="INFO")

        # Log a message
        logger = get_logger(__name__)
        logger.info("Test message")

        # Count occurrences
        message_count = sum(
            1 for record in caplog.records
            if "Test message" in record.message
        )

        assert message_count == 1, f"Message appeared {message_count} times"

    def test_file_handler_added_when_specified(self, tmp_path):
        """Test that file handler is added when log_file specified."""
        log_file = tmp_path / "test.log"

        set_logger(log_level="INFO", log_file=log_file)

        logger = logging.getLogger()

        # Should have console + file handlers
        assert len(logger.handlers) == 2

        # File should be created
        logger.info("Test message")
        assert log_file.exists()

    def test_file_handler_not_duplicated(self, tmp_path):
        """Test that file handler is not duplicated on multiple calls."""
        log_file = tmp_path / "test.log"

        set_logger(log_level="INFO", log_file=log_file)
        set_logger(log_level="INFO", log_file=log_file)
        set_logger(log_level="INFO", log_file=log_file)

        logger = logging.getLogger()

        # Should still have only 2 handlers
        assert len(logger.handlers) == 2

    def test_handler_cleanup_on_reconfigure(self, tmp_path):
        """Test that handlers are properly cleaned up."""
        log_file_1 = tmp_path / "test1.log"
        log_file_2 = tmp_path / "test2.log"

        # First configuration
        set_logger(log_level="INFO", log_file=log_file_1)
        assert len(logging.getLogger().handlers) == 2

        # Second configuration with different file
        set_logger(log_level="INFO", log_file=log_file_2)
        assert len(logging.getLogger().handlers) == 2

        # Log message should only go to test2.log
        logger = get_logger(__name__)
        logger.info("Test message")

        # test2.log should have message, test1.log should not
        assert log_file_2.exists()
        assert "Test message" in log_file_2.read_text()
```

#### Acceptance Criteria

- [ ] `set_logger()` clears existing handlers
- [ ] Multiple calls don't duplicate handlers
- [ ] Log messages appear only once
- [ ] File handlers properly cleaned up
- [ ] All tests pass

---

### Issues #9-11: Summary Specs

**Issue #9: Verbose Flag Default**
- **File**: `cli.py:104`
- **Fix**: Remove `default=True`
- **Test**: Verify verbose is False by default, True when flag set
- **Effort**: 30 minutes

**Issue #10: Downloader Error Handling**
- **Files**: `downloaders/mixcloud.py:104`, `ytdlp.py:216`
- **Fix**: Standardize on raising exceptions
- **Test**: Verify both raise DownloadError on failure
- **Effort**: 1-2 hours

**Issue #11: Spotify Encapsulation**
- **File**: `exporters/spotify.py:92-99`
- **Fix**: Add public methods to SpotifyProvider
- **Test**: Verify exporter uses public API only
- **Effort**: 3-4 hours

---

## Phase 4: High Priority Quality

**Sprint**: 5
**Duration**: 12-16 hours
**Issues**: 6 (Issues #12-17)
**Risk**: Low
**Dependencies**: Phase 3

### Issue #12: Thread-Safe Singletons

**Priority**: 🟠 HIGH
**Files**: Multiple factory files
**Effort**: 3-4 hours

#### Specification

**Current Problem**:
```python
_global_instance = None

def get_global_instance():
    global _global_instance
    if _global_instance is None:  # Race condition!
        _global_instance = SomeClass()
    return _global_instance
```

**Required Behavior**: Thread-safe initialization.

#### Technical Design

**Option 1: Double-checked locking**

```python
import threading

_global_instance = None
_lock = threading.Lock()

def get_global_instance():
    global _global_instance
    if _global_instance is None:
        with _lock:
            # Double-check inside lock
            if _global_instance is None:
                _global_instance = SomeClass()
    return _global_instance
```

**Option 2: functools.lru_cache (cleaner)**

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_global_instance():
    """Get global instance (thread-safe singleton)."""
    return SomeClass()
```

**Apply to**:
- `config/factory.py:get_config()`
- `cache/factory.py:get_cache()`
- `utils/rate_limiter.py:get_global_rate_limiter()`
- `providers/factory.py:create_provider_factory()`

#### Test Specification

```python
import pytest
import threading
from tracklistify.config import get_config
from tracklistify.cache import get_cache
from tracklistify.utils.rate_limiter import get_global_rate_limiter

class TestSingletonThreadSafety:
    """Test singleton pattern thread safety."""

    def test_get_config_thread_safe(self):
        """Test that get_config is thread-safe."""
        instances = []

        def worker():
            config = get_config()
            instances.append(id(config))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get same instance
        assert len(set(instances)) == 1

    def test_get_cache_thread_safe(self):
        """Test that get_cache is thread-safe."""
        instances = []

        def worker():
            cache = get_cache()
            instances.append(id(cache))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(instances)) == 1

    def test_rate_limiter_thread_safe(self):
        """Test that get_global_rate_limiter is thread-safe."""
        instances = []

        def worker():
            limiter = get_global_rate_limiter()
            instances.append(id(limiter))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(instances)) == 1
```

#### Acceptance Criteria

- [ ] All singletons use thread-safe pattern
- [ ] Concurrent access tests pass
- [ ] No race conditions
- [ ] Performance not degraded

---

## Phase 5: Medium Priority Fixes

**Sprint**: 6
**Duration**: 24-32 hours
**Issues**: 25 issues (summarized in groups)
**Risk**: Low
**Dependencies**: Phases 3-4

### Grouped Issues

**Group A: Time Handling (Issues #18-20)**
- Standardize on `time.monotonic()` for elapsed time
- Use `time.time()` only for absolute timestamps
- Update cache, rate limiter, metrics

**Group B: Empty Methods (Issues #21-22)**
- Implement or remove `_setup_validation()`, `_validate()`
- Document why empty if intentional

**Group C: Type Hints (Issues #23-25)**
- Fix `any` → `Any`
- Use consistent `Optional[X]` vs `X | None`
- Add missing return types

**Group D: Code Organization (Issues #26-30)**
- Move inline imports to module level
- Extract nested functions
- Remove unused variables

**Group E: Error Handling (Issues #31-35)**
- Add specific exception types
- Log before swallowing exceptions
- Improve error messages

**Group F: Validation (Issues #36-40)**
- Add input validation
- Check for None before access
- Validate ranges

**Group G: Resource Management (Issues #41-42)**
- Add cleanup methods
- Use context managers
- Close file handlers

### Example: Time Handling Consolidation

**Test Specification**:

```python
class TestTimeConsistency:
    """Test consistent time handling across codebase."""

    def test_cache_uses_monotonic_for_elapsed(self):
        """Cache should use monotonic time for TTL."""
        from tracklistify.cache.invalidation import TTLStrategy
        strategy = TTLStrategy(ttl=3600)

        # Verify it uses time.monotonic()
        # This is implementation verification
        import inspect
        source = inspect.getsource(strategy.should_invalidate)
        assert "time.monotonic" in source or "monotonic()" in source

    def test_rate_limiter_uses_monotonic(self):
        """Rate limiter should use monotonic for elapsed time."""
        from tracklistify.utils.rate_limiter import RateLimiter
        limiter = RateLimiter()
        limiter.register_provider("test", 60)

        limits = limiter._provider_limits["test"]

        # last_update should be monotonic time (always increasing)
        initial = limits.last_update
        time.sleep(0.1)
        limiter._refill_tokens(limits)

        # Should have increased
        assert limits.last_update > initial
```

---

## Phase 6: Low Priority Polish

**Sprint**: 6 (concurrent with Phase 5)
**Duration**: 12-16 hours
**Issues**: 17 issues
**Risk**: Very Low
**Dependencies**: None (can start anytime)

### Categories

1. **Code Style** (Issues #43-47)
   - Consistent string formatting
   - Import organization
   - Comment quality

2. **Magic Numbers** (Issues #48-50)
   - Extract to constants
   - Configuration

3. **Documentation** (Issues #51-55)
   - Add docstring examples
   - Improve error messages
   - Update README

4. **DRY Violations** (Issues #56-59)
   - Extract duplicate code
   - Create utility functions

### Test Strategy

For polish items, focus on:
- Code quality metrics (pylint, ruff)
- Documentation coverage
- Maintainability index

---

## Migration Guide

### For Developers

**After Phase 1-2** (Critical fixes):
```bash
# Update your branch
git pull origin main

# Re-run tests
uv run pytest

# Update environment variables (if using eval expressions)
# Change: TRACKLISTIFY_SEGMENT_LENGTH="2 * 30"
# To: TRACKLISTIFY_SEGMENT_LENGTH="60"

# Update code if using CLI programmatically
# Old: asyncio.run(app.process_input(path))
# New: asyncio.run(app.process_input(path, formats="json"))
```

**After Phase 3** (Consolidation):
```bash
# Update imports if you extended the codebase
# Old: from tracklistify.providers.base import ProviderError
# New: from tracklistify.core.exceptions import ProviderError

# Remove any references to removed debug code
```

### For Users

**Breaking Changes**:
1. CLI verbose flag now defaults to False (was True)
2. Environment variable eval no longer supported
3. Some internal APIs changed (only if you imported internals)

**New Features**:
1. CLI arguments now work as documented
2. Progress display during identification
3. Better error messages

---

## Deployment Strategy

### Stage 1: Canary Deployment
- Deploy to 5% of users
- Monitor for 48 hours
- Check error rates, performance

### Stage 2: Gradual Rollout
- Increase to 25% if Stage 1 successful
- Monitor for 24 hours
- Increase to 50%, then 100%

### Stage 3: Full Deployment
- Deploy to all users
- Monitor closely for first week
- Have rollback plan ready

---

## Validation Checklist

### Pre-Deployment
- [ ] All tests pass (unit, integration, security)
- [ ] Code review complete
- [ ] Security scan passes (bandit, safety)
- [ ] Performance benchmarks acceptable
- [ ] Documentation updated
- [ ] Migration guide complete
- [ ] Rollback plan documented

### Post-Deployment
- [ ] Smoke tests pass
- [ ] Error rate normal
- [ ] Performance metrics normal
- [ ] User feedback positive
- [ ] No security alerts
- [ ] Rollback tested

---

## Timeline and Resource Allocation

### Recommended Schedule

**Week 1-2** (Sprint 1):
- Phase 1: Critical Security (1 dev, full-time)

**Week 3-4** (Sprint 2):
- Phase 2: Critical Functional (1 dev, full-time)

**Week 5-6** (Sprint 3):
- Phase 3: High Priority Consolidation (1-2 devs)

**Week 7-8** (Sprint 4):
- Phase 4: High Priority Quality (1 dev)

**Week 9-10** (Sprint 5):
- Phase 5: Medium Priority (1-2 devs)

**Week 11-12** (Sprint 6):
- Phase 6: Low Priority Polish (1 dev, part-time)
- Buffer for unexpected issues

### Resource Requirements
- 1-2 developers
- Code reviewer
- QA/Testing support
- DevOps for deployment

---

## Success Metrics

### Code Quality Metrics

**Before Fixes**:
- Test coverage: ~75%
- Type hint coverage: ~70%
- Critical issues: 5
- High priority: 12
- Pylint score: ~7.5/10

**Target After All Fixes**:
- Test coverage: >85%
- Type hint coverage: >90%
- Critical issues: 0
- High priority: 0
- Pylint score: >9.0/10

### Validation Commands

```bash
# Coverage
uv run pytest --cov=tracklistify --cov-report=term-missing tests/
# Target: >85%

# Type checking
uv run mypy src/tracklistify/
# Target: 0 errors

# Security
uv run bandit -r src/tracklistify/
# Target: 0 high/medium issues

# Code quality
uv run pylint src/tracklistify/
# Target: Score >9.0

# Dead code
uv run vulture src/tracklistify/
# Target: <5% dead code
```

---

## Appendix: Complete Test Suite Structure

```
tests/
├── conftest.py                    # Shared fixtures
├── test_config_security.py        # Phase 1: Security tests
├── test_cli_arguments.py          # Phase 2: CLI tests
├── test_identification_utils.py   # Phase 2: Stub function tests
├── test_rate_limiter_async.py     # Phase 2: Async lock tests
├── test_exception_consistency.py  # Phase 3: Exception tests
├── test_no_debug_code.py          # Phase 3: Code cleanliness
├── test_logger.py                 # Phase 3: Logger tests
├── test_singleton_thread_safety.py # Phase 4: Thread safety
├── test_time_consistency.py       # Phase 5: Time handling
├── test_type_hints.py             # Phase 5: Type checking
└── integration/                   # Integration tests
    ├── test_end_to_end.py
    └── test_real_audio.py
```

---

*End of Implementation Plan - Phases 3-6*
*Total Document Pages: ~40*
*Total Estimated Effort: 88-124 hours*
*Timeline: 12 weeks with 1-2 developers*
