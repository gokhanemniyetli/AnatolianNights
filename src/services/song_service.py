"""
SongService — creates and advances songs through the status state machine.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.storage.models import Song, SongStatus

logger = logging.getLogger(__name__)


class SongService:
    # Valid one-step forward transitions
    _TRANSITIONS: dict[SongStatus, SongStatus] = {
        SongStatus.PENDING: SongStatus.CONCEPT_READY,
        SongStatus.CONCEPT_READY: SongStatus.LYRICS_READY,
        SongStatus.LYRICS_READY: SongStatus.QUALITY_APPROVED,
        SongStatus.QUALITY_APPROVED: SongStatus.SUNO_READY,
        SongStatus.SUNO_READY: SongStatus.AUDIO_IMPORTED,
        SongStatus.AUDIO_IMPORTED: SongStatus.IMAGE_READY,
        SongStatus.IMAGE_READY: SongStatus.VIDEO_READY,
        SongStatus.VIDEO_READY: SongStatus.UPLOADED,
    }

    def __init__(self, session: Session):
        self.session = session

    # ── Creation ──────────────────────────────────────────────────────

    def create_song(self, city_id: int) -> Song:
        song = Song(
            city_id=city_id,
            status=SongStatus.PENDING,
            lyric_attempt=0,
        )
        self.session.add(song)
        self.session.flush()
        logger.info("Created song %s for city_id=%d", song.id, city_id)
        return song

    def create_concept_song(self, city_id: int, concept_playlist_id: int) -> Song:
        song = Song(
            city_id=city_id,
            concept_playlist_id=concept_playlist_id,
            status=SongStatus.PENDING,
            lyric_attempt=0,
        )
        self.session.add(song)
        self.session.flush()
        logger.info(
            "Created song %s for concept_playlist_id=%d anchor_city_id=%d",
            song.id,
            concept_playlist_id,
            city_id,
        )
        return song

    # ── Status transitions ────────────────────────────────────────────

    def advance(self, song: Song) -> Song:
        """Move song to next status in the happy path."""
        next_status = self._TRANSITIONS.get(song.status)
        if next_status is None:
            raise ValueError(f"No forward transition from {song.status}")
        logger.info("Song %s: %s → %s", song.id, song.status, next_status)
        song.status = next_status
        if next_status == SongStatus.UPLOADED:
            song.uploaded_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.session.flush()
        return song

    def reject(self, song: Song, reason: str) -> Song:
        song.status = SongStatus.QUALITY_REJECTED
        song.rejected_reason = reason
        self.session.flush()
        logger.info("Song %s rejected: %s", song.id, reason)
        return song

    def permanently_reject(self, song: Song, reason: str) -> Song:
        song.status = SongStatus.PERMANENTLY_REJECTED
        song.rejected_reason = reason
        self.session.flush()
        logger.warning("Song %s permanently rejected: %s", song.id, reason)
        return song

    def reset_for_retry(self, song: Song) -> Song:
        """Reset a quality-rejected song back to CONCEPT_READY for a new lyric attempt."""
        song.status = SongStatus.CONCEPT_READY
        song.lyric_attempt = (song.lyric_attempt or 0) + 1
        self.session.flush()
        return song

    # ── Queries ───────────────────────────────────────────────────────

    def get_by_id(self, song_id: str) -> Song | None:
        return self.session.get(Song, song_id)

    def get_by_city(self, city_id: int) -> list[Song]:
        return (
            self.session.query(Song)
            .filter_by(city_id=city_id)
            .order_by(Song.created_at.desc())
            .all()
        )

    def get_pending_at_status(self, status: SongStatus, limit: int = 10) -> list[Song]:
        return (
            self.session.query(Song)
            .filter_by(status=status)
            .order_by(Song.created_at.asc())
            .limit(limit)
            .all()
        )

    def get_by_status(self, status: SongStatus) -> list[Song]:
        return self.session.query(Song).filter_by(status=status).all()
