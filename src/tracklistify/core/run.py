"""Main entry point for Tracklistify."""

import asyncio
import signal
import sys

from tracklistify.utils.project import get_project_root

# Global variables for cleanup
_cleanup_tasks = set()


def setup_environment():
    """Setup the Python path and environment variables."""
    env_file = get_project_root() / ".env"
    if not env_file.exists() and (get_project_root() / ".env.example").exists():
        print("Creating .env from .env.example...")
        with open(get_project_root() / ".env.example") as f:
            with open(env_file, "w") as env:
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


def handle_interrupt(signum, frame):
    """Handle interrupt signal (Ctrl+C) gracefully."""
    print("\n\nGracefully shutting down...")

    # Get the current event loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    # Cancel all tasks
    for task in asyncio.all_tasks(loop):
        task.cancel()

    # Stop the loop
    loop.stop()
    sys.exit(0)


async def cleanup():
    """Clean up resources before shutdown."""
    # Cancel all tracked tasks
    for task in _cleanup_tasks:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def amain():
    """Async main entry point."""
    # Setup environment
    setup_environment()
    check_dependencies()

    try:
        # Import tracklistify main after environment is set up
        from tracklistify.__main__ import main as tracklistify_main

        return await tracklistify_main()
    except ImportError as e:
        print(f"Error importing tracklistify: {e}")
        print(
            "Make sure you're in the correct directory and have installed requirements:"
        )
        print("pip install -r requirements.txt")
        return 1
    except asyncio.CancelledError:
        # Handle cancellation gracefully
        print("\nOperation cancelled by user")
        return 0
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        print("\nOperation cancelled by user")
        return 0
    except Exception as e:
        print(f"Error running tracklistify: {e}")
        return 1


def main():
    """Main entry point."""
    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)

    try:
        # Run the async main with proper cleanup
        return asyncio.run(amain())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 0


if __name__ == "__main__":
    sys.exit(main())
