"""String utilities for Tracklistify."""

import re
import unicodedata
from typing import Any


def sanitizer(text: Any, max_len: int = 200) -> str:
    """Sanitize potentially untrusted text for safe logging.

    - Normalize Unicode (NFKC)
    - Strip ANSI escape sequences and control characters
    - Collapse whitespace and strip
    - Truncate to a reasonable length
    """
    if not isinstance(text, str):
        text = str(text)

    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)

    # Remove ANSI escape sequences
    text = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", text)

    # Replace newlines/tabs with spaces
    text = re.sub(r"[\r\n\t]+", " ", text)

    # Remove other control characters
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"

    return text
