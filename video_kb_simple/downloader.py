"""Simplified video downloader and transcript extractor using yt-dlp."""

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

from rich.console import Console

from .logger import Logger
from .models import (
    PlaylistDetails,
    PlaylistResult,
    PlaylistType,
    VideoResult,
)
from .utils import (
    FILE_TYPE_METADATA,
    FILE_TYPE_SUBTITLE,
    extract_video_id_from_url,
    normalize_languages,
    normalize_playlist_url,
)
from .ytdlp_handler import YTDLPHandler


class SimpleDownloader:
    """Simplified video downloader that focuses on core functionality."""

    def __init__(
        self,
        output_dir: Path = Path("./transcripts"),
        log_level: int = logging.INFO,
        force_download: bool = False,
        browser_for_cookies: str | None = None,
        shutdown_check: Callable[[], bool] | None = None,
    ):
        """Initialize the simple downloader.

        Args:
            output_dir: Directory to save transcripts
            log_level: Logging level (e.g. logging.DEBUG, logging.INFO)
            force_download: Re-download transcripts even if they already exist
            browser_for_cookies: Browser to extract cookies from (e.g. 'firefox', 'chrome')
            shutdown_check: Optional callback to check if shutdown was requested
        """
        self.output_dir = output_dir
        self.log_level = log_level
        self.force_download = force_download
        self.browser_for_cookies = browser_for_cookies
        self.shutdown_check = shutdown_check

        console = Console()
        self.logger = Logger(console, log_level)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize yt-dlp handler
        self.ytdlp_handler = YTDLPHandler(
            output_dir=output_dir,
            log_level=log_level,
            browser_for_cookies=browser_for_cookies,
            shutdown_check=shutdown_check,
        )

    def _is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested.

        Uses the custom shutdown_check callback if provided, otherwise returns False.
        Handles exceptions in the callback gracefully.
        """
        if self.shutdown_check is not None:
            try:
                return self.shutdown_check()
            except Exception:
                # If callback fails, assume no shutdown requested
                return False
        return False

    def download_transcripts(
        self, url: str, max_videos: int | None = None, subtitle_languages: list[str] | None = None
    ) -> PlaylistResult:
        """Main entry point for downloading transcripts from any YouTube URL.

        This method acts as a router - it normalizes the URL, determines if it's
        a single video or playlist/channel, and delegates to the appropriate handler.

        Individual download failures are captured in the result object, not raised as exceptions.
        Only fundamental setup issues (invalid URL) raise exceptions. All other failures
        (network issues, playlist extraction failures, video download failures) are captured
        in the returned PlaylistResult object.

        Args:
            url: YouTube URL (video, playlist, or channel)
            max_videos: Maximum number of videos to process (None = all)
            subtitle_languages: List of language codes for subtitles (None = ['en'])

        Returns:
            PlaylistResult with detailed information about downloads and any errors

        Raises:
            URLNormalizationError: If URL cannot be parsed or normalized
        """
        start_time = time.time()
        subtitle_languages = normalize_languages(subtitle_languages)

        self.logger.info(f"Starting download from: {url}")
        self.logger.info(f"Max videos: {max_videos or 'unlimited'}")
        self.logger.info(f"Languages: {subtitle_languages}")

        normalized_url, playlist_type = normalize_playlist_url(url)
        self.logger.info(f"Normalized URL: {normalized_url}")
        self.logger.info(f"Detected type: {playlist_type.value}")
        if playlist_type == PlaylistType.SINGLE_VIDEO:
            video_result = self._download_video_transcripts(url, subtitle_languages)
            playlist_result = self._wrap_single_video_result(video_result, url, start_time)
        else:
            playlist_details = self.ytdlp_handler._extract_playlist_details(
                normalized_url, playlist_type
            )
            if playlist_details is None:
                # Failed to extract playlist details, create a failed result
                playlist_result = PlaylistResult(
                    playlist_details=None,
                    video_results=[],
                    total_requested=0,
                    processing_time_seconds=time.time() - start_time,
                )
            else:
                playlist_result = self._download_playlist_transcripts(
                    playlist_details, max_videos, subtitle_languages
                )
                playlist_result.processing_time_seconds = time.time() - start_time

        # Check if shutdown was requested during processing
        if self._is_shutdown_requested():
            self.logger.warning("Download was interrupted by user request.")
            successful_count = (
                playlist_result.success_downloads + playlist_result.partial_success_downloads
            )
            self.logger.info(
                f"Partial results: {successful_count} successful, {playlist_result.fail_downloads} failed"
            )
        else:
            successful_count = (
                playlist_result.success_downloads + playlist_result.partial_success_downloads
            )
            self.logger.success(
                f"Success: {successful_count}, Failed: {playlist_result.fail_downloads}"
            )

        return playlist_result

    def _wrap_single_video_result(
        self, video_result: VideoResult, url: str, start_time: float
    ) -> PlaylistResult:
        """Wrap a single video result in a playlist structure for consistent interface.

        Args:
            video_result: Result from single video download
            url: Original video URL
            start_time: When download started

        Returns:
            PlaylistResult with single video wrapped as playlist
        """
        playlist_details = PlaylistDetails(
            playlist_id=video_result.video_id,
            playlist_type=PlaylistType.SINGLE_VIDEO,
            title=video_result.title or "Single Video",
            url=url,
            uploader=None,
            video_urls=[url],
        )

        playlist_result = PlaylistResult(
            playlist_details=playlist_details,
            video_results=[video_result],
            total_requested=1,
            processing_time_seconds=time.time() - start_time,
        )

        return playlist_result

    def _download_video_transcripts(
        self,
        video_url: str,
        subtitle_languages: list[str] | None = None,
    ) -> VideoResult:
        """Download transcripts for a single video.

        Args:
            video_url: YouTube video URL
            subtitle_languages: List of language codes to download

        Returns:
            VideoResult with download status and any files downloaded
        """
        subtitle_languages = normalize_languages(subtitle_languages)
        video_id = extract_video_id_from_url(video_url)

        if not video_id:
            return VideoResult(
                video_id=None,
                title=None,
                url=video_url,
                warnings=[],
                errors=["Could not extract video ID"],
                downloaded_files=[],
            )

        # Check for existing download first
        existing_files = self.ytdlp_handler._scan_downloaded_files(video_id)
        if existing_files and not self.force_download:
            # Check which languages are already downloaded
            downloaded_languages = set()
            metadata_file = None
            for file in existing_files:
                if file.file_type == FILE_TYPE_SUBTITLE and file.language:
                    downloaded_languages.add(file.language)
                elif file.file_type == FILE_TYPE_METADATA:
                    metadata_file = file

            remaining_languages = [
                lang for lang in subtitle_languages if lang not in downloaded_languages
            ]

            if not remaining_languages and metadata_file:
                # All requested languages are already downloaded
                try:
                    with open(metadata_file.path, encoding="utf-8") as f:
                        metadata = json.load(f)
                    title = metadata.get("title", "Unknown Title")
                    upload_date = metadata.get("upload_date")
                    actual_video_id = metadata.get("id", video_id)
                    url = metadata.get("webpage_url") or metadata.get("original_url")

                    self.logger.info(f"Found existing download for: {title}")
                    return VideoResult(
                        video_id=actual_video_id,
                        title=title,
                        url=url,
                        upload_date=upload_date,
                        warnings=[],
                        errors=[],
                        downloaded_files=existing_files,
                    )
                except (json.JSONDecodeError, OSError, KeyError) as e:
                    self.logger.warning(f"Failed to load metadata from {metadata_file.path}: {e}")

            # Update languages to only download missing ones
            if remaining_languages:
                subtitle_languages = remaining_languages
                self.logger.info(f"Downloading only missing languages: {remaining_languages}")

        # Perform the actual download using YTDLPHandler
        return self.ytdlp_handler.download_video_transcripts(
            video_url, video_id, subtitle_languages
        )

    def _download_playlist_transcripts(
        self,
        playlist: PlaylistDetails,
        max_videos: int | None = None,
        subtitle_languages: list[str] | None = None,
    ) -> PlaylistResult:
        """Download transcripts from videos found in a normalized playlist.

        Args:
            playlist: Normalized playlist
            max_videos: Maximum number of videos to process
            subtitle_languages: List of language codes to download (e.g. ['en', 'es'])

        Returns:
            PlaylistResult with detailed information about what was downloaded
        """
        subtitle_languages = normalize_languages(subtitle_languages)

        self.logger.info(f"Downloading from playlist: {playlist.title}")
        self.logger.info(f"Languages: {subtitle_languages}")
        self.logger.info(f"Output directory: {self.output_dir}")

        videos_to_process = playlist.video_urls
        if max_videos and max_videos > 0:
            videos_to_process = videos_to_process[:max_videos]

        total_videos = len(videos_to_process)
        self.logger.info(f"Processing {total_videos} videos...")

        video_results = []
        successful_downloads = 0
        failed_downloads = 0
        errors = []

        for i, video_url in enumerate(videos_to_process, 1):
            # Check for shutdown signal before processing each video
            if self._is_shutdown_requested():
                self.logger.warning(
                    f"Shutdown requested. Stopping after processing {i - 1}/{total_videos} videos."
                )
                break

            self.logger.info(f"Processing video {i}/{total_videos}: {video_url}")

            try:
                video_result = self._download_video_transcripts(video_url, subtitle_languages)
                video_results.append(video_result)

                if video_result.is_full_success:
                    successful_downloads += 1
                else:
                    failed_downloads += 1
                    if video_result.errors:
                        errors.extend([f"Video {i}: {error}" for error in video_result.errors])
                    else:
                        errors.append(f"Video {i}: Unknown error")

            except Exception as error:
                error_message = f"Unexpected error processing video {i}: {error}"
                self.logger.error(error_message)
                errors.append(error_message)
                failed_downloads += 1

                video_result = VideoResult(
                    video_id=None,
                    title=None,
                    url=video_url,
                    warnings=[],
                    errors=[error_message],
                    downloaded_files=[],
                )
                video_results.append(video_result)

        self.logger.success(
            f"Playlist processing complete: {successful_downloads} successful, {failed_downloads} failed"
        )

        return PlaylistResult(
            playlist_details=playlist,
            video_results=video_results,
            total_requested=total_videos,
            processing_time_seconds=0.0,  # Will be set by caller
        )
