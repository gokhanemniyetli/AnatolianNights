"""
PipelineService — drives a single song through the full pipeline
based on its current status. Each stage method is idempotent.
"""

import logging
from pathlib import Path

from src.adapters.suno import get_suno_client
from src.adapters.youtube import QuotaTracker, YouTubeClient
from src.agents import (
    ConceptAgent,
    ImagePromptAgent,
    LyricAgent,
    MetadataAgent,
    SunoPromptAgent,
)
from src.config.settings import settings
from src.image import ImageGenerator
from src.quality.quality_checker import QualityChecker
from src.services.city_service import CityService
from src.services.history_service import HistoryService
from src.services.song_service import SongService
from src.storage.database import get_session
from src.storage.file_storage import file_storage
from src.storage.models import Song, SongStatus
from src.video import (
    LongVideoRenderer,
    ShortRenderer,
    SubtitleBuilder,
    ThumbnailRenderer,
    get_audio_duration,
)

logger = logging.getLogger(__name__)


class PipelineService:
    """Drives one song forward one stage at a time."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._concept_agent = ConceptAgent()
        self._lyric_agent = LyricAgent()
        self._quality_checker = QualityChecker()
        self._suno_prompt_agent = SunoPromptAgent()
        self._image_prompt_agent = ImagePromptAgent()
        self._metadata_agent = MetadataAgent()
        self._image_generator = ImageGenerator()
        self._subtitle_builder = SubtitleBuilder()
        self._thumbnail_renderer = ThumbnailRenderer()
        self._long_renderer = LongVideoRenderer()
        self._short_renderer = ShortRenderer()

    # ── Public entry point ────────────────────────────────────────────

    def run_song(self, song_id: str) -> Song:
        """Advance song one or more stages until it blocks (needs audio or upload)."""
        with get_session() as session:
            song_svc = SongService(session)
            city_svc = CityService(session)
            history_svc = HistoryService(session)

            song = song_svc.get_by_id(song_id)
            if not song:
                raise ValueError(f"Song {song_id} not found")

            city = city_svc.get_by_id(song.city_id)
            cultural_profile = city_svc.load_cultural_profile(city.slug)

            # Run stages in sequence until we hit a blocking point
            while True:
                status = song.status
                if status == SongStatus.PENDING:
                    song = self._stage_concept(song, song_svc, history_svc, city, cultural_profile)
                elif status == SongStatus.CONCEPT_READY:
                    song = self._stage_lyrics(song, song_svc, history_svc, city, cultural_profile)
                elif status == SongStatus.QUALITY_REJECTED:
                    if (song.lyric_attempt or 0) >= settings.pipeline.max_lyric_retries:
                        song_svc.permanently_reject(song, "Max lyric retries reached")
                        break
                    song_svc.reset_for_retry(song)
                    song = self._stage_lyrics(song, song_svc, history_svc, city, cultural_profile)
                elif status == SongStatus.LYRICS_READY:
                    song = self._stage_suno_prompt(song, song_svc, cultural_profile)
                elif status == SongStatus.QUALITY_APPROVED:
                    # QUALITY_APPROVED is set when lyrics pass; advance to SUNO_READY
                    song = self._stage_suno_prompt(song, song_svc, cultural_profile)
                elif status == SongStatus.SUNO_READY:
                    # Blocking: operator must run import-audio
                    logger.info("Song %s is SUNO_READY. Waiting for audio import.", song.id)
                    break
                elif status == SongStatus.AUDIO_IMPORTED:
                    song = self._stage_image(song, song_svc, city, cultural_profile)
                elif status == SongStatus.IMAGE_READY:
                    song = self._stage_video(song, song_svc)
                elif status == SongStatus.VIDEO_READY:
                    if not self.dry_run:
                        song = self._stage_upload(song, song_svc, session, city)
                    else:
                        logger.info("[DRY-RUN] Skipping upload for song %s", song.id)
                    break
                else:
                    # UPLOADED, PERMANENTLY_REJECTED — done
                    break

            return song

    # ── Stages ────────────────────────────────────────────────────────

    def _stage_concept(self, song, song_svc, history_svc, city, cultural_profile):
        logger.info("[%s] Stage: concept", song.id)
        history_dict = history_svc.get_history_dict(city.id)
        concept = self._concept_agent.generate(city.name, cultural_profile, history_dict)
        song.set_concept(concept)
        song.title = concept.get("title", "")
        return song_svc.advance(song)  # → CONCEPT_READY

    def _stage_lyrics(self, song, song_svc, history_svc, city, cultural_profile):
        logger.info("[%s] Stage: lyrics", song.id)
        concept = song.get_concept()
        lyric_result = self._lyric_agent.generate(concept, city.name, cultural_profile)
        lyrics = lyric_result.get("lyrics", "")
        song.lyrics = lyrics

        # Quality check
        qr = self._quality_checker.check(lyrics, city.name, concept)
        song.set_quality_report(qr)
        song.quality_score = qr.get("score")

        if qr["is_approved"]:
            song.status = SongStatus.QUALITY_APPROVED
            history_svc.record_song(city.id, concept, lyric_result.get("keywords", []))
            logger.info("[%s] Lyrics approved (score=%.1f)", song.id, qr.get("score", 0))
        else:
            song.status = SongStatus.QUALITY_REJECTED
            song.rejected_reason = qr.get("rejected_reason", "")
            logger.warning("[%s] Lyrics rejected: %s", song.id, song.rejected_reason)

        return song

    def _stage_suno_prompt(self, song, song_svc, cultural_profile):
        logger.info("[%s] Stage: suno_prompt", song.id)
        concept = song.get_concept()
        result = self._suno_prompt_agent.generate(concept, song.lyrics, cultural_profile)
        song.suno_style_prompt = result.get("style_prompt", "")
        song.suno_lyrics = result.get("suno_lyrics", "")

        # Write prompt file for operator (manual mode)
        suno_client = get_suno_client()
        suno_client.generate(song.suno_style_prompt, song.suno_lyrics, song.id)

        file_storage.write_suno_prompt(city_slug=self._get_city_slug(song), song_id=song.id,
                                       style_prompt=song.suno_style_prompt,
                                       suno_lyrics=song.suno_lyrics)
        return song_svc.advance(song)  # → SUNO_READY

    def _stage_image(self, song, song_svc, city, cultural_profile):
        logger.info("[%s] Stage: image", song.id)
        concept = song.get_concept()
        ip_result = self._image_prompt_agent.generate(concept, city.name, cultural_profile)
        image_prompt = ip_result.get("image_prompt", "")
        negative_prompt = ip_result.get("negative_prompt", "text, watermark, faces")

        song.image_prompt = image_prompt
        file_storage.write_image_prompt(city.slug, song.id, image_prompt)

        bg_path = file_storage.background_path(city.slug, song.id)
        self._image_generator.generate(image_prompt, negative_prompt, bg_path)
        song.background_image_path = str(file_storage.rel(bg_path))

        return song_svc.advance(song)  # → IMAGE_READY

    def _stage_video(self, song, song_svc):
        logger.info("[%s] Stage: video", song.id)
        city_slug = self._get_city_slug(song)
        audio_path = file_storage.audio_path(city_slug, song.id)
        bg_path = file_storage.background_path(city_slug, song.id)
        srt_path = file_storage.subtitles_path(city_slug, song.id)
        long_path = file_storage.video_path(city_slug, song.id)
        short_path = file_storage.short_path(city_slug, song.id)
        thumb_path = file_storage.thumbnail_path(city_slug, song.id)

        duration = get_audio_duration(audio_path)

        # Subtitles
        self._subtitle_builder.build(song.lyrics, duration, srt_path)
        song.subtitles_path = str(file_storage.rel(srt_path))

        # Thumbnail
        self._thumbnail_renderer.render(bg_path, song.title or "", self._get_city_name(song), thumb_path)
        song.thumbnail_path = str(file_storage.rel(thumb_path))

        # Long video
        self._long_renderer.render(bg_path, audio_path, srt_path, long_path)
        song.long_video_path = str(file_storage.rel(long_path))

        # Short
        self._short_renderer.render(bg_path, audio_path, srt_path, short_path)
        song.short_video_path = str(file_storage.rel(short_path))

        return song_svc.advance(song)  # → VIDEO_READY

    def _stage_upload(self, song, song_svc, session, city):
        logger.info("[%s] Stage: upload", song.id)
        quota_tracker = QuotaTracker(session)

        yt = YouTubeClient(
            client_secrets_file=settings.youtube.client_secrets_file,
            dry_run=self.dry_run,
        )

        meta_agent = MetadataAgent()
        concept = song.get_concept()
        meta = meta_agent.generate(song.title or "", city.name, concept, song.lyrics)
        song.set_youtube_metadata(meta)
        file_storage.write_youtube_metadata(city.slug, song.id, meta)

        long_path = Path("outputs") / song.long_video_path if song.long_video_path else None
        short_path = Path("outputs") / song.short_video_path if song.short_video_path else None
        thumb_path = Path("outputs") / song.thumbnail_path if song.thumbnail_path else None

        # Upload long video
        if long_path and long_path.exists() and quota_tracker.can_afford("upload"):
            vid_id = yt.upload_video(
                video_path=long_path,
                title=meta.get("title", song.title or ""),
                description=meta.get("description", ""),
                tags=meta.get("tags", []),
                thumbnail_path=thumb_path,
                playlist_id=city.playlist_id,
            )
            song.youtube_long_video_id = vid_id
            quota_tracker.record("upload", song.id)

        # Upload Short
        if short_path and short_path.exists() and quota_tracker.can_afford("upload_short"):
            short_id = yt.upload_short(
                video_path=short_path,
                title=meta.get("short_title", meta.get("title", "")),
                description=meta.get("short_description", ""),
                tags=meta.get("tags", []),
                playlist_id=None,
            )
            song.youtube_short_video_id = short_id
            quota_tracker.record("upload_short", song.id)

        return song_svc.advance(song)  # → UPLOADED

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_city_slug(self, song: Song) -> str:
        with get_session() as s:
            from src.storage.models import City
            city = s.get(City, song.city_id)
            return city.slug if city else "unknown"

    def _get_city_name(self, song: Song) -> str:
        with get_session() as s:
            from src.storage.models import City
            city = s.get(City, song.city_id)
            return city.name if city else ""
