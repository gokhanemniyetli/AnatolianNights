"""
cycle commands — run-cycle, dry-run
"""

import time
from datetime import date, datetime, timedelta

import click
from rich.console import Console
from sqlalchemy import func

from src.config.settings import settings
from src.services.pipeline_service import PipelineService
from src.scheduler.cycle_runner import CycleRunner
from src.storage.database import get_session
from src.storage.models import City, ConceptPlaylist, Song, SongStatus

console = Console()


@click.command("run-cycle")
@click.option("--city", default=None, help="Limit cycle to a specific city slug")
@click.option("--concept", default=None, help="Limit cycle to a specific concept playlist slug")
@click.option("--k", default=1, show_default=True, help="Number of songs per cycle")
def run_cycle(city: str | None, concept: str | None, k: int):
    """Run one full pipeline cycle (generate → render → upload)."""
    if city and concept:
        raise click.ClickException("Use either --city or --concept, not both.")
    console.print(f"[bold cyan]Running cycle (k={k})...[/]")
    runner = CycleRunner(k=k, dry_run=False)
    song_ids = runner.run_cycle(city_slug=city, concept_slug=concept)
    console.print(f"[green]Cycle complete. Songs: {song_ids}[/]")


@click.command("dry-run")
@click.option("--city", default=None)
@click.option("--concept", default=None)
@click.option("--k", default=1)
def dry_run_cycle(city: str | None, concept: str | None, k: int):
    """Run a dry-run cycle (no upload, no cost)."""
    if city and concept:
        raise click.ClickException("Use either --city or --concept, not both.")
    console.print("[bold yellow][DRY-RUN] Running cycle...[/]")
    runner = CycleRunner(k=k, dry_run=True)
    song_ids = runner.run_cycle(city_slug=city, concept_slug=concept)
    console.print(f"[yellow][DRY-RUN] Done. Songs: {song_ids}[/]")


@click.command("run-concept-set")
@click.argument("group")
@click.option("--limit", default=None, type=int, help="Maximum concepts from the group to run")
@click.option("--force-new", is_flag=True, default=False, help="Create a new song even if the concept already has one")
def run_concept_set(group: str, limit: int | None, force_new: bool):
    """Run one upload for each concept in a concept group."""
    from src.services.concept_playlist_service import ConceptPlaylistService

    with get_session() as session:
        concepts = ConceptPlaylistService(session).get_by_group(group)
        slugs = [concept.slug for concept in concepts]
    if limit is not None:
        slugs = slugs[:limit]
    if not slugs:
        raise click.ClickException(f"No active concepts found for group: {group}")

    console.print(f"[bold cyan]Running concept set '{group}' ({len(slugs)} concepts)...[/]")
    all_song_ids: list[str] = []
    for index, slug in enumerate(slugs, start=1):
        console.print(f"[cyan]{index}/{len(slugs)} concept: {slug}[/]")
        if not force_new:
            existing_song_id = _latest_song_for_concept(slug, status=SongStatus.UPLOADED.value)
            if existing_song_id:
                console.print(f"[dim]Already uploaded for {slug}: {existing_song_id}; skipping.[/]")
                continue
            resumable_song_id = _next_resumable_song_id(concept_slug=slug)
            if resumable_song_id:
                console.print(f"[cyan]Resuming existing concept song: {resumable_song_id}[/]")
                PipelineService(dry_run=False).run_song(str(resumable_song_id))
                all_song_ids.append(str(resumable_song_id))
                continue
        runner = CycleRunner(k=1, dry_run=False)
        song_ids = runner.run_cycle(concept_slug=slug)
        all_song_ids.extend(song_ids)
    console.print(f"[green]Concept set complete. Songs: {all_song_ids}[/]")


def _uploaded_count_for_day(day: str) -> int:
    with get_session() as session:
        return (
            session.query(func.count(Song.id))
            .filter(Song.status == SongStatus.UPLOADED.value)
            .filter(func.date(func.coalesce(Song.uploaded_at, Song.updated_at)) == day)
            .scalar()
            or 0
        )


def _next_resumable_song_id(
    city_slug: str | None = None,
    concept_slug: str | None = None,
) -> int | None:
    resumable_statuses = [
        SongStatus.PENDING.value,
        SongStatus.CONCEPT_READY.value,
        SongStatus.LYRICS_READY.value,
        SongStatus.QUALITY_APPROVED.value,
        SongStatus.QUALITY_REJECTED.value,
        SongStatus.SUNO_READY.value,
        SongStatus.AUDIO_IMPORTED.value,
        SongStatus.IMAGE_READY.value,
        SongStatus.VIDEO_READY.value,
    ]
    cutoff = datetime.now() - timedelta(hours=24)
    with get_session() as session:
        query = (
            session.query(Song.id)
            .filter(Song.status.in_(resumable_statuses))
            .filter(Song.created_at >= cutoff)
            .order_by(Song.created_at.asc())
        )
        if city_slug:
            query = query.join(City).filter(City.slug == city_slug)
        if concept_slug:
            query = query.join(ConceptPlaylist).filter(ConceptPlaylist.slug == concept_slug)
        return query.limit(1).scalar()


