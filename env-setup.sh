#!/bin/bash

# Script name: env-setup.sh
# Description: Setup script for Tracklistify development environment

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

    # Check for ffmpeg
    if ! command -v ffmpeg &> /dev/null; then
        missing_deps+=("ffmpeg")
    fi

    # Check for git (needed for setuptools_scm)
    if ! command -v git &> /dev/null; then
        missing_deps+=("git")
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

# Create and activate virtual environment
setup_venv() {
    print_status "Setting up virtual environment..."

    # Create venv if it doesn't exist
    if [ ! -d "$VENV_DIR" ]; then
        $PYTHON -m venv $VENV_DIR
    else
        print_warning "Virtual environment already exists"
    fi

    # Source the activate script based on OS
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        source $VENV_DIR/Scripts/activate
    else
        source $VENV_DIR/bin/activate
    fi
}

# Install shazamio and its core dependencies
install_shazamio() {
    print_status "Installing shazamio and dependencies..."

    # Create a temporary directory for shazamio-core
    local temp_dir=$(mktemp -d)

    # Clone and install shazamio-core
    git clone https://github.com/shazamio/shazamio-core.git "$temp_dir"
    cd "$temp_dir"
    git switch --detach 1.0.7
    python -m pip install .

    # Install shazamio itself
    pip install shazamio==0.7.0

    # Clean up
    cd - > /dev/null
    rm -rf "$temp_dir"
}

# Install package and dependencies
install_package() {
    print_status "Installing package and dependencies..."

    # Upgrade pip
    pip install --upgrade pip

    if [ "$1" == "--dev" ]; then
        print_status "Installing in development mode with dev dependencies..."
        pip install -e ".[dev]"
    else
        print_status "Installing in development mode..."
        pip install -e "."
    fi
}

# Setup pre-commit hooks
setup_precommit() {
    if [ "$1" == "--dev" ]; then
        print_status "Setting up pre-commit hooks..."
        pre-commit install
        pre-commit install --hook-type commit-msg
    fi
}

# Setup environment file
setup_env() {
    if [ ! -f ".env" ] && [ -f ".env.example" ]; then
        print_status "Creating .env file from example..."
        cp .env.example .env
        print_warning "Please edit .env file with your credentials"
    fi
}

# Main execution
main() {
    print_status "Starting Tracklistify setup..."

    # Check Python installation
    check_python

    # Check system dependencies
    check_system_deps

    # Setup virtual environment
    setup_venv

    # Install package and dependencies
    install_package "$1"

    install_shazamio

    # Setup pre-commit hooks for dev installation
    setup_precommit "$1"

    # Setup environment file
    setup_env

    print_status "Setup complete! You can now:"
    echo "1. Edit .env with your credentials (if you haven't already)"
    echo "2. Activate the virtual environment:"
    echo "   source $VENV_DIR/bin/activate"
    echo "3. Run Tracklistify:"
    echo "   tracklistify <command>"
}

# Run main function with all arguments
main "$@"
