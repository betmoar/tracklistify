# Tracklistify

🎵 Automatically identify and catalog tracks from DJ mixes and audio streams.

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

## Installation

1. Clone the repository:
```bash
git clone https://github.com/betmoar/tracklistify.git
cd tracklistify
```

2. Install FFmpeg (if not already installed):
```bash
# macOS with Homebrew
brew install ffmpeg

# Linux
sudo apt-get install ffmpeg
```

3. Install the package:
```bash
pip install -e .
```

4. Copy the example environment file and configure your settings:
```bash
cp .env.example .env
```

Edit `.env` with your provider credentials and desired settings.

## Usage

### Basic Usage

Process a local audio file:
```bash
tracklistify path/to/audio.mp3
```

Analyze a YouTube video:
```bash
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

The following settings can be configured through environment variables or a `.env` file:

### Provider Settings
- `PRIMARY_PROVIDER`: Primary track identification provider (default: "acrcloud")
- `FALLBACK_ENABLED`: Enable provider fallback (default: true)
- `FALLBACK_PROVIDERS`: List of fallback providers (default: ["shazam"])

### Track Settings
- `SEGMENT_LENGTH`: Length of audio segments in seconds (default: 60)
- `MIN_CONFIDENCE`: Minimum confidence threshold (default: 0.0)
- `TIME_THRESHOLD`: Time threshold for merging nearby tracks (default: 60)

### Cache Settings
- `CACHE_ENABLED`: Enable caching (default: true)
- `CACHE_TTL`: Cache time-to-live in seconds (default: 3600)
- `CACHE_MAX_SIZE`: Maximum cache size (default: 1000)

### Download Settings
- `DOWNLOAD_QUALITY`: Audio quality in kbps (default: 192)
- `DOWNLOAD_FORMAT`: Output audio format (default: mp3)
- `DOWNLOAD_TEMP_DIR`: Custom temporary directory (default: ~/.tracklistify/temp)
- `DOWNLOAD_MAX_RETRIES`: Maximum retry attempts (default: 3)

### Output Settings
- `OUTPUT_DIRECTORY`: Output directory for generated files (default: "output")
- `OUTPUT_FORMAT`: Default output format (default: "json")

## Version History

See [CHANGELOG.md](CHANGELOG.md) for version history and latest changes.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.