def _latest_song_for_concept(concept_slug: str, status: str | None = None) -> int | None:
    with get_session() as session:
        query = (
            session.query(Song.id)
            .join(ConceptPlaylist, Song.concept_playlist_id == ConceptPlaylist.id)
            .filter(ConceptPlaylist.slug == concept_slug)
            .order_by(Song.created_at.desc())
        )
        if status:
            query = query.filter(Song.status == status)
        return query.limit(1).scalar()


def _is_active_hour(now: datetime, start_hour: int, end_hour: int) -> bool:
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= now.hour < end_hour
    return now.hour >= start_hour or now.hour < end_hour


def _seconds_until_active_window(now: datetime, start_hour: int, end_hour: int) -> float:
    if _is_active_hour(now, start_hour, end_hour):
        return 0

    next_start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    if now >= next_start:
        next_start += timedelta(days=1)
    return (next_start - now).total_seconds()


@click.command("run-scheduler")
@click.option("--city", default=None, help="Limit scheduled runs to a specific city slug")
@click.option("--concept", default=None, help="Limit scheduled runs to a specific concept playlist slug")
@click.option(
    "--interval-minutes",
    default=None,
    type=int,
    help="Minutes between scheduled attempts. Defaults to pipeline.publish_interval_minutes.",
)
@click.option(
    "--max-daily",
    default=None,
    type=int,
    help="Maximum successful uploads per day. Defaults to pipeline.max_daily_uploads.",
)
@click.option(
    "--active-start-hour",
    default=9,
    show_default=True,
    type=click.IntRange(0, 23),
    help="Hour when automatic scheduled attempts may start.",
)
@click.option(
    "--active-end-hour",
    default=1,
    show_default=True,
    type=click.IntRange(0, 23),
    help="Hour when automatic scheduled attempts stop. Supports overnight windows.",
)
def run_scheduler(
    city: str | None,
    concept: str | None,
    interval_minutes: int | None,
    max_daily: int | None,
    active_start_hour: int,
    active_end_hour: int,
):
    """Run one song attempt every configured interval until stopped."""
    if city and concept:
        raise click.ClickException("Use either --city or --concept, not both.")
    interval = interval_minutes if interval_minutes is not None else settings.pipeline.publish_interval_minutes
    daily_limit = max_daily if max_daily is not None else settings.pipeline.max_daily_uploads
    interval_seconds = max(interval, 1) * 60

    console.print(
        "[bold cyan]Scheduler started[/] "
        f"(interval={interval} min, max_daily={daily_limit}, city={city or 'auto'}, "
        f"concept={concept or 'auto'}, "
        f"active_hours={active_start_hour:02d}:00-{active_end_hour:02d}:00)"
    )

    while True:
        started = time.monotonic()
        now = datetime.now()
        inactive_sleep_seconds = _seconds_until_active_window(
            now,
            active_start_hour,
            active_end_hour,
        )
        if inactive_sleep_seconds:
            console.print(
                f"[yellow]Scheduler inactive outside "
                f"{active_start_hour:02d}:00-{active_end_hour:02d}:00; "
                f"next attempt in {inactive_sleep_seconds / 3600:.1f} hours.[/]"
            )
            try:
                time.sleep(inactive_sleep_seconds)
            except KeyboardInterrupt:
                console.print("[yellow]Scheduler stopped.[/]")
                raise
            continue

        today = date.today().isoformat()
        uploaded_today = _uploaded_count_for_day(today)

        if daily_limit > 0 and uploaded_today >= daily_limit:
            console.print(
                f"[yellow]Daily upload limit reached ({uploaded_today}/{daily_limit}) for {today}; "
                f"waiting {interval} minutes.[/]"
            )
        else:
            console.print(
                f"[cyan]Starting scheduled attempt; uploaded today: {uploaded_today}/{daily_limit}[/]"
            )
            try:
                resumable_song_id = _next_resumable_song_id(city, concept)
                if resumable_song_id:
                    console.print(f"[cyan]Resuming stalled song: {resumable_song_id}[/]")
                    PipelineService(dry_run=False).run_song(str(resumable_song_id))
                    song_ids = [str(resumable_song_id)]
                else:
                    runner = CycleRunner(k=1, dry_run=False)
                    song_ids = runner.run_cycle(city_slug=city, concept_slug=concept)
                console.print(f"[green]Scheduled attempt complete. Songs: {song_ids}[/]")
            except Exception as exc:
                console.print(f"[red]Scheduled attempt failed: {exc}[/]")

        elapsed = time.monotonic() - started
        sleep_seconds = max(interval_seconds - elapsed, 0)
        console.print(f"[dim]Next scheduled attempt in {sleep_seconds / 60:.1f} minutes.[/]")
        try:
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            console.print("[yellow]Scheduler stopped.[/]")
            raise
