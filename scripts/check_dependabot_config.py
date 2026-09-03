#!/usr/bin/env python3
"""Validate .github/dependabot.yml against the constraints GitHub enforces.

Parsing as YAML is not enough: the config that broke CI was valid YAML and
rejected by Dependabot, which validates its own schema server-side and
reports through a check run rather than the Actions log — so `yaml.safe_load`
returning cleanly proves nothing.

A rejected config disables Dependabot ENTIRELY, not just the offending entry,
which means a mistake here silently stops every update including the security
ones.

Run: uv run python scripts/check_dependabot_config.py
"""

import sys
from pathlib import Path

import yaml

CONFIG = Path(".github/dependabot.yml")


def validate(config: dict) -> list[str]:
    """Return a list of rule violations; empty means the config is valid."""
    errors: list[str] = []

    if config.get("version") != 2:
        errors.append(f"version must be 2, got {config.get('version')!r}")

    seen: dict[tuple, int] = {}
    for i, update in enumerate(config.get("updates", [])):
        # The rule that broke us: "Update configs must have a unique
        # combination of 'package-ecosystem', 'directory', and
        # 'target-branch'." Per-dependency *scheduling* is therefore
        # impossible; per-dependency *grouping* via `groups` is the
        # supported route, and `groups` has no such limit.
        key = (
            update.get("package-ecosystem"),
            update.get("directory") or tuple(update.get("directories", [])),
            update.get("target-branch"),
        )
        if key in seen:
            errors.append(
                f"updates[{i}] duplicates updates[{seen[key]}]: "
                f"ecosystem={key[0]!r} directory={key[1]!r} "
                f"target-branch={key[2]!r}. Only one entry per combination is "
                "allowed — use `groups` for per-dependency treatment."
            )
        seen[key] = i

        if not update.get("schedule", {}).get("interval"):
            errors.append(f"updates[{i}]: schedule.interval is required")

    return errors


def main() -> int:
    if not CONFIG.exists():
        print(f"{CONFIG}: not found")
        return 1

    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    errors = validate(config)

    if errors:
        print(f"{CONFIG} is invalid:\n")
        for error in errors:
            print(f"  - {error}")
        print("\nA rejected config disables Dependabot entirely.")
        return 1

    entries = len(config.get("updates", []))
    groups = sum(len(u.get("groups", {})) for u in config.get("updates", []))
    print(f"{CONFIG} OK: {entries} update entry/entries, {groups} group(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
