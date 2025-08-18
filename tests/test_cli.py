"""Tests for the CLI module."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from video_kb_simple import __version__
from video_kb_simple.cli import app
from video_kb_simple.downloader import BatchResult, PlaylistInfo

runner = CliRunner()


# Test fixtures
@pytest.fixture
def mock_downloader():
    """Mock VideoDownloader for testing."""
    with patch("video_kb_simple.cli.VideoDownloader") as mock:
        instance = Mock()
        mock.return_value = instance
        yield instance


@pytest.fixture
def sample_batch_result():
    """Sample BatchResult for playlist tests."""
    playlist_info = PlaylistInfo(
        title="Test Playlist",
        playlist_type="playlist",
        url="https://example.com/playlist",
        playlist_id="test_playlist_id",
    )
    return BatchResult(
        playlist_info=playlist_info,
        total_videos=5,
        successful_downloads=3,
        failed_downloads=1,
        skipped_videos=1,
        downloaded_files=[Path("/tmp/video1.srt"), Path("/tmp/video2.srt")],
        errors=["Error downloading video3"],
        processing_time=120.5,
    )


# 1. Basic CLI Infrastructure Tests
def test_app_creation():
    """Test that Typer app is properly configured."""
    assert app.info.name == "video-kb"
    assert app.info.help is not None
    assert "Extract transcribed text from videos" in app.info.help


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


# 2. Download Command Tests
def test_download_help():
    """Test download command help text and parameters."""
    result = runner.invoke(app, ["download", "--help"])
    assert result.exit_code == 0
    assert "Download transcripts from a single video, playlist, or channel" in result.stdout
    assert "--output" in result.stdout
    assert "--min-sleep" in result.stdout
    assert "--verbose" in result.stdout


def test_download_with_defaults(mock_downloader, sample_batch_result):
    """Test basic download with default parameters."""
    test_url = "https://www.youtube.com/playlist?list=test"

    mock_downloader.download_playlist_transcripts.return_value = sample_batch_result

    with patch("pathlib.Path.mkdir"):
        result = runner.invoke(app, ["download", test_url])

    assert result.exit_code == 0
    assert "Playlist Download Summary" in result.stdout

    mock_downloader.download_playlist_transcripts.assert_called_once_with(
        playlist_url=test_url, subtitles_langs=["en"]
    )


def test_download_custom_output_dir(mock_downloader, sample_batch_result, tmp_path):
    """Test --output/-o parameter."""
    test_url = "https://www.youtube.com/playlist?list=test"
    custom_output = tmp_path / "custom_transcripts"

    mock_downloader.download_playlist_transcripts.return_value = sample_batch_result

    result = runner.invoke(app, ["download", test_url, "--output", str(custom_output)])

    assert result.exit_code == 0
    assert "Playlist Download Summary" in result.stdout


# Manual preference test removed - no longer supported


def test_download_verbose_mode(mock_downloader, sample_batch_result):
    """Test --verbose/-v output."""
    test_url = "https://www.youtube.com/playlist?list=test"

    mock_downloader.download_playlist_transcripts.return_value = sample_batch_result

    result = runner.invoke(app, ["download", test_url, "--verbose"])

    assert result.exit_code == 0
    assert "Downloading transcripts from:" in result.stdout
    assert "Output directory:" in result.stdout
    assert "Sleep interval:" in result.stdout


def test_download_invalid_url(mock_downloader):
    """Test error handling for invalid URLs."""
    test_url = "https://www.youtube.com/playlist?list=invalid"

    mock_downloader.download_playlist_transcripts.side_effect = Exception("Invalid URL")

    result = runner.invoke(app, ["download", test_url])

    assert result.exit_code == 1
    assert "Playlist Download Failed" in result.stdout
    assert "Error: Invalid URL" in result.stdout


def test_download_network_error(mock_downloader):
    """Test network failure handling."""
    test_url = "https://www.youtube.com/playlist?list=test"

    mock_downloader.download_playlist_transcripts.side_effect = Exception("Network timeout")

    result = runner.invoke(app, ["download", test_url])

    assert result.exit_code == 1
    assert "Playlist Download Failed" in result.stdout
    assert "Error: Network timeout" in result.stdout


def test_download_permission_error(mock_downloader):
    """Test output directory permission issues."""
    test_url = "https://www.youtube.com/playlist?list=test"

    mock_downloader.download_playlist_transcripts.side_effect = PermissionError("Permission denied")

    result = runner.invoke(app, ["download", test_url])

    assert result.exit_code == 1
    assert "Playlist Download Failed" in result.stdout
    assert "Error: Permission denied" in result.stdout


def test_download_sleep_intervals(sample_batch_result):
    """Test --min-sleep/--max-sleep parameters."""
    test_url = "https://www.youtube.com/playlist?list=test"

    with patch("video_kb_simple.cli.VideoDownloader") as mock_downloader_class:
        mock_instance = Mock()
        mock_downloader_class.return_value = mock_instance
        mock_instance.download_playlist_transcripts.return_value = sample_batch_result

        with patch("pathlib.Path.mkdir"):
            result = runner.invoke(
                app, ["download", test_url, "--min-sleep", "5", "--max-sleep", "20"]
            )

    assert result.exit_code == 0
    # Check that VideoDownloader was initialized with correct sleep intervals
    call_args = mock_downloader_class.call_args
    assert call_args.kwargs["min_sleep_interval"] == 5
    assert call_args.kwargs["max_sleep_interval"] == 20


def test_download_cookies(sample_batch_result):
    """Test --cookies-from parameter."""
    test_url = "https://www.youtube.com/playlist?list=test"

    with patch("video_kb_simple.cli.VideoDownloader") as mock_downloader_class:
        mock_instance = Mock()
        mock_downloader_class.return_value = mock_instance
        mock_instance.download_playlist_transcripts.return_value = sample_batch_result

        with patch("pathlib.Path.mkdir"):
            result = runner.invoke(app, ["download", test_url, "--cookies-from", "chrome"])

    assert result.exit_code == 0
    # Check that VideoDownloader was initialized with browser cookies
    call_args = mock_downloader_class.call_args
    assert call_args.kwargs["browser_for_cookies"] == "chrome"


def test_download_batch_results_display(mock_downloader, sample_batch_result):
    """Test batch result display formatting."""
    test_url = "https://www.youtube.com/playlist?list=test"

    mock_downloader.download_playlist_transcripts.return_value = sample_batch_result

    with patch("pathlib.Path.mkdir"):
        result = runner.invoke(app, ["download", test_url])

    assert result.exit_code == 0
    assert "Test Playlist" in result.stdout
    assert "playlist" in result.stdout
    assert "Total videos found" in result.stdout
    assert "5" in result.stdout  # total_videos
    assert "✅ 3" in result.stdout  # successful_downloads
    assert "❌ 1" in result.stdout  # failed_downloads
    assert "⏭️ 1" in result.stdout  # skipped_videos
    assert "120.5s" in result.stdout  # processing_time


def test_download_error_handling(mock_downloader):
    """Test playlist download error handling."""
    test_url = "https://www.youtube.com/playlist?list=invalid"

    mock_downloader.download_playlist_transcripts.side_effect = Exception("Playlist not found")

    result = runner.invoke(app, ["download", test_url])

    assert result.exit_code == 1
    assert "Playlist Download Failed" in result.stdout
    assert "Error: Playlist not found" in result.stdout


# 3. Integration & Edge Case Tests
def test_output_directory_creation(mock_downloader, sample_batch_result, tmp_path):
    """Test that output directories are created."""
    test_url = "https://www.youtube.com/playlist?list=test"
    nonexistent_dir = tmp_path / "new_dir" / "transcripts"

    mock_downloader.download_playlist_transcripts.return_value = sample_batch_result

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        result = runner.invoke(app, ["download", test_url, "--output", str(nonexistent_dir)])

    assert result.exit_code == 0
    mock_mkdir.assert_called_once_with(exist_ok=True)


def test_rich_console_formatting():
    """Test Rich panel/table outputs are properly formatted."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    # Rich formatting should be present in help output
    assert len(result.stdout) > 100  # Rich adds substantial formatting


def test_typer_exit_codes():
    """Test proper exit codes on various scenarios."""
    # Version should exit with 0
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0

    # Help should exit with 0
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0

    # Invalid command should exit with non-zero
    result = runner.invoke(app, ["invalid-command"])
    assert result.exit_code != 0
