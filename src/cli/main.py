"""
CLI entry point — all commands registered here.
Usage: python -m cli <command>
"""

import logging

import click
from rich.logging import RichHandler

from src.cli.commands.cycle import dry_run_cycle, run_cycle
from src.cli.commands.generate import generate_city, generate_next
from src.cli.commands.render import render_video
from src.cli.commands.review import import_audio, review_song
from src.cli.commands.upload import upload_youtube


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

    console = Console()
    init_db()
    console.print("[green]✓ Database initialized[/]")

    with get_session() as session:
        city_svc = CityService(session)
        inserted = city_svc.seed_cities()
    console.print(f"[green]✓ Seeded {inserted} cities[/]")


# Register all commands
cli.add_command(generate_city)
cli.add_command(generate_next)
cli.add_command(review_song)
cli.add_command(import_audio)
cli.add_command(render_video)
cli.add_command(upload_youtube)
cli.add_command(run_cycle)
cli.add_command(dry_run_cycle)

if __name__ == "__main__":
    cli()
