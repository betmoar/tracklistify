"""Tests for dev_cli — config, commands, logging (Q7, 2026-08 review)."""

import json
from pathlib import Path


# ---------------------------------------------------------------------------
# config.py
# ---------------------------------------------------------------------------


class TestToolsConfiguration:
    """Tests for ToolsConfiguration — the dev CLI config loader."""

    def test_loads_valid_tools_json(self, tmp_path: Path):
        """A valid tools.json loads tools and list_tools() returns their names."""
        tools = {
            "lint": {"command": "ruff", "description": "Lint the code"},
            "test": {"command": "pytest", "description": "Run tests"},
        }
        tools_path = tmp_path / "tools.json"
        tools_path.write_text(json.dumps(tools))

        from tracklistify.dev_cli.config import ToolsConfiguration

        cfg = ToolsConfiguration(config_path=str(tools_path))
        assert sorted(cfg.list_tools()) == ["lint", "test"]

    def test_missing_tools_json_falls_back_to_empty(self, tmp_path: Path):
        """Missing tools.json must fall back to an empty config, not crash.

        Before the fix, a ConfigurationError early-exit blocked the fallback
        and the class was unconstructible without a tools.json.
        """
        missing_path = str(tmp_path / "nonexistent.json")

        from tracklistify.dev_cli.config import ToolsConfiguration

        cfg = ToolsConfiguration(config_path=missing_path)
        assert cfg.list_tools() == {}

    def test_malformed_tools_json_degrades_gracefully(self, tmp_path: Path):
        """Malformed tools.json must degrade to empty config, not crash."""
        bad_path = tmp_path / "tools.json"
        bad_path.write_text("not json at all {{{")

        from tracklistify.dev_cli.config import ToolsConfiguration

        cfg = ToolsConfiguration(config_path=str(bad_path))
        assert cfg.list_tools() == {}

    def test_get_tool_returns_config_for_valid_tool(self, tmp_path: Path):
        """get_tool returns the config dict for a known tool."""
        tools = {
            "lint": {
                "command": "ruff",
                "description": "Lint",
                "args": "check .",
            }
        }
        tools_path = tmp_path / "tools.json"
        tools_path.write_text(json.dumps(tools))

        from tracklistify.dev_cli.config import ToolsConfiguration

        cfg = ToolsConfiguration(config_path=str(tools_path))
        tool = cfg.get_tool("lint")
        assert tool["command"] == "ruff"
        assert tool["description"] == "Lint"
        assert tool["args"] == "check ."

    def test_get_tool_returns_none_for_unknown(self, tmp_path: Path):
        """get_tool returns None for an unknown tool name."""
        tools = {"lint": {"command": "ruff", "description": "Lint"}}
        tools_path = tmp_path / "tools.json"
        tools_path.write_text(json.dumps(tools))

        from tracklistify.dev_cli.config import ToolsConfiguration

        cfg = ToolsConfiguration(config_path=str(tools_path))
        assert cfg.get_tool("nonexistent") is None
