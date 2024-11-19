#!/bin/bash

# Script name: env-setup.sh

# Configuration
VENV_DIR="venv"
PYTHON="python3"
REQUIREMENTS="requirements.txt"
DEV_REQUIREMENTS="requirements-dev.txt"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status messages
print_status() {
    echo -e "${GREEN}==>${NC} $1"
}

# Function to print warnings
print_warning() {
    echo -e "${YELLOW}Warning:${NC} $1"
}

# Check if Python is installed
if ! command -v $PYTHON &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Check if system has required system dependencies
check_system_deps() {
    local missing_deps=()
    
    # Check for ffmpeg
    if ! command -v ffmpeg &> /dev/null; then
        missing_deps+=("ffmpeg")
    fi

    # If there are missing dependencies, print instructions
    if [ ${#missing_deps[@]} -ne 0 ]; then
        echo "Missing system dependencies: ${missing_deps[*]}"
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

# Install dependencies
install_deps() {
    print_status "Installing dependencies..."
    
    # Upgrade pip
    pip install --upgrade pip

    # Install requirements
    if [ -f "$REQUIREMENTS" ]; then
        pip install -r "$REQUIREMENTS"
    else
        echo "Error: $REQUIREMENTS not found"
        exit 1
    fi

    # Install dev requirements if --dev flag is passed
    if [ "$1" == "--dev" ] && [ -f "$DEV_REQUIREMENTS" ]; then
        print_status "Installing development dependencies..."
        pip install -r "$DEV_REQUIREMENTS"
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
    
    # Check system dependencies
    check_system_deps
    
    # Setup virtual environment
    setup_venv
    
    # Install dependencies
    install_deps "$1"
    
    # Setup environment file
    setup_env
    
    print_status "Setup complete! You can now run Tracklistify using:"
    echo "source $VENV_DIR/bin/activate  # Activate the virtual environment"
    echo "python -m tracklistify <command>  # Run Tracklistify"
}

# Run main function with all arguments
main "$@"