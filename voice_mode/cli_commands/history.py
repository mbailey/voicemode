"""CLI commands for conversation history search and playback."""

import shutil
import subprocess
from datetime import datetime, date
from pathlib import Path

import click

from voice_mode.history import HistoryDatabase, HistoryLoader, HistorySearcher


@click.group()
def history():
    """Manage and search conversation history."""
    pass


@history.command()
@click.option(
    "--since",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Only load exchanges after this date",
)
@click.option(
    "--days",
    type=int,
    help="Only load exchanges from the last N days",
)
@click.option(
    "--all",
    "load_all",
    is_flag=True,
    help="Load all exchanges (ignore last sync timestamp)",
)
def load(since, days, load_all):
    """Load conversation exchanges from JSONL into SQLite database.

    By default, only loads exchanges since the last sync. Use --all to reload everything.

    Examples:
        voicemode history load                    # Load new exchanges since last sync
        voicemode history load --all              # Reload all exchanges
        voicemode history load --since 2025-12-01 # Load from specific date
        voicemode history load --days 7           # Load last 7 days
    """
    db = HistoryDatabase()
    loader = HistoryLoader(db)

    click.echo("Loading conversation history into SQLite...")

    # Determine what to load
    if days:
        since_datetime = None
        stats = loader.load_recent(days=days)
        click.echo(f"Loaded exchanges from last {days} days")
    elif since:
        # Clear last sync to force reload from this date
        stats = loader.load_all(since=since)
        click.echo(f"Loaded exchanges since {since.date()}")
    elif load_all:
        # Clear last sync to reload everything
        db.set_sync_metadata("last_sync_timestamp", "")
        stats = loader.load_all()
        click.echo("Loaded all exchanges")
    else:
        # Incremental load
        stats = loader.load_all()
        click.echo("Loaded new exchanges since last sync")

    # Display stats
    total_count = db.get_exchange_count()
    click.echo(
        f"\nResults: {stats['inserted']} inserted, {stats['skipped']} skipped, "
        f"{stats['errors']} errors"
    )
    click.echo(f"Total exchanges in database: {total_count}")

    db.close()


@history.command()
@click.argument("query")
@click.option(
    "--type",
    "exchange_type",
    type=click.Choice(["stt", "tts"]),
    help="Filter by exchange type (stt=user speech, tts=agent speech)",
)
@click.option(
    "--date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Filter by specific date",
)
@click.option(
    "--limit",
    type=int,
    default=20,
    help="Maximum number of results (default: 20)",
)
@click.option(
    "--play",
    is_flag=True,
    help="Play audio from first result automatically",
)
def search(query, exchange_type, date, limit, play):
    """Search conversation history using full-text search.

    Searches through all conversation text. Results are ordered by timestamp (newest first).

    Examples:
        voicemode history search "minion indirectly"
        voicemode history search --type tts "hello"   # Only agent speech
        voicemode history search --type stt "hello"   # Only user speech
        voicemode history search --date 2025-12-27 "keyword"
        voicemode history search --play "memorable quote"  # Search and play first result
    """
    db = HistoryDatabase()
    searcher = HistorySearcher(db)

    # Convert datetime to date if provided
    target_date = date.date() if date else None

    # Perform search
    results = searcher.search(
        query=query,
        exchange_type=exchange_type,
        target_date=target_date,
        limit=limit,
    )

    if not results:
        click.echo("No results found.")
        db.close()
        return

    # Display results
    click.echo(f"Found {len(results)} result(s):\n")

    for i, result in enumerate(results, 1):
        # Format timestamp
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M:%S")

        # Type indicator
        type_label = "USER" if result.type == "stt" else "AGENT"

        # Show result
        click.echo(f"{i}. [{ts}] {type_label}: {result.text}")
        click.echo(f"   ID: {result.id}")

        # Show audio file status
        audio_path = result.get_audio_path()
        if audio_path:
            click.echo(f"   Audio: {audio_path}")
        else:
            click.echo(f"   Audio: {result.audio_file} (not found)")

        click.echo()

    db.close()

    # Auto-play first result if requested
    if play and results:
        first_result = results[0]
        audio_path = first_result.get_audio_path()
        if audio_path:
            click.echo(f"Playing: {first_result.text}\n")
            _play_audio(audio_path)
        else:
            click.echo("Audio file not found, cannot play.")


@history.command()
@click.argument("exchange_id")
def play(exchange_id):
    """Play audio from a specific exchange by ID.

    Use the exchange ID from search results.

    Examples:
        voicemode history play ex_abc123def456
    """
    db = HistoryDatabase()
    searcher = HistorySearcher(db)

    # Get exchange by ID
    result = searcher.get_by_id(exchange_id)

    if not result:
        click.echo(f"Exchange not found: {exchange_id}")
        db.close()
        return

    # Get audio path
    audio_path = result.get_audio_path()

    if not audio_path:
        click.echo(f"Audio file not found: {result.audio_file}")
        db.close()
        return

    # Display what we're playing
    ts = result.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    type_label = "USER" if result.type == "stt" else "AGENT"
    click.echo(f"[{ts}] {type_label}: {result.text}\n")

    # Play audio
    _play_audio(audio_path)

    db.close()


def _play_audio(audio_path: Path):
    """Play audio file using available player.

    Args:
        audio_path: Path to audio file
    """
    # Try mpv first (preferred for CLI usage)
    if shutil.which("mpv"):
        subprocess.run(["mpv", "--no-video", str(audio_path)])
        return

    # Fallback to afplay on macOS
    if shutil.which("afplay"):
        subprocess.run(["afplay", str(audio_path)])
        return

    # Fallback to ffplay (from ffmpeg)
    if shutil.which("ffplay"):
        subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-hide_banner", str(audio_path)]
        )
        return

    click.echo("No audio player found. Install mpv, or use afplay/ffplay.")
