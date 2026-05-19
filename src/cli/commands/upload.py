"""
upload commands — upload-youtube
"""

import click
from rich.console import Console

from src.adapters.youtube import YouTubeStudioUploader
from src.adapters.youtube import YouTubeClient
from src.agents import MetadataAgent
from src.config.settings import settings
from src.services.pipeline_service import PipelineService
from src.storage.database import get_session
from src.storage.file_storage import file_storage
from src.storage.models import Song, SongStatus

console = Console()


def _city_playlist_title(city_name: str) -> str:
    return f"{city_name} Türküleri | Anadolu Türküleri Ezgileri"


def _ensure_city_playlist(session, city) -> str:
    if city.playlist_id:
        return city.playlist_id

    yt = YouTubeClient(
        client_secrets_file=settings.youtube.client_secrets_file,
        dry_run=False,
    )
    playlist_id = yt.ensure_playlist(
        _city_playlist_title(city.name),
        f"{city.name} yöresinden üretilen Anadolu türküleri.",
    )
    city.playlist_id = playlist_id
    session.flush()
    return playlist_id


def _add_long_to_city_playlist(session, song: Song) -> None:
    if not song.youtube_long_video_id or not song.city:
        return
    playlist_id = _ensure_city_playlist(session, song.city)
    yt = YouTubeClient(
        client_secrets_file=settings.youtube.client_secrets_file,
        dry_run=False,
    )
    yt.add_to_playlist(song.youtube_long_video_id, playlist_id)


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


@click.command("upload-youtube-web")
@click.argument("song_id")
@click.option("--kind", type=click.Choice(["long", "short"]), default="long", show_default=True)
@click.option("--profile-dir", default="config/youtube_browser_profile_short", show_default=True)
def upload_youtube_web(song_id: str, kind: str, profile_dir: str):
    """Upload a VIDEO_READY song through YouTube Studio web UI."""
    with get_session() as session:
        song: Song | None = session.get(Song, song_id)
        if not song:
            console.print(f"[red]Song not found: {song_id}[/]")
            return
        if song.status != SongStatus.VIDEO_READY:
            console.print(f"[yellow]Song status is {song.status}, expected VIDEO_READY.[/]")
            return

        city = song.city
        if not city:
            console.print("[red]Song city not found.[/]")
            return
        city_name = city.name

        if not song.youtube_metadata:
            meta = MetadataAgent().generate(song.title or "", city.name, song.get_concept(), song.lyrics)
            song.set_youtube_metadata(meta)
            file_storage.write_youtube_metadata(city.slug, song.id, meta)
            session.flush()
        else:
            meta = song.get_youtube_metadata()

        if kind == "long":
            video_rel = song.long_video_path
            title = meta.get("title", song.title or "")
            description = meta.get("description", "")
            already_uploaded = bool(song.youtube_long_video_id)
            related_video_id = None
            related_video_title = None
        else:
            video_rel = song.short_video_path
            title = meta.get("short_title", song.title or "")
            description = meta.get("short_description", "")
            already_uploaded = bool(song.youtube_short_video_id)
            related_video_id = song.youtube_long_video_id
            related_video_title = meta.get("title", song.title or "")

        if already_uploaded:
            console.print(f"[yellow]{kind} already has a YouTube id.[/]")
            return
        if not video_rel:
            console.print(f"[red]No {kind} video path found.[/]")
            return

        video_path = file_storage.base / video_rel
        thumb_path = file_storage.base / song.thumbnail_path if song.thumbnail_path else None
        if not video_path.exists():
            console.print(f"[red]Video file not found: {video_path}[/]")
            return

    console.print(f"[cyan]Uploading song {song_id} {kind} through YouTube Studio web UI...[/]")
    uploader = YouTubeStudioUploader(profile_dir=profile_dir)
    video_id = uploader.upload_video(
        video_path=video_path,
        title=title,
        description=description,
        thumbnail_path=thumb_path if kind == "long" else None,
        playlist_title=_city_playlist_title(city_name) if kind == "long" else None,
    )

    with get_session() as session:
        song = session.get(Song, song_id)
        if kind == "long":
            song.youtube_long_video_id = video_id
            _add_long_to_city_playlist(session, song)
            uploader.add_end_screen(video_id)
        else:
            song.youtube_short_video_id = video_id
            if song.youtube_long_video_id:
                try:
                    uploader.set_related_video(
                        short_video_id=video_id,
                        related_video_id=song.youtube_long_video_id,
                        related_video_title=related_video_title or song.title or "",
                    )
                except PermissionError as exc:
                    console.print(f"[yellow]Related video could not be set: {exc}[/]")
        if song.youtube_long_video_id and song.youtube_short_video_id:
            song.status = SongStatus.UPLOADED
        session.flush()

    console.print(f"[green]✓ Web upload complete for {song_id} {kind}: {video_id}[/]")


