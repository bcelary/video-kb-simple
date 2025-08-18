"""Video downloader and transcript extractor using yt-dlp."""

import random
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import yt_dlp
from pydantic import BaseModel, Field
from rich.console import Console


class VideoInfo(BaseModel):
    """Video information model."""

    title: str
    upload_date: str | None = None
    url: str
    video_id: str | None = None


class PlaylistInfo(BaseModel):
    """Playlist/Channel information model."""

    title: str
    playlist_id: str
    uploader: str | None = None
    video_count: int | None = None
    url: str
    playlist_type: str = "playlist"  # "playlist", "channel_videos", "channel_shorts", etc.


class BatchResult(BaseModel):
    """Batch download result model."""

    playlist_info: PlaylistInfo
    total_videos: int
    successful_downloads: int
    failed_downloads: int
    skipped_videos: int
    downloaded_files: list[Path] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    processing_time: float


class VideoDownloader:
    """Downloads videos and extracts transcripts using yt-dlp."""

    def __init__(
        self,
        output_dir: Path = Path("./transcripts"),
        verbose: bool = False,
        min_sleep_interval: int = 10,
        max_sleep_interval: int = 30,
        browser_for_cookies: str | None = None,
    ):
        """Initialize the downloader.

        Args:
            output_dir: Directory to save transcripts
            verbose: Enable verbose output
            min_sleep_interval: Minimum seconds to sleep between requests
            max_sleep_interval: Maximum seconds to sleep between requests
            browser_for_cookies: Browser to extract cookies from (firefox, chrome, etc)

        Raises:
            RuntimeError: If required dependencies are missing
        """
        self.output_dir = output_dir
        self.verbose = verbose
        self.min_sleep_interval = min_sleep_interval
        self.max_sleep_interval = max_sleep_interval
        self.browser_for_cookies = browser_for_cookies
        self.console = Console()
        self._validate_dependencies()

    def _create_ytdlp_options(
        self, use_impersonation: bool = False, **kwargs: Any
    ) -> dict[str, Any]:
        """Create yt-dlp options dictionary."""
        base_options: dict[str, Any] = {
            "sleep_interval": self.min_sleep_interval,
            "max_sleep_interval": self.max_sleep_interval,
            "socket_timeout": 30,
            "quiet": not self.verbose,
            "no_warnings": not self.verbose,
        }

        # Add cookie support if browser specified
        if self.browser_for_cookies:
            base_options["cookiesfrombrowser"] = (self.browser_for_cookies,)

        if use_impersonation:
            base_options.update(
                {
                    "impersonate": "safari",
                    "sleep_requests": random.randint(3, 7),  # nosec B311
                }
            )

        base_options.update(kwargs)
        return base_options

    def _extract_video_id_from_url(self, url: str) -> str | None:
        """Extract video ID from YouTube URL without API call."""

        # Match various YouTube URL formats
        patterns = [
            r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
            r"youtube\.com/v/([a-zA-Z0-9_-]{11})",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _is_single_video_url(self, url: str) -> bool:
        """Check if URL points to a single video rather than a playlist/channel.

        Returns:
            True if URL is a single video, False if it's a playlist/channel
        """
        # Check for single video patterns
        single_video_patterns = [
            r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
            r"youtube\.com/v/([a-zA-Z0-9_-]{11})",
        ]

        for pattern in single_video_patterns:
            if (
                re.search(pattern, url)
                and "playlist?list=" not in url
                and "/videos" not in url
                and "/shorts" not in url
            ):
                return True

        return False

    def _normalize_playlist_url(self, url: str) -> tuple[str, str]:
        """Normalize URL for optimal playlist/channel processing.

        Returns:
            (normalized_url, playlist_type)
        """

        # If it's a channel URL without specific tab, default to /videos
        if re.match(r"https?://(?:www\.)?youtube\.com/@[\w-]+/?$", url):
            normalized_url = url.rstrip("/") + "/videos"
            playlist_type = "channel_videos"
            if self.verbose:
                self.console.print(
                    f"[blue]Converting channel URL to videos tab:[/blue] {normalized_url}"
                )
        elif "/videos" in url:
            normalized_url = url
            playlist_type = "channel_videos"
        elif "/shorts" in url:
            normalized_url = url
            playlist_type = "channel_shorts"
        elif "/streams" in url or "/live" in url:
            normalized_url = url
            playlist_type = "channel_live"
        elif "playlist?list=" in url:
            normalized_url = url
            playlist_type = "playlist"
        else:
            # Default behavior for other URLs
            normalized_url = url
            playlist_type = "unknown"

        return normalized_url, playlist_type

    def _create_single_video_playlist(self, video_url: str) -> tuple[PlaylistInfo, list[str]]:
        """Create an artificial playlist structure for a single video.

        Args:
            video_url: Single video URL

        Returns:
            (PlaylistInfo, [video_url]) - Artificial playlist with one video
        """
        # Extract basic info without full metadata to minimize API calls
        ydl_opts = self._create_ytdlp_options(extract_flat=True)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

                if not info:
                    raise RuntimeError("No video information extracted")

                # Create artificial playlist info for single video
                playlist_info = PlaylistInfo(
                    title=f"Single Video: {info.get('title', 'Unknown Video')}",
                    playlist_id=info.get("id", "unknown"),
                    uploader=info.get("uploader", info.get("channel", "Unknown")),
                    video_count=1,
                    url=video_url,
                    playlist_type="single_video",
                )

                return playlist_info, [video_url]

        except Exception as e:
            if self.verbose:
                self.console.print(f"[red]Failed to extract video info: {e!s}[/red]")
            raise RuntimeError(f"Failed to extract video info: {e!s}") from e

    def _extract_playlist_info(
        self,
        url: str,
        use_impersonation: bool = False,
    ) -> tuple[PlaylistInfo, list[str]]:
        """Extract playlist info and video URLs only (no metadata) to minimize API calls."""

        # Normalize URL for optimal processing
        normalized_url, playlist_type = self._normalize_playlist_url(url)
        ydl_opts = self._create_ytdlp_options(
            use_impersonation=use_impersonation, extract_flat=True
        )

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(normalized_url, download=False)

                if not info:
                    raise RuntimeError("No playlist/channel information extracted")

                # Extract playlist info
                playlist_info = PlaylistInfo(
                    title=info.get("title", "Unknown Playlist"),
                    playlist_id=info.get("id", info.get("channel_id", "unknown")),
                    uploader=info.get(
                        "uploader", info.get("channel", info.get("title", "Unknown"))
                    ),
                    video_count=info.get("playlist_count", len(info.get("entries", []))),
                    url=normalized_url,
                    playlist_type=playlist_type,
                )

                # Extract video URLs only (minimal metadata)
                entries = info.get("entries", [])
                if not entries:
                    if self.verbose:
                        self.console.print("[yellow]No videos found in playlist/channel[/yellow]")
                    return playlist_info, []

                video_urls = []
                for entry in entries:
                    if not entry:  # Skip None entries
                        continue

                    # Extract URL - use direct URL if available, otherwise construct from video ID
                    video_url = (
                        entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}"
                    )
                    if video_url:
                        video_urls.append(video_url)

                return playlist_info, video_urls

        except Exception as e:
            if self.verbose:
                self.console.print(f"[red]Failed to extract playlist info: {e!s}[/red]")
            raise RuntimeError(f"Failed to extract playlist info: {e!s}") from e

    def download_playlist_transcripts(
        self,
        playlist_url: str,
        max_videos: int | None = None,
        subtitles_langs: list[str] | None = None,
    ) -> BatchResult:
        """Download transcripts from all videos in a playlist or channel.

        Args:
            playlist_url: Playlist or Channel URL
            max_videos: Maximum number of videos to process
            subtitles_langs: List of language codes to download (e.g. ['en', 'es'])

        Returns:
            BatchResult with processing statistics
        """
        start_time = time.time()

        try:
            # Step 1: Determine if this is a single video or playlist and get info accordingly
            if self._is_single_video_url(playlist_url):
                if self.verbose:
                    self.console.print(
                        "[blue]Step 1: Detected single video, creating artificial playlist...[/blue]"
                    )
                playlist_info, video_urls = self._create_single_video_playlist(playlist_url)
            else:
                if self.verbose:
                    self.console.print(
                        "[blue]Step 1: Getting playlist information and video URLs...[/blue]"
                    )
                playlist_info, video_urls = self._extract_playlist_info(playlist_url)

            if self.verbose:
                self.console.print(f"[green]Playlist:[/green] {playlist_info.title}")
                self.console.print(f"[green]Type:[/green] {playlist_info.playlist_type}")
                if playlist_info.video_count:
                    self.console.print(f"[green]Total videos:[/green] {playlist_info.video_count}")
                self.console.print(f"[blue]Found {len(video_urls)} video URLs[/blue]")

            if not video_urls:
                return BatchResult(
                    playlist_info=playlist_info,
                    total_videos=0,
                    successful_downloads=0,
                    failed_downloads=0,
                    skipped_videos=0,
                    processing_time=time.time() - start_time,
                )

            # Step 2: Process each video individually with rate limiting
            if self.verbose:
                self.console.print(
                    "[blue]Step 2: Processing videos individually with metadata...[/blue]"
                )

            successful_downloads = 0
            failed_downloads = 0
            skipped_videos = 0
            downloaded_files = []
            errors = []
            processed_videos = 0

            for i, video_url in enumerate(video_urls):
                # Add rate limiting delay between video processing
                if i > 0:  # Skip delay for first video
                    delay = random.randint(self.min_sleep_interval, self.max_sleep_interval)  # nosec B311
                    if self.verbose:
                        self.console.print(
                            f"[dim]Waiting {delay}s before processing next video...[/dim]"
                        )
                    time.sleep(delay)

                # Add extra delay after every 5 videos to be more conservative
                if i > 0 and (i + 1) % 5 == 0:
                    extra_delay = random.randint(60, 120)  # nosec B311 - 1-2 minute pause every 5 videos
                    if self.verbose:
                        self.console.print(
                            f"[yellow]Taking extended break ({extra_delay}s) after {i + 1} videos...[/yellow]"
                        )
                    time.sleep(extra_delay)

                if self.verbose:
                    self.console.print(
                        f"\n[blue][{i + 1}/{len(video_urls)}][/blue] Processing: {video_url}"
                    )

                try:
                    # Check max_videos limit
                    if max_videos and processed_videos >= max_videos:
                        if self.verbose:
                            self.console.print(
                                f"[blue]Reached max_videos limit ({max_videos})[/blue]"
                            )
                        break

                    if self.verbose:
                        self.console.print(f"[green]Processing:[/green] {video_url}")

                    # Download transcript for this video
                    video_downloaded_files = self._download_video_files(video_url, subtitles_langs)

                    downloaded_files.extend(video_downloaded_files)
                    successful_downloads += 1
                    processed_videos += 1

                    if self.verbose:
                        for file_path in video_downloaded_files:
                            self.console.print(f"[green]✓[/green] 📄 {file_path.name}")

                except Exception as e:
                    failed_downloads += 1
                    error_msg = f"{video_url}: {e!s}"
                    errors.append(error_msg)

                    if self.verbose:
                        self.console.print(f"[red]✗[/red] Failed: {e!s}")

                    # Check if it's a rate limit error and add extra delay
                    error_str = str(e).lower()
                    if (
                        "429" in error_str
                        or "too many requests" in error_str
                        or "rate limit" in error_str
                    ):
                        rate_limit_delay = random.randint(300, 600)  # nosec B311 - 5-10 minute delay for rate limits
                        if self.verbose:
                            self.console.print(
                                f"[red]Rate limited! Taking extended break ({rate_limit_delay}s)...[/red]"
                            )
                        time.sleep(rate_limit_delay)

                    # Continue with next video instead of stopping
                    continue

            processing_time = time.time() - start_time

            return BatchResult(
                playlist_info=playlist_info,
                total_videos=len(video_urls),
                successful_downloads=successful_downloads,
                failed_downloads=failed_downloads,
                skipped_videos=skipped_videos,
                downloaded_files=downloaded_files,
                errors=errors,
                processing_time=processing_time,
            )

        except Exception as e:
            if self.verbose:
                self.console.print(f"[red]Playlist processing failed: {e!s}[/red]")
            raise RuntimeError(f"Failed to process playlist: {e!s}") from e

    def _download_video_files(
        self,
        url: str,
        subtitles_langs: list[str] | None = None,
    ) -> list[Path]:
        """Download transcript and metadata files for a single video in isolated directory.

        Args:
            url: Video URL to download
            subtitles_langs: List of language codes (e.g., ['en', 'es']). Defaults to ['en']

        Returns:
            List of paths to downloaded transcript and metadata files
        """
        if subtitles_langs is None:
            subtitles_langs = ["en"]

        # Create persistent temporary directory (preserved across retry attempts for yt-dlp optimization)
        temp_dir = Path(tempfile.mkdtemp(prefix="video_kb_", dir=self.output_dir))

        try:
            # Create yt-dlp output templates for temp directory
            subtitle_template = str(
                temp_dir / "%(upload_date>%Y-%m-%d)s_%(id)s.%(subtitle_lang)s.%(ext)s"
            )
            metadata_template = str(temp_dir / "%(upload_date>%Y-%m-%d)s_%(id)s.%(ext)s")

            if self.verbose:
                self.console.print(f"[blue]Languages:[/blue] {','.join(subtitles_langs)}")
                self.console.print("[blue]Downloading:[/blue] subtitles + metadata JSON")
                self.console.print(f"[blue]Temp directory:[/blue] {temp_dir}")

            max_attempts = 3
            base_delay = 30

            ydl_opts = {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "writeinfojson": True,
                "skip_download": True,
                "subtitleslangs": subtitles_langs,
                "outtmpl": {
                    "subtitle": subtitle_template,
                    "infojson": metadata_template,
                },
            }

            for attempt in range(max_attempts):
                try:
                    if attempt > 0:
                        delay = base_delay * (2 ** (attempt - 1))
                        if self.verbose:
                            self.console.print(
                                f"[yellow]Waiting {delay}s before retry {attempt + 1}/{max_attempts}[/yellow]"
                            )
                        time.sleep(delay)

                    use_impersonation = attempt == max_attempts - 1
                    if self.verbose and use_impersonation:
                        self.console.print(
                            "[yellow]Using browser impersonation for final attempt[/yellow]"
                        )

                    options = self._create_ytdlp_options(
                        use_impersonation=use_impersonation, **ydl_opts
                    )

                    # yt-dlp will reuse existing files in persistent temp directory across attempts
                    with yt_dlp.YoutubeDL(options) as ydl:
                        ydl.download([url])

                    # If we reach here: yt-dlp completed successfully (downloads whatever is available)
                    # Missing subtitles/metadata don't throw exceptions, only real failures do
                    temp_files = list(temp_dir.glob("*"))

                    final_files: list[Path] = []

                    if not temp_files:
                        # yt-dlp succeeded but no content available - this is valid
                        if self.verbose:
                            self.console.print(
                                f"[yellow]No files available for download from {url}[/yellow]"
                            )
                        return final_files

                    # Success: move all available files to final location
                    for temp_file in temp_files:
                        if temp_file.is_file():  # Skip directories
                            final_path = self.output_dir / temp_file.name
                            temp_file.rename(final_path)
                            final_files.append(final_path)

                    if self.verbose:
                        subtitle_count = len(
                            [f for f in final_files if not f.name.endswith(".json")]
                        )
                        metadata_count = len([f for f in final_files if f.name.endswith(".json")])
                        self.console.print(
                            f"[green]Downloaded {subtitle_count} subtitle file(s) + {metadata_count} metadata file(s)[/green]"
                        )

                    return final_files

                except Exception as e:
                    # Only real failures reach here (network errors, rate limits, access denied, etc.)
                    if attempt == max_attempts - 1:
                        if self.verbose:
                            self.console.print("[red]All retry attempts exhausted[/red]")
                        raise RuntimeError(f"Failed to download subtitles: {e!s}") from e

                    error_str = str(e).lower()
                    if "429" in error_str or "too many requests" in error_str or "403" in error_str:
                        if self.verbose:
                            self.console.print(
                                f"[yellow]Rate limited/blocked on attempt {attempt + 1}, retrying...[/yellow]"
                            )
                        continue
                    else:
                        raise RuntimeError(f"Failed to download subtitles: {e!s}") from e

            # This should never be reached due to the logic above, but included for type safety
            raise RuntimeError("Failed to download subtitles after all attempts")

        finally:
            # Cleanup temp directory
            if temp_dir.exists():
                try:
                    temp_dir.rmdir()  # Will only succeed if empty
                except OSError:
                    # Directory not empty, clean it up
                    shutil.rmtree(temp_dir, ignore_errors=True)

    def _validate_dependencies(self) -> None:
        """Validate required dependencies."""
        try:
            _ = yt_dlp.YoutubeDL
        except AttributeError as e:
            raise RuntimeError(
                "yt-dlp Python module not installed. Install with: pip install yt-dlp"
            ) from e

        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                "ffmpeg not found. Required for yt-dlp. "
                "Install: brew install ffmpeg (macOS) | apt install ffmpeg (Linux)"
            )

        if not shutil.which("ffprobe"):
            raise RuntimeError("ffprobe not found. Should be installed with ffmpeg.")

        if self.verbose:
            self.console.print("[green]✓[/green] Dependencies validated")
