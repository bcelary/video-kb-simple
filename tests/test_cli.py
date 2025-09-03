"""Tests for the CLI module."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from video_kb_simple import __version__
from video_kb_simple.cli import _display_batch_results, _display_items, app
from video_kb_simple.models import (
    PlaylistDetails,
    PlaylistResult,
    PlaylistType,
)

runner = CliRunner()


def test_version_callback():
    """Test --version flag functionality."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"video-kb-simple version: {__version__}" in result.stdout


def test_main_help():
    """Test main help command output."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Extract transcribed text from videos using yt-dlp" in result.stdout
    assert "download" in result.stdout


def test_double_ctrl_c_forces_exit():
    """Test that double Ctrl+C forces immediate exit."""
    # Mock the downloader to simulate a long-running operation
    with patch("video_kb_simple.cli.SimpleDownloader") as mock_downloader:
        mock_instance = mock_downloader.return_value

        # Create a mock result to prevent early exit
        from video_kb_simple.models import PlaylistDetails, PlaylistResult, PlaylistType

        mock_result = PlaylistResult(
            playlist_details=PlaylistDetails(
                playlist_id="test",
                playlist_type=PlaylistType.SINGLE_VIDEO,
                title="Test Video",
                url="https://www.youtube.com/watch?v=test",
                video_urls=["https://www.youtube.com/watch?v=test"],
            ),
            video_results=[],
            total_requested=1,
            processing_time_seconds=0.0,
        )
        mock_instance.download_transcripts.return_value = mock_result

        # Start the CLI in a subprocess with a valid YouTube URL format
        cmd = [
            sys.executable,
            "-m",
            "video_kb_simple",
            "download",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ]

        proc = subprocess.Popen(
            cmd,
            cwd=Path(__file__).parent.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )

        try:
            # Wait for process to start and set up signal handlers
            time.sleep(0.5)

            # Send first SIGINT
            proc.send_signal(signal.SIGINT)
            time.sleep(0.1)

            # Send second SIGINT
            proc.send_signal(signal.SIGINT)

            # Wait for process to exit with timeout
            try:
                stdout, stderr = proc.communicate(timeout=2)
                combined_output = stdout + stderr

                # Verify the process exited (should have non-zero exit code from exit(1))
                assert proc.returncode == 1, f"Expected exit code 1, got {proc.returncode}"

                # Verify we see the force exit message
                assert "Force exiting immediately" in combined_output, (
                    f"Force exit message not found in output: {combined_output}"
                )

            except subprocess.TimeoutExpired:
                proc.kill()
                pytest.fail("Process did not exit within timeout after double Ctrl+C")

        finally:
            # Clean up process if still running
            if proc.poll() is None:
                proc.kill()
                proc.wait()


def test_download_command_basic():
    """Test basic download command execution."""
    with patch("video_kb_simple.cli.SimpleDownloader") as mock_downloader:
        mock_instance = mock_downloader.return_value
        mock_result = PlaylistResult(
            playlist_details=PlaylistDetails(
                playlist_id="test",
                playlist_type=PlaylistType.SINGLE_VIDEO,
                title="Test Video",
                url="https://www.youtube.com/watch?v=test",
                video_urls=["https://www.youtube.com/watch?v=test"],
            ),
            video_results=[],
            total_requested=1,
            processing_time_seconds=1.5,
        )
        mock_instance.download_transcripts.return_value = mock_result

        result = runner.invoke(app, ["download", "https://www.youtube.com/watch?v=test"])
        assert result.exit_code == 0
        mock_downloader.assert_called_once()


def test_download_command_with_options():
    """Test download command with various options."""
    with patch("video_kb_simple.cli.SimpleDownloader") as mock_downloader:
        mock_instance = mock_downloader.return_value
        mock_result = PlaylistResult(
            playlist_details=None,
            video_results=[],
            total_requested=1,
            processing_time_seconds=1.0,
        )
        mock_instance.download_transcripts.return_value = mock_result

        result = runner.invoke(
            app,
            [
                "download",
                "https://www.youtube.com/watch?v=test",
                "--output",
                "/tmp/test",
                "--force",
                "--lang",
                "en,es",
                "--max-videos",
                "5",
                "--verbose",
            ],
        )
        assert result.exit_code == 0


def test_download_command_error_handling():
    """Test download command error handling."""
    with patch("video_kb_simple.cli.SimpleDownloader") as mock_downloader:
        mock_instance = mock_downloader.return_value
        mock_instance.download_transcripts.side_effect = Exception("Test error")

        result = runner.invoke(app, ["download", "https://www.youtube.com/watch?v=test"])
        assert result.exit_code == 1
        assert "Test error" in result.stdout


def test_display_items_empty():
    """Test _display_items with empty list."""
    from io import StringIO

    from rich.console import Console

    console = Console(file=StringIO(), width=80)
    _display_items([], "Warnings", console)
    # Should not print anything for empty list


def test_display_items_with_content():
    """Test _display_items with content."""
    from io import StringIO

    from rich.console import Console

    output = StringIO()
    console = Console(file=output, width=80)
    _display_items(["Warning 1", "Warning 2"], "Warnings", console, "yellow")

    content = output.getvalue()
    assert "Warnings (2)" in content
    assert "Warning 1" in content
    assert "Warning 2" in content


def test_display_batch_results():
    """Test _display_batch_results function."""
    from io import StringIO

    from rich.console import Console

    # Create mock data
    mock_result = PlaylistResult(
        playlist_details=PlaylistDetails(
            playlist_id="test",
            playlist_type=PlaylistType.SINGLE_VIDEO,
            title="Test Video",
            url="https://example.com",
            video_urls=["https://example.com"],
        ),
        video_results=[],
        total_requested=1,
        processing_time_seconds=2.5,
    )

    output = StringIO()
    console = Console(file=output, width=80)
    _display_batch_results(mock_result, console)

    content = output.getvalue()
    assert "Download Summary" in content
    assert "Test Video" in content
    assert "2.5s" in content
