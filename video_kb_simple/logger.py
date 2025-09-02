"""Logging infrastructure for video-kb-simple."""

import logging

from rich.console import Console
from rich.markup import escape

from .ansi_converter import ansi_to_rich


class Logger:
    """Simple logger that handles verbosity internally with consistent color styling."""

    def __init__(self, console: Console, level: int = logging.INFO):
        self.console = console
        self.level = level

    def debug(self, message: str) -> None:
        """Log debug message with cyan styling if level allows."""
        if self.level <= logging.DEBUG:
            self.console.print(message, style="cyan")

    def info(self, message: str) -> None:
        """Log info message with blue styling if level allows."""
        if self.level <= logging.INFO:
            self.console.print(message, style="blue")

    def warning(self, message: str) -> None:
        """Log warning message with yellow styling if level allows."""
        if self.level <= logging.WARNING:
            self.console.print(message, style="yellow")

    def error(self, message: str) -> None:
        """Log error message with red styling (always shown regardless of level)."""
        if self.level <= logging.ERROR:
            self.console.print(message, style="red")

    def success(self, message: str) -> None:
        """Log success message with green styling if level allows."""
        if self.level <= logging.ERROR:
            self.console.print(message, style="green")


class YTDLPLogger:
    """Custom logger for yt-dlp to capture warnings and errors."""

    def __init__(
        self, console_logger: Logger, level: int = logging.INFO, video_id: str | None = None
    ):
        self.console_logger = console_logger
        self.level = level
        self.video_id = video_id
        self.captured_warnings: list[str] = []
        self.captured_errors: list[str] = []

    def debug(self, msg: str) -> None:
        """Handle debug messages."""
        if self.level <= logging.DEBUG:
            rich_msg = ansi_to_rich(msg)
            prefix = escape(f"[YT-DLP] [{self.video_id}]")
            self.console_logger.debug(f"{prefix} {rich_msg}")

    def info(self, msg: str) -> None:
        """Handle info messages."""
        if self.level <= logging.DEBUG:
            rich_msg = ansi_to_rich(msg)
            prefix = escape(f"[YT-DLP] [{self.video_id}]")
            self.console_logger.info(f"{prefix} {rich_msg}")

    def warning(self, msg: str) -> None:
        """Handle warning messages - capture them for reporting."""
        if self.level <= logging.WARNING:
            rich_msg = ansi_to_rich(msg)
            prefix = escape(f"[YT-DLP] [{self.video_id}]")
            full_msg = f"{prefix} {rich_msg}"
            self.console_logger.warning(full_msg)
            self.captured_warnings.append(full_msg)

    def error(self, msg: str) -> None:
        """Handle error messages - capture them for reporting."""
        if self.level <= logging.WARNING:
            rich_msg = ansi_to_rich(msg)
            prefix = escape(f"[YT-DLP] [{self.video_id}]")
            full_msg = f"{prefix} {rich_msg}"
            self.console_logger.error(full_msg)
            self.captured_errors.append(full_msg)

    def get_warnings(self) -> list[str]:
        """Get all captured warnings."""
        return self.captured_warnings.copy()

    def get_errors(self) -> list[str]:
        """Get all captured errors."""
        return self.captured_errors.copy()

    def has_warnings_or_errors(self) -> bool:
        """Check if any warnings or errors were captured."""
        return bool(self.captured_warnings or self.captured_errors)
