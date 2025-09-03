"""CLI interface for video-kb-simple."""

import logging
import signal
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from video_kb_simple import __version__
from video_kb_simple.downloader import PlaylistResult, SimpleDownloader

# Constants
MAX_FILES_TO_SHOW_INDIVIDUALLY = 10
MAX_WARNINGS_ERRORS_TO_SHOW = 5
MAX_FILES_TO_SHOW_BEFORE_SUMMARY = 3
DEFAULT_LANGUAGE = "en"

app = typer.Typer(
    name="video-kb",
    help="Extract transcribed text from videos using yt-dlp",
    rich_markup_mode="rich",
)
console = Console()


def create_signal_handler(console: Console) -> Callable[[], bool]:
    """Create a signal handler that uses the provided console for output."""
    shutdown_requested = False
    signal_count = 0

    def signal_handler(_signum: int, _frame) -> None:  # type: ignore[no-untyped-def]
        nonlocal shutdown_requested, signal_count
        signal_count += 1

        if signal_count == 1:
            # First signal - request graceful shutdown
            shutdown_requested = True
            console.print(
                "\n[yellow]Shutdown requested. Finishing current download and exiting gracefully...[/yellow]"
            )
            console.print("[dim]Press Ctrl+C again to force immediate exit.[/dim]")
        else:
            # Second signal - force immediate exit
            console.print("\n[red]Force exiting immediately...[/red]")
            exit(1)

    def is_shutdown_requested() -> bool:
        return shutdown_requested

    def setup_signals() -> None:
        """Set up signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    # Set up the signals
    setup_signals()

    return is_shutdown_requested


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        rprint(f"video-kb-simple version: {__version__}")
        raise typer.Exit()


@app.command()
def download(
    url: Annotated[
        str, typer.Argument(help="Video, Playlist or Channel URL to download transcripts from")
    ],
    output_dir: Annotated[
        Path, typer.Option("--output", "-o", help="Output directory for transcripts")
    ] = Path("./transcripts"),
    force_download: Annotated[
        bool,
        typer.Option("--force", "-f", help="Re-download transcripts even if they already exist"),
    ] = False,
    browser_cookies: Annotated[
        str | None,
        typer.Option(
            "--cookies-from", help="Extract cookies from browser (firefox, chrome, safari, etc)"
        ),
    ] = None,
    languages: Annotated[
        list[str] | None,
        typer.Option(
            "--lang",
            "-l",
            help="Subtitle languages to download (e.g. 'en', 'es', 'en,pl'). Can be specified multiple times or comma-separated.",
        ),
    ] = None,
    max_videos: Annotated[
        int | None,
        typer.Option(
            "--max-videos", help="Maximum number of videos to process from playlist/channel"
        ),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Enable yt-dlp debug output")] = False,
) -> None:
    """Download transcripts from a single video, playlist, or channel."""
    output_dir.mkdir(exist_ok=True)

    # Process language options: handle comma-separated values and remove duplicates
    if languages:
        selected_languages = list(
            dict.fromkeys(lang.strip() for language in languages for lang in language.split(","))
        )
    else:
        selected_languages = [DEFAULT_LANGUAGE]

    # Set log level based on flags
    if debug:
        log_level = logging.DEBUG
    elif verbose:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    if verbose:
        console.print(f"[green]Downloading transcripts from:[/green] {url}")
        console.print(f"[green]Output directory:[/green] {output_dir}")
        console.print(
            "[yellow]Note: Using conservative rate limiting to avoid bot detection[/yellow]"
        )
        if browser_cookies:
            console.print(f"[green]Using cookies from:[/green] {browser_cookies}")
        console.print(f"[green]Languages:[/green] {', '.join(selected_languages)}")

    try:
        # Create signal handler for graceful shutdown
        shutdown_check = create_signal_handler(console)

        downloader = SimpleDownloader(
            output_dir=output_dir,
            log_level=log_level,
            force_download=force_download,
            browser_for_cookies=browser_cookies,
            shutdown_check=shutdown_check,
        )

        result = downloader.download_transcripts(
            url=url,
            max_videos=max_videos,
            subtitle_languages=selected_languages,
        )

        # Display results
        _display_batch_results(result, console)

    except Exception as error:
        error_display_panel = Panel(
            f"❌ Error: {error!s}",
            title="Playlist Download Failed",
            style="red",
        )
        console.print(error_display_panel)
        raise typer.Exit(1) from error


def _display_items(items: list[str], label: str, console: Console, color: str = "yellow") -> None:
    """Display a list of items (warnings/errors) with truncation if needed.

    Args:
        items: List of strings to display
        label: Label for the items (e.g., "Warnings", "Errors")
        console: Rich console for output
        color: Color for the label ("yellow" for warnings, "red" for errors)
    """
    if not items:
        return

    console.print(f"\n[{color}]{label} ({len(items)}):[/{color}]")
    icon = "⚠️" if color == "yellow" else "•"
    for item in items[:MAX_WARNINGS_ERRORS_TO_SHOW]:
        console.print(f"  {icon}  {item}")
    if len(items) > MAX_WARNINGS_ERRORS_TO_SHOW:
        console.print(f"  ... and {len(items) - MAX_WARNINGS_ERRORS_TO_SHOW} more {label.lower()}")


def _display_batch_results(result: PlaylistResult, console: Console) -> None:
    """Display playlist download results in a formatted table."""
    # Create summary table
    table = Table(title="Download Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green")

    if result.playlist_details:
        table.add_row("Title", result.playlist_details.title or "Unknown")
        table.add_row(
            "Type",
            result.playlist_details.playlist_type.value
            if result.playlist_details.playlist_type
            else "Unknown",
        )

    table.add_row("Total videos requested", str(result.total_requested))

    table.add_row(":white_check_mark: Success", f"[green]{result.success_downloads}[/green]")
    table.add_row(
        ":yellow_circle: Partial success", f"[yellow]{result.partial_success_downloads}[/yellow]"
    )
    table.add_row(":cross_mark: Failed", f"[red]{result.fail_downloads}[/red]")

    table.add_row("Processing time", f"{result.processing_time_seconds:.1f}s")

    # Calculate language-specific download counts and add to table
    total_successful = result.success_downloads + result.partial_success_downloads
    if total_successful > 0:
        table.add_row("Total successful downloads", f"[green]{total_successful}[/green]")

        # Count downloads by language
        downloads_by_lang: dict[str, int] = {}
        for video_result in result.video_results:
            if video_result.is_full_success or video_result.is_partial_success:
                for downloaded_file in video_result.downloaded_files:
                    if downloaded_file.language:
                        downloads_by_lang[downloaded_file.language] = (
                            downloads_by_lang.get(downloaded_file.language, 0) + 1
                        )

        if downloads_by_lang:
            # Add language breakdown rows to the table
            for lang, count in sorted(downloads_by_lang.items()):
                table.add_row(f"  └─ {lang} downloads", f"[blue]{count}[/blue]")

    console.print(table)

    # Show downloaded files
    downloaded_files = []
    for video_result in result.video_results:
        if video_result.is_full_success:
            for downloaded_file in video_result.downloaded_files:
                downloaded_files.append(downloaded_file.path)

    if downloaded_files:
        console.print(
            f"\n[green]Downloaded {len(downloaded_files)} files to:[/green] {downloaded_files[0].parent}"
        )

        if len(downloaded_files) <= MAX_FILES_TO_SHOW_INDIVIDUALLY:
            # Show all files if threshold or fewer
            for file_path in downloaded_files:
                console.print(f"  📄 {file_path.name}")
        else:
            # Show first few and summarize
            for file_path in downloaded_files[:MAX_FILES_TO_SHOW_BEFORE_SUMMARY]:
                console.print(f"  📄 {file_path.name}")
            console.print(
                f"  ... and {len(downloaded_files) - MAX_FILES_TO_SHOW_BEFORE_SUMMARY} more files"
            )

    # Show warnings and errors
    all_warnings = []
    for video_result in result.video_results:
        if video_result.warnings:
            all_warnings.extend(video_result.warnings)

    _display_items(all_warnings, "Warnings", console, "yellow")
    _display_items(result.errors, "Errors", console, "red")

    # Show final success panel
    total_successful = result.success_downloads + result.partial_success_downloads
    if total_successful > 0:
        success_display_panel = Panel(
            f"✅ Successfully downloaded transcripts from {total_successful} videos\n"
            f"📁 Files saved to: [bold blue]{downloaded_files[0].parent if downloaded_files else 'N/A'}[/bold blue]",
            title="Download Complete",
            style="green",
        )
        console.print(success_display_panel)


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version", callback=version_callback, is_eager=True, help="Show version and exit"
        ),
    ] = None,
) -> None:
    """CLI application for extracting video transcripts using yt-dlp.

    This is the main entry point for the video-kb CLI tool that provides
    commands for downloading transcripts from YouTube videos, playlists, and channels.
    """
    pass
