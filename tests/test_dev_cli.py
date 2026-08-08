"""Tests for dev_cli — config, commands, logging (Q7, 2026-08 review)."""

import json
import logging
import sys
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

    def test_malformed_tools_json_degrades_gracefully(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        """Malformed tools.json must degrade to empty config, not crash."""
        bad_path = tmp_path / "tools.json"
        bad_path.write_text("not json at all {{{")

        from tracklistify.dev_cli.config import ToolsConfiguration

        caplog.set_level(logging.WARNING, logger="dev_cli")
        cfg = ToolsConfiguration(config_path=str(bad_path))
        assert cfg.list_tools() == {}
        assert any(record.levelno >= logging.WARNING for record in caplog.records)

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
            [sys.executable, "-c", "print('arg with spaces')"], check=True
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


# ---------------------------------------------------------------------------
# logging.py
# ---------------------------------------------------------------------------


class TestDevCliLogger:
    """Tests for DevCliLogger — the dev CLI logging setup."""

    def setup_method(self):
        """Clear handlers on the shared 'dev_cli' logger before each test.

        DevCliLogger() always binds to logging.getLogger("dev_cli"), a
        process-wide singleton logger. Handlers added by setup() in one
        test would otherwise accumulate and leak into the next.
        """
        logging.getLogger("dev_cli").handlers.clear()

    def teardown_method(self):
        """Close and clear handlers on the shared 'dev_cli' logger after each test.

        Mirrors setup_method — without this, the last logging test in this
        class leaks an open RotatingFileHandler pointing at a deleted
        tmp_path dir (plus a stdout handler) into subsequent test modules.
        """
        dev_cli_logger = logging.getLogger("dev_cli")
        for handler in dev_cli_logger.handlers:
            handler.close()
        dev_cli_logger.handlers.clear()

    def test_setup_constructs_without_error(self, tmp_path: Path):
        """setup() must not raise."""
        from tracklistify.dev_cli.logging import DevCliLogger

        logger = DevCliLogger()
        logger.setup(debug=False, log_dir=None)
        # The underlying stdlib logger is accessible.
        assert logger.logger is not None

    def test_setup_debug_sets_debug_level(self, tmp_path: Path):
        """setup(debug=True) sets the console handler to DEBUG."""
        import logging

        from tracklistify.dev_cli.logging import DevCliLogger

        logger = DevCliLogger()
        logger.setup(debug=True, log_dir=None)
        # The console handler (first handler) should be at DEBUG level.
        console_handler = logger.logger.handlers[0]
        assert console_handler.level == logging.DEBUG

    def test_setup_log_dir_creates_directory_and_file(self, tmp_path: Path):
        """setup(log_dir=...) creates the directory and a log file."""
        from tracklistify.dev_cli.logging import DevCliLogger

        log_dir = tmp_path / "logs"
        logger = DevCliLogger()
        logger.setup(debug=False, log_dir=str(log_dir))

        assert log_dir.is_dir()
        log_files = list(log_dir.glob("dev-cli-*.log"))
        assert len(log_files) == 1

    def test_setup_is_idempotent(self, tmp_path: Path):
        """Calling setup() twice must not add duplicate handlers."""
        from tracklistify.dev_cli.logging import DevCliLogger

        logger = DevCliLogger()
        logger.setup(debug=False, log_dir=None)
        handler_count = len(logger.logger.handlers)
        logger.setup(debug=False, log_dir=None)
        assert len(logger.logger.handlers) == handler_count

    def test_get_context_logger_returns_logger(self):
        """get_context_logger returns a LoggerAdapter."""
        from tracklistify.dev_cli.logging import DevCliLogger

        logger = DevCliLogger()
        ctx = logger.get_context_logger(config_class="TestClass")
        assert ctx is not None
