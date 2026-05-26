"""
CLI entry point — all commands registered here.
Usage: python -m cli <command>
"""

import logging

import click
from rich.logging import RichHandler

from src.cli.commands.cycle import dry_run_cycle, run_concept_set, run_cycle, run_scheduler
from src.cli.commands.generate import generate_city, generate_concept, generate_next, resume_song
from src.cli.commands.render import render_video
from src.cli.commands.review import import_audio, review_song
from src.cli.commands.status import list_songs, song_stats
from src.cli.commands.upload import publish_youtube_id, sync_youtube_ui, upload_youtube, upload_youtube_web


@click.group()
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging")
def cli(debug: bool):
    """Anadolu Türküleri Ezgileri — automated folk music pipeline."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )


@cli.command("db-init")
def db_init():
    """Initialize the database and seed all 81 cities."""
    from rich.console import Console
    from src.storage.database import get_session, init_db
    from src.services.city_service import CityService
    from src.services.concept_playlist_service import ConceptPlaylistService

    console = Console()
    init_db()
    console.print("[green]✓ Database initialized[/]")

    with get_session() as session:
        city_svc = CityService(session)
        inserted = city_svc.seed_cities()
    console.print(f"[green]✓ Seeded {inserted} cities[/]")

    with get_session() as session:
        concept_svc = ConceptPlaylistService(session)
        inserted = concept_svc.seed_concepts()
    console.print(f"[green]✓ Seeded {inserted} concept playlists[/]")


# Register all commands
cli.add_command(generate_city)
cli.add_command(generate_concept)
cli.add_command(generate_next)
cli.add_command(resume_song)
cli.add_command(review_song)
cli.add_command(import_audio)
cli.add_command(render_video)
cli.add_command(upload_youtube)
cli.add_command(upload_youtube_web)
cli.add_command(publish_youtube_id)
cli.add_command(sync_youtube_ui)
cli.add_command(run_cycle)
cli.add_command(run_concept_set)
cli.add_command(run_scheduler)
cli.add_command(dry_run_cycle)
cli.add_command(list_songs)
cli.add_command(song_stats)

if __name__ == "__main__":
    cli()
