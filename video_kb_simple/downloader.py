"""Simplified video downloader and transcript extractor using yt-dlp."""

import json
import re
import time
from enum import Enum
from pathlib import Path
from typing import Any

import yt_dlp
from pydantic import BaseModel, Field
from rich.console import Console
from slugify import slugify

YOUTUBE_VIDEO_URL_PATTERNS = [
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
    r"youtube\.com/v/([a-zA-Z0-9_-]{11})",
]

YOUTUBE_CHANNEL_URL_PATTERN = r"https?://(?:www\.)?youtube\.com/@[\w-]+/?$"

DEFAULT_SUBTITLE_LANGUAGES = ["en"]
SUBTITLE_EXTENSIONS = {".vtt", ".srt", ".ass"}
METADATA_EXTENSION = ".json"
FILE_TYPE_SUBTITLE = "subtitle"
FILE_TYPE_METADATA = "metadata"
FILE_TYPE_UNKNOWN = "unknown"
DEFAULT_SLUG_MAX_LENGTH = 20


class DownloadError(Exception):
    """Base exception for downloader setup/initialization errors."""

    pass


class URLNormalizationError(DownloadError):
    """Raised when URL cannot be normalized or is invalid."""

    pass


class PlaylistType(Enum):
    """Enumeration of supported playlist types."""

    CHANNEL_VIDEOS = "channel_videos"
    CHANNEL_SHORTS = "channel_shorts"
    CHANNEL_LIVE = "channel_live"
    PLAYLIST = "playlist"
    SINGLE_VIDEO = "single_video"


def normalize_languages(subtitle_languages: list[str] | None) -> list[str]:
    """Normalize language list, providing defaults if None."""
    return (
        subtitle_languages if subtitle_languages is not None else DEFAULT_SUBTITLE_LANGUAGES.copy()
    )


def detect_file_type_and_language(file_path: Path) -> tuple[str, str | None]:
    """Detect file type and language from file path."""
    if file_path.suffix == METADATA_EXTENSION:
        return FILE_TYPE_METADATA, None
    elif file_path.suffix in SUBTITLE_EXTENSIONS:
        parts = file_path.stem.split(".")
        language = parts[-1] if len(parts) >= 2 else "unknown"
        return FILE_TYPE_SUBTITLE, language
    else:
        return FILE_TYPE_UNKNOWN, None


def extract_video_id_from_url(url: str) -> str | None:
    """Extract video ID from YouTube URL without API call."""
    for pattern in YOUTUBE_VIDEO_URL_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def normalize_playlist_url(url: str) -> tuple[str, PlaylistType]:
    """Normalize URL for optimal playlist/channel processing."""
    normalized_url = url
    playlist_type = None

    if re.match(YOUTUBE_CHANNEL_URL_PATTERN, url):
        normalized_url = url.rstrip("/") + "/videos"
        playlist_type = PlaylistType.CHANNEL_VIDEOS
    else:
        if "/videos" in url:
            playlist_type = PlaylistType.CHANNEL_VIDEOS
        elif "/shorts" in url:
            playlist_type = PlaylistType.CHANNEL_SHORTS
        elif "/streams" in url or "/live" in url:
            playlist_type = PlaylistType.CHANNEL_LIVE
        elif "playlist?list=" in url:
            playlist_type = PlaylistType.PLAYLIST
        else:
            for pattern in YOUTUBE_VIDEO_URL_PATTERNS:
                if re.search(pattern, url):
                    playlist_type = PlaylistType.SINGLE_VIDEO

    if playlist_type is None:
        raise URLNormalizationError(f"Unable to normalize the playlist url: {url}")

    return normalized_url, playlist_type


class PlaylistDetails(BaseModel):
    """Details about the playlist/channel/video collection."""

    playlist_id: str | None = None
    playlist_type: PlaylistType | None = None
    title: str | None = None
    url: str
    uploader: str | None = None
    video_urls: list[str] = Field(default_factory=list)  # URLs of videos found in playlist


class DownloadedFile(BaseModel):
    """Information about a downloaded file."""

    path: Path
    file_type: str  # "subtitle", "metadata", "transcript", etc.
    language: str | None = None  # Language code for subtitles, None for metadata
    size_bytes: int | None = None


