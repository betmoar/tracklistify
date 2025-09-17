"""Project path discovery utilities."""

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_root() -> Path:
    """Get project root directory for loading .env files and resolving config paths.

    Simple approach:
    1. Check environment variable TRACKLISTIFY_PROJECT_ROOT
    2. Walk up from current file until we find pyproject.toml
    3. Fallback to current working directory

    Returns:
        Path: Project root directory
    """
    # Environment variable override
    if root_env := os.getenv("TRACKLISTIFY_PROJECT_ROOT"):
        root_path = Path(root_env).resolve()
        if root_path.exists():
            return root_path

    # Walk up from this file to find pyproject.toml
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent

    # Fallback to current working directory
    return Path.cwd()


def clear_root() -> None:
    """Clear the project root cache."""
    get_root.cache_clear()
