![Tracklistify banner](docs/assets/banner.png)

<div align="center">

[![GitHub stars](https://img.shields.io/github/stars/betmoar/tracklistify?style=social)](https://github.com/betmoar/tracklistify/stargazers)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](docs/CONTRIBUTING.md)
[![Made with ❤️](https://img.shields.io/badge/Made%20with-❤️-red.svg)](https://github.com/betmoar/tracklistify)

### [Changelog](docs/CHANGELOG.md) · [Issues](https://github.com/betmoar/tracklistify/issues) · [Contributing](docs/CONTRIBUTING.md)

</div>

# Tracklistify

Automatic tracklist generator for DJ mixes and audio streams. Identifies tracks
in your mixes using multiple providers (Shazam, ACRCloud) and generates
formatted playlists.

## Key Features

### Multi-Provider Track Identification

- Shazam and ACRCloud for fingerprint-based identification
- Smart provider fallback with per-provider circuit breaker
- Confidence scoring
- Download from YouTube, Mixcloud, and SoundCloud

### Metadata Enrichment

- Spotify, MusicBrainz, and Beatport resolve canonical streaming links
  post-dedup (first-writer-wins per platform)
- MusicBrainz is keyless (ISRC lookup); Beatport adds DJ metadata
  (BPM, key, label, genre, remixers, catalog number) and is opt-in with your
  own account
- Enrichment is best-effort: never fails a run

### Output Formats

- JSON with full metadata
- Markdown tracklists
- M3U playlists (VLC `#EXTVLCOPT:start-time` per-track seeking)

### Architecture

- Async throughout; token-bucket rate limiting with circuit breaker
- Thread-safe singletons for config, cache, and rate limiter
- Async context managers for deterministic resource cleanup
- Intelligent caching (TTL/LRU/size invalidation; download cache)

## Requirements

- Python 3.11+
- ffmpeg
- git
- [uv](https://docs.astral.sh/uv/) (package manager)
- [Deno](https://deno.com/) — required for YouTube downloads (the `yt-dlp-ejs`
  solver scripts run inside Deno to handle YouTube's signature/n-param
  challenges)

## Quick Start

```bash
# Clone and install
git clone https://github.com/betmoar/tracklistify.git
cd tracklistify
uv sync

# Configure (copy the example env, then edit as needed)
cp .env.example .env

# Identify tracks in a file or URL
uv run tracklistify <input>
# e.g.
uv run tracklistify path/to/mix.mp3
uv run tracklistify https://youtube.com/watch?v=example
```

## Usage

```bash
# Output format (json | markdown | m3u | all)
tracklistify -f json input.mp3

# Ignore stored identifications and re-identify (--no-cache is a refresh,
# not a disable: reads are skipped, writes stay live)
tracklistify --no-cache input.mp3

# Keep the source codec end-to-end (skip yt-dlp's MP3 transcode)
tracklistify --stream-copy <youtube-url>

# Specify the primary provider; disable fallback
tracklistify --provider shazam input.mp3
tracklistify --no-fallback input.mp3
```

See `.env.example` for every configuration option (provider credentials,
segmentation, rate limits, cache, enrichment).

## Development

- [`CLAUDE.md`](CLAUDE.md) — full development guide: project layout, coding
  conventions, patterns, testing, and common tasks.
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) — contribution workflow and
  code of conduct.
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) — version history.
- [`docs/PLAYBOOKS.md`](docs/PLAYBOOKS.md) — step-by-step procedures for
  common development tasks.

```bash
uv sync --dev                          # install runtime + dev deps
uv run python -m pytest -q             # run the test suite (~666 tests)
uv run ruff check src/ tests/ scripts/ # lint
uv run ruff format src/ tests/ scripts/  # format
uv run python scripts/check_mypy_baseline.py  # type-check ratchet
```

## Contributing

Contributions are welcome! Please read the [Contributing Guide](docs/CONTRIBUTING.md)
for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file
for details.
