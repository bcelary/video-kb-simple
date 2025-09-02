"""Tests for the downloader module."""

from pathlib import Path
from unittest.mock import Mock, patch

from video_kb_simple.downloader import SimpleDownloader, VideoResult, YTDLPLogger


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
    """Test VideoResult model with warnings."""

    def test_video_result_with_warnings(self):
        """Test that VideoResult can store warnings."""
        result = VideoResult(
            video_id="test123",
            title="Test Video",
            url="https://example.com",
            success=True,
            warnings=["Warning 1", "Warning 2"],
        )

        assert result.video_id == "test123"
        assert result.warnings == ["Warning 1", "Warning 2"]
        assert result.success is True


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

    @patch("yt_dlp.YoutubeDL")
    def test_download_with_simulated_warning(self, mock_ytdl_class):
        """Test download process with simulated yt-dlp warning."""
        # Mock yt-dlp
        mock_ytdl_instance = Mock()
        mock_ytdl_class.return_value.__enter__.return_value = mock_ytdl_instance

        # Mock video info
        mock_ytdl_instance.extract_info.return_value = {
            "id": "test123",
            "title": "Test Video",
            "upload_date": "20230101",
        }

        # Create downloader
        import logging

        output_dir = Path("/tmp/test")
        downloader = SimpleDownloader(output_dir=output_dir, log_level=logging.INFO)

        # Mock the file scanning and renaming methods
        with (
            patch.object(downloader, "_scan_downloaded_files", return_value=[]),
            patch.object(downloader, "_rename_files_with_slug", return_value=[]),
        ):
            # Call the download method
            result = downloader._perform_video_download(
                "https://youtube.com/watch?v=test123", "test123", ["en"]
            )

        # Verify the result structure
        assert isinstance(result, VideoResult)
        assert result.video_id == "test123"
        assert result.title == "Test Video"

        # Verify yt-dlp was called
        mock_ytdl_class.assert_called_once()
        mock_ytdl_instance.extract_info.assert_called_once()
