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

- 🎵 **Multi-Provider Track Identification**
  - Shazam and ACRCloud integration
  - Smart provider fallback system
  - High accuracy with confidence scoring
  - Support for multiple platforms (YouTube, Mixcloud, SoundCloud)

- 📊 **Versatile Output Formats**
  - JSON with detailed metadata
  - Markdown formatted tracklists
  - M3U playlists
  - CSV and XML exports
  - Rekordbox compatible format

- 🚀 **Advanced Processing**
  - Automatic format conversion
  - Batch processing for multiple files
  - Intelligent caching system
  - Progress tracking with detailed status
  - Configurable audio quality settings

- ⚙️ **Robust Architecture**
  - Asynchronous processing
  - Smart rate limiting
  - Advanced error recovery
  - Comprehensive logging system
  - Docker support

## Requirements

- Python 3.11 or higher
- ffmpeg
- git
- Poetry (package manager)

## Quick Start

1. **Installation**
   ```bash
   # Clone the repository
   git clone https://github.com/betmoar/tracklistify.git
   cd tracklistify

   # Install dependencies using Poetry
   poetry install
   ```

2. **Configuration**
   ```bash
   # Copy example environment file
   cp .env.example .env

   # Edit .env with your provider credentials
   # Required for ACRCloud:
   # - ACRCLOUD_ACCESS_KEY
   # - ACRCLOUD_ACCESS_SECRET
   # - ACRCLOUD_HOST
   ```

3. **Basic Usage**
   ```bash
   # Identify tracks in a file or URL
   poetry run tracklistify <input>

   # Examples:
   poetry run tracklistify path/to/mix.mp3
   poetry run tracklistify https://youtube.com/watch?v=example
   ```

## Advanced Usage

### Output Formats
```bash
# Specify output format
poetry run tracklistify -f json input.mp3    # JSON output
poetry run tracklistify -f markdown input.mp3 # Markdown output
poetry run tracklistify -f m3u input.mp3     # M3U playlist
poetry run tracklistify -f csv input.mp3     # CSV export
poetry run tracklistify -f all input.mp3     # Generate all formats
```

### Batch Processing
```bash
# Process multiple files
poetry run tracklistify -b path/to/folder/*.mp3

# With specific output format
poetry run tracklistify -b -f json path/to/folder/*.mp3
```

### Additional Options
```bash
# Show progress with detailed status
poetry run tracklistify --progress input.mp3

# Specify provider
poetry run tracklistify --provider shazam input.mp3
poetry run tracklistify --provider acrcloud input.mp3

# Set output directory
poetry run tracklistify -o path/to/output input.mp3
```

## Contributing

Contributions are welcome! Please read our [Contributing Guide](docs/CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
