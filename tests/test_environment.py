"""Environment validation tests for Tracklistify."""

# Standard library imports
import os
import subprocess
import sys
from pathlib import Path

# Third-party imports
import pytest


def test_python_version():
    """Test Python version meets minimum requirements."""
    min_version = (3, 11)  # From env-setup.sh
    current = sys.version_info[:2]
    assert (
        current >= min_version
    ), f"Python version must be >= {min_version} (found {current})"


def test_ffmpeg_installed():
    """Test ffmpeg is installed and accessible."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.fail(f"ffmpeg is not installed or not accessible: {e}")


def test_git_installed():
    """Test git is installed and accessible."""
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.fail(f"git is not installed or not accessible: {e}")


def test_env_file_exists():
    """Test .env file exists in project root."""
    env_file = Path(".env")
    env_example = Path(".env.example")

    assert env_example.exists(), ".env.example file is missing"
    if not env_file.exists():
        pytest.skip(".env file not found - copy .env.example to .env and configure")


def test_virtual_environment():
    """Test code is running in a virtual environment."""
    in_venv = any(
        (
            hasattr(sys, "real_prefix"),  # Old-style virtualenv
            sys.base_prefix != sys.prefix,  # New-style venv
            os.environ.get("VIRTUAL_ENV") is not None,  # Explicitly set
            os.environ.get("CONDA_DEFAULT_ENV") is not None,  # Conda environment
        )
    )
    assert in_venv, "Code is not running in a virtual environment"


def test_development_dependencies():
    """Test development dependencies are installed."""
    # Python packages to import
    python_packages = [
        "pytest",
        "black",
        "isort",
        "flake8",
        "mypy",
    ]

    for package in python_packages:
        try:
            __import__(package)
        except ImportError:
            pytest.fail(f"Development dependency '{package}' is not installed")

    # Check pre-commit separately as it's a command-line tool
    result = subprocess.run(["which", "pre-commit"], capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail("pre-commit is not installed or not in PATH")


def test_precommit_config_exists():
    """Test pre-commit configuration exists."""
    config_file = Path(".pre-commit-config.yaml")
    assert config_file.exists(), ".pre-commit-config.yaml is missing"


def test_precommit_installed():
    """Test pre-commit hooks are installed in git."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"], capture_output=True, check=True
        )
        hooks_dir = Path(".git/hooks")
        pre_commit_hook = hooks_dir / "pre-commit"
        assert pre_commit_hook.exists(), "pre-commit hook is not installed"
    except subprocess.CalledProcessError:
        pytest.skip("Not a git repository")
