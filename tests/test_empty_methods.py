"""
Tests for Phase 5 Group B: Empty Methods Documentation

Ensures empty template methods are properly documented.
"""

# Standard library imports
import inspect


class TestTemplateMethodDocumentation:
    """Test that template methods have proper documentation."""

    def test_setup_validation_has_docstring(self):
        """_setup_validation should have descriptive docstring."""
        from tracklistify.config.base import BaseConfig

        docstring = BaseConfig._setup_validation.__doc__
        assert docstring is not None, "_setup_validation should have a docstring"
        assert "template method" in docstring.lower(), (
            "_setup_validation docstring should explain it's a template method"
        )
        assert "subclass" in docstring.lower(), (
            "_setup_validation docstring should mention subclasses"
        )

    def test_validate_has_docstring(self):
        """_validate should have descriptive docstring."""
        from tracklistify.config.base import BaseConfig

        docstring = BaseConfig._validate.__doc__
        assert docstring is not None, "_validate should have a docstring"
        assert "template method" in docstring.lower(), (
            "_validate docstring should explain it's a template method"
        )

    def test_setup_validation_has_return_type(self):
        """_setup_validation should have return type annotation."""
        from tracklistify.config.base import BaseConfig

        annotations = BaseConfig._setup_validation.__annotations__
        assert "return" in annotations, "_setup_validation should have return type"

    def test_validate_has_return_type(self):
        """_validate should have return type annotation."""
        from tracklistify.config.base import BaseConfig

        annotations = BaseConfig._validate.__annotations__
        assert "return" in annotations, "_validate should have return type"

    def test_subclass_implements_setup_validation(self):
        """TrackIdentificationConfig should implement _setup_validation."""
        from tracklistify.config.base import TrackIdentificationConfig

        # Get source to verify it's not just inherited empty
        source = inspect.getsource(TrackIdentificationConfig._setup_validation)
        assert "add_type_rule" in source or "add_range_rule" in source, (
            "TrackIdentificationConfig._setup_validation should add validation rules"
        )
