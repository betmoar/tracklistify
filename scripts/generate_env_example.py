#!/usr/bin/env python3
"""Regenerate .env.example from TrackIdentificationConfig.

Run:
    python scripts/generate_env_example.py [--check]

The generator is the single source of truth for the example. Adding a new
field to ``TrackIdentificationConfig`` (or ``BaseConfig``) requires adding
that field name to ``FIELD_SECTIONS`` below — otherwise the script raises so
the drift can't go unnoticed.

``--check`` exits non-zero if running the generator would change the file
(useful for CI / pre-commit). Without it, the file is rewritten in place.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from typing import Iterable

# Make src/ importable when run directly from the repo root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tracklistify.config.base import TrackIdentificationConfig  # noqa: E402

ENV_FILE = PROJECT_ROOT / ".env.example"
ENV_PREFIX = "TRACKLISTIFY_"

HEADER = """\
# Tracklistify configuration example.
# Copy to .env and edit. Every variable below maps directly to a field on
# TrackIdentificationConfig (src/tracklistify/config/base.py); fields not
# declared there are NOT picked up. Regenerate with:
#     python scripts/generate_env_example.py
"""

# Section ID -> (display title, ordered list of field names in that section)
# Every dataclass field must appear in exactly one section. Fields not listed
# here trigger an error so drift can't slip in silently.
FIELD_SECTIONS: list[tuple[str, list[str]]] = [
    ("Directories", ["output_dir", "cache_dir", "temp_dir", "log_dir"]),
    ("Logging", ["verbose", "debug"]),
    (
        "Segmentation / identification",
        [
            "segment_length",
            "min_confidence",
            "time_threshold",
            "max_duplicates",
            "overlap_duration",
            "overlap_strategy",
            "min_segment_length",
        ],
    ),
    ("Providers", ["primary_provider", "fallback_enabled", "fallback_providers"]),
    (
        "Rate limiting",
        ["rate_limit_enabled", "max_requests_per_minute", "max_concurrent_requests"],
    ),
    (
        "Circuit breaker",
        [
            "circuit_breaker_enabled",
            "circuit_breaker_threshold",
            "circuit_breaker_reset_timeout",
        ],
    ),
    (
        "Per-provider rate limits",
        [
            "shazam_max_rpm",
            "shazam_max_concurrent",
            "shazam_cooldown_seconds",
            "acrcloud_max_rpm",
            "acrcloud_max_concurrent",
            "spotify_max_rpm",
            "spotify_max_concurrent",
        ],
    ),
    (
        "Caching",
        [
            "cache_enabled",
            "cache_ttl",
            "cache_max_size",
            "cache_storage_format",
            "cache_compression_enabled",
            "cache_compression_level",
            "cache_cleanup_enabled",
            "cache_cleanup_interval",
            "cache_max_age",
            "cache_min_free_space",
        ],
    ),
    (
        "Output / download",
        [
            "output_format",
            "download_quality",
            "download_format",
            "download_max_retries",
        ],
    ),
]

# Inline annotations (units, bounds) that aren't derivable from the dataclass.
INLINE_COMMENTS: dict[str, str] = {
    "segment_length": "10..300 seconds",
    "min_confidence": "0.0..1.0",
    "time_threshold": "0.0..300.0 seconds, dedup window",
    "max_duplicates": "0..10",
    "overlap_duration": "0..30 seconds",
    "overlap_strategy": "weighted | longest",
    "min_segment_length": "minimum segment duration in seconds",
    "circuit_breaker_threshold": "consecutive failures",
    "circuit_breaker_reset_timeout": "seconds",
    "cache_ttl": "seconds",
    "cache_max_size": "bytes (~1MB default)",
    "cache_compression_level": "1..9",
    "cache_cleanup_interval": "seconds",
    "cache_max_age": "seconds",
    "cache_min_free_space": "bytes",
    "output_format": "json | markdown | m3u",
    "download_quality": "kbps",
    "download_format": "mp3 | flac | ...",
}

# Fields rendered as commented-out (optional / not always set).
COMMENTED_OUT_FIELDS: set[str] = {"fallback_providers"}

# Static trailing block for env vars read directly via os.getenv (not on the
# dataclass).
CREDENTIALS_BLOCK = """\
# --- API credentials (do NOT commit real values) ------------------------
# These are read directly by provider modules via os.getenv, not via the
# dataclass. They are listed here for completeness.
# TRACKLISTIFY_ACR_ACCESS_KEY=
# TRACKLISTIFY_ACR_ACCESS_SECRET=
# TRACKLISTIFY_SPOTIFY_CLIENT_ID=
# TRACKLISTIFY_SPOTIFY_CLIENT_SECRET=
# TRACKLISTIFY_SPOTIFY_COOKIES=~/.mozilla/firefox/profile/cookies.sqlite
# TRACKLISTIFY_SPOTIFY_QUALITY=AAC_256
# TRACKLISTIFY_SPOTIFY_FORMAT=m4a
"""


def _format_default(field: dataclasses.Field) -> str:
    """Render a field's default value as the env-var string."""
    if field.default is not dataclasses.MISSING:
        default = field.default
    elif field.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
        default = field.default_factory()  # type: ignore[misc]
    else:
        return ""

    if isinstance(default, bool):
        return "true" if default else "false"
    if isinstance(default, Path):
        # Render project-relative paths cleanly; absolute paths as-is.
        try:
            return str(default.relative_to(PROJECT_ROOT))
        except ValueError:
            return str(default)
    if isinstance(default, list):
        return ",".join(str(x) for x in default)
    return str(default)


