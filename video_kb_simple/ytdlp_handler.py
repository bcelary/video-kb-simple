"""yt-dlp operations handler for video-kb-simple."""

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yt_dlp
from rich.console import Console
from slugify import slugify

from .logger import Logger, YTDLPLogger
from .models import DownloadedFile, PlaylistDetails, PlaylistType, VideoResult
from .utils import detect_file_type_and_language


class YTDLPHandler:
    """Handles all yt-dlp operations for video downloading and metadata extraction."""

    # yt-dlp specific constants (owned by YTDLPHandler)
    DEFAULT_SLEEP_REQUESTS = 5  # Sleep between metadata API requests
    DEFAULT_SLEEP_SUBTITLES = 120  # Sleep between subtitle downloads
    DEFAULT_SLEEP_INTERVAL = 15  # Minimum sleep between downloads
    DEFAULT_MAX_SLEEP_INTERVAL = 90  # Maximum sleep between downloads
    DEFAULT_SLEEP_BEFORE_DOWNLOAD = 120  # Sleep before yt-dlp download to avoid rate limits
    DEFAULT_RATE_LIMIT = 500000  # Download bandwidth limit (bytes/sec)
    DEFAULT_RETRIES = 3  # Number of download retries
    DEFAULT_EXTRACTOR_RETRIES = 5  # Number of extractor retries (increased for 429 handling)
    DEFAULT_FILE_ACCESS_RETRIES = 3  # Number of file access retries
    # Retry sleep function parameters
    HTTP_RETRY_BASE = 2  # Base for exponential backoff (2^n)
    HTTP_RETRY_MAX = 120  # Maximum sleep time for HTTP retries (seconds)
    EXTRACTOR_RETRY_MULTIPLIER = 5  # Multiplier for linear extractor backoff (5*n)
    EXTRACTOR_RETRY_MAX = 30  # Maximum sleep time for extractor retries (seconds)
    SOCKET_TIMEOUT = 30  # Network connection timeout
    DEFAULT_SLUG_MAX_LENGTH = 20  # Maximum length for slugified titles in filenames

    def __init__(
        self,
        output_dir: Path,
        log_level: int = logging.INFO,
        browser_for_cookies: str | None = None,
        shutdown_check: Callable[[], bool] | None = None,
    ):
        """Initialize the yt-dlp handler.

        Args:
            output_dir: Directory to save transcripts
            log_level: Logging level
            browser_for_cookies: Browser to extract cookies from
            shutdown_check: Optional callback to check if shutdown was requested
        """
        self.output_dir = output_dir
        self.log_level = log_level
        self.browser_for_cookies = browser_for_cookies
        self.slug_max_length = self.DEFAULT_SLUG_MAX_LENGTH
        self.shutdown_check: Callable[[], bool] | None = shutdown_check

        console = Console()
        self.logger = Logger(console, log_level)
        # Create a single YTDLPLogger instance that can be reused
        self.ytdlp_logger = YTDLPLogger(self.logger, log_level)

    def _is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        if self.shutdown_check is not None:
            try:
                return bool(self.shutdown_check())
            except Exception:
                return False
        return False

    def _create_ytdlp_options(self, **kwargs: Any) -> dict[str, Any]:
        """Create yt-dlp options dictionary with rate limiting and sensible defaults."""
        base_options: dict[str, Any] = {
            "sleep_interval": self.DEFAULT_SLEEP_INTERVAL,
            "sleep_interval_requests": self.DEFAULT_SLEEP_REQUESTS,
            "sleep_interval_subtitles": self.DEFAULT_SLEEP_SUBTITLES,
            "max_sleep_interval": self.DEFAULT_MAX_SLEEP_INTERVAL,
            "socket_timeout": self.SOCKET_TIMEOUT,
            "ratelimit": self.DEFAULT_RATE_LIMIT,
            "retries": self.DEFAULT_RETRIES,
            "extractor_retries": self.DEFAULT_EXTRACTOR_RETRIES,
            "file_access_retries": self.DEFAULT_FILE_ACCESS_RETRIES,
            "retry_sleep_functions": {
                "http": lambda n: min(
                    self.HTTP_RETRY_BASE**n, self.HTTP_RETRY_MAX
                ),  # Exponential backoff for HTTP errors
                "extractor": lambda n: min(
                    self.EXTRACTOR_RETRY_MULTIPLIER * n, self.EXTRACTOR_RETRY_MAX
                ),  # Linear backoff for extractor errors
                "file_access": lambda n: n,  # Simple linear backoff for file access
            },
            "quiet": self.log_level > logging.DEBUG,
            "no_warnings": self.log_level > logging.DEBUG,
        }

        if self.browser_for_cookies:
            base_options["cookiesfrombrowser"] = (self.browser_for_cookies,)

        # Override with any provided options
        base_options.update(kwargs)

        # Debug logging: Print options when log level is DEBUG
        if self.log_level <= logging.DEBUG:
            self.logger.debug("yt-dlp options created:")
            import pprint

            options_str = pprint.pformat(base_options, width=120, depth=4)
            for line in options_str.split("\n"):
                self.logger.debug(f"  {line}")

        return base_options

    def _prepare_ytdlp_options(self, prefix: str, **kwargs: Any) -> dict[str, Any]:
        """Prepare yt-dlp options with logger setup for the given prefix."""
        # Configure the shared logger
        self.ytdlp_logger.set_prefix(prefix)
        self.ytdlp_logger.clear_captured_logs()

        # Create options with logger and warning capture enabled
        return self._create_ytdlp_options(
            logger=self.ytdlp_logger,
            no_warnings=False,  # Enable warnings so they can be captured
            **kwargs,
        )

    def _get_output_templates(self) -> dict[str, str]:
        """Get standardized output templates for yt-dlp."""
        return {
            "infojson": str(
                self.output_dir / "%(upload_date>%Y-%m-%d,release_date>%Y-%m-%d,NA)s_%(id)s.%(ext)s"
            ),
            "subtitle": str(
                self.output_dir
                / "%(upload_date>%Y-%m-%d,release_date>%Y-%m-%d,NA)s_%(id)s.%(subtitle_lang)s.%(ext)s"
            ),
        }

    def _extract_playlist_details(
        self, normalized_url: str, playlist_type: PlaylistType
    ) -> PlaylistDetails | None:
        """Extract basic playlist information without downloading videos."""
        self.logger.info(f"Extracting playlist details from: {normalized_url}")

        try:
            # Prepare yt-dlp options with playlist prefix
            extraction_options = self._prepare_ytdlp_options(
                "PLAYLIST",
                extract_flat=True,
                quiet=self.log_level > logging.DEBUG,  # Only quiet if debug is not enabled
            )

            with yt_dlp.YoutubeDL(extraction_options) as ydl:
                video_info = ydl.extract_info(normalized_url, download=False)

            if not video_info:
                self.logger.error(f"Could not extract playlist information from: {normalized_url}")
                return None

            playlist_id = video_info.get("id")
            title = video_info.get("title", "Unknown Playlist")
            uploader = video_info.get("uploader") or video_info.get("channel")

            video_urls = []
            video_entries = video_info.get("entries", [])

            for entry in video_entries:
                if entry and entry.get("url"):
                    video_urls.append(entry["url"])
                elif entry and entry.get("id"):
                    video_urls.append(f"https://www.youtube.com/watch?v={entry['id']}")

            self.logger.success(f"Found {len(video_urls)} videos in playlist: {title}")

            return PlaylistDetails(
                playlist_id=playlist_id,
                playlist_type=playlist_type,
                title=title,
                url=normalized_url,
                uploader=uploader,
                video_urls=video_urls,
            )

        except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as e:
            self.logger.error(f"Failed to extract playlist details: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error extracting playlist: {e}")
            return None

    def _create_download_options(
        self,
        download_metadata: bool,
        download_subtitles: bool,
        subtitle_languages: list[str],
        video_id: str | None = None,
    ) -> dict[str, Any]:
        """Create yt-dlp options for downloading transcripts with custom logger."""
        # Use the shared YTDLPLogger instance with video_id as prefix
        prefix = video_id if video_id is not None else "VIDEO"

        return self._prepare_ytdlp_options(
            prefix,
            writeinfojson=download_metadata,
            writesubtitles=download_subtitles,
            writeautomaticsub=download_subtitles,
            skip_download=True,
            subtitleslangs=subtitle_languages,
            continue_dl=True,
            ignoreerrors=True,
            nooverwrites=False,
            outtmpl=self._get_output_templates(),
        )

    def _scan_downloaded_files(self, video_id: str) -> list[DownloadedFile]:
        """Scan for files matching video_id with optimized globbing."""
        if not self.output_dir.exists():
            return []

        # Use more specific pattern to reduce filesystem calls
        pattern = f"*{video_id}*"
        files = list(self.output_dir.glob(pattern))

        return [self._create_downloaded_file(f) for f in files if f.is_file()]

    def _create_downloaded_file(self, file_path: Path) -> DownloadedFile:
        """Create DownloadedFile object from path."""
        file_type, language = detect_file_type_and_language(file_path)
        try:
            size_bytes = file_path.stat().st_size
        except OSError:
            size_bytes = None

        return DownloadedFile(
            path=file_path, file_type=file_type, language=language, size_bytes=size_bytes
        )

    def _rename_files_with_slug(
        self, files: list[DownloadedFile], video_id: str, slug: str
    ) -> list[DownloadedFile]:
        """Rename files to include slug, return updated DownloadedFile objects."""
        renamed_files: list[DownloadedFile] = []

        for downloaded_file in files:
            file_path = downloaded_file.path
            original_name = file_path.name

            if video_id not in original_name:
                self.logger.warning(
                    f"File {original_name} doesn't contain {video_id}, skipping rename"
                )
                renamed_files.append(downloaded_file)
                continue

            video_id_pos = original_name.find(video_id)
            before_video_id = original_name[:video_id_pos]
            video_id_part = video_id
            after_video_id = original_name[video_id_pos + len(video_id) :]

            # Check what comes after video_id to determine if renaming is needed
            if after_video_id.startswith("."):
                # Original yt-dlp pattern (video_id.ext or video_id.lang.ext) - needs renaming
                new_name = f"{before_video_id}{video_id_part}_{slug}{after_video_id}"
                new_path = self.output_dir / new_name

                try:
                    file_path.rename(new_path)
                    self.logger.info(f"Renamed: {file_path.name} -> {new_name}")
                    final_path = new_path
                except OSError as e:
                    self.logger.warning(f"Failed to rename {file_path.name}: {e}")
                    final_path = file_path
            elif after_video_id.startswith("_"):
                # File already has slug (video_id_slug.ext pattern) - skip renaming
                self.logger.info(f"File {original_name} already has slug, skipping rename")
                final_path = file_path
            else:
                # Unexpected pattern after video_id - warn but don't rename
                self.logger.warning(
                    f"Unexpected pattern after video_id in {original_name}, skipping rename"
                )
                final_path = file_path

            updated_file = DownloadedFile(
                path=final_path,
                file_type=downloaded_file.file_type,
                language=downloaded_file.language,
                size_bytes=downloaded_file.size_bytes,
            )
            renamed_files.append(updated_file)

        return renamed_files

    def download_video_transcripts(
        self, video_url: str, video_id: str, subtitle_languages: list[str]
    ) -> VideoResult:
        """Perform the actual video download using yt-dlp."""
        self.logger.info(f"Downloading transcripts for video: {video_id}")
        self.logger.info(f"Languages requested: {subtitle_languages}")

        # Create download options with custom logger to capture warnings
        download_subtitles = bool(subtitle_languages)
        download_metadata = download_subtitles or False  # Could be made configurable

        self.logger.info(f"Downloading {'metadata and ' if download_metadata else ''}subtitles...")

        download_options = self._create_download_options(
            download_metadata, download_subtitles, subtitle_languages, video_id
        )

        try:
            # Check for shutdown signal before starting yt-dlp download
            if self._is_shutdown_requested():
                return self._create_failed_result(
                    video_url=video_url,
                    error_message="Download cancelled by user",
                    video_id=video_id,
                )

            # Add delay before yt-dlp download to prevent rate limiting
            self.logger.info(
                f"Sleeping {self.DEFAULT_SLEEP_BEFORE_DOWNLOAD} seconds before yt-dlp download to avoid rate limits..."
            )
            time.sleep(self.DEFAULT_SLEEP_BEFORE_DOWNLOAD)

            with yt_dlp.YoutubeDL(download_options) as youtube_downloader:
                video_info = youtube_downloader.extract_info(video_url, download=True)

            if not video_info:
                warnings, errors = self.ytdlp_logger.get_warnings_and_errors_separate()
                return self._create_failed_result(
                    video_url=video_url,
                    error_message="Could not extract video information",
                    video_id=video_id,
                    warnings=warnings,
                    errors=errors,
                )

            title = video_info.get("title", "Unknown Title")
            upload_date = video_info.get("upload_date")
            actual_video_id = video_info.get("id", video_id)

            title_slug = slugify(title, max_length=self.slug_max_length) if title else "unknown"
            downloaded_files = self._scan_downloaded_files(actual_video_id)
            downloaded_files = self._rename_files_with_slug(
                downloaded_files, actual_video_id, title_slug
            )

            self.logger.success(f"Successfully downloaded transcripts for: {title}")

            warnings, errors = self.ytdlp_logger.get_warnings_and_errors_separate()

            return self._create_success_result(
                video_id=actual_video_id,
                title=title,
                video_url=video_url,
                upload_date=upload_date,
                downloaded_files=downloaded_files,
                warnings=warnings,
                errors=errors,
            )

        except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as error:
            error_message = f"Failed to download transcripts: {error!s}"
            self.logger.error(error_message)
            warnings, errors = self.ytdlp_logger.get_warnings_and_errors_separate()
            return self._create_failed_result(
                video_url=video_url,
                error_message=error_message,
                video_id=video_id,
                warnings=warnings,
                errors=errors,
            )
        except Exception as error:
            # Catch any other unexpected errors
            error_message = f"Unexpected error during download: {error!s}"
            self.logger.error(error_message)
            warnings, errors = self.ytdlp_logger.get_warnings_and_errors_separate()
            return self._create_failed_result(
                video_url=video_url,
                error_message=error_message,
                video_id=video_id,
                warnings=warnings,
                errors=errors,
            )

    def _create_failed_result(
        self,
        video_url: str,
        error_message: str,
        video_id: str | None = None,
        title: str | None = None,
        downloaded_files: list[DownloadedFile] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> VideoResult:
        """Create a failed VideoResult with the given error message."""
        self.logger.error(error_message)
        # If no errors list provided but we have an error_message, add it to errors
        if not errors:
            errors = [error_message]
        return VideoResult(
            video_id=video_id,
            title=title,
            url=video_url,
            warnings=warnings or [],
            errors=errors or [],
            downloaded_files=downloaded_files or [],
        )

    def _create_success_result(
        self,
        video_id: str,
        title: str,
        video_url: str,
        upload_date: str | None = None,
        downloaded_files: list[DownloadedFile] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> VideoResult:
        """Create a successful VideoResult with the given information."""
        return VideoResult(
            video_id=video_id,
            title=title,
            url=video_url,
            upload_date=upload_date,
            warnings=warnings or [],
            errors=errors or [],
            downloaded_files=downloaded_files or [],
        )
