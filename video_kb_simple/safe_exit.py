"""Safe exit mechanisms for video-kb-simple CLI tool."""

import atexit
import contextlib
import os
import signal
import tempfile
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

from rich.console import Console


class SafeFileManager:
    """Context manager for atomic file operations with cleanup on forced exit."""

    def __init__(self, target_path: Path, console: Console | None = None):
        """Initialize safe file manager.

        Args:
            target_path: Final destination path for the file
            console: Optional Rich console for status messages
        """
        self.target_path = target_path
        self.temp_path: Path | None = None
        self.console = console or Console()
        self._cleanup_registered = False

    def __enter__(self) -> Path:
        """Enter context manager and return temporary file path."""
        # Create temporary file in same directory as target for atomic move
        temp_fd, temp_name = tempfile.mkstemp(
            suffix=".tmp", dir=self.target_path.parent, prefix=f"{self.target_path.stem}_"
        )
        os.close(temp_fd)  # Close the file descriptor immediately
        self.temp_path = Path(temp_name)

        # Register cleanup on exit
        if not self._cleanup_registered:
            atexit.register(self._cleanup_temp_file)
            self._cleanup_registered = True

        return self.temp_path

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any
    ) -> None:
        """Exit context manager and handle file finalization."""
        if self.temp_path and self.temp_path.exists():
            if exc_type is None:
                # Success - atomically move temp file to target
                try:
                    self.temp_path.rename(self.target_path)
                    if self.console:
                        self.console.print(f"[green]✓[/green] Safely wrote {self.target_path}")
                except Exception as e:
                    if self.console:
                        self.console.print(f"[red]Failed to finalize {self.target_path}: {e}[/red]")
                    self._cleanup_temp_file()
                    raise
            else:
                # Exception occurred - cleanup temp file
                self._cleanup_temp_file()

    def _cleanup_temp_file(self) -> None:
        """Clean up temporary file if it exists."""
        if self.temp_path and self.temp_path.exists():
            try:
                self.temp_path.unlink()
                if self.console:
                    self.console.print(
                        f"[yellow]Cleaned up temp file: {self.temp_path.name}[/yellow]"
                    )
            except Exception:  # nosec B110
                pass  # Ignore cleanup errors during shutdown


class GracefulExitHandler:
    """Handles graceful shutdown on SIGINT/SIGTERM signals."""

    def __init__(self, console: Console | None = None):
        """Initialize graceful exit handler.

        Args:
            console: Optional Rich console for status messages
        """
        self.console = console or Console()
        self.shutdown_requested = False
        self.cleanup_functions: list[Callable[[], None]] = []
        self._original_handlers: dict[int, Any] = {}

    def register_cleanup(self, func: Callable[[], None]) -> None:
        """Register a cleanup function to be called on exit.

        Args:
            func: Cleanup function to call
        """
        self.cleanup_functions.append(func)

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        for sig in [signal.SIGINT, signal.SIGTERM]:
            self._original_handlers[sig] = signal.signal(sig, self._signal_handler)

    def restore_signal_handlers(self) -> None:
        """Restore original signal handlers."""
        for sig, handler in self._original_handlers.items():
            signal.signal(sig, handler)
        self._original_handlers.clear()

    def _signal_handler(self, signum: int, _frame: Any) -> None:
        """Handle shutdown signals."""
        self.shutdown_requested = True
        signal_name = signal.Signals(signum).name

        self.console.print(
            f"\n[yellow]Received {signal_name}, shutting down gracefully...[/yellow]"
        )

        # Run cleanup functions
        for cleanup_func in self.cleanup_functions:
            try:
                cleanup_func()
            except Exception as e:
                self.console.print(f"[red]Cleanup error: {e}[/red]")

        self.console.print("[green]Cleanup complete. Exiting.[/green]")
        exit(0)

    @contextlib.contextmanager
    def protected_operation(self) -> Generator[None, None, None]:
        """Context manager that checks for shutdown requests during operation."""
        try:
            yield
        finally:
            if self.shutdown_requested:
                self.console.print("[yellow]Operation interrupted by shutdown request[/yellow]")
                raise KeyboardInterrupt("Shutdown requested")


@contextlib.contextmanager
def atomic_file_write(
    target_path: Path, console: Console | None = None
) -> Generator[Path, None, None]:
    """Context manager for atomic file writes.

    Args:
        target_path: Final destination for the file
        console: Optional Rich console for messages

    Yields:
        Path to temporary file to write to

    Example:
        with atomic_file_write(Path("output.txt")) as temp_path:
            temp_path.write_text("content")
        # File is atomically moved to output.txt
    """
    with SafeFileManager(target_path, console) as temp_path:
        yield temp_path


def setup_safe_exit(console: Console | None = None) -> GracefulExitHandler:
    """Setup safe exit handling for the application.

    Args:
        console: Optional Rich console for messages

    Returns:
        GracefulExitHandler instance for additional cleanup registration
    """
    handler = GracefulExitHandler(console)
    handler.setup_signal_handlers()

    # Register handler restoration on normal exit
    atexit.register(handler.restore_signal_handlers)

    return handler
