# Troubleshooting Guide

<div align="center">

[⬅️ Plan](05_refactoring_plan.md) | [🏠 Home](README.md) | [Contributing ➡️](07_contributing.md)

</div>

---

**Topics:** `#debugging` `#issues` `#solutions` `#common-problems`

**Related Files:**
- [`dev.py`](../tracklistify/dev.py)
- [`tests/`](../tests/)
- [`docs/logs/`](../logs/)
- [`.env.example`](../.env.example)

---

## Common Issues and Solutions

### 1. Poetry Environment Issues
- Ensure Poetry is installed correctly: `poetry --version`
- Try recreating the virtual environment: `poetry env remove python && poetry install`
- Check Python version compatibility: `poetry env info`

### 2. Tool Integration Problems
- Verify tool configurations in `pyproject.toml`
- Ensure you're in Poetry shell: `poetry shell`
- Check tool-specific dependencies: `poetry show`

### 3. Runtime Issues
- FFmpeg not found: Install FFmpeg using system package manager
- API rate limits: Check provider documentation for limits
- Memory issues: Monitor memory usage during audio processing

### 4. Testing Problems
- Test database connection issues: Check database configuration
- Mock object failures: Verify mock setup and dependencies
- CI/CD pipeline failures: Review GitHub Actions logs

### 5. Development Environment
- IDE integration issues: Configure Python interpreter path
- Code formatting conflicts: Check `.editorconfig` and tool settings
- Git hook failures: Verify pre-commit configuration