class VideoResult(BaseModel):
    """Result for a single video download."""

    video_id: str | None = None
    title: str | None = None
    url: str | None = None
    upload_date: str | None = None
    success: bool = False
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)  # Captured yt-dlp warnings and errors
    downloaded_files: list[DownloadedFile] = Field(default_factory=list)


class PlaylistResult(BaseModel):
    """Complete result from a download operation."""

    playlist_details: PlaylistDetails | None = None
    video_results: list[VideoResult] = Field(default_factory=list)
    total_requested: int = 0
    successful_downloads: int = 0
    failed_downloads: int = 0
    processing_time_seconds: float = 0.0
    errors: list[str] = Field(default_factory=list)


class Logger:
    """Simple logger that handles verbosity internally with consistent color styling."""

    def __init__(self, console: Console, verbose: bool = False):
        self.console = console
        self.verbose = verbose

    def info(self, message: str) -> None:
        """Log info message with blue styling if verbose is enabled."""
        if self.verbose:
            self.console.print(f"[blue]{message}[/blue]")

    def error(self, message: str) -> None:
        """Log error message with red styling (always shown regardless of verbosity)."""
        self.console.print(f"[red]{message}[/red]")

    def success(self, message: str) -> None:
        """Log success message with green styling if verbose is enabled."""
        if self.verbose:
            self.console.print(f"[green]{message}[/green]")

    def warning(self, message: str) -> None:
        """Log warning message with yellow styling if verbose is enabled."""
        if self.verbose:
            self.console.print(f"[yellow]{message}[/yellow]")

    def debug(self, message: str) -> None:
        """Log debug message with cyan styling (always shown regardless of verbosity)."""
        self.console.print(f"[cyan]{message}[/cyan]")


class YTDLPLogger:
    """Custom logger for yt-dlp to capture warnings and errors."""

    def __init__(self, console_logger: Logger, debug: bool = False):
        self.console_logger = console_logger
        self.debug_enabled = debug
        self.captured_warnings: list[str] = []
        self.captured_errors: list[str] = []

    def debug(self, msg: str) -> None:
        """Handle debug messages."""
        if self.debug_enabled:
            # Clean up the message - strip all leading/trailing whitespace and remove yt-dlp prefixes
            clean_msg = self._clean_message(msg)
            if clean_msg:
                self.console_logger.debug(f"[DEBUG] {clean_msg}")

    def info(self, msg: str) -> None:
        """Handle info messages."""
        if self.debug_enabled:
            # Clean up the message - strip all leading/trailing whitespace and remove yt-dlp prefixes
            clean_msg = self._clean_message(msg)
            if clean_msg:
                self.console_logger.debug(f"[INFO] {clean_msg}")

    def _clean_message(self, msg: str) -> str:
        """Clean yt-dlp message by removing prefixes and extra whitespace."""
        if not msg:
            return ""

        # Strip leading/trailing whitespace
        clean_msg = msg.strip()

        # Remove common yt-dlp prefixes like [download], [info], etc.
        import re

        clean_msg = re.sub(r"^\[[^\]]+\]\s*", "", clean_msg)

        # Strip again in case the prefix removal left leading whitespace
        return clean_msg.strip()

    def warning(self, msg: str) -> None:
        """Handle warning messages - capture them for reporting."""
        # Clean up the message
        clean_msg = msg.strip()
        if clean_msg:
            self.captured_warnings.append(clean_msg)
            self.console_logger.warning(clean_msg)

    def error(self, msg: str) -> None:
        """Handle error messages - capture them for reporting."""
        # Clean up the message
        clean_msg = msg.strip()
        if clean_msg:
            self.captured_errors.append(clean_msg)
            self.console_logger.error(clean_msg)

    def get_warnings(self) -> list[str]:
        """Get all captured warnings."""
        return self.captured_warnings.copy()

    def get_errors(self) -> list[str]:
        """Get all captured errors."""
        return self.captured_errors.copy()

    def has_warnings_or_errors(self) -> bool:
        """Check if any warnings or errors were captured."""
        return bool(self.captured_warnings or self.captured_errors)


