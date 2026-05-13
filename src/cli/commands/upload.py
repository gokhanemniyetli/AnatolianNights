"""
upload commands — upload-youtube
"""

import click
from rich.console import Console

from src.services.pipeline_service import PipelineService
from src.storage.database import get_session
from src.storage.models import Song, SongStatus

console = Console()


@click.command("upload-youtube")
@click.argument("song_id")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without actually uploading")
def upload_youtube(song_id: str, dry_run: bool):
    """Upload a VIDEO_READY song to YouTube (long + short)."""
    with get_session() as session:
        song: Song | None = session.get(Song, song_id)
        if not song:
            console.print(f"[red]Song not found: {song_id}[/]")
            return
        if song.status != SongStatus.VIDEO_READY:
            console.print(f"[yellow]Song status is {song.status}, expected VIDEO_READY.[/]")
            return

    console.print(f"[cyan]Uploading song {song_id} to YouTube...[/]")
    pipeline = PipelineService(dry_run=dry_run)
    pipeline.run_song(song_id)
    console.print(f"[green]✓ Upload complete for {song_id}[/]")
