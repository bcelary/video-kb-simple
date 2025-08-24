"""Tests for the CLI module."""

from typer.testing import CliRunner

from video_kb_simple import __version__
from video_kb_simple.cli import app

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
