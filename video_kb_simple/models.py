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
