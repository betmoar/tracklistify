# Tracklistify

Automatic tracklist generator for DJ mixes and audio streams. Identifies tracks in your mixes using multiple providers (Shazam, ACRCloud) and generates formatted playlists.

## Features

- 🎧 Track Identification:
  - Multiple provider support (Shazam, ACRCloud)
  - Configurable provider fallback
  - Robust error handling and retry logic
  - High accuracy with confidence scoring

- 📝 Output Formats:
  - JSON export with detailed metadata
  - Markdown formatted tracklists
  - M3U playlist generation
  - Configurable via environment or CLI

- 🔄 Audio Processing:
  - Automatic format conversion
  - Stereo and sample rate normalization
  - Segment-based analysis
  - YouTube download support

- ⚡ Performance:
  - Asynchronous processing
  - Intelligent rate limiting
  - Session management with auto-recovery
  - Exponential backoff retry logic

- 🛠️ Configuration:
  - Environment-based setup
  - Command-line overrides
  - Flexible provider selection
  - Customizable output options

## Requirements

- Python 3.11 or higher
- ffmpeg
- git

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/betmoar/tracklistify.git
   cd tracklistify
   ```

2. Run the setup script:
   ```bash
   ./env-setup.sh
   ```

3. Configure your environment:
   - Copy `.env.example` to `.env`
   - Edit `.env` with your settings

## Usage

   ```bash
# Basic usage:

tracklistify https://youtube.com/watch?v=example
```

### Output Format Options

By default, Tracklistify uses the format specified in your `.env` file (TRACKLISTIFY_OUTPUT_FORMAT). You can override this using the command line:

   ```bash
# Use specific format

tracklistify -f json input.mp3    # JSON output
tracklistify -f markdown input.mp3 # Markdown output
tracklistify -f m3u input.mp3     # M3U playlist

# Generate all formats

tracklistify -f all input.mp3
```

If no format is specified via command line, the TRACKLISTIFY_OUTPUT_FORMAT from your environment will be used, defaulting to JSON if not set.

### Provider Selection

```bash
# Use specific provider

tracklistify -p shazam input.mp3

# Disable provider fallback

tracklistify --no-fallback input.mp3
   ```

## Configuration

Key settings in `.env`:

```ini
# Directory Settings
TRACKLISTIFY_OUTPUT_DIR=~/.tracklistify/output   # Output directory
TRACKLISTIFY_CACHE_DIR=~/.tracklistify/cache     # Cache directory
TRACKLISTIFY_TEMP_DIR=~/.tracklistify/temp       # Temporary files

# Provider Settings
TRACKLISTIFY_PRIMARY_PROVIDER=shazam             # Primary provider (shazam, acrcloud)
TRACKLISTIFY_FALLBACK_ENABLED=false             # Enable fallback to other providers
TRACKLISTIFY_FALLBACK_PROVIDERS=["acrcloud"]    # Fallback providers list

# Track Identification Settings
TRACKLISTIFY_SEGMENT_LENGTH=30                  # Length of audio segments (10-300s)
TRACKLISTIFY_MIN_CONFIDENCE=0.0                 # Minimum confidence (0.0-1.0)
TRACKLISTIFY_TIME_THRESHOLD=60.0                # Time between tracks (0.0-300.0s)
TRACKLISTIFY_MAX_DUPLICATES=2                   # Maximum duplicate tracks

# Output Settings
TRACKLISTIFY_OUTPUT_FORMAT=all                  # Output format (json, markdown, m3u, all)
```

### Environment Variable Formats

Tracklistify supports various formats for environment variables:

- **Lists**: Can be specified in multiple formats:
  ```bash
  TRACKLISTIFY_FALLBACK_PROVIDERS=["provider1", "provider2"]  # Python list syntax
  TRACKLISTIFY_FALLBACK_PROVIDERS=provider1,provider2         # Comma-separated
  TRACKLISTIFY_FALLBACK_PROVIDERS=provider1                   # Single value
  ```

- **Booleans**: Support multiple formats:
  ```bash
  TRACKLISTIFY_FALLBACK_ENABLED=true   # or false
  TRACKLISTIFY_FALLBACK_ENABLED=1      # or 0
  TRACKLISTIFY_FALLBACK_ENABLED=yes    # or no
  TRACKLISTIFY_FALLBACK_ENABLED=on     # or off
  ```

- **Paths**: Support home directory expansion:
  ```bash
  TRACKLISTIFY_OUTPUT_DIR=~/.tracklistify/output  # Expands to home directory
  TRACKLISTIFY_OUTPUT_DIR=/absolute/path          # Absolute paths
  ```

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/betmoar/tracklistify.git
cd tracklistify
```

2. Run the environment setup script:
```bash
./env-setup.sh --dev
```

This will:
- Check system requirements
- Create a virtual environment
- Install all dependencies
- Set up pre-commit hooks
- Create initial configuration

3. Activate the virtual environment:
```bash
source venv/bin/activate
```

4. Configure your environment:
- Copy `.env.example` to `.env` if not already done
- Edit `.env` with your API credentials

## Development Guidelines

- Use pre-commit hooks for code quality
- Follow conventional commits for version control
- Run tests before submitting changes
- Update documentation for new features

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guidelines.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and changes.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Shazam](https://www.shazam.com/) for audio recognition
- [ACRCloud](https://www.acrcloud.com/) for audio recognition
- [FFmpeg](https://ffmpeg.org/) for audio processing