@click.command("publish-youtube-id")
@click.argument("song_id")
@click.argument("video_id")
@click.option("--kind", type=click.Choice(["long", "short"]), default="long", show_default=True)
def publish_youtube_id(song_id: str, video_id: str, kind: str):
    """Mark an existing YouTube Studio upload public and save its id."""
    console.print(f"[cyan]Publishing existing YouTube video {video_id}...[/]")
    yt = YouTubeClient(
        client_secrets_file=settings.youtube.client_secrets_file,
        dry_run=False,
    )
    yt.publish_video(video_id)

    with get_session() as session:
        song: Song | None = session.get(Song, song_id)
        if not song:
            console.print(f"[red]Song not found: {song_id}[/]")
            return
        if kind == "long":
            song.youtube_long_video_id = video_id
            _add_long_to_city_playlist(session, song)
            YouTubeStudioUploader().add_end_screen(video_id)
        else:
            song.youtube_short_video_id = video_id
            if song.youtube_long_video_id:
                try:
                    YouTubeStudioUploader().set_related_video(
                        short_video_id=video_id,
                        related_video_id=song.youtube_long_video_id,
                        related_video_title=song.title or "",
                    )
                except PermissionError as exc:
                    console.print(f"[yellow]Related video could not be set: {exc}[/]")
        if song.youtube_long_video_id and song.youtube_short_video_id:
            song.status = SongStatus.UPLOADED
        session.flush()

    console.print(f"[green]✓ Published and saved {kind} id for song {song_id}: {video_id}[/]")


@click.command("sync-youtube-ui")
@click.argument("song_id")
@click.option("--profile-dir", default="config/youtube_browser_profile_short", show_default=True)
def sync_youtube_ui(song_id: str, profile_dir: str):
    """Apply Studio-only UI settings for an already uploaded song."""
    with get_session() as session:
        song: Song | None = session.get(Song, song_id)
        if not song:
            console.print(f"[red]Song not found: {song_id}[/]")
            return

        long_video_id = song.youtube_long_video_id
        short_video_id = song.youtube_short_video_id
        title = song.title or ""

    uploader = YouTubeStudioUploader(profile_dir=profile_dir)

    if long_video_id:
        console.print(f"[cyan]Adding end screen through Studio UI: {long_video_id}[/]")
        uploader.add_end_screen(long_video_id)
    else:
        console.print("[yellow]Long video id is missing; end screen skipped.[/]")

    if short_video_id and long_video_id:
        console.print(f"[cyan]Setting Short related video through Studio UI: {short_video_id} -> {long_video_id}[/]")
        try:
            uploader.set_related_video(
                short_video_id=short_video_id,
                related_video_id=long_video_id,
                related_video_title=title,
            )
        except PermissionError as exc:
            console.print(f"[yellow]Related video could not be set: {exc}[/]")
    elif short_video_id:
        console.print("[yellow]Long video id is missing; Short related video skipped.[/]")
    else:
        console.print("[yellow]Short video id is missing; related video skipped.[/]")

    console.print(f"[green]✓ Studio UI sync finished for song {song_id}[/]")