class SimpleDownloader:
    """Simplified video downloader that focuses on core functionality."""

    DEFAULT_SLEEP_REQUESTS = 5  # Sleep between metadata API requests
    DEFAULT_SLEEP_SUBTITLES = 60  # Sleep between subtitle downloads
    DEFAULT_SLEEP_INTERVAL = 15  # Minimum sleep between downloads
    DEFAULT_MAX_SLEEP_INTERVAL = 90  # Maximum sleep between downloads
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

    def __init__(
        self,
        output_dir: Path = Path("./transcripts"),
        verbose: bool = False,
        force_download: bool = False,
        browser_for_cookies: str | None = None,
        slug_max_length: int = DEFAULT_SLUG_MAX_LENGTH,
        debug: bool = False,
    ):
        """Initialize the simple downloader.

        Args:
            output_dir: Directory to save transcripts
            verbose: Enable verbose output
            force_download: Re-download transcripts even if they already exist
            browser_for_cookies: Browser to extract cookies from (e.g. 'firefox', 'chrome')
            slug_max_length: Maximum length for slugified titles in filenames
            debug: Enable yt-dlp debug output
        """
        self.output_dir = output_dir
        self.verbose = verbose
        self.force_download = force_download
        self.browser_for_cookies = browser_for_cookies
        self.slug_max_length = slug_max_length
        self.debug = debug

        console = Console()
        self.logger = Logger(console, verbose)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _create_ytdlp_options(self, **kwargs: Any) -> dict[str, Any]:
        """Create yt-dlp options dictionary with rate limiting and sensible defaults.

        For complete yt-dlp options documentation, see:
        https://github.com/yt-dlp/yt-dlp#usage-and-options

        Args:
            **kwargs: Additional options to override defaults

        Returns:
            Dictionary of yt-dlp options
        """
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
            "quiet": not (self.verbose or self.debug),
            "no_warnings": not (self.verbose or self.debug),
        }

        if self.browser_for_cookies:
            base_options["cookiesfrombrowser"] = (self.browser_for_cookies,)

        # Override with any provided options
        base_options.update(kwargs)
        return base_options

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
            playlist_details = self._extract_playlist_details(normalized_url, playlist_type)
            if playlist_details is None:
                # Failed to extract playlist details, create a failed result
                playlist_result = PlaylistResult(
                    playlist_details=None,
                    video_results=[],
                    total_requested=0,
                    successful_downloads=0,
                    failed_downloads=0,
                    processing_time_seconds=time.time() - start_time,
                    errors=["Failed to extract playlist details"],
                )
            else:
                playlist_result = self._download_playlist_transcripts(
                    playlist_details, max_videos, subtitle_languages
                )
                playlist_result.processing_time_seconds = time.time() - start_time

        self.logger.success(f"Download completed in {playlist_result.processing_time_seconds:.1f}s")
        self.logger.success(
            f"Success: {playlist_result.successful_downloads}, Failed: {playlist_result.failed_downloads}"
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
            successful_downloads=1 if video_result.success else 0,
            failed_downloads=0 if video_result.success else 1,
            processing_time_seconds=time.time() - start_time,
        )

        if not video_result.success:
            playlist_result.errors.append(video_result.error_message or "Unknown error")

        return playlist_result

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
        """Rename files to include slug, return updated DownloadedFile objects.

        Args:
            files: List of DownloadedFile objects to rename
            video_id: YouTube video ID
            slug: Slugified title to include in filename

        Returns:
            List of DownloadedFile objects with updated paths
        """
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

    def _check_existing_download(self, video_id: str) -> VideoResult | None:
        """Check if video already downloaded with metadata, return VideoResult if found.

        Args:
            video_id: YouTube video ID to check

        Returns:
            VideoResult if metadata JSON exists and can be loaded, None otherwise
        """
        existing_files = self._scan_downloaded_files(video_id)

        metadata_file = None
        for file in existing_files:
            if file.file_type == FILE_TYPE_METADATA:
                metadata_file = file
                break

        if not metadata_file:
            return None

        try:
            with open(metadata_file.path, encoding="utf-8") as f:
                metadata = json.load(f)

            title = metadata.get("title", "Unknown Title")
            upload_date = metadata.get("upload_date")
            actual_video_id = metadata.get("id", video_id)
            url = metadata.get("webpage_url") or metadata.get("original_url")

            self.logger.info(f"Found existing download for: {title}")

            return self._create_success_result(
                video_id=actual_video_id,
                title=title,
                video_url=url,
                upload_date=upload_date,
                downloaded_files=existing_files,
            )

        except (json.JSONDecodeError, OSError, KeyError) as e:
            self.logger.warning(f"Failed to load metadata from {metadata_file.path}: {e}")
            return None

    def _get_downloaded_languages(self, downloaded_files: list[DownloadedFile]) -> set[str]:
        """Extract set of language codes from downloaded subtitle files.

        Args:
            downloaded_files: List of DownloadedFile objects

        Returns:
            Set of language codes that have been downloaded
        """
        downloaded_languages = set()
        for file in downloaded_files:
            if file.file_type == FILE_TYPE_SUBTITLE and file.language:
                downloaded_languages.add(file.language)
        return downloaded_languages

    def _extract_playlist_details(
        self, normalized_url: str, playlist_type: PlaylistType
    ) -> PlaylistDetails | None:
        """Extract basic playlist information without downloading videos.

        Args:
            normalized_url: The normalized playlist/channel URL
            playlist_type: Type of playlist detected

        Returns:
            PlaylistDetails with basic info and video URLs, or None if extraction failed
        """
        self.logger.info(f"Extracting playlist details from: {normalized_url}")

        try:
            # Create custom logger to capture warnings and debug messages
            ytdlp_logger = YTDLPLogger(self.logger, debug=self.debug)

            # Use extract_flat=True to get only playlist metadata and video URLs
            extraction_options = self._create_ytdlp_options(
                extract_flat=True,
                quiet=not self.debug,  # Only quiet if debug is not enabled
                logger=ytdlp_logger,  # Use custom logger to capture warnings and debug messages
                no_warnings=False,  # Enable warnings so they can be captured
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

    def _create_failed_result(
        self,
        video_url: str,
        error_message: str,
        video_id: str | None = None,
        title: str | None = None,
        downloaded_files: list[DownloadedFile] | None = None,
        warnings: list[str] | None = None,
    ) -> VideoResult:
        """Create a failed VideoResult with the given error message.

        Args:
            video_url: The video URL that failed
            error_message: The error message to include
            video_id: Optional video ID if available
            title: Optional video title if available
            downloaded_files: Optional list of downloaded files
            warnings: Optional list of warnings captured during download

        Returns:
            VideoResult with success=False and the error message
        """
        self.logger.error(error_message)
        return VideoResult(
            video_id=video_id,
            title=title,
            url=video_url,
            success=False,
            error_message=error_message,
            warnings=warnings or [],
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
    ) -> VideoResult:
        """Create a successful VideoResult with the given information.

        Args:
            video_id: The video ID
            title: The video title
            video_url: The video URL
            upload_date: Optional upload date
            downloaded_files: Optional list of downloaded files
            warnings: Optional list of warnings captured during download

        Returns:
            VideoResult with success=True
        """
        return VideoResult(
            video_id=video_id,
            title=title,
            url=video_url,
            upload_date=upload_date,
            success=True,
            warnings=warnings or [],
            downloaded_files=downloaded_files or [],
        )

    def _handle_existing_download(
        self, existing_result: VideoResult, subtitle_languages: list[str]
    ) -> tuple[VideoResult | None, list[str]]:
        """Handle logic when existing download is found.

        Args:
            existing_result: The existing VideoResult from previous download
            subtitle_languages: List of requested subtitle languages

        Returns:
            Tuple of (VideoResult or None, updated subtitle_languages list)
            - If VideoResult is returned, use it directly (no download needed)
            - If None is returned, proceed with download using the updated subtitle_languages
        """
        # Check which languages are already downloaded
        downloaded_languages = self._get_downloaded_languages(existing_result.downloaded_files)
        remaining_languages = [
            lang for lang in subtitle_languages if lang not in downloaded_languages
        ]

        if not remaining_languages:
            # All requested languages are already downloaded
            self.logger.info(
                f"Skipping download, all requested languages {subtitle_languages} already exist (use --force to re-download)"
            )
            return existing_result, subtitle_languages
        else:
            # Some languages are missing, update subtitle_languages to only download missing ones
            self.logger.info(
                f"Found existing download, but missing languages: {remaining_languages}. Downloading only missing languages."
            )
            return None, remaining_languages

    def _create_download_options(
        self, download_metadata: bool, download_subtitles: bool, subtitle_languages: list[str]
    ) -> tuple[dict[str, Any], YTDLPLogger]:
        """Create yt-dlp options for downloading transcripts with custom logger.

        Returns:
            Tuple of (options_dict, logger_instance)
        """
        # Create custom logger to capture warnings
        ytdlp_logger = YTDLPLogger(self.logger, debug=self.debug)

        options = self._create_ytdlp_options(
            writeinfojson=download_metadata,
            writesubtitles=download_subtitles,
            writeautomaticsub=download_subtitles,
            skip_download=True,
            subtitleslangs=subtitle_languages,
            continue_dl=True,
            ignoreerrors=True,
            nooverwrites=False,
            outtmpl=self._get_output_templates(),
            logger=ytdlp_logger,  # Use custom logger to capture warnings
            no_warnings=False,  # Enable warnings so they can be captured
        )

        return options, ytdlp_logger

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

    def _perform_video_download(
        self, video_url: str, video_id: str, subtitle_languages: list[str]
    ) -> VideoResult:
        """Perform the actual video download using yt-dlp.

        Args:
            video_url: The video URL to download
            video_id: The extracted video ID
            subtitle_languages: List of subtitle languages to download

        Returns:
            VideoResult with download status and files
        """
        self.logger.info(f"Downloading transcripts for video: {video_id}")
        self.logger.info(f"Languages requested: {subtitle_languages}")

        # Create download options with custom logger to capture warnings
        download_subtitles = bool(subtitle_languages)
        download_metadata = download_subtitles or self.force_download

        self.logger.info(f"Downloading {'metadata and ' if download_metadata else ''}subtitles...")

        download_options, ytdlp_logger = self._create_download_options(
            download_metadata, download_subtitles, subtitle_languages
        )

        try:
            with yt_dlp.YoutubeDL(download_options) as youtube_downloader:
                video_info = youtube_downloader.extract_info(video_url, download=True)

            if not video_info:
                return self._create_failed_result(
                    video_url=video_url,
                    error_message="Could not extract video information",
                    video_id=video_id,
                    warnings=ytdlp_logger.get_warnings() + ytdlp_logger.get_errors(),
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

            return self._create_success_result(
                video_id=actual_video_id,
                title=title,
                video_url=video_url,
                upload_date=upload_date,
                downloaded_files=downloaded_files,
                warnings=ytdlp_logger.get_warnings() + ytdlp_logger.get_errors(),
            )

        except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as error:
            error_message = f"Failed to download transcripts: {error!s}"
            self.logger.error(error_message)
            return self._create_failed_result(
                video_url=video_url,
                error_message=error_message,
                video_id=video_id,
                warnings=ytdlp_logger.get_warnings() + ytdlp_logger.get_errors(),
            )
        except Exception as error:
            # Catch any other unexpected errors
            error_message = f"Unexpected error during download: {error!s}"
            self.logger.error(error_message)
            return self._create_failed_result(
                video_url=video_url,
                error_message=error_message,
                video_id=video_id,
                warnings=ytdlp_logger.get_warnings() + ytdlp_logger.get_errors(),
            )

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
            return self._create_failed_result(video_url, "Could not extract video ID")

        existing_result = self._check_existing_download(video_id)
        if existing_result and not self.force_download:
            result, updated_languages = self._handle_existing_download(
                existing_result, subtitle_languages
            )
            if result:
                return result
            subtitle_languages = updated_languages

        return self._perform_video_download(video_url, video_id, subtitle_languages)

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
            self.logger.info(f"Processing video {i}/{total_videos}: {video_url}")

            try:
                video_result = self._download_video_transcripts(video_url, subtitle_languages)
                video_results.append(video_result)

                if video_result.success:
                    successful_downloads += 1
                else:
                    failed_downloads += 1
                    if video_result.error_message:
                        errors.append(f"Video {i}: {video_result.error_message}")

            except Exception as error:
                error_message = f"Unexpected error processing video {i}: {error}"
                self.logger.error(error_message)
                errors.append(error_message)
                failed_downloads += 1

                video_result = self._create_failed_result(
                    video_url=video_url,
                    error_message=error_message,
                )
                video_results.append(video_result)

        self.logger.success(
            f"Playlist processing complete: {successful_downloads} successful, {failed_downloads} failed"
        )

        return PlaylistResult(
            playlist_details=playlist,
            video_results=video_results,
            total_requested=total_videos,
            successful_downloads=successful_downloads,
            failed_downloads=failed_downloads,
            errors=errors,
        )
