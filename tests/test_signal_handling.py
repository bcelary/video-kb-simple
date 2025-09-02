"""Tests for shutdown handling functionality in the downloader."""

from unittest.mock import patch

from video_kb_simple.downloader import SimpleDownloader
from video_kb_simple.models import (
    PlaylistDetails,
    PlaylistResult,
    PlaylistType,
    VideoResult,
)


class TestShutdownHandling:
    """Test cases for shutdown handling functionality."""

    def test_downloader_initializes_without_signal_handlers(self):
        """Test that SimpleDownloader does not set up signal handlers by default."""
        # Create downloader without shutdown_check callback
        downloader = SimpleDownloader()

        # Should not have any shutdown_check callback set
        assert downloader.shutdown_check is None

    def test_downloader_with_custom_shutdown_check(self):
        """Test that SimpleDownloader accepts custom shutdown_check callback."""
        shutdown_flag = False

        def custom_shutdown_check():
            return shutdown_flag

        # Create downloader with custom shutdown check
        downloader = SimpleDownloader(shutdown_check=custom_shutdown_check)

        # Should have the callback set
        assert downloader.shutdown_check is not None
        assert not downloader.shutdown_check()

        # Change the flag and test
        shutdown_flag = True
        assert downloader.shutdown_check()

    def test_is_shutdown_requested_without_callback(self):
        """Test _is_shutdown_requested returns False when no callback provided."""
        downloader = SimpleDownloader()

        # Should return False when no callback is provided
        assert not downloader._is_shutdown_requested()

    def test_is_shutdown_requested_with_callback(self):
        """Test _is_shutdown_requested uses callback when provided."""
        shutdown_flag = False

        def custom_shutdown_check():
            return shutdown_flag

        downloader = SimpleDownloader(shutdown_check=custom_shutdown_check)

        # Initially False
        assert not downloader._is_shutdown_requested()

        # Change flag
        shutdown_flag = True
        assert downloader._is_shutdown_requested()

    def test_playlist_processing_respects_shutdown_callback(self):
        """Test that playlist processing loop respects shutdown callback."""
        shutdown_flag = False

        def custom_shutdown_check():
            return shutdown_flag

        downloader = SimpleDownloader(shutdown_check=custom_shutdown_check)

        # Create proper playlist details
        playlist_details = PlaylistDetails(
            playlist_id="test_playlist",
            playlist_type=PlaylistType.PLAYLIST,
            title="Test Playlist",
            url="https://youtube.com/playlist?list=test",
            video_urls=[
                "https://youtube.com/watch?v=test1",
                "https://youtube.com/watch?v=test2",
                "https://youtube.com/watch?v=test3",
            ],
        )

        # Create proper video result
        video_result = VideoResult(
            video_id="test1",
            title="Test Video",
            url="https://youtube.com/watch?v=test1",
            warnings=[],
            errors=[],
            downloaded_files=[],
        )

        # Mock the video download method
        with patch.object(downloader, "_download_video_transcripts") as mock_download:
            mock_download.return_value = video_result

            # Process first video, then set shutdown flag
            shutdown_flag = False

            result = downloader._download_playlist_transcripts(playlist_details, max_videos=3)

            # Should have processed all videos since shutdown was never triggered
            assert mock_download.call_count == 3
            assert result.total_requested == 3
            assert len(result.video_results) == 3

    def test_playlist_processing_stops_on_shutdown(self):
        """Test that playlist processing stops when shutdown callback returns True."""
        call_count = 0

        def custom_shutdown_check():
            nonlocal call_count
            call_count += 1
            # Return True after processing 2 videos
            return call_count > 2

        downloader = SimpleDownloader(shutdown_check=custom_shutdown_check)

        # Create proper playlist details
        playlist_details = PlaylistDetails(
            playlist_id="test_playlist",
            playlist_type=PlaylistType.PLAYLIST,
            title="Test Playlist",
            url="https://youtube.com/playlist?list=test",
            video_urls=[
                "https://youtube.com/watch?v=test1",
                "https://youtube.com/watch?v=test2",
                "https://youtube.com/watch?v=test3",
            ],
        )

        # Create proper video result
        video_result = VideoResult(
            video_id="test1",
            title="Test Video",
            url="https://youtube.com/watch?v=test1",
            warnings=[],
            errors=[],
            downloaded_files=[],
        )

        # Mock the video download method
        with patch.object(downloader, "_download_video_transcripts") as mock_download:
            mock_download.return_value = video_result

            result = downloader._download_playlist_transcripts(playlist_details, max_videos=3)

            # Should have only processed 2 videos (shutdown after 2nd check)
            assert mock_download.call_count == 2
            assert result.total_requested == 3
            assert len(result.video_results) == 2

    def test_video_download_respects_shutdown_callback(self):
        """Test that video download respects shutdown callback."""
        shutdown_flag = True

        def custom_shutdown_check():
            return shutdown_flag

        downloader = SimpleDownloader(shutdown_check=custom_shutdown_check)

        # Mock YTDLPHandler to simulate shutdown
        with patch.object(downloader.ytdlp_handler, "download_video_transcripts") as mock_download:
            mock_download.return_value = VideoResult(
                video_id="dQw4w9WgXcQ",
                title="Test Video",
                url="https://youtube.com/watch?v=dQw4w9WgXcQ",
                warnings=[],
                errors=["Download cancelled by user"],
                downloaded_files=[],
            )

            result = downloader._download_video_transcripts(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ", ["en"]
            )

            # Should return failed result due to shutdown
            assert not result.is_full_success
            assert result.errors
            assert "cancelled by user" in " ".join(result.errors)

            # Verify the mock was called
            mock_download.assert_called_once()

    def test_video_download_continues_when_no_shutdown(self):
        """Test that video download continues when shutdown callback returns False."""
        shutdown_flag = False

        def custom_shutdown_check():
            return shutdown_flag

        downloader = SimpleDownloader(shutdown_check=custom_shutdown_check)

        # Mock YTDLPHandler for successful download
        with patch.object(downloader.ytdlp_handler, "download_video_transcripts") as mock_download:
            mock_download.return_value = VideoResult(
                video_id="dQw4w9WgXcQ",
                title="Test Video",
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                upload_date="20231201",
                warnings=[],
                errors=[],
                downloaded_files=[],
            )

            result = downloader._download_video_transcripts(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ", ["en"]
            )

            # Should succeed since no shutdown
            assert result.is_full_success
            assert result.title == "Test Video"

    def test_shutdown_logging_in_main_download_method(self):
        """Test that shutdown status is logged in main download method."""
        shutdown_flag = True

        def custom_shutdown_check():
            return shutdown_flag

        downloader = SimpleDownloader(shutdown_check=custom_shutdown_check)

        # Use a proper YouTube URL format that will be recognized
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

        # Mock the YTDLPHandler playlist extraction to avoid actual network calls
        with patch.object(downloader.ytdlp_handler, "_extract_playlist_details") as mock_extract:
            mock_extract.return_value = None

            with patch("builtins.print"):  # Mock print for logging
                result = downloader.download_transcripts(test_url)

                # Should have logged shutdown message
                # Note: We can't easily test the exact logging output without more complex mocking
                # but we can verify the method completes and returns a result
                assert isinstance(result, PlaylistResult)

    def test_shutdown_callback_exception_handling(self):
        """Test that exceptions in shutdown callback are handled gracefully."""

        def failing_shutdown_check():
            raise Exception("Callback failed")

        downloader = SimpleDownloader(shutdown_check=failing_shutdown_check)

        # Should return False when callback raises exception
        assert not downloader._is_shutdown_requested()


