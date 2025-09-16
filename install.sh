#!/bin/bash

# Script name: install.sh
# Description: Check system dependencies for Tracklistify

# Configuration
VENV_DIR=".venv"
PYTHON="python3"
MIN_PYTHON_VERSION="3.11"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print status messages
print_status() {
    echo -e "${GREEN}==>${NC} $1"
}

# Function to print warnings
print_warning() {
    echo -e "${YELLOW}Warning:${NC} $1"
}

# Function to print errors
print_error() {
    echo -e "${RED}Error:${NC} $1"
}

# Check Python version
check_python_version() {
    local python_version
    python_version=$($PYTHON --version 2>&1 | cut -d' ' -f2)

    # Convert versions to comparable integers (e.g., 3.11.1 -> 3011001)
    local min_version_int=$(echo $MIN_PYTHON_VERSION | awk -F. '{ printf("%d%03d%03d\n", $1, $2, $3) }')
    local current_version_int=$(echo $python_version | awk -F. '{ printf("%d%03d%03d\n", $1, $2, $3) }')

    if [ "$current_version_int" -lt "$min_version_int" ]; then
        print_error "Python version must be >= $MIN_PYTHON_VERSION (found $python_version)"
        exit 1
    fi
}

# Check if Python is installed
check_python() {
    if ! command -v $PYTHON &> /dev/null; then
        print_error "Python 3 is not installed"
        exit 1
    fi
    check_python_version
}

# Check if system has required system dependencies
check_system_deps() {
    local missing_deps=()

    # Check for uv
    if ! command -v uv &> /dev/null; then
        echo "uv is not installed."
        missing_deps+=("uv")
    fi

    # Check for ffmpeg
    if ! command -v ffmpeg &> /dev/null; then
        echo "FFmpeg is not installed."
        missing_deps+=("ffmpeg")
    fi

    # Check for git (needed for setuptools_scm)
    if ! command -v git &> /dev/null; then
        echo "Git is not installed."
        missing_deps+=("git")
    fi

    # Check for rustc (needed for shazamio-core)
    if ! command -v rustc &> /dev/null; then
        missing_deps+=("rustup")
    fi

    # If there are missing dependencies, print instructions
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Missing system dependencies: ${missing_deps[*]}"
        echo "Please install them using your package manager:"

        if [[ "$OSTYPE" == "darwin"* ]]; then
            echo "brew install ${missing_deps[*]}"
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            echo "sudo apt-get install ${missing_deps[*]}"
        fi

        exit 1
    fi
}

# Install package and dependencies
install_package() {
    print_status "Installing package and dependencies..."

    if [ "$1" == "--dev" ]; then
        print_status "Installing in development mode with dev dependencies..."
        uv sync --all-packages
        uv run pre-commit install
    else
        print_status "Installing in default mode..."
        uv sync
    fi
}

# Main execution
main() {
    print_status "Starting Tracklistify setup..."

    # Check Python installation
    check_python

    # Check system dependencies
    check_system_deps

    # Install package and dependencies
    install_package "$1"

    print_status "Setup complete! You can now:"
    echo " "
    echo "1. Edit .env with your credentials"
    echo "2. Activate the virtual environment:"
    echo "   source $VENV_DIR/bin/activate"
    echo "3. Run Tracklistify:"
    echo "   tracklistify <command>"
}

# Run main function with all arguments
main "$@"
