"""
generate commands — generate-city, generate-next, resume-song
"""

import click
from rich.console import Console
from rich.table import Table

from src.scheduler.orchestrator import Orchestrator

console = Console()


@click.command("generate-city")
@click.argument("city_slug")
@click.option("--dry-run", is_flag=True, default=False, help="Skip publishing")
def generate_city(city_slug: str, dry_run: bool):
    """Generate a new song for the given city slug."""
    console.print(f"[bold cyan]Generating song for city: {city_slug}[/]")
    orch = Orchestrator(dry_run=dry_run)
    song_id = orch.run_one(city_slug=city_slug)
    if song_id:
        console.print(f"[green]✓ Song created: {song_id}[/]")
    else:
        console.print("[red]✗ Generation failed. Check logs.[/]")


@click.command("generate-next")
@click.option("--dry-run", is_flag=True, default=False)
def generate_next(dry_run: bool):
    """Generate a song for the next concept playlist."""
    console.print("[bold cyan]Generating song for next concept...[/]")
    orch = Orchestrator(dry_run=dry_run)
    song_id = orch.run_one()
    if song_id:
        console.print(f"[green]✓ Song created: {song_id}[/]")
    else:
        console.print("[red]✗ Generation failed. Check logs.[/]")


@click.command("generate-concept")
@click.argument("concept_slug")
@click.option("--dry-run", is_flag=True, default=False, help="Skip publishing")
def generate_concept(concept_slug: str, dry_run: bool):
    """Generate a new song for the given concept playlist slug."""
    console.print(f"[bold cyan]Generating song for concept: {concept_slug}[/]")
    orch = Orchestrator(dry_run=dry_run)
    song_id = orch.run_one(concept_slug=concept_slug)
    if song_id:
        console.print(f"[green]✓ Song created: {song_id}[/]")
    else:
        console.print("[red]✗ Generation failed. Check logs.[/]")


@click.command("resume-song")
@click.argument("song_id")
@click.option("--dry-run", is_flag=True, default=False, help="Skip publishing step")
def resume_song(song_id: str, dry_run: bool):
    """Resume a stalled song from its current status through the pipeline.

    The pipeline will advance the song through all remaining stages until it
    reaches a blocking point (awaiting manual audio import or already uploaded).

    \b
    Resumable statuses:
      PENDING, CONCEPT_READY, LYRICS_READY, QUALITY_APPROVED,
      QUALITY_REJECTED, SUNO_READY, AUDIO_IMPORTED, IMAGE_READY, VIDEO_READY
    """
    from src.services.pipeline_service import PipelineService
    from src.storage.database import get_session
    from src.storage.models import Song, SongStatus

    TERMINAL_STATUSES = {SongStatus.UPLOADED, SongStatus.PERMANENTLY_REJECTED}
    BLOCKING_STATUSES = {SongStatus.SUNO_READY}

    with get_session() as session:
        song: Song | None = session.get(Song, song_id)
        if not song:
            console.print(f"[red]Song not found: {song_id}[/]")
            return
        current_status = song.status
        if isinstance(current_status, str):
            current_status = SongStatus(current_status)
        city_name = song.city.name if song.city else "?"

    console.print(
        f"[cyan]Resuming song [bold]{song_id}[/] ({city_name}) "
        f"from status [yellow]{current_status.value}[/]...[/]"
    )

    if current_status in TERMINAL_STATUSES:
        console.print(
            f"[yellow]Song is in terminal status {current_status.value} — nothing to resume.[/]"
        )
        return

    from src.config.settings import settings
    if current_status in BLOCKING_STATUSES and settings.suno.client.lower() != "browser":
        console.print(
            "[yellow]Song is waiting for manual audio import (SUNO_READY).[/]\n"
            "Run: [bold]python -m cli import-audio --song-id "
            f"{song_id} --file <mp3_path>[/]"
        )
        return

    pipeline = PipelineService(dry_run=dry_run)
    try:
        pipeline.run_song(song_id)
        _resume_twin_if_needed(song_id, pipeline)
        console.print(f"[green]✓ Song {song_id} advanced successfully.[/]")
    except Exception as exc:
        _resume_twin_if_needed(song_id, pipeline)
        console.print(f"[red]✗ Pipeline error: {exc}[/]")
        raise SystemExit(1) from exc


def _resume_twin_if_needed(song_id: str, pipeline) -> None:
    from src.storage.database import get_session
    from src.storage.models import Song

    with get_session() as session:
        refreshed: Song | None = session.get(Song, song_id)
        if not refreshed or refreshed.language != "tr" or not refreshed.twin_song_id:
            return
        twin_song_id = refreshed.twin_song_id
        twin: Song | None = session.get(Song, twin_song_id)
        if not twin or twin.status in {SongStatus.UPLOADED, SongStatus.PERMANENTLY_REJECTED}:
            return

    console.print(f"[cyan]Resuming English twin song [bold]{twin_song_id}[/]...[/]")
    pipeline.run_song(str(twin_song_id))
