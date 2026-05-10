![Tracklistify banner](docs/assets/banner.png)

<div align="center">

[![GitHub stars](https://img.shields.io/github/stars/betmoar/tracklistify?style=social)](https://github.com/betmoar/tracklistify/stargazers)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](docs/CONTRIBUTING.md)
[![Made with ❤️](https://img.shields.io/badge/Made%20with-❤️-red.svg)](https://github.com/betmoar/tracklistify)

### [Changelog](docs/CHANGELOG.md) · [Issues](https://github.com/betmoar/tracklistify/issues) · [Contributing](docs/CONTRIBUTING.md)

</div>

# Tracklistify

A powerful and flexible automatic tracklist generator for DJ mixes and audio streams. Identifies tracks in your mixes using multiple providers (Shazam, ACRCloud) and generates formatted playlists with high accuracy.

## Key Features

### 🎵 **Multi-Provider Track Identification**

  - Shazam and ACRCloud for fingerprint-based identification
  - Spotify integration for metadata enrichment and playlist export
  - Smart provider fallback system with circuit breaker
  - High accuracy with confidence scoring
  - Support for multiple platforms (YouTube, Mixcloud, SoundCloud, Spotify)

### 📊 **Versatile Output Formats**

  - JSON with detailed metadata
  - Markdown formatted tracklists
  - M3U playlists
  - CSV and XML exports
  - Rekordbox compatible format

### 🚀 **Advanced Processing**

  - Automatic format conversion via FFmpeg
  - Batch processing for multiple files
  - Intelligent caching with TTL/LRU/size invalidation strategies
  - Progress tracking with detailed status
  - Configurable audio quality settings

### ⚙️ **Robust Architecture**

  - Asynchronous processing throughout
  - Token-bucket rate limiting with circuit breaker per provider
  - Thread-safe singletons for config, cache, and rate limiter
  - Async context managers for deterministic resource cleanup
  - Centralised, structured exception hierarchy
  - Coloured console + rotating-file logging

## Requirements

- Python 3.11 or higher
- ffmpeg
- git
- uv (package and project manager)

### Important Note:

- Tracklistify is managed by uv, so you will need to install it.
- Follow the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) for your platform.

## Quick Start

### **1. Installation**

   ```bash
   # Clone the repository
   git clone https://github.com/betmoar/tracklistify.git
   cd tracklistify

   # Install dependencies using uv
   uv sync
   ```

### **2. Configuration**

   ```bash
   # Copy example environment file
   cp .env.example .env
   ```

### **3. Basic Usage**

   ```bash
   # Identify tracks in a file or URL
   uv run tracklistify <input>

   # Examples:
   tracklistify path/to/mix.mp3
   tracklistify https://youtube.com/watch?v=example
   ```

## Advanced Usage

### Output Formats

```bash
# Specify output format
tracklistify -f json input.mp3    # JSON output
tracklistify -f markdown input.mp3 # Markdown output
tracklistify -f m3u input.mp3     # M3U playlist
tracklistify -f csv input.mp3     # CSV export
tracklistify -f all input.mp3     # Generate all formats
```

### Batch Processing

```bash
# Process multiple files
tracklistify -b path/to/folder/*.mp3

# With specific output format
tracklistify -b -f json path/to/folder/*.mp3
```

### Additional Options

```bash
# Show progress with detailed status
tracklistify --progress input.mp3

# Specify provider
tracklistify --provider shazam input.mp3

# Set output directory
tracklistify -o path/to/output input.mp3
```

## Development

Working on the codebase? Start here:

- [`CLAUDE.md`](CLAUDE.md) — full development guide covering project layout, coding conventions, factory/strategy patterns, testing, and common tasks (also used as context for AI assistants).
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) — contribution workflow and code of conduct.
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) — version history.
- [`docs/archive/`](docs/archive/) — historical audit and implementation-plan artefacts (informational only).

```bash
uv sync --dev                       # install runtime + dev deps
uv run python -m pytest -q          # run the full test suite (~335 tests)
uv run ruff check src/ tests/       # lint
uv run ruff format src/ tests/      # format
```

## Contributing

Contributions are welcome! Please read our [Contributing Guide](docs/CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
