"""Tests for identification utility functions.

Tests for Phase 2, Issue #3: Implement stub functions
- format_duration()
- create_progress_bar()
- ProgressDisplay class
"""

import pytest
import time
import sys
from tracklistify.utils.identification import (
    format_duration,
    create_progress_bar,
    ProgressDisplay,
)


class TestFormatDuration:
    """Test duration formatting."""

    def test_zero_duration(self):
        """Test zero duration formatting."""
        assert format_duration(0) == "00:00:00"

    def test_seconds_only(self):
        """Test formatting seconds only."""
        assert format_duration(45) == "00:00:45"
        assert format_duration(59) == "00:00:59"

    def test_minutes_and_seconds(self):
        """Test formatting minutes and seconds."""
        assert format_duration(90) == "00:01:30"
        assert format_duration(150) == "00:02:30"

    def test_hours_minutes_seconds(self):
        """Test formatting hours, minutes, and seconds."""
        assert format_duration(3665) == "01:01:05"
        assert format_duration(7200) == "02:00:00"

    def test_large_duration(self):
        """Test large duration values."""
        assert format_duration(86400) == "24:00:00"
        assert format_duration(90000) == "25:00:00"

    def test_fractional_seconds(self):
        """Test that fractional seconds are handled correctly."""
        assert format_duration(90.7) == "00:01:30"
        assert format_duration(90.2) == "00:01:30"
        assert format_duration(90.9) == "00:01:30"


class TestCreateProgressBar:
    """Test progress bar creation."""

    def test_empty_progress(self):
        """Test empty progress bar (0%)."""
        bar = create_progress_bar(0.0, 10)
        assert bar == "[░░░░░░░░░░]"
        assert len(bar) == 12  # 10 chars + 2 brackets

    def test_full_progress(self):
        """Test full progress bar (100%)."""
        bar = create_progress_bar(1.0, 10)
        assert bar == "[██████████]"
        assert len(bar) == 12

    def test_half_progress(self):
        """Test half progress bar (50%)."""
        bar = create_progress_bar(0.5, 10)
        assert bar == "[█████░░░░░]"

    def test_quarter_progress(self):
        """Test quarter progress bar (25%)."""
        bar = create_progress_bar(0.25, 10)
        assert bar == "[██░░░░░░░░]" or bar == "[███░░░░░░░]"  # Rounding

    def test_custom_width(self):
        """Test progress bar with custom width."""
        bar = create_progress_bar(0.5, 20)
        assert len(bar) == 22  # 20 + 2 brackets
        assert bar.startswith("[")
        assert bar.endswith("]")

    def test_progress_clamping_low(self):
        """Test that negative progress is clamped to 0."""
        bar = create_progress_bar(-0.5, 10)
        assert bar == "[░░░░░░░░░░]"

    def test_progress_clamping_high(self):
        """Test that progress > 1.0 is clamped to 1.0."""
        bar = create_progress_bar(1.5, 10)
        assert bar == "[██████████]"

    def test_progress_contains_correct_characters(self):
        """Test that progress bar only contains valid characters."""
        bar = create_progress_bar(0.7, 20)
        # Remove brackets
        inner = bar[1:-1]
        # Should only contain filled or empty blocks
        for char in inner:
            assert char in ["█", "░"], f"Invalid character: {char}"


class TestProgressDisplay:
    """Test progress display functionality."""

    def test_initialization(self):
        """Test ProgressDisplay initializes correctly."""
        display = ProgressDisplay()
        assert display.current_segment == 0
        assert display.total_segments == 0
        assert display.start_time is None

    def test_start_sets_values(self):
        """Test that start() sets correct values."""
        display = ProgressDisplay()
        display.start(total=10)

        assert display.total_segments == 10
        assert display.current_segment == 0
        assert display.start_time is not None
        assert display.start_time <= time.time()

    def test_update_changes_current(self):
        """Test that update() changes current segment."""
        display = ProgressDisplay()
        display.start(total=10)

        display.update(current=5)
        assert display.current_segment == 5

        display.update(current=8)
        assert display.current_segment == 8

    def test_update_with_zero_total_no_crash(self):
        """Test that update() with zero total doesn't crash."""
        display = ProgressDisplay()
        display.start(total=0)

        # Should not raise exception
        display.update(current=0)
        display.complete()

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Terminal output differs on Windows"
    )
    def test_update_writes_to_stdout(self, capsys):
        """Test that update() writes progress to stdout."""
        display = ProgressDisplay()
        display.start(total=10)
        display.update(current=5)

        captured = capsys.readouterr()
        # Should contain progress information
        assert "5/10" in captured.out or "5" in captured.out
        assert "50" in captured.out or "5" in captured.out  # 50% or 5/10

    def test_complete_writes_newline(self, capsys):
        """Test that complete() writes completion message."""
        display = ProgressDisplay()
        display.start(total=10)
        display.update(current=10)
        display.complete()

        captured = capsys.readouterr()
        # Should contain completion message
        assert "Completed" in captured.out or "\n" in captured.out

    def test_complete_without_start_no_crash(self):
        """Test that complete() without start() doesn't crash."""
        display = ProgressDisplay()
        # Should not raise exception
        display.complete()

    def test_clear_removes_progress(self):
        """Test that clear() clears the progress line."""
        display = ProgressDisplay()
        display.start(total=10)
        display.update(current=5)
        display.clear()

        assert display._last_line_length == 0

    def test_multiple_updates(self):
        """Test multiple sequential updates."""
        display = ProgressDisplay()
        display.start(total=100)

        for i in range(0, 101, 10):
            # Should not crash
            display.update(current=i)

        display.complete()

    def test_progress_timing(self):
        """Test that elapsed time is tracked correctly."""
        display = ProgressDisplay()
        display.start(total=10)

        # Small delay
        time.sleep(0.1)

        display.update(current=5)

        # Start time should be in the past
        assert display.start_time < time.time()

    def test_update_idempotent(self):
        """Test that calling update with same value is safe."""
        display = ProgressDisplay()
        display.start(total=10)

        display.update(current=5)
        display.update(current=5)
        display.update(current=5)

        assert display.current_segment == 5
