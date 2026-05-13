"""
review commands — review-song, import-audio
"""

import shutil
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.services.pipeline_service import PipelineService
from src.storage.database import get_session
from src.storage.file_storage import file_storage
from src.storage.models import Song

console = Console()


@click.command("review-song")
@click.argument("song_id")
def review_song(song_id: str):
    """Display full details of a song (concept, lyrics, status, quality score)."""
    with get_session() as session:
        song: Song | None = session.get(Song, song_id)
        if not song:
            console.print(f"[red]Song not found: {song_id}[/]")
            return

        from src.storage.models import City
        city = session.get(City, song.city_id)
        city_name = city.name if city else "?"

        console.print(Panel(
            f"[bold]Song ID:[/] {song.id}\n"
            f"[bold]City:[/] {city_name}\n"
            f"[bold]Status:[/] {song.status}\n"
            f"[bold]Title:[/] {song.title or '—'}\n"
            f"[bold]Quality score:[/] {song.quality_score or '—'}\n"
            f"[bold]Lyric attempts:[/] {song.lyric_attempt or 0}\n"
            f"[bold]Rejected reason:[/] {song.rejected_reason or '—'}",
            title="Song Details",
        ))

        if song.lyrics:
            console.print(Panel(song.lyrics, title="Lyrics"))

        concept = song.get_concept()
        if concept:
            console.print(Panel(str(concept), title="Concept"))


@click.command("import-audio")
@click.option("--song-id", required=True, help="Song ID to import audio for")
@click.option("--file", "audio_file", required=True, type=click.Path(exists=True),
              help="Path to the downloaded MP3 file")
def import_audio(song_id: str, audio_file: str):
    """Import a Suno-generated audio file into the pipeline."""
    with get_session() as session:
        song: Song | None = session.get(Song, song_id)
        if not song:
            console.print(f"[red]Song not found: {song_id}[/]")
            return

        from src.storage.models import City, SongStatus
        city = session.get(City, song.city_id)
        city_slug = city.slug if city else "unknown"

        source = Path(audio_file)
        dest = file_storage.import_audio(city_slug, song_id, source)
        song.audio_path = str(file_storage.rel(dest))
        song.status = SongStatus.AUDIO_IMPORTED
        console.print(f"[green]✓ Audio imported to {dest}[/]")

    # Continue the pipeline from AUDIO_IMPORTED
    pipeline = PipelineService()
    pipeline.run_song(song_id)
    console.print(f"[green]✓ Pipeline resumed for song {song_id}[/]")
