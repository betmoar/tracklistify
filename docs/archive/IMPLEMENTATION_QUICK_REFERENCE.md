# Implementation Quick Reference Guide

**For**: Tracklistify Code Fixes
**Total Issues**: 59
**Timeline**: 12 weeks
**Effort**: 88-124 hours

---

## Quick Start

### For Developers Starting Implementation

1. **Read the audit report first**: `AUDIT_REPORT.md`
2. **Review full plan**: `IMPLEMENTATION_PLAN.md` + `IMPLEMENTATION_PLAN_PHASES_3_6.md`
3. **Start with Phase 1**: Critical security fixes
4. **Write tests first**: TDD approach for all fixes
5. **Validate after each fix**: Run test suite

---

## Phase Summary

| Phase | Issues | Effort | Priority | Can Start |
|-------|--------|--------|----------|-----------|
| 1 | 2 | 8-12h | 🔴 Critical Security | ✅ Now |
| 2 | 3 | 16-24h | 🔴 Critical Functional | ✅ Now |
| 3 | 6 | 16-24h | 🟠 High Consolidation | After 1-2 |
| 4 | 6 | 12-16h | 🟠 High Quality | After 3 |
| 5 | 25 | 24-32h | 🟡 Medium | After 3-4 |
| 6 | 17 | 12-16h | 🟢 Low Polish | Anytime |

---

## Critical Issues (Do First!)

### 1. Remove eval() - SECURITY CRITICAL
- **File**: `src/tracklistify/config/base.py:85`
- **Risk**: Arbitrary code execution
- **Test**: `tests/test_config_security.py`
- **Time**: 4-6 hours

```bash
# Validation
uv run bandit -r src/tracklistify/config/
uv run pytest tests/test_config_security.py
```

### 2. Mask Secrets in Logs - SECURITY CRITICAL
- **File**: `src/tracklistify/cli.py:127-129`
- **Risk**: Credential exposure
- **Test**: `tests/test_config_security.py::TestSecretMasking`
- **Time**: 4-6 hours

```bash
# Validation
# Check logs don't contain API keys
uv run tracklistify --debug test.mp3 2>&1 | grep -i "secret"
```

### 3. Implement Stub Functions - BREAKING
- **File**: `src/tracklistify/utils/identification.py:27-40`
- **Risk**: Runtime crashes
- **Test**: `tests/test_identification_utils.py`
- **Time**: 4-6 hours

### 4. Fix CLI Arguments - BREAKING
- **Files**: `cli.py`, `core/base.py`
- **Risk**: User expectations
- **Test**: `tests/test_cli_arguments.py`
- **Time**: 6-8 hours

### 5. Async Locks - BREAKING
- **File**: `src/tracklistify/utils/rate_limiter.py`
- **Risk**: Event loop blocking
- **Test**: `tests/test_rate_limiter_async.py`
- **Time**: 6-10 hours

---

## Test Files to Create

### Phase 1-2 Tests (Critical)
```bash
touch tests/test_config_security.py
touch tests/test_cli_arguments.py
touch tests/test_identification_utils.py
touch tests/test_rate_limiter_async.py
```

### Phase 3 Tests (High Priority)
```bash
touch tests/test_exception_consistency.py
touch tests/test_no_debug_code.py
touch tests/test_logger.py
```

### Phase 4 Tests (Quality)
```bash
touch tests/test_singleton_thread_safety.py
touch tests/test_time_consistency.py
```

---

## Pre-Implementation Checklist

Before starting any fix:

- [ ] Read the issue specification in implementation plan
- [ ] Understand the current behavior
- [ ] Write failing tests first (TDD)
- [ ] Implement the fix
- [ ] Run tests until they pass
- [ ] Run full test suite (no regressions)
- [ ] Manual testing if user-facing
- [ ] Update documentation if needed
- [ ] Code review
- [ ] Merge

---

## Validation Commands

### After Each Fix
```bash
# Run specific test
uv run pytest tests/test_<module>.py -v

# Run all tests
uv run pytest

# Check coverage
uv run pytest --cov=tracklistify tests/
```

### Before Merging Phase
```bash
# Full test suite
uv run pytest --cov=tracklistify --cov-report=html tests/

# Security scan
uv run bandit -r src/tracklistify/

# Type checking
uv run mypy src/tracklistify/

# Code quality
uv run ruff check src/tracklistify/
uv run pylint src/tracklistify/

# Dead code
uv run vulture src/tracklistify/
```

### Smoke Test
```bash
# Basic functionality still works
uv run tracklistify test.mp3 -f json
uv run tracklistify test.mp3 --debug
uv run tracklistify --help
```

---

## Common Patterns

