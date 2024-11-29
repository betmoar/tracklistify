# Getting Started with Tracklistify

<div align="center">

[🏠 Home](README.md) | [Architecture ➡️](02_architecture.md)

</div>

---

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)

**Topics:** `#setup` `#installation` `#configuration` `#prerequisites`

---

Tracklistify is an automatic tracklist generator for DJ mixes and audio streams. This guide provides a systematic approach to refactoring the codebase, focusing on improving code quality, maintainability, and architectural design without altering external behavior.

## Prerequisites

- Python 3.11+
- Poetry 1.7+
- Git
- FFmpeg (required for audio processing)
- Graphviz (for UML diagrams)

## Installation

```bash
# Clone the repository
git clone https://github.com/betmoar/tracklistify.git
cd tracklistify

# Install Poetry if you haven't already
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies using Poetry
poetry install

# Activate the virtual environment
poetry shell
```
