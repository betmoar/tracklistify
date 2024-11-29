# Development Tools & Workflow

<div align="center">

[⬅️ Architecture](02_architecture.md) | [🏠 Home](README.md) | [Refactoring Goals ➡️](04_refactoring_goals.md)

</div>

---

**Topics:** `#tools` `#quality` `#testing` `#ci-cd` `#automation`

**Related Files:**
- [`pyproject.toml`](../pyproject.toml)
- [`dev.py`](../tracklistify/dev.py)
- [`.github/workflows/quality.yml`](../.github/workflows/quality.yml)
- [`.pre-commit-config.yaml`](../.pre-commit-config.yaml)

---

## Built-in CLI Tool

```bash
# Show available commands
poetry run dev --help

# List all available tools
poetry run dev list

# Run a specific tool
poetry run dev -t pylint

# Run all tools
poetry run dev -a
```

## Code Quality Tools

| Tool | Purpose | Command | Alternative Tools |
|------|---------|---------|-------------------|
| `pylint` | Code quality & style | `poetry run dev -t pylint` | [`ruff`](https://github.com/astral-sh/ruff) |
| `pyreverse` | UML diagrams | `poetry run dev -t pyreverse` | [`pycg`](https://github.com/vwxyzjn/pycg) |
| `pipdeptree` | Dependency analysis | `poetry run dev -t pipdeptree` | [`poetry show --tree`](https://python-poetry.org/docs/cli/#show) |
| `sphinx` | Documentation | `poetry run dev -t sphinx` | [`mkdocs`](https://www.mkdocs.org/) |
| `vulture` | Dead code detection | `poetry run dev -t vulture` | [`coverage`](https://coverage.readthedocs.io/) |

## CI/CD Integration

```yaml
# .github/workflows/quality.yml
name: Code Quality

on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install Poetry
        run: pipx install poetry
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
          cache: 'poetry'
      - name: Install dependencies
        run: poetry install
      - name: Run Ruff
        run: poetry run ruff check .
      - name: Run Tests
        run: poetry run pytest
```

## Code Style Configuration

```toml
# pyproject.toml
[tool.ruff]
line-length = 88
target-version = "py311"
select = ["E", "F", "I", "N", "W", "D", "UP"]
```

## Pre-commit Integration

```bash
# Install pre-commit hooks
poetry run pre-commit install

# Run pre-commit checks
poetry run pre-commit run --all-files
