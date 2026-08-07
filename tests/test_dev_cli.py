"""Tests for dev_cli — config, commands, logging (Q7, 2026-08 review)."""

import json
from pathlib import Path

import pytest


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


# ---------------------------------------------------------------------------
# commands/run.py
# ---------------------------------------------------------------------------


class TestRunCommand:
    """Tests for RunCommand — the dev CLI shell command execution."""

    def test_run_shell_command_str_input(self):
        """run_shell_command with a string command."""
        from tracklistify.dev_cli.commands.run import RunCommand

        cmd = RunCommand()
        result = cmd.run_shell_command("echo hello", check=True)
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_run_shell_command_list_input(self):
        """run_shell_command with a list command — args survive verbatim."""
        from tracklistify.dev_cli.commands.run import RunCommand

        cmd = RunCommand()
        result = cmd.run_shell_command(["echo", "hello world"], check=True)
        assert result.returncode == 0
        assert "hello world" in result.stdout

    def test_run_shell_command_list_input_preserves_spaced_args(self):
        """List-form: spaced/quoted args survive as one argv element.

        This is the arg-mangling fix — the old code joined the list into a
        string and let shlex re-split it, mangling args with spaces.
        """
        from tracklistify.dev_cli.commands.run import RunCommand

        cmd = RunCommand()
        # python -c "print('arg with spaces')" — the script is one arg.
        result = cmd.run_shell_command(
            ["python", "-c", "print('arg with spaces')"], check=True
        )
        assert result.returncode == 0
        assert "arg with spaces" in result.stdout

    def test_run_shell_command_empty_input(self):
        """run_shell_command with empty input raises IndexError (no argv[0]).

        shlex.split("") returns [], and subprocess.run([], ...) internally
        does `executable = args[0]`, which raises IndexError on an empty
        list (verified against the actual CPython 3.11 subprocess module —
        not ValueError as might be assumed).
        """
        from tracklistify.dev_cli.commands.run import RunCommand

        cmd = RunCommand()
        with pytest.raises(IndexError):
            cmd.run_shell_command("", check=True)

    def test_run_shell_command_nonzero_exit(self):
        """run_shell_command with a failing command raises ToolExecutionError."""
        from tracklistify.dev_cli.commands.run import RunCommand
        from tracklistify.dev_cli.exceptions import ToolExecutionError

        cmd = RunCommand()
        with pytest.raises(ToolExecutionError) as exc_info:
            # `false` is a standard Unix command that exits 1 with shell=False.
            cmd.run_shell_command("false", check=True)
        assert exc_info.value.exit_code == 1

    def test_run_shell_command_nonexistent_command(self):
        """run_shell_command with a nonexistent command raises FileNotFoundError."""
        from tracklistify.dev_cli.commands.run import RunCommand

        cmd = RunCommand()
        with pytest.raises(FileNotFoundError):
            cmd.run_shell_command("nonexistent_command_xyzzy", check=True)
