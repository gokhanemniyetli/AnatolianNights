"""
status commands — list-songs, song-stats
"""

import click
from rich.console import Console
from rich.table import Table
from rich import box

from src.storage.database import get_session
from src.storage.models import Song, City, ConceptPlaylist, SongStatus

console = Console()


@click.command("list-songs")
@click.option(
    "--status",
    "filter_status",
    default=None,
    help="Filter by status (e.g. suno_ready, video_ready, uploaded)",
)
@click.option("--city", default=None, help="Filter by city slug")
@click.option("--limit", default=30, show_default=True, help="Max rows to show")
def list_songs(filter_status: str | None, city: str | None, limit: int):
    """List songs with their current pipeline status."""
    with get_session() as session:
        query = (
            session.query(Song, City, ConceptPlaylist)
            .join(City, Song.city_id == City.id)
            .outerjoin(ConceptPlaylist, Song.concept_playlist_id == ConceptPlaylist.id)
        )

        if filter_status:
            query = query.filter(Song.status == filter_status)
        if city:
            query = query.filter(City.slug == city)

        rows = query.order_by(Song.created_at.desc()).limit(limit).all()

        table = Table(
            title=f"Songs (filter: {filter_status or 'all'}, city: {city or 'all'})",
            box=box.ROUNDED,
            show_lines=False,
        )
        table.add_column("ID", style="dim", max_width=10)
        table.add_column("Context", style="cyan")
        table.add_column("Title", max_width=40)
        table.add_column("Status", style="bold")
        table.add_column("Score")
        table.add_column("Attempt")
        table.add_column("Created")

        STATUS_COLORS = {
            "pending": "white",
            "concept_ready": "yellow",
            "lyrics_ready": "yellow",
            "quality_approved": "green",
            "quality_rejected": "red",
            "permanently_rejected": "red",
            "suno_ready": "magenta",
            "audio_imported": "blue",
            "image_ready": "blue",
            "video_ready": "cyan",
            "uploaded": "bright_green",
        }

        for song, song_city, concept_playlist in rows:
            color = STATUS_COLORS.get(song.status, "white")
            context_name = concept_playlist.title if concept_playlist else song_city.name
            table.add_row(
                str(song.id)[:8] + "…",
                context_name,
                (song.title or "—")[:40],
                f"[{color}]{song.status}[/]",
                f"{song.quality_score:.1f}" if song.quality_score else "—",
                str(song.lyric_attempt or 0),
                song.created_at.strftime("%m-%d %H:%M") if song.created_at else "—",
            )

        console.print(table)
        console.print(f"[dim]Showing {len(rows)} of {limit} max rows[/]")


@click.command("song-stats")
def song_stats():
    """Show pipeline stage counts across all songs."""
    with get_session() as session:
        from sqlalchemy import func

        counts = (
            session.query(Song.status, func.count(Song.id).label("cnt"))
            .group_by(Song.status)
            .all()
        )

        total = sum(c for _, c in counts)

        table = Table(title="Pipeline Stats", box=box.ROUNDED)
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("% of Total", justify="right")

        # Sort by pipeline order
        order = [s.value for s in SongStatus]
        count_dict = {status: cnt for status, cnt in counts}

        for status in order:
            cnt = count_dict.get(status, 0)
            pct = (cnt / total * 100) if total else 0
            table.add_row(status, str(cnt), f"{pct:.1f}%")

        # Any unknown statuses
        for status, cnt in count_dict.items():
            if status not in order:
                table.add_row(f"[dim]{status}[/]", str(cnt), "—")

        console.print(table)
        console.print(f"[bold]Total songs:[/] {total}")
