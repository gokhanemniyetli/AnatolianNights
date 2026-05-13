"""
render commands — render-video, render-short
"""

import click
from rich.console import Console

from src.services.pipeline_service import PipelineService
from src.storage.database import get_session
from src.storage.models import Song, SongStatus

console = Console()


@click.command("render-video")
@click.argument("song_id")
@click.option("--dry-run", is_flag=True, default=False)
def render_video(song_id: str, dry_run: bool):
    """Render the long video and Short for a song that has audio imported."""
    with get_session() as session:
        song: Song | None = session.get(Song, song_id)
        if not song:
            console.print(f"[red]Song not found: {song_id}[/]")
            return
        if song.status not in (SongStatus.AUDIO_IMPORTED, SongStatus.IMAGE_READY):
            console.print(f"[yellow]Song is in status {song.status}. Must be AUDIO_IMPORTED or IMAGE_READY.[/]")
            return

    console.print(f"[cyan]Rendering video for song {song_id}...[/]")
    pipeline = PipelineService(dry_run=dry_run)
    pipeline.run_song(song_id)
    console.print(f"[green]✓ Render complete for {song_id}[/]")
