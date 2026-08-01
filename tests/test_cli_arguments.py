"""
Tests for Issue #4: CLI Arguments Ignored

Validates that CLI arguments are properly passed from cli.py to AsyncApp
and that AsyncApp respects these argument overrides.
"""

# Standard library imports
from unittest.mock import AsyncMock, patch

# Third-party imports
import pytest

# Local/package imports
from tracklistify.cli import main, parse_args
from tracklistify.config import TrackIdentificationConfig
from tracklistify.core import AsyncApp


class TestCLIParsing:
    """Test that CLI arguments are parsed correctly."""

    def test_default_formats(self):
        """Test default formats value."""
        args = parse_args(["test.mp3"])
        assert args.formats == "all"

    def test_formats_json(self):
        """Test --formats json argument."""
        args = parse_args(["test.mp3", "-f", "json"])
        assert args.formats == "json"

    def test_formats_markdown(self):
        """Test --formats markdown argument."""
        args = parse_args(["test.mp3", "--formats", "markdown"])
        assert args.formats == "markdown"

    def test_provider_argument(self):
        """Test --provider argument."""
        args = parse_args(["test.mp3", "-p", "acrcloud"])
        assert args.provider == "acrcloud"

    def test_no_fallback_default(self):
        """When --no-fallback is omitted, args.no_fallback must be None
        so the CLI can defer to config.fallback_enabled instead of
        clobbering it with a concrete bool."""
        args = parse_args(["test.mp3"])
        assert args.no_fallback is None

    def test_no_fallback_flag(self):
        """Test --no-fallback flag."""
        args = parse_args(["test.mp3", "--no-fallback"])
        assert args.no_fallback is True

    def test_combined_arguments(self):
        """Test multiple arguments together."""
        args = parse_args(["test.mp3", "-f", "json", "-p", "shazam", "--no-fallback"])
        assert args.formats == "json"
        assert args.provider == "shazam"
        assert args.no_fallback is True

    def test_verbose_default_false(self):
        """Test --verbose default is False (Issue #9)."""
        args = parse_args(["test.mp3"])
        assert args.verbose is False, "verbose should default to False"

    def test_verbose_flag_sets_true(self):
        """Test --verbose flag sets True."""
        args = parse_args(["test.mp3", "-v"])
        assert args.verbose is True

    def test_debug_default_false(self):
        """Test --debug default is False."""
        args = parse_args(["test.mp3"])
        assert args.debug is False

    def test_debug_flag_sets_true(self):
        """Test --debug flag sets True."""
        args = parse_args(["test.mp3", "-d"])
        assert args.debug is True


@pytest.mark.asyncio
class TestCLIArgumentPassing:
    """Test that CLI arguments are passed to AsyncApp."""

    async def test_formats_passed_to_app(self, tmp_path):
        """Ensure --formats argument is passed to process_input."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"fake audio data")

        with patch("tracklistify.cli.AsyncApp") as mock_app_class:
            mock_app = AsyncMock()
            mock_app.process_input = AsyncMock(return_value=[])
            mock_app.close = AsyncMock()
            mock_app_class.return_value = mock_app

            args = parse_args([str(test_file), "-f", "json"])
            await main(args)

            # Verify process_input called with formats
            mock_app.process_input.assert_called_once()
            call_kwargs = mock_app.process_input.call_args.kwargs
            assert "formats" in call_kwargs
            assert call_kwargs["formats"] == "json"

    async def test_provider_passed_to_app(self, tmp_path):
        """Ensure --provider argument is passed to process_input."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"fake audio data")

        with patch("tracklistify.cli.AsyncApp") as mock_app_class:
            mock_app = AsyncMock()
            mock_app.process_input = AsyncMock(return_value=[])
            mock_app.close = AsyncMock()
            mock_app_class.return_value = mock_app

            args = parse_args([str(test_file), "-p", "acrcloud"])
            await main(args)

            # Verify process_input called with provider
            call_kwargs = mock_app.process_input.call_args.kwargs
            assert "provider" in call_kwargs
            assert call_kwargs["provider"] == "acrcloud"

    async def test_no_fallback_passed_to_app(self, tmp_path):
        """Ensure --no-fallback argument is passed to process_input."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"fake audio data")

        with patch("tracklistify.cli.AsyncApp") as mock_app_class:
            mock_app = AsyncMock()
            mock_app.process_input = AsyncMock(return_value=[])
            mock_app.close = AsyncMock()
            mock_app_class.return_value = mock_app

            args = parse_args([str(test_file), "--no-fallback"])
            await main(args)

            # Verify fallback_enabled=False
            call_kwargs = mock_app.process_input.call_args.kwargs
            assert "fallback_enabled" in call_kwargs
            assert call_kwargs["fallback_enabled"] is False

    async def test_fallback_enabled_defers_to_config_when_flag_absent(self, tmp_path):
        """Without --no-fallback, the CLI must pass fallback_enabled=None so
        AsyncApp.process_input falls back to config.fallback_enabled instead
        of being silently forced to True."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"fake audio data")

        with patch("tracklistify.cli.AsyncApp") as mock_app_class:
            mock_app = AsyncMock()
            mock_app.process_input = AsyncMock(return_value=[])
            mock_app.close = AsyncMock()
            mock_app_class.return_value = mock_app

            args = parse_args([str(test_file)])
            await main(args)

            call_kwargs = mock_app.process_input.call_args.kwargs
            assert "fallback_enabled" in call_kwargs
            assert call_kwargs["fallback_enabled"] is None


