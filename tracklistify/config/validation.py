"""
Configuration validation system.

This module provides a comprehensive validation system for configuration values,
including type checking, range validation, dependency validation, and path validation.
"""

# Standard library imports
import re
from dataclasses import fields
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Type, TypeVar, Union

# Local/package imports

T = TypeVar("T")


class ValidationError(Exception):
    """Base exception for validation errors."""

    pass


class ConfigValidationError(ValidationError):
    """Raised when configuration validation fails."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


class DependencyError(ValidationError):
    """Raised when configuration dependencies are not satisfied."""

    pass


class RangeValidationError(ValidationError):
    """Raised when a value is outside its valid range."""

    pass


class PathValidationError(ValidationError):
    """Raised when a path validation fails."""

    pass


class PathRequirement(Enum):
    """Requirements for path validation."""

    EXISTS = "exists"
    READABLE = "readable"
    WRITABLE = "writable"
    EXECUTABLE = "executable"
    IS_FILE = "is_file"
    IS_DIR = "is_dir"
    IS_ABSOLUTE = "is_absolute"


class ValidationRule:
    """Base class for validation rules."""

    def __init__(self, field: str, message: Optional[str] = None):
        self.field = field
        self.message = message

    def validate(self, value: Any) -> None:
        """Validate a value against this rule."""
        raise NotImplementedError


class TypeRule(ValidationRule):
    """Rule for type validation."""

    def __init__(
        self,
        field: str,
        expected_type: Union[Type, tuple[Type, ...]],
        message: Optional[str] = None,
        allow_none: bool = False,
    ):
        super().__init__(field, message)
        self.expected_type = expected_type
        self.allow_none = allow_none

    def validate(self, value: Any) -> None:
        """Validate value type."""
        if value is None:
            if not self.allow_none:
                raise ConfigValidationError(
                    self.field, self.message or "Value cannot be None"
                )
            return

        if not isinstance(value, self.expected_type):
            raise ConfigValidationError(
                self.field,
                self.message
                or f"Expected type {self.expected_type.__name__}, got {type(value).__name__}",
            )


class RangeRule(ValidationRule):
    """Rule for range validation."""

    def __init__(
        self,
        field: str,
        min_value: Optional[Any],
        max_value: Optional[Any],
        message: Optional[str] = None,
        include_min: bool = True,
        include_max: bool = True,
    ):
        super().__init__(field, message)
        self.min_value = min_value
        self.max_value = max_value
        self.include_min = include_min
        self.include_max = include_max
        self.description = (
            "must be positive"
            if min_value == 0
            else f"must be between {min_value} and {max_value}"
        )

    def validate(self, value: Any) -> None:
        """Validate value range."""
        if value is None:
            return

        if self.min_value is not None:
            if self.include_min and value < self.min_value:
                raise RangeValidationError(
                    f"{self.field}: Value {value} is less than minimum {self.min_value}"
                )
            if not self.include_min and value <= self.min_value:
                raise RangeValidationError(
                    f"{self.field}: Value {value} is less than or equal to minimum {self.min_value}"
                )

        if self.max_value is not None:
            if self.include_max and value > self.max_value:
                raise RangeValidationError(
                    f"{self.field}: Value {value} is greater than maximum {self.max_value}"
                )
            if not self.include_max and value >= self.max_value:
                raise RangeValidationError(
                    f"{self.field}: Value {value} is greater than or equal to maximum {self.max_value}"
                )


class PatternRule(ValidationRule):
    """Rule for pattern validation."""

    def __init__(
        self,
        field: str,
        pattern: str,
        message: Optional[str] = None,
        is_regex: bool = False,
    ):
        super().__init__(field, message)
        self.pattern = pattern
        self.is_regex = is_regex

    def validate(self, value: str) -> None:
        """Validate value against pattern."""
        if value is None:
            return

        if not isinstance(value, str):
            raise ConfigValidationError(
                self.field,
                f"Expected string for pattern matching, got {type(value).__name__}",
            )

        if self.is_regex:
            if not re.match(self.pattern, value):
                raise ConfigValidationError(
                    self.field,
                    self.message or f"Value does not match pattern {self.pattern}",
                )
        else:
            if not value.startswith(self.pattern):
                raise ConfigValidationError(
                    self.field,
                    self.message or f"Value does not start with {self.pattern}",
                )


class PathRule(ValidationRule):
    """Rule for path validation."""

    def __init__(
        self,
        field: str,
        requirements: Set[PathRequirement],
        message: Optional[str] = None,
        create_if_missing: bool = False,
    ):
        super().__init__(field, message)
        self.requirements = requirements
        self.create_if_missing = create_if_missing

    def validate(self, value: Any) -> None:
        """Validate path value."""
        if value is None:
            return

        if not isinstance(value, (str, Path)):
            raise PathValidationError(
                f"{self.field}: Expected string or Path, got {type(value).__name__}"
            )

        # Convert to string and check if empty
        str_value = str(value).strip()
        if not str_value:
            raise ValueError(f"{self.field}: Path cannot be empty")

        path = Path(value)

        if PathRequirement.IS_ABSOLUTE in self.requirements and not path.is_absolute():
            raise PathValidationError(f"{self.field}: Path must be absolute")

        # Handle directory creation before existence checks
        if self.create_if_missing and PathRequirement.IS_DIR in self.requirements:
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise PathValidationError(
                    f"{self.field}: Failed to create directory: {e}"
                )

        if PathRequirement.EXISTS in self.requirements and not path.exists():
            if self.create_if_missing:
                try:
                    if PathRequirement.IS_DIR not in self.requirements:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.touch()
                except Exception as e:
                    raise PathValidationError(
                        f"{self.field}: Failed to create path: {e}"
                    )
            else:
                raise PathValidationError(f"{self.field}: Path does not exist")

        if PathRequirement.IS_FILE in self.requirements and not path.is_file():
            raise PathValidationError(f"{self.field}: Path must be a file")

        if PathRequirement.IS_DIR in self.requirements and not path.is_dir():
            raise PathValidationError(f"{self.field}: Path must be a directory")

        if PathRequirement.READABLE in self.requirements:
            try:
                if path.is_file():
                    with open(path, "r"):
                        pass
            except Exception as e:
                raise PathValidationError(f"{self.field}: Path is not readable: {e}")

        if PathRequirement.WRITABLE in self.requirements:
            try:
                if path.is_file():
                    with open(path, "a"):
                        pass
                else:
                    # Create directory if it doesn't exist
                    path.mkdir(parents=True, exist_ok=True)
                    # Test writability with a temporary file
                    test_file = path / ".write_test"
                    test_file.touch()
                    test_file.unlink()
            except Exception as e:
                raise PathValidationError(f"{self.field}: Path is not writable: {e}")


class DependencyRule(ValidationRule):
    """Rule for dependency validation."""

    def __init__(
        self,
        field: str,
        required_fields: Set[str],
        message: Optional[str] = None,
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ):
        super().__init__(field, message)
        self.required_fields = required_fields
        self.condition = condition

    def validate(self, config: Dict[str, Any]) -> None:
        """Validate dependencies between fields."""
        if self.condition is not None and not self.condition(config):
            return

        missing_fields = {
            field
            for field in self.required_fields
            if field not in config or config[field] is None
        }

        if missing_fields:
            raise DependencyError(
                self.message
                or f"Missing required fields for {self.field}: {', '.join(missing_fields)}"
            )


class ConfigValidator:
    """Configuration validator with comprehensive validation rules."""

    def __init__(self):
        self.rules: Dict[str, List[ValidationRule]] = {}
        self.dependency_rules: List[DependencyRule] = []

    def add_rule(self, rule: ValidationRule) -> None:
        """Add a validation rule."""
        if rule.field not in self.rules:
            self.rules[rule.field] = []
        self.rules[rule.field].append(rule)

    def add_type_rule(
        self,
        field: str,
        expected_type: Union[Type, tuple[Type, ...]],
        allow_none: bool = False,
        message: Optional[str] = None,
    ) -> None:
        """Add a type validation rule."""
        self.add_rule(TypeRule(field, expected_type, message, allow_none))

    def add_range_rule(
        self,
        field: str,
        min_value: Optional[Any] = None,
        max_value: Optional[Any] = None,
        include_min: bool = True,
        include_max: bool = True,
        message: Optional[str] = None,
    ) -> None:
        """Add a range validation rule."""
        self.add_rule(
            RangeRule(field, min_value, max_value, message, include_min, include_max)
        )

    def add_pattern_rule(
        self,
        field: str,
        pattern: str,
        is_regex: bool = False,
        message: Optional[str] = None,
    ) -> None:
        """Add a pattern validation rule."""
        self.add_rule(PatternRule(field, pattern, message, is_regex))

    def add_path_rule(
        self,
        field: str,
        requirements: Set[PathRequirement],
        create_if_missing: bool = False,
        message: Optional[str] = None,
    ) -> None:
        """Add a path validation rule."""
        self.add_rule(PathRule(field, requirements, message, create_if_missing))

    def add_dependency_rule(
        self,
        field: str,
        required_fields: Set[str],
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
        message: Optional[str] = None,
    ) -> None:
        """Add a dependency validation rule."""
        rule = DependencyRule(field, required_fields, message, condition)
        self.dependency_rules.append(rule)

    def validate(self, config: Dict[str, Any]) -> None:
        """
        Validate configuration against all rules.

        Args:
            config: Configuration dictionary to validate

        Raises:
            ValidationError: If validation fails
        """
        # Validate individual fields
        for field, value in config.items():
            self.validate_field(field, value)

        # Validate dependencies
        for rule in self.dependency_rules:
            rule.validate(config)

    def validate_field(self, field: str, value: Any) -> None:
        """
        Validate a single field value.

        Args:
            field: Field name to validate
            value: Value to validate

        Raises:
            ValidationError: If validation fails
        """
        if field in self.rules:
            for rule in self.rules[field]:
                rule.validate(value)

    def validate_track_config(self, config: Dict[str, Any]) -> None:
        if "time_threshold" in config:
            if (
                not isinstance(config["time_threshold"], (int, float))
                or config["time_threshold"] <= 0
            ):
                raise ValueError("Time threshold must be a positive number")

        if "max_duplicates" in config:
            if (
                not isinstance(config["max_duplicates"], int)
                or config["max_duplicates"] < 0
            ):
                raise ValueError("Max duplicates must be a non-negative integer")

        if "min_confidence" in config:
            if (
                not isinstance(config["min_confidence"], float)
                or not 0 <= config["min_confidence"] <= 1
            ):
                raise ValueError("Minimum confidence must be a float between 0 and 1")


def validate_field_type(value: Any, field_type: Type[T]) -> T:
    """Validate that a value matches the expected type."""
    if not isinstance(value, field_type):
        raise TypeError(
            f"Expected type {field_type.__name__}, got {type(value).__name__}"
        )
    return value


def validate_path(
    value: Union[str, Path], field_name: str = "path", must_exist: bool = True
) -> Path:
    """
    Validate a path value.

    Args:
        value: Path value to validate
        field_name: Name of the field being validated
        must_exist: Whether the path must exist

    Returns:
        Path: Validated path

    Raises:
        ValueError: If path validation fails
    """
    if not str(value).strip():
        raise ValueError(f"{field_name}: Path cannot be empty")

    try:
        path = Path(value).resolve()
        if must_exist and not path.exists():
            raise ValueError(f"{field_name}: Path does not exist: {path}")
        return path
    except Exception as e:
        raise ValueError(f"{field_name}: Invalid path: {e}")


def validate_positive_float(value: float, field_name: str) -> float:
    """
    Validate that a float value is positive.

    Args:
        value: Value to validate
        field_name: Name of the field being validated

    Returns:
        float: The validated value

    Raises:
        TypeError: If value is not a float
        ValueError: If value is not positive
    """
    if not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number, got {type(value).__name__}")

    value = float(value)
    if value <= 0:
        raise ValueError(f"{field_name} must be positive, got {value}")

    return value


def validate_positive_int(value: int, field_name: str) -> int:
    """
    Validate that an integer value is positive.

    Args:
        value: Value to validate
        field_name: Name of the field being validated

    Returns:
        int: The validated value

    Raises:
        TypeError: If value is not an integer
        ValueError: If value is not positive
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer, got {type(value).__name__}")

    if value <= 0:
        raise ValueError(f"{field_name} must be positive, got {value}")

    return value


