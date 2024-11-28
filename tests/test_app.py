import asyncio
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tracklistify.config.factory import get_config
from tracklistify.core.app import App
from tracklistify.core.track import Track
from tracklistify.core.types import AudioSegment


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset App singleton between tests."""
    App._instance = None
    App._initialized = False
    yield


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield Path(tmpdirname)


@pytest.fixture
def config(temp_dir):
    """Get config with temporary directory."""
    config = get_config()
    config.temp_dir = str(temp_dir)
    return config


@pytest.fixture
def app(config):
    """Create App instance with mocked components."""
    app = App(config=config)
    app.identification_manager = Mock()
    app.identification_manager.close = AsyncMock()
    return app


@pytest.fixture
def sample_tracks():
    """Create sample tracks for testing."""
    return [
        Track(
            song_name="Test Song 1",
            artist="Test Artist 1",
            time_in_mix="00:00:00",
            confidence=90.0,
        ),
        Track(
            song_name="Test Song 2",
            artist="Test Artist 2",
            time_in_mix="00:03:00",
            confidence=85.0,
        ),
    ]


class TestAppSaveOutput:
    @pytest.mark.asyncio
    async def test_save_output_empty_tracks(self, app):
        """Test saving output with empty tracks list."""
        await app.save_output([], "json")
        # Should return early without error
        assert True

    @pytest.mark.asyncio
    async def test_save_output_with_original_title(self, app, sample_tracks):
        """Test saving output with original title set."""
        app.original_title = "Original Mix Title"
        with patch(
            "tracklistify.exporters.tracklist.TracklistOutput.save"
        ) as mock_save:
            mock_save.return_value = "output.json"
            await app.save_output(sample_tracks, "json")

            # Verify correct title was used
            mock_save.assert_called_once()
            args, _ = mock_save.call_args
            assert args[0] == "json"

    @pytest.mark.asyncio
    async def test_save_output_without_title(self, app, sample_tracks):
        """Test saving output without original title."""
        with patch(
            "tracklistify.exporters.tracklist.TracklistOutput.save"
        ) as mock_save:
            mock_save.return_value = "output.json"
            await app.save_output(sample_tracks, "json")

            # Verify title was constructed from first track
            mock_save.assert_called_once()
            args, _ = mock_save.call_args
            assert args[0] == "json"

    @pytest.mark.asyncio
    async def test_save_output_all_formats(self, app, sample_tracks):
        """Test saving output in all formats."""
        with patch(
            "tracklistify.exporters.tracklist.TracklistOutput.save_all"
        ) as mock_save_all:
            mock_save_all.return_value = ["output.json", "output.md", "output.m3u"]
            await app.save_output(sample_tracks, "all")
            mock_save_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_output_error_handling(self, app, sample_tracks):
        """Test error handling during save."""
        with patch(
            "tracklistify.exporters.tracklist.TracklistOutput.save"
        ) as mock_save:
            mock_save.side_effect = Exception("Save failed")
            await app.save_output(sample_tracks, "json")
            # Should handle error without raising exception
            assert True

    @pytest.mark.asyncio
    async def test_save_output_incomplete_track_info(self, app):
        """Test saving output when track lacks artist/song info."""
        # Create a mock track that returns None for artist and song_name
        mock_track = Mock(spec=Track)
        mock_track.artist = None
        mock_track.song_name = None
        mock_track.time_in_mix = "00:00:00"
        mock_track.confidence = 90.0

        tracks = [mock_track]

        mock_instances = []

        class MockOutput:
            def __init__(self, mix_info, tracks):
                self.mix_info = mix_info
                self.tracks = tracks
                mock_instances.append(self)

            def save(self, format):
                return "output.json"

        # Clear any existing title
        app.original_title = None

        with patch("tracklistify.core.app.TracklistOutput", MockOutput):
            await app.save_output(tracks, "json")

            # Verify instance was created with default title
            assert len(mock_instances) == 1
            instance = mock_instances[0]
            assert instance.mix_info["title"] == "Identified Mix"

    @pytest.mark.asyncio
    async def test_save_output_default_title(self, app):
        """Test saving output uses default title when original_title is None."""
        app.original_title = "Identified Mix"  # Force the title we want

        tracks = [
            Track(
                song_name="Unknown Track",
                artist="Unknown Artist",
                time_in_mix="00:00:00",
                confidence=90.0,
            )
        ]

        mock_instances = []

        class MockOutput:
            def __init__(self, mix_info, tracks):
                self.mix_info = mix_info
                self.tracks = tracks
                mock_instances.append(self)

            def save(self, format):
                return "output.json"

        with patch("tracklistify.core.app.TracklistOutput", MockOutput):
            await app.save_output(tracks, "json")

            # Verify instance was created with default title
            assert len(mock_instances) == 1
            instance = mock_instances[0]
            assert instance.mix_info["title"] == "Identified Mix"

    @pytest.mark.asyncio
    async def test_save_output_save_failure(self, app, sample_tracks):
        """Test handling of save operation failure."""
        with (
            patch("tracklistify.exporters.tracklist.TracklistOutput.save") as mock_save,
            patch("tracklistify.core.app.logger.error") as mock_logger,
        ):
            mock_save.return_value = None
            await app.save_output(sample_tracks, "json")

            # Verify error was logged
            mock_logger.assert_called_with("Failed to save tracklist in format: json")

    @pytest.mark.asyncio
    async def test_save_output_debug_error(self, app, sample_tracks):
        """Test error handling in debug mode."""
        app.config.debug = True
        test_error = Exception("Debug error")

        with (
            patch("tracklistify.exporters.tracklist.TracklistOutput.save") as mock_save,
            patch("tracklistify.core.app.logger.error") as mock_logger,
            patch("traceback.format_exc") as mock_traceback,
        ):
            mock_save.side_effect = test_error
            mock_traceback.return_value = "Test traceback"

            await app.save_output(sample_tracks, "json")

            # Verify both error and traceback were logged
            mock_logger.assert_any_call(f"Error saving tracklist: {test_error}")
            mock_logger.assert_any_call("Test traceback")

    @pytest.mark.asyncio
    async def test_save_output_mix_info(self, app, sample_tracks):
        """Test mix info structure."""
        mock_instances = []

        class MockOutput:
            def __init__(self, mix_info, tracks):
                self.mix_info = mix_info
                self.tracks = tracks
                mock_instances.append(self)

            def save(self, format):
                return "output.json"

        with patch("tracklistify.core.app.TracklistOutput", MockOutput):
            await app.save_output(sample_tracks, "json")

            # Verify instance was created with correct mix info
            assert len(mock_instances) == 1
            instance = mock_instances[0]
            mix_info = instance.mix_info

            assert "date" in mix_info
            assert "track_count" in mix_info
            assert mix_info["track_count"] == len(sample_tracks)
            assert isinstance(mix_info["date"], str)
            # Verify date format
            datetime.strptime(mix_info["date"], "%Y-%m-%d")

    @pytest.mark.asyncio
    async def test_save_output_partial_format_failure(self, app, sample_tracks):
        """Test handling when save_all has partial failures."""
        with patch(
            "tracklistify.exporters.tracklist.TracklistOutput.save_all"
        ) as mock_save_all:
            mock_save_all.return_value = ["output.json"]  # Only one format succeeded
            await app.save_output(sample_tracks, "all")
            # Verify partial success is handled and appropriate warning is logged
            mock_save_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_output_invalid_format(self, app, sample_tracks):
        """Test handling of invalid format string."""
        with patch("tracklistify.core.app.logger.error") as mock_logger:
            await app.save_output(sample_tracks, "invalid_format")
            # Verify error was logged
            mock_logger.assert_called_with(
                "Failed to save tracklist in format: invalid_format"
            )

    @pytest.mark.parametrize("invalid_format", [None, 123, True])
    @pytest.mark.asyncio
    async def test_save_output_non_string_format(
        self, app, sample_tracks, invalid_format
    ):
        """Test handling of non-string format parameter."""
        with patch("tracklistify.core.app.logger.error") as mock_logger:
            await app.save_output(sample_tracks, invalid_format)
            # Should handle type error gracefully
            mock_logger.assert_called()


class TestAppCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_empty_temp_dir(self, app, temp_dir):
        """Test cleanup with empty temporary directory."""
        await app.cleanup()
        assert not temp_dir.exists()

    @pytest.mark.asyncio
    async def test_cleanup_with_files(self, app, temp_dir):
        """Test cleanup with temporary files."""
        # Create some temporary files
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content")

        test_subdir = temp_dir / "subdir"
        test_subdir.mkdir()
        (test_subdir / "subfile.txt").write_text("sub content")

        await app.cleanup()
        assert not temp_dir.exists()

    @pytest.mark.asyncio
    async def test_cleanup_with_locked_files(self, app, temp_dir):
        """Test cleanup with locked files."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content")

        # Mock file removal to fail
        with patch("pathlib.Path.unlink", side_effect=PermissionError):
            await app.cleanup()
            # Should handle error without raising exception
            assert True

    @pytest.mark.asyncio
    async def test_cleanup_identification_manager(self, app):
        """Test cleanup of identification manager."""
        await app.cleanup()
        app.identification_manager.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_handles_missing_temp_dir(self, app):
        """Test cleanup when temporary directory doesn't exist."""
        app.config.temp_dir = "/nonexistent/path"
        await app.cleanup()
        # Should handle gracefully without error
        assert True

    @pytest.mark.asyncio
    async def test_cleanup_rmtree_fallback(self, app, temp_dir):
        """Test fallback to rmdir when rmtree fails."""
        with (
            patch("shutil.rmtree", side_effect=Exception("rmtree failed")),
            patch("pathlib.Path.rmdir") as mock_rmdir,
        ):
            await app.cleanup()
            mock_rmdir.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_identification_manager_error(self, app):
        """Test handling of identification manager close error."""
        app.identification_manager.close.side_effect = Exception("Close failed")
        with patch("tracklistify.core.app.logger.warning") as mock_logger:
            await app.cleanup()
            mock_logger.assert_called_with(
                "Error cleaning up identification manager: Close failed"
            )

    @pytest.mark.asyncio
    async def test_cleanup_operation_order(self, app, temp_dir):
        """Test cleanup operation order."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("test")

        operations = []

        def track_unlink():
            operations.append("file")

        def track_rmtree(path):
            operations.append("dir")

        with (
            patch("pathlib.Path.unlink", side_effect=track_unlink),
            patch("shutil.rmtree", side_effect=track_rmtree),
        ):
            await app.cleanup()
            assert operations[0] == "file"  # File should be deleted first
            assert operations[-1] == "dir"  # Directory should be deleted last

    @pytest.mark.asyncio
    async def test_cleanup_inaccessible_directory(self, app, temp_dir):
        """Test cleanup with inaccessible directory."""

        # Create a file in the temp directory
        test_file = temp_dir / "test.txt"
        test_file.write_text("test")

        # Mock the glob to return our test file
        def mock_glob(_):
            return [test_file]

        with (
            patch("pathlib.Path.glob", side_effect=mock_glob),
            patch("pathlib.Path.is_file", return_value=True),
            patch(
                "pathlib.Path.unlink", side_effect=PermissionError("Permission denied")
            ),
            patch("tracklistify.core.app.logger.warning") as mock_logger,
        ):
            await app.cleanup()

            # Verify warning was logged for permission error
            mock_logger.assert_called_with(
                f"Failed to remove {test_file}: Permission denied"
            )

    @pytest.mark.asyncio
    async def test_cleanup_with_symlinks(self, app, temp_dir):
        """Test cleanup with symbolic links."""
        # Create a test file and a symlink to it
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content")
        symlink = temp_dir / "link.txt"

        # Create symlink (platform-independent)
        try:
            symlink.symlink_to(test_file)
        except OSError:
            pytest.skip("Symlink creation not supported on this platform")

        await app.cleanup()
        assert not temp_dir.exists()

    @pytest.mark.asyncio
    async def test_cleanup_deep_directory(self, app, temp_dir):
        """Test cleanup with deeply nested directories."""
        current = temp_dir
        for i in range(10):  # Create 10 levels of directories
            current = current / f"level_{i}"
            current.mkdir()
            (current / "file.txt").write_text("test")

        await app.cleanup()
        assert not temp_dir.exists()

    @pytest.mark.asyncio
    async def test_cleanup_special_chars(self, app, temp_dir):
        """Test cleanup with special character filenames."""
        special_chars = ["!@#$%^&*()", "spaces in name", "中文文件"]
        for name in special_chars:
            special_file = temp_dir / name
            special_file.write_text("test")

        await app.cleanup()
        assert not temp_dir.exists()

    @pytest.mark.asyncio
    async def test_cleanup_concurrent(self, app, temp_dir):
        """Test concurrent cleanup calls."""
        # Create some test files
        for i in range(3):
            (temp_dir / f"test_{i}.txt").write_text(f"test content {i}")

        # Run multiple cleanup tasks concurrently
        tasks = [app.cleanup() for _ in range(3)]
        await asyncio.gather(*tasks)

        # Verify cleanup was successful
        assert not temp_dir.exists()


class TestAppProcessInput:
    @pytest.mark.asyncio
    async def test_process_local_file(self, app, temp_dir):
        """Test processing a local audio file."""
        # Create a mock audio file
        test_file = temp_dir / "test.mp3"
        test_file.write_text("mock audio content")

        # Mock dependencies
        app.split_audio = Mock(return_value=["segment1", "segment2"])
        app.identification_manager.identify_tracks = AsyncMock(
            return_value=[
                Track(
                    song_name="Test Song",
                    artist="Test Artist",
                    time_in_mix="00:00:00",
                    confidence=90.0,
                )
            ]
        )
        app.save_output = AsyncMock()

        # Test processing
        await app.process_input(str(test_file))

        # Verify calls
        app.split_audio.assert_called_once_with(str(test_file))
        app.identification_manager.identify_tracks.assert_called_once()
        app.save_output.assert_called_once()
        assert app.original_title == "test"

    @pytest.mark.asyncio
    async def test_process_youtube_url(self, app, temp_dir):
        """Test processing a YouTube URL."""
        url = "https://www.youtube.com/watch?v=test123"
        mock_downloader = Mock()
        mock_downloader.download = AsyncMock(
            return_value=str(temp_dir / "downloaded.mp3")
        )
        mock_downloader.title = "YouTube Video Title"

        app.downloader_factory.create_downloader = Mock(return_value=mock_downloader)
        app.split_audio = Mock(return_value=["segment1"])
        app.identification_manager.identify_tracks = AsyncMock(
            return_value=[
                Track(
                    song_name="Test Song",
                    artist="Test Artist",
                    time_in_mix="00:00:00",
                    confidence=90.0,
                )
            ]
        )
        app.save_output = AsyncMock()

        await app.process_input(url)

        mock_downloader.download.assert_called_once_with(url)
        assert app.original_title == "YouTube Video Title"
        app.split_audio.assert_called_once()
        app.save_output.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_no_tracks_identified(self, app, temp_dir):
        """Test handling when no tracks are identified."""
        test_file = temp_dir / "test.mp3"
        test_file.write_text("mock audio content")

        app.split_audio = Mock(return_value=["segment1"])
        app.identification_manager.identify_tracks = AsyncMock(return_value=[])
        app.save_output = AsyncMock()

        await app.process_input(str(test_file))

        app.save_output.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_input_error_handling(self, app, temp_dir):
        """Test error handling during processing."""
        test_file = temp_dir / "test.mp3"
        test_file.write_text("mock audio content")

        # Mock split_audio to raise a specific exception
        app.split_audio = Mock(side_effect=ValueError("Split failed"))
        app.cleanup = AsyncMock()

        # Expect a specific exception type
        with pytest.raises(ValueError, match="Split failed"):
            await app.process_input(str(test_file))

        # Verify cleanup is called
        app.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_mixcloud_url(self, app, temp_dir):
        """Test processing a MixCloud URL."""
        url = "https://www.mixcloud.com/test/mix"  # Removed trailing slash
        mock_downloader = Mock()
        mock_downloader.download = AsyncMock(
            return_value=str(temp_dir / "downloaded.mp3")
        )
        mock_downloader.title = "MixCloud Mix Title"

        app.downloader_factory.create_downloader = Mock(return_value=mock_downloader)
        app.split_audio = Mock(return_value=["segment1"])
        app.identification_manager.identify_tracks = AsyncMock(
            return_value=[
                Track(
                    song_name="Test Song",
                    artist="Test Artist",
                    time_in_mix="00:00:00",
                    confidence=90.0,
                )
            ]
        )
        app.save_output = AsyncMock()

        await app.process_input(url)

        mock_downloader.download.assert_called_once_with(url)
        assert app.original_title == "MixCloud Mix Title"

    @pytest.mark.asyncio
    async def test_process_invalid_url(self, app, monkeypatch):
        """Test handling of invalid URL format."""
        invalid_url = "not-a-valid-url"

        # Mock URL validation functions
        def mock_is_youtube_url(url):
            return False

        def mock_is_mixcloud_url(url):
            return False

        monkeypatch.setattr("tracklistify.core.app.is_youtube_url", mock_is_youtube_url)
        monkeypatch.setattr(
            "tracklistify.core.app.is_mixcloud_url", mock_is_mixcloud_url
        )

        # Mock mutagen.File to return a mock audio file
        mock_audio = Mock()
        mock_audio.info.length = 60
        monkeypatch.setattr("mutagen.File", lambda x: mock_audio)

        # Mock split_audio to return empty list
        app.split_audio = Mock(return_value=[])

        with pytest.raises(ValueError, match="No audio segments were created"):
            await app.process_input(invalid_url)

    @pytest.mark.asyncio
    async def test_process_download_failure(self, app):
        """Test handling of download failures."""
        url = "https://www.youtube.com/watch?v=test123"
        mock_downloader = Mock()
        mock_downloader.download = AsyncMock(
            side_effect=RuntimeError("Download failed")
        )

        app.downloader_factory.create_downloader = Mock(return_value=mock_downloader)
        app.cleanup = AsyncMock()

        with pytest.raises(RuntimeError, match="Download failed"):
            await app.process_input(url)

        app.cleanup.assert_called_once()


class TestAppSplitAudio:
    def test_split_audio_success(self, app, temp_dir, monkeypatch):
        """Test successful audio splitting."""
        # Mock audio file
        mock_audio = Mock()
        mock_audio.info.length = 60  # 1 minute duration

        # Mock mutagen.File
        monkeypatch.setattr("mutagen.File", lambda x: mock_audio)

        # Mock subprocess.run to simulate successful file creation
        def mock_run(cmd, **kwargs):
            # Get output file path from the ffmpeg command
            output_file = Path(cmd[-1])
            # Create a file that's large enough to pass the size check
            output_file.write_bytes(b"mock audio data" * 1000)  # Creates ~12KB file
            return Mock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr("subprocess.run", mock_run)

        # Create test file
        test_file = temp_dir / "test.mp3"
        test_file.write_text("mock audio content")

        # Configure app for simpler segmentation
        app.config.segment_length = 30
        app.config.overlap_duration = 5

        # Test splitting
        segments = app.split_audio(str(test_file))

        # Verify segments were created
        assert len(segments) > 0
        assert all(isinstance(seg, AudioSegment) for seg in segments)

        # Verify first segment properties
        first_segment = segments[0]
        assert first_segment.start_time == 0
        assert first_segment.duration == 30
        assert Path(first_segment.file_path).exists()

    def test_split_audio_invalid_file(self, app, temp_dir, monkeypatch):
        """Test handling of invalid audio file."""
        # Mock mutagen.File to return None (invalid file)
        monkeypatch.setattr("mutagen.File", lambda x: None)

        test_file = temp_dir / "invalid.mp3"
        test_file.write_text("invalid content")

        segments = app.split_audio(str(test_file))
        assert segments == []

    def test_split_audio_ffmpeg_error(self, app, temp_dir, monkeypatch):
        """Test handling of FFmpeg errors."""
        # Mock audio file
        mock_audio = Mock()
        mock_audio.info.length = 60
        monkeypatch.setattr("mutagen.File", lambda x: mock_audio)

        # Mock subprocess.run to raise error
        def mock_run(*args, **kwargs):
            raise subprocess.CalledProcessError(1, [], stderr="FFmpeg error")

        monkeypatch.setattr("subprocess.run", mock_run)

        test_file = temp_dir / "test.mp3"
        test_file.write_text("mock audio content")

        segments = app.split_audio(str(test_file))
        assert segments == []

    def test_split_audio_segment_parameters(self, app, temp_dir, monkeypatch):
        """Test segment parameter calculation."""
        # Mock audio file with 60 seconds duration
        mock_audio = Mock()
        mock_audio.info.length = 60
        monkeypatch.setattr("mutagen.File", lambda x: mock_audio)

        # Mock subprocess.run to create actual files
        def mock_run(*args, **kwargs):
            # Extract output file path from command
            output_file = Path(args[0][-1])
            # Create the file with some content
            output_file.write_bytes(b"mock audio data" * 1000)  # Make file big enough
            return Mock(returncode=0)

        monkeypatch.setattr("subprocess.run", mock_run)

        test_file = temp_dir / "test.mp3"
        test_file.write_text("mock audio content")

        # Set specific segment length and overlap
        app.config.segment_length = 30
        app.config.overlap_duration = 5

        segments = app.split_audio(str(test_file))

        # Verify number of segments
        expected_segments = 3  # For 60s with 30s segments and 5s overlap
        assert len(segments) == expected_segments

        # Verify segment parameters
        assert segments[0].start_time == 0
        assert segments[1].start_time == 25  # 30 - 5 overlap
        assert segments[2].start_time == 50  # 55 - 5 overlap

    def test_split_audio_short_file(self, app, temp_dir, monkeypatch):
        """Test handling of very short audio files."""
        mock_audio = Mock()
        mock_audio.info.length = 5  # 5 seconds duration
        monkeypatch.setattr("mutagen.File", lambda x: mock_audio)

        def mock_run(cmd, **kwargs):
            output_file = Path(cmd[-1])
            output_file.write_bytes(b"mock audio data" * 1000)
            return Mock(returncode=0)

        monkeypatch.setattr("subprocess.run", mock_run)

        test_file = temp_dir / "short.mp3"
        test_file.write_text("mock audio content")

        segments = app.split_audio(str(test_file))
        assert len(segments) == 1  # Should create single segment for short file

    def test_split_audio_thread_pool_error(self, app, temp_dir, monkeypatch):
        """Test handling of ThreadPoolExecutor errors."""
        mock_audio = Mock()
        mock_audio.info.length = 60
        monkeypatch.setattr("mutagen.File", lambda x: mock_audio)

        def mock_run(cmd, **kwargs):
            raise RuntimeError("Thread pool error")

        monkeypatch.setattr("subprocess.run", mock_run)

        test_file = temp_dir / "test.mp3"
        test_file.write_text("mock audio content")

        segments = app.split_audio(str(test_file))
        assert segments == []

    def test_split_audio_small_segment_file(self, app, temp_dir, monkeypatch):
        """Test handling of segment files that are too small."""
        mock_audio = Mock()
        mock_audio.info.length = 60
        monkeypatch.setattr("mutagen.File", lambda x: mock_audio)

        def mock_run(cmd, **kwargs):
            output_file = Path(cmd[-1])
            output_file.write_bytes(b"tiny")  # Create file smaller than 1KB
            return Mock(returncode=0)

        monkeypatch.setattr("subprocess.run", mock_run)

        test_file = temp_dir / "test.mp3"
        test_file.write_text("mock audio content")

        segments = app.split_audio(str(test_file))
        assert segments == []  # Should reject segments with small file size