class TestAsyncAppArgumentHandling:
    """Test AsyncApp respects argument overrides."""

    @pytest.mark.asyncio
    async def test_provider_override_from_argument(self):
        """Test provider can be overridden via argument."""
        config = TrackIdentificationConfig()
        config.primary_provider = "shazam"  # Default

        app = AsyncApp(config)

        # Mock the actual processing to avoid real downloads
        with patch.object(
            app.identification_manager, "identify_tracks", return_value=[]
        ):
            with patch(
                "tracklistify.core.base.validate_input", return_value=("test.mp3", True)
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch.object(app, "split_audio", return_value=[]):
                        with patch.object(app, "save_output", return_value=None):
                            try:
                                await app.process_input(
                                    "test.mp3",
                                    provider="acrcloud",  # Override
                                )
                            except ValueError:
                                # Expected: "No tracks were successfully identified"
                                pass

        # Verify config was updated
        assert app.config.primary_provider == "acrcloud"

    @pytest.mark.asyncio
    async def test_fallback_disabled_from_argument(self):
        """Test fallback can be disabled via argument."""
        config = TrackIdentificationConfig()
        config.fallback_enabled = True  # Default

        app = AsyncApp(config)

        # Mock the actual processing
        with patch.object(
            app.identification_manager, "identify_tracks", return_value=[]
        ):
            with patch(
                "tracklistify.core.base.validate_input", return_value=("test.mp3", True)
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch.object(app, "split_audio", return_value=[]):
                        with patch.object(app, "save_output", return_value=None):
                            try:
                                await app.process_input(
                                    "test.mp3",
                                    fallback_enabled=False,  # Override
                                )
                            except ValueError:
                                # Expected: "No tracks were successfully identified"
                                pass

        # Verify config was updated
        assert app.config.fallback_enabled is False

    @pytest.mark.asyncio
    async def test_formats_override_from_argument(self):
        """Test output formats can be specified via argument."""
        config = TrackIdentificationConfig()
        app = AsyncApp(config)

        # Create a mock track and mock audio segment
        from tracklistify.core.track import Track
        from tracklistify.core.types import AudioSegment

        mock_track = Track(
            song_name="Test Song",
            artist="Test Artist",
            time_in_mix="00:00:00",
            confidence=0.9,
        )
        mock_segment = AudioSegment(file_path="test.mp3", start_time=0, duration=60)

        # Mock the actual processing
        with patch.object(
            app.identification_manager, "identify_tracks", return_value=[mock_track]
        ):
            with patch(
                "tracklistify.core.base.validate_input", return_value=("test.mp3", True)
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch.object(
                        app, "split_audio", return_value=[mock_segment]
                    ):  # Non-empty!
                        with patch.object(app, "save_output") as mock_save:
                            await app.process_input(
                                "test.mp3",
                                formats="json",  # Override
                            )

                            # Verify save_output called with "json" format
                            mock_save.assert_called_once()
                            assert (
                                mock_save.call_args[0][1] == "json"
                            )  # format argument

    @pytest.mark.asyncio
    async def test_no_override_uses_config_defaults(self):
        """Test that no arguments means config defaults are used."""
        config = TrackIdentificationConfig()
        config.primary_provider = "shazam"
        config.fallback_enabled = True

        app = AsyncApp(config)

        # Mock the actual processing
        with patch.object(
            app.identification_manager, "identify_tracks", return_value=[]
        ):
            with patch(
                "tracklistify.core.base.validate_input", return_value=("test.mp3", True)
            ):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch.object(app, "split_audio", return_value=[]):
                        with patch.object(app, "save_output", return_value=None):
                            try:
                                # Call without any overrides
                                await app.process_input("test.mp3")
                            except ValueError:
                                # Expected: "No tracks were successfully identified"
                                pass

        # Verify config unchanged
        assert app.config.primary_provider == "shazam"
        assert app.config.fallback_enabled is True


@pytest.mark.integration
class TestCLIEndToEnd:
    """Integration tests for CLI with real argument flow."""

    @pytest.mark.asyncio
    async def test_cli_to_app_integration(self, tmp_path):
        """Test full flow from CLI parsing to AsyncApp."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"fake audio data")

        # Mock AsyncApp methods to avoid real processing
        with patch("tracklistify.cli.AsyncApp") as mock_app_class:
            mock_app = AsyncMock()
            mock_app.process_input = AsyncMock(return_value=[])
            mock_app.close = AsyncMock()
            mock_app_class.return_value = mock_app

            # Simulate CLI call with arguments
            args = parse_args(
                [str(test_file), "-f", "json", "-p", "acrcloud", "--no-fallback"]
            )

            result = await main(args)

            # Verify successful execution
            assert result == 0

            # Verify all arguments passed correctly
            mock_app.process_input.assert_called_once()
            call_kwargs = mock_app.process_input.call_args.kwargs

            assert call_kwargs["formats"] == "json"
            assert call_kwargs["provider"] == "acrcloud"
            assert call_kwargs["fallback_enabled"] is False


class TestNoCacheFlag:
    """--no-cache is a REFRESH, not a disable.

    Both cache reads are skipped and both writes still fire, so the stale
    entry is overwritten rather than stepped around. Disabling the caches
    outright would leave the bad result on disk to be served again on the
    next normal run — the opposite of what someone chasing a wrong
    identification wants.
    """

    def test_absent_leaves_config_alone(self):
        """Omitted must be None, not False, so the CLI defers to config."""
        args = parse_args(["test.mp3"])
        assert args.no_cache is None

    def test_flag_sets_true(self):
        args = parse_args(["test.mp3", "--no-cache"])
        assert args.no_cache is True

    @pytest.mark.asyncio
    async def test_flag_reaches_process_input(self, tmp_path):
        test_file = tmp_path / "mix.mp3"
        test_file.write_bytes(b"audio")

        with patch("tracklistify.cli.AsyncApp") as mock_app_class:
            mock_app = AsyncMock()
            mock_app.process_input = AsyncMock()
            mock_app.close = AsyncMock()
            mock_app_class.return_value = mock_app

            assert await main(parse_args([str(test_file), "--no-cache"])) == 0

            kwargs = mock_app.process_input.call_args.kwargs
            assert kwargs["cache_enabled"] is False

    @pytest.mark.asyncio
    async def test_omitted_passes_none(self, tmp_path):
        test_file = tmp_path / "mix.mp3"
        test_file.write_bytes(b"audio")

        with patch("tracklistify.cli.AsyncApp") as mock_app_class:
            mock_app = AsyncMock()
            mock_app.process_input = AsyncMock()
            mock_app.close = AsyncMock()
            mock_app_class.return_value = mock_app

            assert await main(parse_args([str(test_file)])) == 0

            assert mock_app.process_input.call_args.kwargs["cache_enabled"] is None


class TestBareInvocation:
    """Typing the bare command is a question, not a mistake."""

    def test_no_args_prints_help_and_exits_zero(self, capsys):
        """argparse would emit a usage line and exit 2. A user typing
        `tracklistify` to see what it does deserves the full help."""
        with pytest.raises(SystemExit) as exc:
            parse_args([])
        assert exc.value.code == 0

        out = capsys.readouterr().out
        assert "examples:" in out, "help must show a worked example"
        assert "--no-cache" in out

    def test_bad_args_still_error(self):
        """An argv with actual content IS a mistake — keep argparse's
        non-zero exit rather than swallowing it into help."""
        with pytest.raises(SystemExit) as exc:
            parse_args(["test.mp3", "--nonsense"])
        assert exc.value.code != 0


class TestNoCacheRefreshSemantics:
    """--no-cache must set cache_refresh, NOT cache_enabled=False.

    Disabling the caches gates the writes too (both write paths check the
    same enabled flag), so the stale entry would survive on disk and be
    served again on the next normal run. The flag exists to replace a bad
    cached identification, not to step around it once.
    """

    @pytest.mark.asyncio
    async def test_sets_refresh_and_leaves_caches_enabled(self, tmp_path):
        from tracklistify.config import get_config

        cfg = get_config(force_refresh=True)
        cfg.cache_enabled = True
        cfg.download_cache_enabled = True
        cfg.cache_refresh = False

        app = AsyncApp(cfg)
        try:
            # validate_input returning None aborts right after the
            # override block — the override is all this test cares about.
            with patch("tracklistify.core.base.validate_input", return_value=None):
                with pytest.raises(ValueError, match="Invalid URL or file path"):
                    await app.process_input("x.mp3", cache_enabled=False)
        finally:
            pass

        assert cfg.cache_refresh is True, "--no-cache must request a refresh"
        assert cfg.cache_enabled is True, (
            "disabling the cache would gate the WRITE too, leaving the "
            "stale entry on disk to be served again next run"
        )
        assert cfg.download_cache_enabled is True

    @pytest.mark.asyncio
    async def test_omitted_does_not_touch_cache_config(self, tmp_path):
        from tracklistify.config import get_config

        cfg = get_config(force_refresh=True)
        cfg.cache_enabled = True
        cfg.cache_refresh = False

        app = AsyncApp(cfg)
        with patch("tracklistify.core.base.validate_input", return_value=None):
            with pytest.raises(ValueError, match="Invalid URL or file path"):
                await app.process_input("x.mp3", cache_enabled=None)

        assert cfg.cache_refresh is False
        assert cfg.cache_enabled is True
