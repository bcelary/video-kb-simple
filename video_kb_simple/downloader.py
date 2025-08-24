"""Simplified video downloader and transcript extractor using yt-dlp."""

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

# File processing constants
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


class PlaylistExtractionError(DownloadError):
    """Raised when playlist information cannot be extracted from a valid URL."""

    pass


class PlaylistType(Enum):
    """Enumeration of supported playlist types."""

    CHANNEL_VIDEOS = "channel_videos"
    CHANNEL_SHORTS = "channel_shorts"
    CHANNEL_LIVE = "channel_live"
    PLAYLIST = "playlist"
    SINGLE_VIDEO = "single_video"


def normalize_languages(langs: list[str] | None) -> list[str]:
    """Normalize language list, providing defaults if None."""
    return langs if langs is not None else DEFAULT_SUBTITLE_LANGUAGES.copy()


def detect_file_type_and_language(file_path: Path) -> tuple[str, str | None]:
    """Detect file type and language from file path.

    Args:
        file_path: Path to the file

    Returns:
        (file_type, language) tuple
    """
    if file_path.suffix == METADATA_EXTENSION:
        return FILE_TYPE_METADATA, None
    elif file_path.suffix in SUBTITLE_EXTENSIONS:
        # Extract language from yt-dlp filename - last part before extension
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
    """Normalize URL for optimal playlist/channel processing.

    Returns:
        (normalized_url, playlist_type)
    """
    normalized_url = url
    playlist_type = None

    # If it's a channel URL without specific tab, default to /videos
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


