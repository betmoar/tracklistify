#!/usr/bin/env python3
"""
Generate configuration documentation from code.
"""

# Standard library imports
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from tracklistify.config import get_config


def main():
    """Generate configuration documentation."""
    config = get_config()

    # Generate documentation
    docs_dir = project_root / "docs"
    docs_dir.mkdir(exist_ok=True)

    # Generate main configuration documentation
    output_file = docs_dir / "configuration.md"
    documentation = config.generate_documentation(str(output_file))

    # Also update .env.example with latest configuration
    env_example = project_root / ".env.example"
    if not env_example.exists():
        print("Warning: .env.example not found")

    print(f"Configuration documentation generated at: {output_file}")
    print("\nDocumentation preview:")
    print("=" * 80)
    preview = documentation.split("\n")[:20]  # Show first 20 lines
    print("\n".join(preview))
    print("..." if len(documentation.split("\n")) > 20 else "")
    print("=" * 80)


if __name__ == "__main__":
    main()
