"""Project root discovery utilities."""

import os
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from .logger import get_logger

logger = get_logger(__name__)


class ProjectRootError(Exception):
    """Raised when project root cannot be determined."""

    pass


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    """Get project root directory with multiple fallback strategies.

    The result is cached for performance as project root doesn't change during runtime.

    Returns:
        Path: Absolute path to the project root directory

    Raises:
        ProjectRootError: If project root cannot be determined reliably
    """

    project_root_env = os.getenv("TRACKLISTIFY_PROJECT_ROOT")

    if project_root_env:
        try:
            project_root = Path(project_root_env).resolve()
            if project_root.exists():
                return project_root
        except (OSError, ValueError):
            pass

    current_file = Path(__file__).resolve()

    for parent in [current_file] + list(current_file.parents):
        pyproject_path = parent / "pyproject.toml"
        if pyproject_path.exists():
            return parent

    try:
        dist = distribution("tracklistify")
        package_path = Path(dist.locate_file(""))

        if (package_path / "pyproject.toml").exists():
            return package_path

        for parent in package_path.parents:
            pyproject_path = parent / "pyproject.toml"
            if pyproject_path.exists():
                return parent

    except (PackageNotFoundError, AttributeError, OSError):
        pass

    raise ProjectRootError(
        "Unable to determine project root. Please set TRACKLISTIFY_PROJECT_ROOT "
        "environment variable or ensure pyproject.toml exists in the project root."
    )


def clear_project_root_cache() -> None:
    """Clear the cached project root."""

    get_project_root.cache_clear()
    logger.debug("Cleared project root cache")
