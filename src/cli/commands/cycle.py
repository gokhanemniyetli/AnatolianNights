"""
cycle commands — run-cycle, dry-run
"""

import click
from rich.console import Console

from src.scheduler.cycle_runner import CycleRunner

console = Console()


@click.command("run-cycle")
@click.option("--city", default=None, help="Limit cycle to a specific city slug")
@click.option("--k", default=1, show_default=True, help="Number of songs per cycle")
def run_cycle(city: str | None, k: int):
    """Run one full pipeline cycle (generate → render → upload)."""
    console.print(f"[bold cyan]Running cycle (k={k})...[/]")
    runner = CycleRunner(k=k, dry_run=False)
    song_ids = runner.run_cycle(city_slug=city)
    console.print(f"[green]Cycle complete. Songs: {song_ids}[/]")


@click.command("dry-run")
@click.option("--city", default=None)
@click.option("--k", default=1)
def dry_run_cycle(city: str | None, k: int):
    """Run a dry-run cycle (no upload, no cost)."""
    console.print("[bold yellow][DRY-RUN] Running cycle...[/]")
    runner = CycleRunner(k=k, dry_run=True)
    song_ids = runner.run_cycle(city_slug=city)
    console.print(f"[yellow][DRY-RUN] Done. Songs: {song_ids}[/]")