class SimpleDownloader:
    """Simplified video downloader that focuses on core functionality."""

    # Rate limiting configuration to reduce YouTube API hits
    DEFAULT_SLEEP_REQUESTS = 2  # Sleep between metadata API requests
    DEFAULT_SLEEP_SUBTITLES = 10  # Sleep between subtitle downloads (increased from 3)
    DEFAULT_SLEEP_INTERVAL = 3  # Minimum sleep between downloads
    DEFAULT_MAX_SLEEP_INTERVAL = 30  # Maximum sleep between downloads
    DEFAULT_RATE_LIMIT = 500000  # Download bandwidth limit (bytes/sec)
    SOCKET_TIMEOUT = 30  # Network connection timeout

    def __init__(
        self,
        output_dir: Path = Path("./transcripts"),
        verbose: bool = False,
        force_download: bool = False,
        browser_for_cookies: str | None = None,
        slug_max_length: int = DEFAULT_SLUG_MAX_LENGTH,
    ):
        """Initialize the simple downloader.

        Args:
            output_dir: Directory to save transcripts
            verbose: Enable verbose output
            force_download: Re-download transcripts even if they already exist
            browser_for_cookies: Browser to extract cookies from (e.g. 'firefox', 'chrome')
            slug_max_length: Maximum length for slugified titles in filenames
        """
        self.output_dir = output_dir
        self.verbose = verbose
        self.force_download = force_download
        self.browser_for_cookies = browser_for_cookies
        self.slug_max_length = slug_max_length

        # Initialize logger with verbosity handling
        console = Console()
        self.logger = Logger(console, verbose)

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _create_ytdlp_options(self, **kwargs: Any) -> dict[str, Any]:
        """Create yt-dlp options dictionary with rate limiting and sensible defaults.

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
            "quiet": not self.verbose,
            "no_warnings": not self.verbose,
        }

        # Add browser cookies if specified
        if self.browser_for_cookies:
            base_options["cookiesfrombrowser"] = (self.browser_for_cookies,)

        # Override with any provided options
        base_options.update(kwargs)
        return base_options

    def download_transcripts(
        self, url: str, max_videos: int | None = None, langs: list[str] | None = None
    ) -> PlaylistResult:
        """Main entry point for downloading transcripts from any YouTube URL.

        This method acts as a router - it normalizes the URL, determines if it's
        a single video or playlist/channel, and delegates to the appropriate handler.

        Individual download failures are captured in the result object, not raised as exceptions.
        Only fundamental setup issues (invalid URL, network unavailable) raise exceptions.

        Args:
            url: YouTube URL (video, playlist, or channel)
            max_videos: Maximum number of videos to process (None = all)
            langs: List of language codes for subtitles (None = ['en'])

        Returns:
            PlaylistResult with detailed information about downloads and any errors

        Raises:
            URLNormalizationError: If URL cannot be parsed or normalized
            PlaylistExtractionError: If playlist info cannot be extracted (connection/auth issues)
        """
        start_time = time.time()
        langs = normalize_languages(langs)

        self.logger.info(f"Starting download from: {url}")
        self.logger.info(f"Max videos: {max_videos or 'unlimited'}")
        self.logger.info(f"Languages: {langs}")

        # Normalize URL and determine type (can raise URLNormalizationError)
        normalized_url, playlist_type = normalize_playlist_url(url)
        self.logger.info(f"Normalized URL: {normalized_url}")
        self.logger.info(f"Detected type: {playlist_type.value}")

        # Route to appropriate handler based on URL type
        if playlist_type == PlaylistType.SINGLE_VIDEO:
            # Handle single video as a playlist of one
            video_result = self._download_video_transcripts(url, langs)
            playlist_result = self._wrap_single_video_result(video_result, url, start_time)

        else:
            # Handle playlist/channel - extract details first (can raise PlaylistExtractionError)
            playlist_details = self._extract_playlist_details(normalized_url, playlist_type)

            # Then download from the playlist (errors go into result, not raised)
            playlist_result = self._download_playlist_transcripts(
                playlist_details, max_videos, langs
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
        # Create playlist details for single video
        playlist_details = PlaylistDetails(
            playlist_id=video_result.video_id,
            playlist_type=PlaylistType.SINGLE_VIDEO,
            title=video_result.title or "Single Video",
            url=url,
            uploader=None,
            video_urls=[url],
        )

        # Create playlist result
        playlist_result = PlaylistResult(
            playlist_details=playlist_details,
            video_results=[video_result],
            total_requested=1,
            successful_downloads=1 if video_result.success else 0,
            failed_downloads=0 if video_result.success else 1,
            processing_time_seconds=time.time() - start_time,
        )

        # Add error if video failed
        if not video_result.success:
            playlist_result.errors.append(video_result.error_message or "Unknown error")

        return playlist_result

    def _scan_and_rename_files(self, video_id: str, title: str) -> list[DownloadedFile]:
        """Scan downloaded files and rename them to include slugified title.

        Args:
            video_id: YouTube video ID
            title: Video title to slugify

        Returns:
            List of DownloadedFile objects with renamed files
        """
        downloaded_files: list[DownloadedFile] = []

        if not self.output_dir.exists():
            return downloaded_files

        # Create slugified title
        slug = slugify(title, max_length=self.slug_max_length) if title else "unknown"

        # Look for files that start with the video ID
        for file_path in self.output_dir.glob(f"{video_id}*"):
            if file_path.is_file():
                # Determine file type and language
                file_type, language = detect_file_type_and_language(file_path)

                # Simple approach: just insert slug after video_id, preserve everything else
                original_name = file_path.name

                # This should always be true since we found it with glob(f"{video_id}*")
                assert original_name.startswith(video_id), (
                    f"File {original_name} should start with {video_id}"
                )

                # Replace: videoId.rest -> videoId_slug.rest
                rest_of_name = original_name[len(video_id) :]  # Everything after video_id
                new_name = f"{video_id}_{slug}{rest_of_name}"

                # Rename the file
                new_path = self.output_dir / new_name
                try:
                    file_path.rename(new_path)
                    if self.verbose:
                        self.logger.info(f"Renamed: {file_path.name} -> {new_name}")
                    final_path = new_path
                except OSError as e:
                    if self.verbose:
                        self.logger.warning(f"Failed to rename {file_path.name}: {e}")
                    final_path = file_path

                # Get file size
                try:
                    size_bytes = final_path.stat().st_size
                except OSError:
                    size_bytes = None

                downloaded_file = DownloadedFile(
                    path=final_path, file_type=file_type, language=language, size_bytes=size_bytes
                )
                downloaded_files.append(downloaded_file)

        return downloaded_files

    def _extract_playlist_details(
        self, normalized_url: str, playlist_type: PlaylistType
    ) -> PlaylistDetails:
        """Extract basic playlist information without downloading videos.

        Args:
            normalized_url: The normalized playlist/channel URL
            playlist_type: Type of playlist detected

        Returns:
            PlaylistDetails with basic info and video URLs

        Raises:
            PlaylistExtractionError: If playlist info cannot be extracted
        """
        self.logger.info(f"Extracting playlist details from: {normalized_url}")

        try:
            # Use extract_flat=True to get only playlist metadata and video URLs
            extract_opts = self._create_ytdlp_options(
                extract_flat=True,
                quiet=True,  # Minimize output noise during extraction
            )

            with yt_dlp.YoutubeDL(extract_opts) as ydl:
                info = ydl.extract_info(normalized_url, download=False)

            if not info:
                raise PlaylistExtractionError(
                    f"Could not extract playlist information from: {normalized_url}"
                )

            # Extract playlist metadata
            playlist_id = info.get("id")
            title = info.get("title", "Unknown Playlist")
            uploader = info.get("uploader") or info.get("channel")

            # Extract video URLs from entries
            video_urls = []
            entries = info.get("entries", [])

            for entry in entries:
                if entry and entry.get("url"):
                    video_urls.append(entry["url"])
                elif entry and entry.get("id"):
                    # Construct URL from video ID if direct URL not available
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
            raise PlaylistExtractionError(f"Failed to extract playlist details: {e}") from e
        except Exception as e:
            raise PlaylistExtractionError(f"Unexpected error extracting playlist: {e}") from e

    def _download_video_transcripts(
        self,
        video_url: str,
        subtitles_langs: list[str] | None = None,
    ) -> VideoResult:
        """Download transcripts for a single video using metadata-first approach.

        Step 1: Download metadata to get video info
        Step 2: Download subtitles with requested languages

        Args:
            video_url: YouTube video URL
            subtitles_langs: List of language codes to download

        Returns:
            VideoResult with download status and any files downloaded
        """
        subtitles_langs = normalize_languages(subtitles_langs)

        # Extract video ID for tracking
        video_id = extract_video_id_from_url(video_url)

        self.logger.info(f"Downloading transcripts for video: {video_id}")
        self.logger.info(f"Languages requested: {subtitles_langs}")

        try:
            # Step 1+2: Download metadata and requested subtitles in single yt-dlp call
            self.logger.info("Downloading metadata and requested subtitles...")

            combined_opts = self._create_ytdlp_options(
                writeinfojson=True,
                writesubtitles=True,
                writeautomaticsub=True,
                skip_download=True,
                subtitleslangs=subtitles_langs,
                outtmpl={
                    "infojson": str(self.output_dir / "%(id)s.%(ext)s"),
                    "subtitle": str(self.output_dir / "%(id)s.%(subtitle_lang)s.%(ext)s"),
                },
            )

            with yt_dlp.YoutubeDL(combined_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)  # Extract info AND download files

            if not info:
                return VideoResult(
                    video_id=video_id,
                    url=video_url,
                    success=False,
                    error_message="Could not extract video information",
                )

            # Extract video metadata
            title = info.get("title", "Unknown Title")
            upload_date = info.get("upload_date")
            actual_video_id = info.get("id", video_id)

            self.logger.success(f"Downloaded metadata and subtitles for: {title}")

            # TODO: Step 3+4: Analyze metadata for additional required languages
            # - Check automatic_captions and subtitles in info dict
            # - Determine if source languages should be added for completeness
            # - Download additional subtitles if needed with second yt-dlp call

            # Scan output directory for files created by this download and rename them
            downloaded_files = self._scan_and_rename_files(actual_video_id, title)

            self.logger.success(f"Successfully downloaded transcripts for: {title}")

            return VideoResult(
                video_id=actual_video_id,
                title=title,
                url=video_url,
                upload_date=upload_date,
                success=True,
                downloaded_files=downloaded_files,
            )

        except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError) as e:
            error_message = f"Failed to download transcripts: {e!s}"
            self.logger.error(error_message)
        except Exception as e:
            # Catch any other unexpected errors
            error_message = f"Unexpected error during download: {e!s}"
            self.logger.error(error_message)

        return VideoResult(
            video_id=video_id, url=video_url, success=False, error_message=error_message
        )

    def _download_playlist_transcripts(
        self,
        playlist: PlaylistDetails,
        max_videos: int | None = None,
        subtitles_langs: list[str] | None = None,
    ) -> PlaylistResult:
        """Download transcripts from videos found in a normalized playlist.

        Args:
            playlist: Normalized playlist
            max_videos: Maximum number of videos to process
            subtitles_langs: List of language codes to download (e.g. ['en', 'es'])

        Returns:
            PlaylistResult with detailed information about what was downloaded
        """
        subtitles_langs = normalize_languages(subtitles_langs)

        self.logger.info(f"Downloading from playlist: {playlist.title}")
        self.logger.info(f"Languages: {subtitles_langs}")
        self.logger.info(f"Output directory: {self.output_dir}")

        # Determine videos to process
        videos_to_process = playlist.video_urls
        if max_videos and max_videos > 0:
            videos_to_process = videos_to_process[:max_videos]

        total_videos = len(videos_to_process)
        self.logger.info(f"Processing {total_videos} videos...")

        # Initialize result tracking
        video_results = []
        successful_downloads = 0
        failed_downloads = 0
        errors = []

        # Process each video
        for i, video_url in enumerate(videos_to_process, 1):
            self.logger.info(f"Processing video {i}/{total_videos}: {video_url}")

            try:
                # Download transcripts for this video
                video_result = self._download_video_transcripts(video_url, subtitles_langs)
                video_results.append(video_result)

                # Update counters
                if video_result.success:
                    successful_downloads += 1
                else:
                    failed_downloads += 1
                    if video_result.error_message:
                        errors.append(f"Video {i}: {video_result.error_message}")

            except Exception as e:
                # Handle unexpected errors during individual video processing
                error_message = f"Unexpected error processing video {i}: {e}"
                self.logger.error(error_message)
                errors.append(error_message)
                failed_downloads += 1

                # Create failed result for this video
                video_result = VideoResult(url=video_url, success=False, error_message=str(e))
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
