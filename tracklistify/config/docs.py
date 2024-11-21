"""Configuration documentation generator.

This module provides tools to generate documentation for the configuration system,
including markdown documentation, JSON schema, and example configurations.
"""

import json
from typing import Any, Dict, List, Optional, Set, Type, Union
from dataclasses import dataclass
from pathlib import Path

from .validation import (
    ConfigValidator,
    ValidationRule,
    TypeRule,
    RangeRule,
    PatternRule,
    PathRule,
    DependencyRule,
    PathRequirement
)

@dataclass
class ConfigField:
    """Configuration field documentation."""
    name: str
    type_info: str
    description: str
    default: Optional[Any] = None
    required: bool = True
    example: Optional[Any] = None
    constraints: List[str] = None

    def __post_init__(self):
        if self.constraints is None:
            self.constraints = []

class ConfigDocGenerator:
    """Configuration documentation generator."""
    
    def __init__(self, validator: ConfigValidator):
        self.validator = validator
        self.dependency_rules = getattr(self.validator, "dependency_rules", [])
        self.fields: Dict[str, ConfigField] = {}
        self._process_rules()
    
    def _process_rules(self) -> None:
        """Process validation rules to build field documentation."""
        for field, rules in self.validator.rules.items():
            field_doc = self._create_field_doc(field, rules)
            self.fields[field] = field_doc
    
    def _create_field_doc(self, field: str, rules: List[ValidationRule]) -> ConfigField:
        """Create field documentation from validation rules."""
        type_info = "any"
        description = []
        constraints = []
        example = None
        required = True
        
        for rule in rules:
            if isinstance(rule, TypeRule):
                type_info = self._get_type_info(rule.expected_type)
                required = not rule.allow_none
            elif isinstance(rule, RangeRule):
                constraints.extend(self._get_range_constraints(rule))
                example = self._generate_example_for_range(rule)
            elif isinstance(rule, PatternRule):
                constraints.append(f"Must match pattern: {rule.pattern}")
                example = self._generate_example_for_pattern(rule)
            elif isinstance(rule, PathRule):
                constraints.extend(self._get_path_constraints(rule))
                example = str(Path.home() / ".tracklistify" / field)
        
        # Add dependency constraints
        dep_constraints = self._get_dependency_constraints(field)
        if dep_constraints:
            constraints.extend(dep_constraints)
        
        return ConfigField(
            name=field,
            type_info=type_info,
            description=self._generate_description(field),
            required=required,
            example=example,
            constraints=constraints
        )
    
    def _get_type_info(self, type_: Union[Type, tuple[Type, ...]]) -> str:
        """Get type information string."""
        if isinstance(type_, tuple):
            return " | ".join(t.__name__ for t in type_)
        return type_.__name__
    
    def _get_range_constraints(self, rule: RangeRule) -> List[str]:
        """Get range rule constraints."""
        constraints = []
        if rule.min_value is not None:
            op = ">=" if rule.include_min else ">"
            constraints.append(f"Must be {op} {rule.min_value}")
        if rule.max_value is not None:
            op = "<=" if rule.include_max else "<"
            constraints.append(f"Must be {op} {rule.max_value}")
        return constraints
    
    def _get_path_constraints(self, rule: PathRule) -> List[str]:
        """Get path rule constraints."""
        constraints = []
        for req in rule.requirements:
            if req == PathRequirement.EXISTS:
                constraints.append("Path must exist")
            elif req == PathRequirement.IS_FILE:
                constraints.append("Must be a file")
            elif req == PathRequirement.IS_DIR:
                constraints.append("Must be a directory")
            elif req == PathRequirement.READABLE:
                constraints.append("Must be readable")
            elif req == PathRequirement.WRITABLE:
                constraints.append("Must be writable")
            elif req == PathRequirement.IS_ABSOLUTE:
                constraints.append("Must be an absolute path")
        return constraints
    
    def _get_dependency_constraints(self, field: str) -> List[str]:
        """Get dependency constraints for a field."""
        constraints = []
        for rule in self.dependency_rules:
            if field in rule.required_fields:
                deps = ", ".join(f"`{f}`" for f in rule.required_fields if f != field)
                if deps:
                    constraints.append(f"Required when using {deps}")
        return constraints
    
    def _generate_example_for_range(self, rule: RangeRule) -> Any:
        """Generate example value for range rule."""
        if rule.min_value is not None and rule.max_value is not None:
            if isinstance(rule.min_value, (int, float)):
                return (rule.min_value + rule.max_value) / 2
        return rule.min_value if rule.min_value is not None else rule.max_value
    
    def _generate_example_for_pattern(self, rule: PatternRule) -> str:
        """Generate example value for pattern rule."""
        if "client_id" in rule.field.lower():
            return "1234567890abcdef1234567890abcdef"
        return "example-value"
    
    def _generate_description(self, field: str) -> str:
        """Generate field description."""
        descriptions = {
            "confidence_threshold": "Confidence threshold for track detection",
            "segment_length": "Length of audio segments in seconds",
            "overlap": "Overlap between audio segments in seconds",
            "cache_enabled": "Enable caching of processed audio segments",
            "cache_dir": "Directory for caching processed audio segments",
            "output_dir": "Directory for output files",
            "spotify_client_id": "Spotify API client ID",
            "spotify_client_secret": "Spotify API client secret (sensitive)",
            "time_threshold": "Time threshold for merging similar tracks (in seconds)",
            "max_duplicates": "Maximum number of duplicate tracks to keep",
            "min_confidence": "Minimum confidence threshold for track detection"
        }
        return descriptions.get(field, f"Configuration value for {field}")
    
    def generate_markdown(self) -> str:
        """Generate markdown documentation."""
        docs = ["# Tracklistify Configuration\n"]
        docs.append("This document describes the configuration options for Tracklistify.\n")
        docs.append("## Configuration Fields\n")
        
        # Add fields in alphabetical order
        fields = sorted(self.fields.keys())
        for field in fields:
            field_doc = self.fields[field]
            docs.append(f"### {field}\n")
            docs.append(f"**Type:** `{field_doc.type_info}`\n")
            docs.append(f"{field_doc.description}\n")
            
            docs.append("**Properties:**")
            docs.append(f"- Required: {'Yes' if field_doc.required else 'No'}")
            docs.append("")
            
            if field_doc.constraints:
                docs.append("**Constraints:**")
                for constraint in field_doc.constraints:
                    docs.append(f"- {constraint}")
                docs.append("")
            
            if field_doc.example is not None:
                docs.append("**Example:**")
                docs.append("```python")
                docs.append(f"{field_doc.name} = {repr(field_doc.example)}")
                docs.append("```")
                docs.append("")
        
        # Add sensitive fields
        sensitive_fields = [
            "spotify_client_secret",
            "spotify_client_id",
            "acrcloud_access_key",
            "acrcloud_access_secret"
        ]
        
        for field in sensitive_fields:
            if field not in fields:
                docs.append(f"### {field}\n")
                docs.append(f"**Type:** `str`\n")
                docs.append(f"API credential for {field.replace('_', ' ').title()}\n")
                docs.append("**Properties:**")
                docs.append("- Required: Yes")
                docs.append("- Sensitive: Yes")
                docs.append("")
        
        return "\n".join(docs)
    
    def generate_schema(self) -> Dict[str, Any]:
        """Generate JSON schema."""
        properties = {}
        required = []
        
        for field in self.fields.values():
            field_schema = self._field_to_schema(field)
            properties[field.name] = field_schema
            if field.required:
                required.append(field.name)
        
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False
        }
    
    def _field_to_schema(self, field: ConfigField) -> Dict[str, Any]:
        """Convert field to JSON schema."""
        schema: Dict[str, Any] = {}
        
        # Type
        if field.type_info == "str":
            schema["type"] = "string"
        elif field.type_info == "int":
            schema["type"] = "integer"
        elif field.type_info == "float":
            schema["type"] = "number"
        elif field.type_info == "bool":
            schema["type"] = "boolean"
        else:
            schema["type"] = "string"
        
        # Description
        schema["description"] = field.description
        
        # Add constraints
        for constraint in field.constraints:
            if "pattern" in constraint.lower():
                schema["pattern"] = constraint.split(": ")[1]
            elif ">" in constraint or "<" in constraint:
                parts = constraint.split()
                if ">" in parts[1]:
                    schema["minimum"] = float(parts[3])
                    schema["exclusiveMinimum"] = "=" not in parts[1]
                elif "<" in parts[1]:
                    schema["maximum"] = float(parts[3])
                    schema["exclusiveMaximum"] = "=" not in parts[1]
        
        if not field.required:
            schema["type"] = [schema["type"], "null"]
        
        return schema
    
    def generate_example_config(self) -> Dict[str, Any]:
        """Generate example configuration."""
        example = {}
        for field in self.fields.values():
            if field.example is not None:
                example[field.name] = field.example
            elif field.type_info == "str":
                example[field.name] = "example-value"
            elif field.type_info == "int":
                example[field.name] = 0
            elif field.type_info == "float":
                example[field.name] = 0.0
            elif field.type_info == "bool":
                example[field.name] = False
        return example
