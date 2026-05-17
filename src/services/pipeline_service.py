"""
PipelineService — drives a single song through the full pipeline
based on its current status. Each stage method is idempotent.
"""

import logging
from pathlib import Path

from googleapiclient.errors import HttpError

from src.adapters.suno import get_suno_client
from src.adapters.youtube import YouTubeClient, YouTubeStudioUploader
from src.agents import (
    ConceptAgent,
    ImagePromptAgent,
    MetadataAgent,
    SunoPromptAgent,
)
from src.config.settings import settings
from src.image import ImageGenerator
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
                    session.commit()
                elif status == SongStatus.CONCEPT_READY:
                    song = self._stage_suno_prompt(song, song_svc, cultural_profile)
                    session.commit()
                elif status == SongStatus.QUALITY_REJECTED:
                    if (song.lyric_attempt or 0) >= settings.pipeline.max_lyric_retries:
                        song_svc.permanently_reject(song, "Max lyric retries reached")
                        session.commit()
                        break
                    song_svc.reset_for_retry(song)
                    song = self._stage_suno_prompt(song, song_svc, cultural_profile)
                    session.commit()
                elif status == SongStatus.LYRICS_READY:
                    song = self._stage_suno_prompt(song, song_svc, cultural_profile)
                    session.commit()
                elif status == SongStatus.QUALITY_APPROVED:
                    # QUALITY_APPROVED is set when lyrics pass; advance to SUNO_READY
                    song = self._stage_suno_prompt(song, song_svc, cultural_profile)
                    session.commit()
                elif status == SongStatus.SUNO_READY:
                    if settings.suno.client.lower() == "browser":
                        song = self._stage_suno_wait(song, song_svc, city)
                        session.commit()
                    else:
                        # manual mode — operator must run import-audio
                        logger.info("Song %s is SUNO_READY. Waiting for audio import.", song.id)
                        break
                elif status == SongStatus.AUDIO_IMPORTED:
                    song = self._stage_image(song, song_svc, city, cultural_profile)
                    session.commit()
                elif status == SongStatus.IMAGE_READY:
                    song = self._stage_video(song, song_svc)
                    session.commit()
                elif status == SongStatus.VIDEO_READY:
                    if not self.dry_run:
                        song = self._stage_upload(song, song_svc, session, city)
                        session.commit()
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
        history_svc.record_song(city.id, concept, self._concept_history_hooks(concept, cultural_profile))
        return song_svc.advance(song)  # → CONCEPT_READY

    def _stage_suno_prompt(self, song, song_svc, cultural_profile):
        logger.info("[%s] Stage: suno_prompt", song.id)
        concept = song.get_concept()
        result = self._suno_prompt_agent.generate(concept, cultural_profile)
        simple_prompt = (
            result.get("simple_prompt")
            or result.get("style_prompt")
            or ""
        ).strip()

        if not simple_prompt:
            raise ValueError("Suno simple prompt boş geldi.")

        # Simple mode: send only the description and let Suno generate lyrics/style.
        song.suno_style_prompt = simple_prompt
        song.suno_full_prompt = simple_prompt
        song.suno_lyrics = ""
        song.lyrics = None
        song.quality_report = None
        song.quality_score = None

        # Submit to Suno (manual: writes prompt file; browser: submits to API)
        suno_client = get_suno_client()
        task_id = suno_client.generate(song.suno_style_prompt, song.suno_lyrics, song.id)
        song.suno_task_id = str(task_id) if task_id else None

        file_storage.write_suno_prompt(city_slug=self._get_city_slug(song), song_id=song.id,
                                       style_prompt=song.suno_style_prompt,
                                       suno_lyrics=song.suno_lyrics)
        song.status = SongStatus.SUNO_READY
        song_svc.session.flush()
        return song

    def _stage_suno_wait(self, song, song_svc, city):
        """Browser mode: poll Suno until clip is ready, download WAV, advance to AUDIO_IMPORTED."""
        logger.info("[%s] Stage: suno_wait (clip_id=%s)", song.id, song.suno_task_id)
        if not song.suno_task_id:
            raise ValueError(f"Song {song.id} is SUNO_READY but has no suno_task_id.")

        city_slug = city.slug
        suno_client = get_suno_client()
        audio_dest = file_storage.audio_path(city_slug, song.id)  # returns .wav path
        downloaded = suno_client.download_audio(song.suno_task_id, audio_dest)
        suno_status = suno_client.get_status(song.suno_task_id)

        suno_title = (suno_status.get("suno_title") or "").strip()
        if suno_title and not (song.title or "").strip():
            song.title = suno_title

        suno_lyrics = (suno_status.get("suno_lyrics") or "").strip()
        if suno_lyrics:
            song.suno_lyrics = suno_lyrics
            song.lyrics = suno_lyrics
            file_storage.write_lyrics(city.slug, song.id, suno_lyrics)

        song.audio_path = str(file_storage.rel(downloaded))
        song.status = SongStatus.AUDIO_IMPORTED
        song_svc.session.flush()
        logger.info("[%s] Audio indirme tamam: %s", song.id, downloaded)
        return song

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

        short_prompt = (
            f"{image_prompt} Vertical 9:16 composition for a YouTube Short, "
            "strong central landscape subject, no stretching, no people, no instruments."
        )
        short_bg_path = file_storage.short_background_path(city.slug, song.id)
        self._image_generator.generate(
            short_prompt,
            negative_prompt,
            short_bg_path,
            target_width=1080,
            target_height=1920,
            gen_width=576,
            gen_height=1024,
        )

        return song_svc.advance(song)  # → IMAGE_READY

    def _stage_video(self, song, song_svc):
        logger.info("[%s] Stage: video", song.id)
        city_slug = self._get_city_slug(song)
        audio_path = file_storage.audio_path(city_slug, song.id)
        bg_path = file_storage.background_path(city_slug, song.id)
        short_bg_path = file_storage.short_background_path(city_slug, song.id)
        if not short_bg_path.exists():
            short_bg_path = bg_path
        srt_path = file_storage.subtitles_path(city_slug, song.id)
        long_path = file_storage.video_path(city_slug, song.id)
        short_path = file_storage.short_path(city_slug, song.id)
        thumb_path = file_storage.thumbnail_path(city_slug, song.id)

        duration = get_audio_duration(audio_path)

        # Subtitles
        subtitle_text = song.lyrics or ""
        if len(self._content_lines(subtitle_text)) < 4:
            subtitle_text = self._fallback_subtitle_text(song)
            logger.warning(
                "[%s] Suno did not return usable lyrics; using fallback title/concept captions.",
                song.id,
            )
        self._subtitle_builder.build(subtitle_text, duration, srt_path)
        song.subtitles_path = str(file_storage.rel(srt_path))

        # Thumbnail
        self._thumbnail_renderer.render(bg_path, song.title or "", self._get_city_name(song), thumb_path)
        song.thumbnail_path = str(file_storage.rel(thumb_path))

        # Long video
        self._long_renderer.render(
            bg_path,
            audio_path,
            srt_path,
            long_path,
            title=song.title or "",
            city_name=self._get_city_name(song),
        )
        song.long_video_path = str(file_storage.rel(long_path))

        # Short
        self._short_renderer.render(
            short_bg_path,
            audio_path,
            srt_path,
            short_path,
            title=song.title or "",
            city_name=self._get_city_name(song),
        )
        song.short_video_path = str(file_storage.rel(short_path))

        return song_svc.advance(song)  # → VIDEO_READY

    def _fallback_subtitle_text(self, song: Song) -> str:
        concept = song.get_concept() or {}
        parts = [
            song.title or "Anadolu Türküleri Ezgileri",
            self._get_city_name(song),
            concept.get("theme") or "",
            concept.get("story") or "",
            concept.get("mood") or "",
        ]
        lines: list[str] = []
        for part in parts:
            text = str(part).strip()
            if not text:
                continue
            for sentence in text.replace(";", ".").split("."):
                line = sentence.strip()
                if line:
                    lines.append(line[:90])
        return "\n".join(lines[:12] or [song.title or "Anadolu Türküleri Ezgileri"])

    @staticmethod
    def _content_lines(text: str) -> list[str]:
        return [
            line.strip()
            for line in (text or "").splitlines()
            if line.strip() and not line.strip().startswith("[")
        ]

    def _stage_upload(self, song, song_svc, session, city):
        logger.info("[%s] Stage: upload", song.id)

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

        missing_ops: list[str] = []
        if long_path and long_path.exists() and not song.youtube_long_video_id:
            missing_ops.append("upload")
            missing_ops.append("playlist_insert")
        if short_path and short_path.exists() and not song.youtube_short_video_id:
            missing_ops.append("upload_short")

        if not missing_ops:
            if song.youtube_long_video_id or song.youtube_short_video_id:
                return song_svc.advance(song)  # → UPLOADED
            raise RuntimeError(f"No uploadable video files found for song {song.id}")

        # Upload long video
        if long_path and long_path.exists() and not song.youtube_long_video_id:
            playlist_id = self._ensure_city_playlist(yt, city)
            studio = YouTubeStudioUploader()
            vid_id = studio.upload_video(
                video_path=long_path,
                title=meta.get("title", song.title or ""),
                description=meta.get("description", ""),
                thumbnail_path=thumb_path,
                playlist_title=self._city_playlist_title(city),
            )
            yt.publish_video(vid_id)
            song.youtube_long_video_id = vid_id
            if playlist_id:
                try:
                    yt.add_to_playlist(vid_id, playlist_id)
                except HttpError as exc:
                    logger.warning("Playlist API insert failed after Studio upload; playlist UI selection was already attempted: %s", exc)
            studio.add_end_screen(vid_id)

        # Upload Short
        if short_path and short_path.exists() and not song.youtube_short_video_id:
            studio = YouTubeStudioUploader()
            short_id = studio.upload_video(
                video_path=short_path,
                title=meta.get("short_title", meta.get("title", "")),
                description=meta.get("short_description", ""),
            )
            yt.publish_video(short_id)
            song.youtube_short_video_id = short_id
            if song.youtube_long_video_id:
                try:
                    studio.set_related_video(
                        short_video_id=short_id,
                        related_video_id=song.youtube_long_video_id,
                        related_video_title=meta.get("title", song.title or ""),
                    )
                except PermissionError as exc:
                    logger.warning("Short related video could not be set: %s", exc)

        return song_svc.advance(song)  # → UPLOADED

    # ── Helpers ───────────────────────────────────────────────────────

    def _ensure_city_playlist(self, yt: YouTubeClient, city) -> str | None:
        if city.playlist_id:
            return city.playlist_id

        title = self._city_playlist_title(city)
        description = f"{city.name} yöresinden üretilen Anadolu türküleri."
        try:
            playlist_id = yt.ensure_playlist(title, description)
        except HttpError as exc:
            if not self._is_youtube_quota_error(exc):
                raise
            logger.warning("Playlist API quota/rate limit reached; creating playlist via YouTube Studio web UI.")
            YouTubeStudioUploader().create_playlist(
                title=title,
                description=description,
                language="Turkish",
            )
            try:
                playlist_id = yt.find_playlist_by_title(title)
            except HttpError as lookup_exc:
                logger.warning(
                    "Playlist was created in Studio, but API lookup failed; upload will select it by title in Studio: %s",
                    lookup_exc,
                )
                playlist_id = None

        if not playlist_id:
            logger.warning("Playlist id is unavailable for '%s'; continuing with Studio playlist title selection.", title)
            return None

        city.playlist_id = playlist_id
        return playlist_id

    @staticmethod
    def _is_youtube_quota_error(exc: HttpError) -> bool:
        status = getattr(getattr(exc, "resp", None), "status", None)
        text = str(exc).lower()
        return status in {403, 429} and (
            "quota" in text
            or "rate_limit" in text
            or "resource has been exhausted" in text
            or "daily limit" in text
        )

    @staticmethod
    def _city_playlist_title(city) -> str:
        return f"{city.name} Türküleri | Anadolu Türküleri Ezgileri"

    @staticmethod
    def _concept_history_hooks(concept: dict, cultural_profile: dict) -> list[str]:
        hooks: list[str] = []
        for key in ("theme", "story", "season", "narrator"):
            value = concept.get(key)
            if value:
                hooks.append(str(value))
        for place in cultural_profile.get("place_names", [])[:3]:
            hooks.append(str(place))
        return hooks

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
