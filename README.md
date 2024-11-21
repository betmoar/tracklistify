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

By default, Tracklistify uses the format specified in your `.env` file (OUTPUT_FORMAT). You can override this using the command line:

   ```bash
# Use specific format

tracklistify -f json input.mp3    # JSON output
tracklistify -f markdown input.mp3 # Markdown output
tracklistify -f m3u input.mp3     # M3U playlist

# Generate all formats

tracklistify -f all input.mp3
```

If no format is specified via command line, the OUTPUT_FORMAT from your environment will be used, defaulting to JSON if not set.

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
# Provider Selection
PRIMARY_PROVIDER=shazam
PROVIDER_FALLBACK_ENABLED=false
PROVIDER_FALLBACK_ORDER=acrcloud

# Track Identification Settings
SEGMENT_LENGTH=15
MIN_CONFIDENCE=50
TIME_THRESHOLD=60
MAX_DUPLICATES=1

# Output Settings
OUTPUT_FORMAT=all
OUTPUT_DIRECTORY=output
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