"""CLI interface for video-kb-simple."""

from pathlib import Path
from typing import Annotated

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from video_kb_simple import __version__
from video_kb_simple.downloader import BatchResult, VideoDownloader

app = typer.Typer(
    name="video-kb",
    help="Extract transcribed text from videos using yt-dlp",
    rich_markup_mode="rich",
)
console = Console()


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
    min_sleep: Annotated[
        int, typer.Option("--min-sleep", help="Minimum seconds to sleep between downloads")
    ] = 10,
    max_sleep: Annotated[
        int, typer.Option("--max-sleep", help="Maximum seconds to sleep between downloads")
    ] = 30,
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
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable verbose output")] = False,
) -> None:
    """Download transcripts from a single video, playlist, or channel."""
    output_dir.mkdir(exist_ok=True)

    # Handle comma-separated language strings and multiple flags
    processed_languages = []
    if languages:
        for lang in languages:
            # Split comma-separated languages and strip whitespace
            processed_languages.extend([s.strip() for s in lang.split(",")])
        # Remove duplicates while preserving order
        processed_languages = list(dict.fromkeys(processed_languages))
    else:
        processed_languages = ["en"]

    if verbose:
        console.print(f"[green]Downloading transcripts from:[/green] {url}")
        console.print(f"[green]Output directory:[/green] {output_dir}")
        console.print(f"[green]Sleep interval:[/green] {min_sleep}-{max_sleep}s")
        console.print(
            "[yellow]Note: Using conservative rate limiting to avoid bot detection[/yellow]"
        )
        if browser_cookies:
            console.print(f"[green]Using cookies from:[/green] {browser_cookies}")
        console.print(f"[green]Languages:[/green] {', '.join(processed_languages)}")

    try:
        downloader = VideoDownloader(
            output_dir=output_dir,
            verbose=verbose,
            force_download=force_download,
            min_sleep_interval=min_sleep,
            max_sleep_interval=max_sleep,
            browser_for_cookies=browser_cookies,
        )

        result = downloader.download_playlist_transcripts(
            playlist_url=url,
            subtitles_langs=processed_languages,
        )

        # Display results
        _display_batch_results(result, console)

    except Exception as e:
        error_panel = Panel(
            f"❌ Error: {e!s}",
            title="Playlist Download Failed",
            style="red",
        )
        console.print(error_panel)
        raise typer.Exit(1) from None


def _display_batch_results(result: BatchResult, console: Console) -> None:
    """Display batch download results in a formatted table."""
    # Create summary table
    table = Table(title="Playlist Download Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green")

    table.add_row("Playlist", result.playlist_info.title)
    table.add_row("Type", result.playlist_info.playlist_type)
    table.add_row("Total videos found", str(result.total_videos))
    table.add_row("Successful downloads", f"✅ {result.successful_downloads}")
    table.add_row("Failed downloads", f"❌ {result.failed_downloads}")
    table.add_row("Skipped (already downloaded)", f"⏭️ {result.skipped_videos}")
    table.add_row("Processing time", f"{result.processing_time:.1f}s")

    console.print(table)

    # Show downloaded files
    if result.downloaded_files:
        console.print(
            f"\n[green]Downloaded {len(result.downloaded_files)} transcripts to:[/green] {result.downloaded_files[0].parent}"
        )

        if len(result.downloaded_files) <= 10:
            # Show all files if 10 or fewer
            for file_path in result.downloaded_files:
                console.print(f"  📄 {file_path.name}")
        else:
            # Show first few and summarize
            for file_path in result.downloaded_files[:3]:
                console.print(f"  📄 {file_path.name}")
            console.print(f"  ... and {len(result.downloaded_files) - 3} more files")

    # Show errors if any
    if result.errors:
        console.print(f"\n[red]Errors ({len(result.errors)}):[/red]")
        for error in result.errors[:5]:  # Show first 5 errors
            console.print(f"  • {error}")
        if len(result.errors) > 5:
            console.print(f"  ... and {len(result.errors) - 5} more errors")

    # Show final success panel
    if result.successful_downloads > 0:
        success_panel = Panel(
            f"✅ Successfully downloaded transcripts from {result.successful_downloads} videos\n"
            f"📁 Files saved to: [bold blue]{result.downloaded_files[0].parent if result.downloaded_files else 'N/A'}[/bold blue]",
            title="Playlist Download Complete",
            style="green",
        )
        console.print(success_panel)


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version", callback=version_callback, is_eager=True, help="Show version and exit"
        ),
    ] = None,
) -> None:
    """Video Knowledge Base - Extract transcripts from videos."""
    pass
