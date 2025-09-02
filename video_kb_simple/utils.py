"""Utility functions and constants for video-kb-simple."""

import re
from pathlib import Path
from typing import Any

# ==================== URL PATTERNS AND CONSTANTS ====================
YOUTUBE_VIDEO_URL_PATTERNS = [
    r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
    r"https?://(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})",
]

YOUTUBE_CHANNEL_URL_PATTERN = r"https?://(?:www\.)?youtube\.com/@[\w-]+/?$"

DEFAULT_SUBTITLE_LANGUAGES = ["en"]
SUBTITLE_EXTENSIONS = {".vtt", ".srt", ".ass"}
METADATA_EXTENSION = ".json"
FILE_TYPE_SUBTITLE = "subtitle"
FILE_TYPE_METADATA = "metadata"
FILE_TYPE_UNKNOWN = "unknown"


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


def normalize_playlist_url(url: str) -> tuple[str, Any]:
    """Normalize URL for optimal playlist/channel processing."""
    from .models import PlaylistType

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
        from .models import URLNormalizationError

        raise URLNormalizationError(f"Unable to normalize the playlist url: {url}")

    return normalized_url, playlist_type