def _render() -> str:
    fields_by_name = {f.name: f for f in dataclasses.fields(TrackIdentificationConfig)}
    # _validator and similar private fields are excluded from the dataclass via
    # ``field(init=False)`` typing, but be defensive anyway.
    public = {n: f for n, f in fields_by_name.items() if not n.startswith("_")}

    listed: set[str] = set()
    for _, names in FIELD_SECTIONS:
        listed.update(names)

    unmapped = sorted(set(public) - listed)
    extras = sorted(listed - set(public))
    if unmapped or extras:
        msg_parts = []
        if unmapped:
            msg_parts.append(
                "Dataclass fields not assigned to any section in FIELD_SECTIONS:\n  - "
                + "\n  - ".join(unmapped)
            )
        if extras:
            msg_parts.append(
                "Section entries that no longer exist on the dataclass:\n  - "
                + "\n  - ".join(extras)
            )
        raise SystemExit(
            "FIELD_SECTIONS is out of sync with TrackIdentificationConfig.\n\n"
            + "\n\n".join(msg_parts)
        )

    lines: list[str] = [HEADER.rstrip(), ""]
    for title, names in FIELD_SECTIONS:
        # Section header uses 72-char dashed rule to match prior style.
        rule = "-" * max(8, 60 - len(title))
        lines.append(f"# --- {title} {rule}")
        for name in names:
            field = public[name]
            env_key = f"{ENV_PREFIX}{name.upper()}"
            value = _format_default(field)
            line = f"{env_key}={value}"
            if name in INLINE_COMMENTS:
                # Pad the value column for readability.
                pad = max(1, 42 - len(line))
                line = f"{line}{' ' * pad}# {INLINE_COMMENTS[name]}"
            if name in COMMENTED_OUT_FIELDS:
                line = f"# {line}"
            lines.append(line)
        lines.append("")

    lines.append(CREDENTIALS_BLOCK.rstrip())
    return "\n".join(lines) + "\n"


def main(argv: Iterable[str]) -> int:
    check_only = "--check" in argv
    new = _render()
    if not ENV_FILE.exists() or ENV_FILE.read_text() != new:
        if check_only:
            print(f".env.example is out of date — run: python {Path(__file__).name}")
            return 1
        ENV_FILE.write_text(new)
        print(f"Wrote {ENV_FILE.relative_to(PROJECT_ROOT)}")
        return 0
    print(".env.example is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