def validate_probability(value: float, field_name: str) -> float:
    """
    Validate that a value is a valid probability (between 0 and 1).

    Args:
        value: Value to validate
        field_name: Name of the field being validated

    Returns:
        float: The validated value

    Raises:
        TypeError: If value is not a float
        ValueError: If value is not between 0 and 1
    """
    if not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number, got {type(value).__name__}")

    value = float(value)
    if not 0 <= value <= 1:
        raise ValueError(f"{field_name} must be between 0 and 1, got {value}")

    return value


def validate_string_list(value: List[str], field_name: str) -> List[str]:
    """
    Validate that a value is a list of strings.

    Args:
        value: Value to validate
        field_name: Name of the field being validated

    Returns:
        List[str]: The validated value

    Raises:
        TypeError: If value is not a list of strings
    """
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")

    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must contain only strings")

    return value


def validate_optional_string(value: Optional[str], field_name: str) -> Optional[str]:
    """
    Validate that a value is either None or a string.

    Args:
        value: Value to validate
        field_name: Name of the field being validated

    Returns:
        Optional[str]: The validated value

    Raises:
        TypeError: If value is not None or a string
    """
    if value is not None and not isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a string or None, got {type(value).__name__}"
        )

    return value


def validate_config_dict(
    config: Dict[str, Any], config_class: Type[T]
) -> Dict[str, Any]:
    """Validate a configuration dictionary against a configuration class."""
    validated = {}
    config_fields = {field.name: field for field in fields(config_class)}

    # Check for unknown fields
    unknown_fields = set(config.keys()) - set(config_fields.keys())
    if unknown_fields:
        raise ValueError(f"Unknown configuration fields: {', '.join(unknown_fields)}")

    # Validate each field
    for name, field in config_fields.items():
        value = config.get(name)
        if value is None and not field.default:
            raise ValueError(f"Missing required field: {name}")
        if value is not None:
            validated[name] = validate_field_type(value, field.type)

    return validated


__all__ = [
    "validate_field_type",
    "validate_path",
    "validate_positive_float",
    "validate_positive_int",
    "validate_probability",
    "validate_string_list",
    "validate_optional_string",
    "validate_config_dict",
]
