"""
YouTubeClient — uploads long videos and Shorts, manages playlists.
Uses google-api-python-client with OAuth2.
"""

import logging
import os
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
TOKEN_FILE = "data/youtube_token.json"

# Category: Music = 10
MUSIC_CATEGORY_ID = "10"


class YouTubeClient:
    def __init__(self, client_secrets_file: str, dry_run: bool = False):
        self.client_secrets_file = client_secrets_file
        self.dry_run = dry_run
        self._service = None

    # ── Auth ──────────────────────────────────────────────────────────

    def _get_service(self):
        if self._service:
            return self._service

        creds = None
        token_path = Path(TOKEN_FILE)

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing YouTube OAuth token...")
                creds.refresh(Request())
            else:
                logger.info("Running OAuth flow for YouTube...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secrets_file, SCOPES
                )
                creds = flow.run_local_server(port=0)

            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")

        self._service = build("youtube", "v3", credentials=creds)
        return self._service

    # ── Upload ────────────────────────────────────────────────────────

    def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list[str],
        thumbnail_path: Path | None = None,
        playlist_id: str | None = None,
    ) -> str:
        """Upload long video. Returns YouTube video ID."""
        return self._upload(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            thumbnail_path=thumbnail_path,
            playlist_id=playlist_id,
            is_short=False,
        )

    def upload_short(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list[str],
        thumbnail_path: Path | None = None,
        playlist_id: str | None = None,
    ) -> str:
        """Upload YouTube Short. Returns YouTube video ID."""
        return self._upload(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            thumbnail_path=thumbnail_path,
            playlist_id=playlist_id,
            is_short=True,
        )

    def update_video_metadata(
        self,
        video_id: str,
        title: str,
        description: str,
        tags: list[str],
    ) -> None:
        """Update title/description/tags for an existing YouTube video."""
        if self.dry_run:
            logger.info("[DRY-RUN] Would update metadata for video %s", video_id)
            return

        service = self._get_service()
        service.videos().update(
            part="snippet",
            body={
                "id": video_id,
                "snippet": {
                    "title": title[:100],
                    "description": description[:5000],
                    "tags": tags[:500],
                    "categoryId": MUSIC_CATEGORY_ID,
                },
            },
        ).execute()
        logger.info("Updated metadata for video %s", video_id)

    def publish_video(self, video_id: str) -> None:
        """Set an existing YouTube video to public."""
        if self.dry_run:
            logger.info("[DRY-RUN] Would publish video %s", video_id)
            return

        service = self._get_service()
        service.videos().update(
            part="status",
            body={
                "id": video_id,
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                },
            },
        ).execute()
        logger.info("Published video %s", video_id)

    def _upload(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: list[str],
        thumbnail_path: Path | None,
        playlist_id: str | None,
        is_short: bool,
    ) -> str:
        if self.dry_run:
            fake_id = f"DRY_RUN_{int(time.time())}"
            logger.info("[DRY-RUN] Would upload %s → fake id: %s", video_path.name, fake_id)
            return fake_id

        service = self._get_service()

        body = {
            "snippet": {
                "title": title[:100],  # YouTube limit
                "description": description[:5000],  # YouTube limit
                "tags": tags[:500],
                "categoryId": MUSIC_CATEGORY_ID,
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024 * 10,  # 10MB chunks
        )

        logger.info("Uploading %s to YouTube: %s", "Short" if is_short else "long video", title)
        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info("Upload progress: %.1f%%", status.progress() * 100)

        video_id = response["id"]
        logger.info("Uploaded video id=%s", video_id)

        # Set thumbnail
        if thumbnail_path and thumbnail_path.exists():
            try:
                self._set_thumbnail(service, video_id, thumbnail_path)
            except HttpError as exc:
                logger.warning("Thumbnail upload failed (non-fatal): %s", exc)

        # Add to playlist
        if playlist_id:
            try:
                self._add_to_playlist(service, video_id, playlist_id)
            except HttpError as exc:
                logger.warning("Playlist insert failed (non-fatal): %s", exc)

        return video_id

    # ── Helpers ───────────────────────────────────────────────────────

    def _set_thumbnail(self, service, video_id: str, thumbnail_path: Path) -> None:
        media = MediaFileUpload(str(thumbnail_path), mimetype="image/png", resumable=False)
        service.thumbnails().set(videoId=video_id, media_body=media).execute()
        logger.info("Thumbnail set for video %s", video_id)

    def _add_to_playlist(self, service, video_id: str, playlist_id: str) -> None:
        service.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        logger.info("Added video %s to playlist %s", video_id, playlist_id)

    def add_to_playlist(self, video_id: str, playlist_id: str) -> None:
        """Add an existing video to a playlist."""
        if self.dry_run:
            logger.info("[DRY-RUN] Would add video %s to playlist %s", video_id, playlist_id)
            return
        try:
            self._add_to_playlist(self._get_service(), video_id, playlist_id)
        except HttpError as exc:
            if getattr(exc, "resp", None) is not None and exc.resp.status == 409:
                logger.info("Video %s is already in playlist %s", video_id, playlist_id)
                return
            raise

    def find_playlist_by_title(self, title: str) -> str | None:
        """Return the authenticated channel playlist id with an exact title match."""
        if self.dry_run:
            return None

        service = self._get_service()
        page_token = None
        while True:
            resp = service.playlists().list(
                part="snippet",
                mine=True,
                maxResults=50,
                pageToken=page_token,
            ).execute()
            for item in resp.get("items", []):
                if item.get("snippet", {}).get("title") == title:
                    return item.get("id")
            page_token = resp.get("nextPageToken")
            if not page_token:
                return None

    def ensure_playlist(self, title: str, description: str = "") -> str:
        """Find an existing playlist by title or create it."""
        existing = self.find_playlist_by_title(title)
        if existing:
            logger.info("Found playlist '%s' id=%s", title, existing)
            return existing
        return self.create_playlist(title, description)

    def create_playlist(self, title: str, description: str = "") -> str:
        """Create a new playlist and return its ID."""
        if self.dry_run:
            return f"DRY_PLAYLIST_{int(time.time())}"
        service = self._get_service()
        resp = service.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {"title": title, "description": description},
                "status": {"privacyStatus": "public"},
            },
        ).execute()
        playlist_id = resp["id"]
        logger.info("Created playlist '%s' id=%s", title, playlist_id)
        return playlist_id
