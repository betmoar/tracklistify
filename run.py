#!/usr/bin/env python3

import os
import sys
import shutil
import asyncio
from pathlib import Path

def setup_environment():
    """Setup the Python path and environment variables."""
    # Add the parent directory to Python path so tracklistify can be imported
    current_dir = Path(__file__).parent.absolute()
    sys.path.append(str(current_dir))

    # Load environment variables from .env file if it exists
    env_file = current_dir / '.env'
    if not env_file.exists() and (current_dir / '.env.example').exists():
        print("Creating .env from .env.example...")
        with open(current_dir / '.env.example') as f:
            with open(env_file, 'w') as env:
                env.write(f.read())
        print("Please edit .env with your credentials")
        sys.exit(1)

def check_dependencies():
    """Check if required system dependencies are installed."""
    try:
        from pydub.utils import which
    except ImportError:
        print("Error: pydub not found. Please install requirements:")
        print("pip install -r requirements.txt")
        sys.exit(1)

    # Check for system ffmpeg using pydub's which utility
    ffmpeg_path = which("ffmpeg")
    if not ffmpeg_path:
        print("Error: ffmpeg not found in system PATH")
        print("Please make sure ffmpeg is installed and accessible from command line:")
        if sys.platform == "darwin":
            print("brew install ffmpeg")
        else:
            print("sudo apt-get install ffmpeg")
        print("\nIf ffmpeg is already installed, ensure it's in your system PATH")
        sys.exit(1)
    
    # Additional verification by trying to run ffmpeg
    try:
        import subprocess
        subprocess.run([ffmpeg_path, "-version"], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        print(f"Error: Found ffmpeg at {ffmpeg_path} but unable to execute it")
        print("Please check if you have the necessary permissions")
        sys.exit(1)
    except Exception as e:
        print(f"Error verifying ffmpeg: {e}")
        sys.exit(1)

async def main():
    """Main entry point."""
    # Setup environment
    setup_environment()
    check_dependencies()

    try:
        # Import tracklistify main after environment is set up
        from tracklistify.__main__ import main as tracklistify_main
        await tracklistify_main()
    except ImportError as e:
        print(f"Error importing tracklistify: {e}")
        print("Make sure you're in the correct directory and have installed requirements:")
        print("pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"Error running tracklistify: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())