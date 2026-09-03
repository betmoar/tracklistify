"""The dependabot config obeys the rules GitHub enforces server-side.

A config that is valid YAML can still be rejected — and a rejected config
disables Dependabot ENTIRELY, not just the offending entry, so every update
including the security ones stops silently. GitHub reports it through a
check run rather than the Actions log, which is easy to miss.

That is exactly what happened: a second `uv` + `/` entry, added to give
yt-dlp its own schedule, produced

    Update configs must have a unique combination of 'package-ecosystem',
    'directory', and 'target-branch'. Ecosystem 'uv' has overlapping
    directories.
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_dependabot_config import validate  # noqa: E402

CONFIG = Path(__file__).resolve().parents[1] / ".github" / "dependabot.yml"


@pytest.fixture
def config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_config_is_valid(config):
    """The checked-in config passes every rule the validator knows."""
    assert validate(config) == []


def test_no_duplicate_ecosystem_directory_pairs(config):
    """No two entries share (package-ecosystem, directory, target-branch)."""
    keys = [
        (u.get("package-ecosystem"), u.get("directory"), u.get("target-branch"))
        for u in config["updates"]
    ]
    assert len(keys) == len(set(keys)), f"duplicate update entries: {keys}"


def test_validator_catches_a_duplicate_entry():
    """The validator must actually reject what GitHub rejects.

    Without this the checker could be vacuously green — it is the assertion
    that proves the rule is enforced rather than merely written down.
    """
    duplicated = {
        "version": 2,
        "updates": [
            {
                "package-ecosystem": "uv",
                "directory": "/",
                "schedule": {"interval": "weekly"},
            },
            {
                "package-ecosystem": "uv",
                "directory": "/",
                "schedule": {"interval": "daily"},
            },
        ],
    }
    errors = validate(duplicated)
    assert errors, "a duplicate (ecosystem, directory) pair must be rejected"
    assert "duplicates" in errors[0]


def test_yt_dlp_is_grouped_separately(config):
    """yt-dlp gets its own group, not folded into the general roll-up.

    A stale yt-dlp pin is a total YouTube outage rather than a missing
    feature (#91), so its bumps must not wait behind an unrelated group
    that a reviewer is sitting on.
    """
    groups = config["updates"][0]["groups"]
    assert "yt-dlp" in groups, "yt-dlp has no group of its own"
    assert groups["yt-dlp"]["patterns"] == ["yt-dlp"]

    for name, group in groups.items():
        if name == "yt-dlp":
            continue
        assert "yt-dlp" in group.get("exclude-patterns", []), (
            f"group {name!r} does not exclude yt-dlp, so it can absorb the "
            "bump the dedicated group exists to surface"
        )


def test_schedule_is_daily(config):
    """Daily, so a yt-dlp break is caught in a day rather than a week."""
    assert config["updates"][0]["schedule"]["interval"] == "daily"