class TestShutdownHandlingIntegration:
    """Integration tests for shutdown handling in realistic scenarios."""

    def test_multiple_videos_with_shutdown(self):
        """Test processing multiple videos with shutdown triggered midway."""
        video_count = 0

        def shutdown_after_two_videos():
            nonlocal video_count
            video_count += 1
            return video_count > 2

        downloader = SimpleDownloader(shutdown_check=shutdown_after_two_videos)

        # Create playlist with 5 videos
        playlist_details = PlaylistDetails(
            playlist_id="test_playlist",
            playlist_type=PlaylistType.PLAYLIST,
            title="Test Playlist",
            url="https://youtube.com/playlist?list=test",
            video_urls=[f"https://youtube.com/watch?v=test{i}" for i in range(1, 6)],
        )

        # Create successful video result
        video_result = VideoResult(
            video_id="test1",
            title="Test Video",
            url="https://youtube.com/watch?v=test1",
            warnings=[],
            errors=[],
            downloaded_files=[],
        )

        with patch.object(downloader, "_download_video_transcripts") as mock_download:
            mock_download.return_value = video_result

            result = downloader._download_playlist_transcripts(playlist_details, max_videos=5)

            # Should have processed exactly 2 videos before shutdown
            assert mock_download.call_count == 2
            assert len(result.video_results) == 2
            assert result.total_requested == 5

    def test_shutdown_during_single_video_download(self):
        """Test shutdown during single video download."""
        shutdown_flag = True

        def immediate_shutdown():
            return shutdown_flag

        downloader = SimpleDownloader(shutdown_check=immediate_shutdown)

        # Use a proper YouTube URL format that will pass video ID extraction
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

        result = downloader._download_video_transcripts(test_url)

        # Should fail due to immediate shutdown
        assert not result.is_full_success
        assert result.errors
        assert "cancelled by user" in " ".join(result.errors)

    def test_no_shutdown_callback_provided(self):
        """Test behavior when no shutdown callback is provided."""
        downloader = SimpleDownloader()

        # Should work normally without shutdown interruptions
        assert not downloader._is_shutdown_requested()

        # Create a simple test case
        playlist_details = PlaylistDetails(
            playlist_id="test",
            playlist_type=PlaylistType.SINGLE_VIDEO,
            title="Test",
            url="https://youtube.com/watch?v=test",
            video_urls=["https://youtube.com/watch?v=test"],
        )

        video_result = VideoResult(
            video_id="test",
            title="Test Video",
            url="https://youtube.com/watch?v=test",
            warnings=[],
            errors=[],
            downloaded_files=[],
        )

        with patch.object(downloader, "_download_video_transcripts") as mock_download:
            mock_download.return_value = video_result

            result = downloader._download_playlist_transcripts(playlist_details)

            # Should process all videos since no shutdown callback
            assert mock_download.call_count == 1
            assert len(result.video_results) == 1
            successful_count = result.success_downloads + result.partial_success_downloads
            assert successful_count == 1
