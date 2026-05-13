"""
generate commands — generate-city, generate-next
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
    """Generate a song for the next city in round-robin order."""
    console.print("[bold cyan]Generating song for next city...[/]")
    orch = Orchestrator(dry_run=dry_run)
    song_id = orch.run_one()
    if song_id:
        console.print(f"[green]✓ Song created: {song_id}[/]")
    else:
        console.print("[red]✗ Generation failed. Check logs.[/]")
