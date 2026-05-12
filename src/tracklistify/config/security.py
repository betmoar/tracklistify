"""
Security utilities for configuration management.
"""

# Standard library imports
from typing import Any, Dict, Set

# Local/package imports
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)

# Fields that should be masked in logs and error messages
SENSITIVE_FIELDS = {
    "access_key",
    "access_secret",
    "secret",
    "password",
    "token",
    "api_key",
    "client_secret",
    "private_key",
    "auth_token",
}

# Sensitive field patterns for environment variables
SENSITIVE_PATTERNS = [
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "key",
    "api_key",
    "apikey",
    "access_key",
    "access_secret",
    "client_secret",
    "client_id",
    "auth",
    "credential",
]


def is_sensitive_key(key: str) -> bool:
    """Check if environment variable key is sensitive.

    Args:
        key: Environment variable name

    Returns:
        True if key appears to contain sensitive data

    Examples:
        >>> is_sensitive_key("TRACKLISTIFY_API_KEY")
        True
        >>> is_sensitive_key("TRACKLISTIFY_DEBUG")
        False
    """
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in SENSITIVE_PATTERNS)


def mask_sensitive_value(key: str, value: str) -> str:
    """Mask sensitive values for logging.

    Shows first 3 and last 3 characters for sensitive values,
    masking the middle with asterisks.

    Args:
        key: Environment variable or field name
        value: Value to potentially mask

    Returns:
        Masked value if sensitive, original value if not

    Examples:
        >>> mask_sensitive_value("TRACKLISTIFY_API_KEY", "secret123456")
        'sec*****456'
        >>> mask_sensitive_value("TRACKLISTIFY_DEBUG", "true")
        'true'
        >>> mask_sensitive_value("TRACKLISTIFY_PASSWORD", "short")
        '***'
    """
    if not is_sensitive_key(key):
        return value

    if not value or len(value) < 8:
        return "***"

    # Show first 3 and last 3 characters
    return f"{value[:3]}*****{value[-3:]}"


def is_sensitive_field(field_name: str) -> bool:
    """Check if a field name corresponds to sensitive data."""
    return any(sensitive in field_name.lower() for sensitive in SENSITIVE_FIELDS)


def detect_sensitive_fields(data: Dict[str, Any], parent_key: str = "") -> Set[str]:
    """
    Recursively detect sensitive fields in a dictionary.

    Args:
        data: Dictionary to scan
        parent_key: Parent key for nested fields

    Returns:
        Set of sensitive field names
    """
    sensitive_fields = set()

    for key, value in data.items():
        current_key = f"{parent_key}.{key}" if parent_key else key

        # Check if the current field is sensitive
        if is_sensitive_field(key):
            sensitive_fields.add(current_key)

        # Recursively check nested dictionaries
        if isinstance(value, dict):
            sensitive_fields.update(detect_sensitive_fields(value, current_key))

    return sensitive_fields


def mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mask sensitive values in a dictionary.

    Args:
        data: Dictionary containing potentially sensitive data

    Returns:
        Dict[str, Any]: Dictionary with sensitive values masked
    """
    if not isinstance(data, dict):
        return data

    masked = {}
    for key, value in data.items():
        if isinstance(value, dict):
            masked[key] = mask_sensitive_data(value)
        elif isinstance(value, str) and is_sensitive_field(key):
            masked[key] = mask_sensitive_value(key, value)
        else:
            masked[key] = value
    return masked
