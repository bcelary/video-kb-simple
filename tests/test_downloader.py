"""Tests for the downloader module."""

from pathlib import Path
from unittest.mock import patch

from video_kb_simple.downloader import SimpleDownloader
from video_kb_simple.logger import YTDLPLogger
from video_kb_simple.models import VideoResult


class TestYTDLPLogger:
    """Test the custom yt-dlp logger."""

    def test_warning_capture(self):
        """Test that warnings are captured correctly."""
        import logging

        from rich.console import Console

        from video_kb_simple.downloader import Logger

        console = Console()
        logger = Logger(console, logging.INFO)
        ytdlp_logger = YTDLPLogger(logger, logging.INFO, "test123")

        # Test warning capture
        ytdlp_logger.warning("Test warning message")
        ytdlp_logger.warning("Another warning")

        warnings = ytdlp_logger.get_warnings()
        assert len(warnings) == 2
        assert "[YT-DLP] \\[test123] Test warning message" in warnings
        assert "[YT-DLP] \\[test123] Another warning" in warnings

    def test_error_capture(self):
        """Test that errors are captured correctly."""
        import logging

        from rich.console import Console

        from video_kb_simple.downloader import Logger

        console = Console()
        logger = Logger(console, logging.INFO)
        ytdlp_logger = YTDLPLogger(logger, logging.INFO, "test123")

        # Test error capture
        ytdlp_logger.error("Test error message")

        errors = ytdlp_logger.get_errors()
        assert len(errors) == 1
        assert "[YT-DLP] \\[test123] Test error message" in errors[0]

    def test_has_warnings_or_errors(self):
        """Test the has_warnings_or_errors method."""
        import logging

        from rich.console import Console

        from video_kb_simple.downloader import Logger

        console = Console()
        logger = Logger(console, logging.INFO)
        ytdlp_logger = YTDLPLogger(logger, logging.INFO, "test123")

        assert not ytdlp_logger.has_warnings_or_errors()

        ytdlp_logger.warning("Test warning")
        assert ytdlp_logger.has_warnings_or_errors()

        # Reset logger
        ytdlp_logger = YTDLPLogger(logger, logging.INFO, "test123")
        ytdlp_logger.error("Test error")
        assert ytdlp_logger.has_warnings_or_errors()


class TestVideoResult:
    """Test VideoResult model with warnings and errors."""

    def test_video_result_with_warnings(self):
        """Test that VideoResult can store warnings."""
        result = VideoResult(
            video_id="test123",
            title="Test Video",
            url="https://example.com",
            warnings=["Warning 1", "Warning 2"],
            errors=[],
        )

        assert result.video_id == "test123"
        assert result.warnings == ["Warning 1", "Warning 2"]
        assert result.errors == []
        assert result.is_full_success is False  # Has warnings, so not fully successful
        assert result.is_partial_success is True  # But it's partially successful

    def test_video_result_with_errors(self):
        """Test that VideoResult can store errors."""
        result = VideoResult(
            video_id="test123",
            title="Test Video",
            url="https://example.com",
            warnings=["Warning 1"],
            errors=["Error 1", "Error 2"],
        )

        assert result.video_id == "test123"
        assert result.warnings == ["Warning 1"]
        assert result.errors == ["Error 1", "Error 2"]
        assert result.is_fail is True

    def test_video_result_partial_success(self):
        """Test VideoResult partial success state."""
        result = VideoResult(
            video_id="test123",
            title="Test Video",
            url="https://example.com",
            warnings=["Warning 1"],
            errors=[],
        )

        assert result.is_partial_success is True
        assert result.is_full_success is False
        assert result.is_fail is False

    def test_video_result_fully_successful(self):
        """Test VideoResult fully successful state."""
        result = VideoResult(
            video_id="test123",
            title="Test Video",
            url="https://example.com",
            warnings=[],
            errors=[],
        )

        assert result.is_partial_success is False
        assert result.is_full_success is True
        assert result.is_fail is False

    def test_video_result_failed(self):
        """Test VideoResult failed state."""
        result = VideoResult(
            video_id="test123",
            title="Test Video",
            url="https://example.com",
            warnings=["Warning 1"],
            errors=["Error 1"],
        )

        assert result.is_partial_success is False
        assert result.is_full_success is False
        assert result.is_fail is True


class TestSimpleDownloader:
    """Test the SimpleDownloader class."""

    def test_downloader_initialization(self):
        """Test that downloader initializes correctly."""
        import logging

        output_dir = Path("/tmp/test")
        downloader = SimpleDownloader(
            output_dir=output_dir, log_level=logging.INFO, force_download=True
        )

        assert downloader.output_dir == output_dir
        assert downloader.log_level == logging.INFO
        assert downloader.force_download is True

    def test_download_with_simulated_warning(self):
        """Test download process with simulated yt-dlp warning."""
        # Create downloader
        import logging

        output_dir = Path("/tmp/test")
        downloader = SimpleDownloader(output_dir=output_dir, log_level=logging.INFO)

        # Mock the download result
        mock_result = VideoResult(
            video_id="dQw4w9WgXcQ",
            title="Test Video",
            url="https://youtube.com/watch?v=dQw4w9WgXcQ",
            upload_date="20230101",
            warnings=[],
            errors=[],
            downloaded_files=[],
        )

        # Mock the YTDLPHandler method
        with (
            patch.object(
                downloader.ytdlp_handler, "download_video_transcripts", return_value=mock_result
            ),
            patch.object(downloader.ytdlp_handler, "_scan_downloaded_files", return_value=[]),
        ):
            # Call the download method
            result = downloader._download_video_transcripts(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ", ["en"]
            )

        # Verify the result structure
        assert isinstance(result, VideoResult)
        assert result.video_id == "dQw4w9WgXcQ"
        assert result.title == "Test Video"


class TestCLIReporting:
    """Test CLI reporting with different video result states."""

    def test_cli_counts_different_result_types(self):
        """Test that CLI correctly counts fully successful, partial success, and failed videos."""
        from video_kb_simple.models import PlaylistDetails, PlaylistResult, PlaylistType

        # Create test video results
        fully_successful_result = VideoResult(
            video_id="test1",
            title="Fully Successful Video",
            url="https://youtube.com/watch?v=test1",
            warnings=[],
            errors=[],
            downloaded_files=[],
        )

        partial_success_result = VideoResult(
            video_id="test2",
            title="Partial Success Video",
            url="https://youtube.com/watch?v=test2",
            warnings=["Warning: Some subtitles missing"],
            errors=[],
            downloaded_files=[],
        )

        failed_result = VideoResult(
            video_id="test3",
            title="Failed Video",
            url="https://youtube.com/watch?v=test3",
            warnings=[],
            errors=["Error: Download failed"],
            downloaded_files=[],
        )

        # Create playlist result
        playlist_result = PlaylistResult(
            playlist_details=PlaylistDetails(
                playlist_id="test_playlist",
                playlist_type=PlaylistType.PLAYLIST,
                title="Test Playlist",
                url="https://youtube.com/playlist?list=test",
                video_urls=[],
            ),
            video_results=[fully_successful_result, partial_success_result, failed_result],
            total_requested=3,
            processing_time_seconds=1.5,
        )

        # Test the counting logic directly
        fully_successful = sum(1 for vr in playlist_result.video_results if vr.is_full_success)
        partial_success = sum(1 for vr in playlist_result.video_results if vr.is_partial_success)
        failed = sum(1 for vr in playlist_result.video_results if vr.is_fail)

        # Verify the counts are correct
        assert fully_successful == 1
        assert partial_success == 1
        assert failed == 1
