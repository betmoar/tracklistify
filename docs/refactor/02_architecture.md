# System Architecture

<div align="center">

[⬅️ Setup](01_overview.md) | [🏠 Home](README.md) | [Development Tools ➡️](03_development_tools.md)

</div>

---

**Topics:** `#architecture` `#components` `#structure` `#modules` `#design`

**Related Files:**
- [`core/__init__.py`](../tracklistify/core/__init__.py)
- [`providers/__init__.py`](../tracklistify/providers/__init__.py)
- [`downloaders/__init__.py`](../tracklistify/downloaders/__init__.py)
- [`exporters/__init__.py`](../tracklistify/exporters/__init__.py)

---

The project follows a modular architecture with clear separation of concerns:

```
tracklistify/
├── __init__.py          # Package initialization and metadata
├── core/               # Core functionality and base classes
│   ├── __init__.py
│   ├── base.py        # Base application and error handling
│   ├── track.py       # Track data model and matching
│   └── types.py       # Core type definitions
├── providers/         # Track identification services
│   ├── __init__.py
│   ├── shazam.py     # Shazam integration
│   ├── acrcloud.py   # ACRCloud integration
│   └── spotify.py    # Spotify metadata enrichment
├── downloaders/       # Audio download implementations
│   ├── __init__.py
│   ├── youtube.py    # YouTube downloader
│   ├── mixcloud.py   # Mixcloud downloader
│   └── spotify.py    # Spotify downloader
├── exporters/        # Output format handlers
│   ├── __init__.py
│   ├── tracklist.py  # Tracklist generation
│   └── spotify.py    # Spotify playlist export
├── cache/           # Caching implementation
│   ├── __init__.py
│   ├── base.py      # Base cache functionality
│   └── storage.py   # Cache storage backends
├── config/          # Configuration management
│   ├── __init__.py
│   ├── base.py      # Configuration classes
│   └── factory.py   # Configuration loading
└── utils/           # Shared utilities
    ├── __init__.py
    ├── logger.py    # Logging configuration
    └── validation.py # Input validation
```

## Key Components

### 1. Core System
- Track identification engine
- Audio segment processing
- Metadata management
- Async operation handling

### 2. Providers
- Multiple identification services (Shazam, ACRCloud)
- Provider factory pattern
- Metadata enrichment (Spotify)
- Error handling and rate limiting

### 3. Downloaders
- Support for multiple sources (YouTube, Mixcloud, Spotify)
- Async download operations
- FFmpeg integration
- Progress tracking

### 4. Exporters
- Multiple output formats (JSON, Markdown, M3U)
- Metadata formatting
- File handling
