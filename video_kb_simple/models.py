"""Data models and types for video-kb-simple."""

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


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
    warnings: list[str] = Field(default_factory=list)  # Captured yt-dlp warnings
    errors: list[str] = Field(default_factory=list)  # Captured yt-dlp errors
    downloaded_files: list[DownloadedFile] = Field(default_factory=list)

    @property
    def is_full_success(self) -> bool:
        """Check if this is fully successful (no warnings or errors)."""
        return not self.warnings and not self.errors

    @property
    def is_partial_success(self) -> bool:
        """Check if this is a partial success (successful with warnings)."""
        return bool(self.warnings) and not self.errors

    @property
    def is_fail(self) -> bool:
        """Check if this download failed (has errors)."""
        return bool(self.errors)


class PlaylistResult(BaseModel):
    """Complete result from a download operation."""

    playlist_details: PlaylistDetails | None = None
    video_results: list[VideoResult] = Field(default_factory=list)
    total_requested: int = 0
    processing_time_seconds: float = 0.0

    @property
    def success_downloads(self) -> int:
        """Count of videos that were fully successful (no warnings or errors)."""
        return sum(1 for vr in self.video_results if vr.is_full_success)

    @property
    def partial_success_downloads(self) -> int:
        """Count of videos that were partially successful (warnings but no errors)."""
        return sum(1 for vr in self.video_results if vr.is_partial_success)

    @property
    def fail_downloads(self) -> int:
        """Count of videos that failed to download (have errors)."""
        return sum(1 for vr in self.video_results if vr.is_fail)

    @property
    def errors(self) -> list[str]:
        """All errors from all video results."""
        all_errors = []
        for video_result in self.video_results:
            all_errors.extend(video_result.errors)
        return all_errors

    @property
    def warnings(self) -> list[str]:
        """All warnings from all video results."""
        all_warnings = []
        for video_result in self.video_results:
            all_warnings.extend(video_result.warnings)
        return all_warnings
