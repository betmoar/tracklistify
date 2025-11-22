"""Time formatting utilities."""

from tracklistify.utils.constants import SECONDS_PER_HOUR, SECONDS_PER_MINUTE


def format_seconds_to_hhmmss(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format.

    Args:
        seconds: Time in seconds to format

    Returns:
        String in HH:MM:SS format
    """
    hours = int(seconds // SECONDS_PER_HOUR)
    minutes = int((seconds % SECONDS_PER_HOUR) // SECONDS_PER_MINUTE)
    secs = int(seconds % SECONDS_PER_MINUTE)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