### Pattern 1: Fixing Security Issues

```python
# 1. Write security test
def test_malicious_input_blocked():
    with pytest.raises(ValueError):
        dangerous_function("__import__('os').system('ls')")

# 2. Implement fix
def dangerous_function(input_str):
    # REMOVE: eval(input_str)
    # ADD: safe parsing
    return safe_parse(input_str)

# 3. Validate
# - Test passes
# - Bandit scan clean
# - Manual penetration test
```

### Pattern 2: Fixing Breaking Changes

```python
# 1. Write backward compatibility test
def test_old_api_still_works():
    # Old way should still work if possible
    result = old_function()
    assert result is not None

# 2. Write new API test
def test_new_api_works():
    result = new_function(with_new_param=True)
    assert result is not None

# 3. Implement with deprecation warning if needed
def old_function():
    warnings.warn("Deprecated, use new_function", DeprecationWarning)
    return new_function()
```

### Pattern 3: Refactoring

```python
# 1. Write characterization tests (current behavior)
def test_current_behavior():
    result = messy_function(input)
    assert result == expected_output

# 2. Refactor
def refactored_function(input):
    # Cleaner implementation
    return result

# 3. Ensure tests still pass (behavior unchanged)
```

---

## Rollback Procedure

If a phase causes issues:

```bash
# 1. Identify the problematic commit
git log --oneline

# 2. Create rollback branch
git checkout -b rollback-phase-X main

# 3. Revert the merge commit
git revert -m 1 <merge-commit-hash>

# 4. Test rollback
uv run pytest

# 5. Deploy rollback
git push origin rollback-phase-X

# 6. Investigate issue
# Fix in separate branch
# Re-test thoroughly
# Re-deploy
```

---

## Issue Cross-Reference

### By File

**config/base.py**:
- Issue #1: eval() usage (Line 85)
- Issue #21: Empty _setup_validation() (Line 97)
- Issue #22: Empty _validate() (Line 101)

**cli.py**:
- Issue #2: Secret logging (Lines 127-129)
- Issue #4: Arguments ignored (Lines 68-85)
- Issue #9: Verbose default (Line 104)
- Issue #52: Signal handler (Lines 36-37)

**utils/rate_limiter.py**:
- Issue #5: Blocking locks (Lines 51, 174-178)
- Issue #12: Singleton thread safety (Lines 306-314)
- Issue #14: SimpleLimiter sync in async (Lines 50-51)

**utils/identification.py**:
- Issue #3: Stub functions (Lines 27-40)

**core/track.py**:
- Issue #7: Test code in production (Lines 116-124, 252-287)

**cache/base.py**:
- Issue #7: MockConfig in production (Lines 60-66)

**core/base.py**:
- Issue #6: Duplicate exceptions (Lines 418-430)

**providers/base.py**:
- Issue #6: Duplicate exceptions

**exporters/spotify.py**:
- Issue #11: Encapsulation violation (Lines 92-99)

**utils/logger.py**:
- Issue #8: Handler duplication (Lines 78-89)

**downloaders/mixcloud.py**:
- Issue #10: Error handling inconsistency (Line 104)

**utils/decorators.py**:
- Issue #13: Hash collision risk (Line 49)

---

## FAQ

### Q: Can I skip low-priority issues?
**A**: Yes, Phase 6 is optional polish. Focus on Phases 1-4 first.

### Q: Can I work on multiple phases simultaneously?
**A**: Yes, but ensure Phase 1-2 (critical) complete first. Phase 6 can run anytime.

### Q: What if a test fails?
**A**: Don't proceed until it passes. Either fix the code or fix the test.

### Q: How do I handle merge conflicts?
**A**: Resolve carefully. Re-run full test suite after conflict resolution.

### Q: Can I modify the implementation plan?
**A**: Yes, but document changes and rationale. Update this guide.

### Q: What if I find new issues?
**A**: Document in AUDIT_REPORT.md as addendum. Create new issues.

---

## Resources

- **Audit Report**: `AUDIT_REPORT.md`
- **Implementation Plan**: `IMPLEMENTATION_PLAN.md`, `IMPLEMENTATION_PLAN_PHASES_3_6.md`
- **Codebase Guide**: `CLAUDE.md`
- **Testing Guide**: `tests/TESTING.md`
- **Contributing**: `docs/CONTRIBUTING.md`

---

## Support

For questions or issues during implementation:
- Review the detailed specs in implementation plan
- Check CLAUDE.md for codebase conventions
- Create GitHub issue if blocked
- Tag @maintainers for urgent issues

---

**Last Updated**: 2025-11-21
**Version**: 1.0
**Status**: Ready for Implementation ✅
