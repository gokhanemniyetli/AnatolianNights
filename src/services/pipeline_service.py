"""
PipelineService — drives a single song through the full pipeline
based on its current status. Each stage method is idempotent.
"""

import logging
import os
from pathlib import Path

from googleapiclient.errors import HttpError

from src.adapters.suno import get_suno_client
from src.adapters.youtube import YouTubeClient, YouTubeStudioUploader
from src.agents import (
    ConceptAgent,
    ImagePromptAgent,
    LyricAgent,
    MetadataAgent,
    SunoPromptAgent,
)
from src.config.settings import settings
from src.image import ImageGenerator
from src.services.city_service import CityService
from src.services.concept_playlist_service import ConceptPlaylistService
from src.services.history_service import HistoryService
from src.services.song_service import SongService
from src.services.title_bank_service import TitleBankService
from src.storage.database import get_session
from src.storage.file_storage import file_storage
from src.storage.models import ConceptPlaylist, Song, SongStatus
from src.video import (
    LongVideoRenderer,
    ShortRenderer,
    SubtitleBuilder,
    ThumbnailRenderer,
    get_audio_duration,
    trim_audio_to_max_duration,
)

logger = logging.getLogger(__name__)


class PipelineService:
    """Drives one song forward one stage at a time."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._concept_agent = ConceptAgent()
        self._lyric_agent = LyricAgent()
        self._suno_prompt_agent = SunoPromptAgent()
        self._image_prompt_agent = ImagePromptAgent()
        self._metadata_agent = MetadataAgent()
        self._image_generator = ImageGenerator()
        self._subtitle_builder = SubtitleBuilder()
        self._thumbnail_renderer = ThumbnailRenderer()
        self._long_renderer = LongVideoRenderer()
        self._short_renderer = ShortRenderer()

    # ── Public entry point ────────────────────────────────────────────

    def run_song_and_twin(self, song_id: str) -> Song:
        """Run a song and, for Turkish songs, run its English twin if one exists."""
        song = self.run_song(song_id)
        twin_id = self._english_twin_id(song_id)
        if twin_id:
            logger.info("[%s] Running English twin song %s", song_id, twin_id)
            self.run_song(str(twin_id))
        return song

    def run_song(self, song_id: str) -> Song:
        """Advance song one or more stages until it blocks (needs audio or upload)."""
        with get_session() as session:
            song_svc = SongService(session)
            city_svc = CityService(session)
            concept_playlist_svc = ConceptPlaylistService(session)
            history_svc = HistoryService(session)

            song = song_svc.get_by_id(song_id)
            if not song:
                raise ValueError(f"Song {song_id} not found")

            city = city_svc.get_by_id(song.city_id)
            cultural_profile = city_svc.load_cultural_profile(city.slug)
            concept_playlist = song.concept_playlist
            concept_profile = (
                concept_playlist_svc.build_profile(concept_playlist)
                if concept_playlist
                else None
            )

            # Run stages in sequence until we hit a blocking point
            while True:
                status = song.status
                if status == SongStatus.PENDING:
                    song = self._stage_concept(
                        song,
                        song_svc,
                        history_svc,
                        city,
                        cultural_profile,
                        concept_playlist,
                        concept_profile,
                    )
                    session.commit()
                elif status == SongStatus.CONCEPT_READY:
                    song = self._stage_suno_prompt(song, song_svc, cultural_profile, concept_profile)
                    session.commit()
                elif status == SongStatus.QUALITY_REJECTED:
                    if (song.lyric_attempt or 0) >= settings.pipeline.max_lyric_retries:
                        song_svc.permanently_reject(song, "Max lyric retries reached")
                        session.commit()
                        break
                    song_svc.reset_for_retry(song)
                    song = self._stage_suno_prompt(song, song_svc, cultural_profile, concept_profile)
                    session.commit()
                elif status == SongStatus.LYRICS_READY:
                    song = self._stage_suno_prompt(song, song_svc, cultural_profile, concept_profile)
                    session.commit()
                elif status == SongStatus.QUALITY_APPROVED:
                    # QUALITY_APPROVED is set when lyrics pass; advance to SUNO_READY
                    song = self._stage_suno_prompt(song, song_svc, cultural_profile, concept_profile)
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
                    song = self._stage_image(song, song_svc, city, cultural_profile, concept_playlist, concept_profile)
                    session.commit()
                elif status == SongStatus.IMAGE_READY:
                    song = self._stage_video(song, song_svc)
                    session.commit()
                elif status == SongStatus.VIDEO_READY:
                    if not self.dry_run:
                        song = self._stage_upload(song, song_svc, session, city, concept_playlist)
                        session.commit()
                    else:
                        logger.info("[DRY-RUN] Skipping upload for song %s", song.id)
                    break
                else:
                    # UPLOADED, PERMANENTLY_REJECTED — done
                    break

            return song

    @staticmethod
    def _english_twin_id(song_id: str) -> int | None:
        with get_session() as session:
            song = session.get(Song, song_id)
            if not song:
                return None
            language = (getattr(song, "language", None) or "tr").lower()
            if language != "tr" or not song.twin_song_id:
                return None
            return int(song.twin_song_id)

    # ── Stages ────────────────────────────────────────────────────────

    def _stage_concept(
        self,
        song,
        song_svc,
        history_svc,
        city,
        cultural_profile,
        concept_playlist,
        concept_profile,
    ):
        logger.info("[%s] Stage: concept", song.id)
        # Always pick a title from the bank first
        title_bank_svc = TitleBankService(song_svc.session)
        forced_title = title_bank_svc.get_next_title()
        if not forced_title:
            logger.warning("Title bank exhausted — concept agent will generate a title freely.")

        if concept_playlist and concept_profile:
            history_dict = history_svc.get_concept_history_dict(concept_playlist.id)
            concept = self._concept_agent.generate_for_playlist(
                concept_playlist.title,
                concept_profile,
                history_dict,
                forced_title=forced_title,
            )
        else:
            history_dict = history_svc.get_history_dict(city.id)
            concept = self._concept_agent.generate(
                city.name, cultural_profile, history_dict, forced_title=forced_title
            )
        song.set_concept(concept)
        song.title = concept.get("title", "")
        self._force_lyrical_concept(song)
        concept = song.get_concept()
        file_storage.write_concept(self._get_context_slug(song), song.id, concept)
        if concept_playlist:
            history_svc.record_concept_song(
                concept_playlist.id,
                concept,
                self._concept_history_hooks(concept, concept_profile or {}),
            )
        else:
            history_svc.record_song(city.id, concept, self._concept_history_hooks(concept, cultural_profile))
        return song_svc.advance(song)  # → CONCEPT_READY

    def _stage_suno_prompt(self, song, song_svc, cultural_profile, concept_profile=None):
        logger.info("[%s] Stage: suno_prompt", song.id)
        language = (getattr(song, "language", None) or "tr")
        concept = song.get_concept()
        if language == "en":
            self._ensure_english_title(song)
        concept["track_type"] = "lyrical"
        if language == "en":
            concept["vocal"] = "atmospheric English vocals, soft modern delivery"
        else:
            concept["vocal"] = "atmospheric Turkish vocals, soft modern delivery"
        song.set_concept(concept)

        if concept_profile:
            result = self._suno_prompt_agent.generate_for_playlist(concept, concept_profile)
        else:
            result = self._suno_prompt_agent.generate(concept, cultural_profile)
        simple_prompt = (
            result.get("simple_prompt")
            or result.get("style_prompt")
            or ""
        ).strip()

        if not simple_prompt:
            raise ValueError("Suno simple prompt boş geldi.")
        simple_prompt = self._force_simple_vocal_prompt(simple_prompt, concept, language=language)

        # Suno generates its own lyrics in Simple mode — no pre-generated lyrics needed
        song.suno_style_prompt = simple_prompt
        song.suno_full_prompt = simple_prompt
        song.suno_lyrics = ""
        song.lyrics = None
        song.quality_report = None
        song.quality_score = None

        logger.info("[%s] Suno Simple mode ile gönderiliyor (lang=%s). Prompt: %s", song.id, language, simple_prompt[:120])

        # Submit to Suno in Simple mode (no lyrics — Suno generates them)
        suno_client = get_suno_client()
        task_id = suno_client.generate(song.suno_style_prompt, "", song.id)
        song.suno_task_id = str(task_id) if task_id else None

        file_storage.write_suno_prompt(city_slug=self._get_context_slug(song), song_id=song.id,
                                       style_prompt=song.suno_style_prompt,
                                       suno_lyrics=song.suno_lyrics)
        song.status = SongStatus.SUNO_READY
        song_svc.session.flush()

        # Create English twin if this is a Turkish song and no twin exists yet
        if language == "tr" and not song.twin_song_id:
            twin = Song(
                city_id=song.city_id,
                concept_playlist_id=song.concept_playlist_id,
                title=song.title,
                theme=song.theme,
                mood=song.mood,
                tempo=song.tempo,
                vocal_type=song.vocal_type,
                style_variant=song.style_variant,
                concept=song.concept,
                status=SongStatus.CONCEPT_READY,
                language="en",
                lyric_attempt=0,
            )
            song_svc.session.add(twin)
            song_svc.session.flush()
            song.twin_song_id = twin.id
            song_svc.session.flush()
            logger.info("[%s] Created English twin song %s", song.id, twin.id)

        return song

    def _stage_suno_wait(self, song, song_svc, city):
        """Browser mode: poll Suno until clip is ready, download WAV, advance to AUDIO_IMPORTED."""
        logger.info("[%s] Stage: suno_wait (clip_id=%s)", song.id, song.suno_task_id)

        # If task_id is a manual placeholder (equals the DB song ID), re-submit via browser
        if not song.suno_task_id or song.suno_task_id == str(song.id):
            logger.info(
                "[%s] Manual placeholder task_id detected — re-submitting suno prompt via browser.", song.id
            )
            if not song.suno_style_prompt:
                raise ValueError(f"Song {song.id} has no suno_style_prompt to re-submit.")
            suno_client = get_suno_client()
            task_id = suno_client.generate(song.suno_style_prompt, "", song.id)
            song.suno_task_id = str(task_id)
            song_svc.session.flush()
            logger.info("[%s] New Suno clip_id: %s", song.id, song.suno_task_id)

        if not song.suno_task_id:
            raise ValueError(f"Song {song.id} is SUNO_READY but has no suno_task_id.")

        city_slug = self._get_context_slug(song)
        suno_client = get_suno_client()
        audio_dest = file_storage.audio_path(city_slug, song.id)  # returns .wav path
        downloaded = suno_client.download_audio(song.suno_task_id, audio_dest)
        downloaded = trim_audio_to_max_duration(downloaded, 300)
        suno_status = suno_client.get_status(song.suno_task_id)

        suno_title = (suno_status.get("suno_title") or "").strip()
        if suno_title and not (song.title or "").strip():
            song.title = suno_title

        suno_lyrics = (suno_status.get("suno_lyrics") or "").strip()
        if suno_lyrics:
            song.suno_lyrics = suno_lyrics
            song.lyrics = suno_lyrics
            file_storage.write_lyrics(city_slug, song.id, suno_lyrics)
        elif (song.get_concept() or {}).get("track_type") == "lyrical":
            raise RuntimeError(
                f"Song {song.id} was requested as lyrical, but Suno returned no lyrics. "
                "Stopping before video/upload so the prompt can be retried."
            )

        song.audio_path = str(file_storage.rel(downloaded))
        song.status = SongStatus.AUDIO_IMPORTED
        song_svc.session.flush()
        logger.info("[%s] Audio indirme tamam: %s", song.id, downloaded)
        return song

    def _stage_image(self, song, song_svc, city, cultural_profile, concept_playlist=None, concept_profile=None):
        logger.info("[%s] Stage: image", song.id)
        concept = song.get_concept()
        language = (getattr(song, "language", None) or "tr")
        if concept_playlist and concept_profile:
            ip_result = self._image_prompt_agent.generate_for_playlist(
                concept,
                concept_playlist.title,
                concept_profile,
                language=language,
            )
        else:
            ip_result = self._image_prompt_agent.generate(concept, city.name, cultural_profile, language=language)
        image_prompt = ip_result.get("image_prompt", "")
        negative_prompt = ip_result.get("negative_prompt", "text, watermark, faces")

        song.image_prompt = image_prompt
        context_slug = self._get_context_slug(song)
        file_storage.write_image_prompt(context_slug, song.id, image_prompt)

        bg_path = file_storage.background_path(context_slug, song.id)
        self._image_generator.generate(image_prompt, negative_prompt, bg_path)
        song.background_image_path = str(file_storage.rel(bg_path))

        short_prompt = (
            f"{image_prompt} Vertical 9:16 composition for a YouTube Short, "
            "strong central landscape subject, no stretching, no people, no instruments."
        )
        short_bg_path = file_storage.short_background_path(context_slug, song.id)
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
        city_slug = self._get_context_slug(song)
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
        self._thumbnail_renderer.render(bg_path, song.title or "", self._get_context_name(song), thumb_path)
        song.thumbnail_path = str(file_storage.rel(thumb_path))

        # Long video
        self._long_renderer.render(
            bg_path,
            audio_path,
            srt_path,
            long_path,
            title=song.title or "",
            city_name=self._get_context_name(song),
        )
        song.long_video_path = str(file_storage.rel(long_path))

        # Short
        self._short_renderer.render(
            short_bg_path,
            audio_path,
            srt_path,
            short_path,
            title=song.title or "",
            city_name=self._get_context_name(song),
        )
        song.short_video_path = str(file_storage.rel(short_path))

        return song_svc.advance(song)  # → VIDEO_READY

    def _fallback_subtitle_text(self, song: Song) -> str:
        concept = song.get_concept() or {}
        parts = [
            song.title or "Anadolu Türküleri Ezgileri",
            self._get_context_name(song),
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

    def _stage_upload(self, song, song_svc, session, city, concept_playlist=None):
        logger.info("[%s] Stage: upload", song.id)

        yt = YouTubeClient(
            client_secrets_file=settings.youtube.client_secrets_file,
            dry_run=self.dry_run,
        )

        meta_agent = MetadataAgent()
        concept = song.get_concept()
        language = (getattr(song, "language", None) or "tr")
        if concept_playlist:
            meta = meta_agent.generate_for_playlist(
                song.title or "",
                concept_playlist.title,
                concept,
                song.lyrics,
                language=language,
            )
        else:
            meta = meta_agent.generate(song.title or "", city.name, concept, song.lyrics, language=language)
        song.set_youtube_metadata(meta)
        file_storage.write_youtube_metadata(self._get_context_slug(song), song.id, meta)

        long_path = Path("outputs") / song.long_video_path if song.long_video_path else None
        short_path = Path("outputs") / song.short_video_path if song.short_video_path else None
        thumb_path = Path("outputs") / song.thumbnail_path if song.thumbnail_path else None
        tags = self._metadata_tags(meta)
        use_api_first = os.getenv("YOUTUBE_UPLOAD_USE_API_FIRST", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

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
            playlist_id = (
                self._ensure_concept_playlist(yt, concept_playlist)
                if concept_playlist
                else self._ensure_city_playlist(yt, city)
            )
            playlist_title = (
                self._concept_playlist_title(concept_playlist)
                if concept_playlist
                else self._city_playlist_title(city)
            )
            studio = YouTubeStudioUploader()
            playlist_inserted_by_api_upload = False
            if use_api_first:
                vid_id = yt.upload_video(
                    video_path=long_path,
                    title=meta.get("title", song.title or ""),
                    description=meta.get("description", ""),
                    tags=tags,
                    thumbnail_path=thumb_path if thumb_path and thumb_path.exists() else None,
                    playlist_id=playlist_id,
                )
                playlist_inserted_by_api_upload = bool(playlist_id)
            else:
                try:
                    vid_id = studio.upload_video(
                        video_path=long_path,
                        title=meta.get("title", song.title or ""),
                        description=meta.get("description", ""),
                        thumbnail_path=thumb_path,
                        playlist_title=playlist_title,
                    )
                except Exception as exc:
                    logger.warning(
                        "Studio long upload failed for song %s; falling back to API upload: %s",
                        song.id,
                        exc,
                    )
                    vid_id = yt.upload_video(
                        video_path=long_path,
                        title=meta.get("title", song.title or ""),
                        description=meta.get("description", ""),
                        tags=tags,
                        thumbnail_path=thumb_path if thumb_path and thumb_path.exists() else None,
                        playlist_id=playlist_id,
                    )
                    playlist_inserted_by_api_upload = bool(playlist_id)
            song.youtube_long_video_id = vid_id
            self._verify_uploaded_channel(yt, vid_id)
            self._publish_after_studio_upload(yt, vid_id)
            song_svc.session.flush()
            session.commit()
            if playlist_id and not playlist_inserted_by_api_upload:
                try:
                    yt.add_to_playlist(vid_id, playlist_id)
                except HttpError as exc:
                    logger.warning("Playlist API insert failed after Studio upload; playlist UI selection was already attempted: %s", exc)
            if use_api_first:
                logger.info("API-first mode: skipping Studio end screen step for %s", vid_id)
            else:
                try:
                    studio.add_end_screen(vid_id)
                except Exception as exc:
                    logger.warning("End screen step skipped for %s: %s", vid_id, exc)

        # Upload Short
        if short_path and short_path.exists() and not song.youtube_short_video_id:
            studio = YouTubeStudioUploader()
            if use_api_first:
                short_id = yt.upload_short(
                    video_path=short_path,
                    title=meta.get("short_title", meta.get("title", "")),
                    description=meta.get("short_description", ""),
                    tags=tags,
                    thumbnail_path=None,
                    playlist_id=None,
                )
            else:
                try:
                    short_id = studio.upload_video(
                        video_path=short_path,
                        title=meta.get("short_title", meta.get("title", "")),
                        description=meta.get("short_description", ""),
                    )
                except Exception as exc:
                    logger.warning(
                        "Studio short upload failed for song %s; falling back to API upload: %s",
                        song.id,
                        exc,
                    )
                    short_id = yt.upload_short(
                        video_path=short_path,
                        title=meta.get("short_title", meta.get("title", "")),
                        description=meta.get("short_description", ""),
                        tags=tags,
                        thumbnail_path=None,
                        playlist_id=None,
                    )
            song.youtube_short_video_id = short_id
            self._verify_uploaded_channel(yt, short_id)
            self._publish_after_studio_upload(yt, short_id)
            song_svc.session.flush()
            session.commit()
            if song.youtube_long_video_id and not use_api_first:
                try:
                    studio.set_related_video(
                        short_video_id=short_id,
                        related_video_id=song.youtube_long_video_id,
                        related_video_title=meta.get("title", song.title or ""),
                    )
                except Exception as exc:
                    logger.warning("Short related video could not be set: %s", exc)
            elif song.youtube_long_video_id:
                logger.info("API-first mode: skipping Studio related video step for %s", short_id)

        return song_svc.advance(song)  # → UPLOADED

    @staticmethod
    def _metadata_tags(meta: dict) -> list[str]:
        raw_tags = meta.get("tags", []) if isinstance(meta, dict) else []
        if isinstance(raw_tags, list):
            tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()]
            return tags[:500]
        if isinstance(raw_tags, str) and raw_tags.strip():
            return [raw_tags.strip()]
        return []

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _force_simple_vocal_prompt(prompt: str, concept: dict, language: str = "tr") -> str:
        """Keep Suno in Simple mode but make the vocal/lyrics request unambiguous.

        NOTE: "Anatolian ambient" / "lo-fi ambient" were deliberately removed here because
        Suno treats "ambient" as a near-synonym for instrumental, overriding make_instrumental=false.
        Genre tags must be vocal-forward to guarantee lyrics generation.
        """
        topic = str(concept.get("story") or concept.get("theme") or "").strip()
        mood = str(concept.get("mood") or "").strip()
        visual = str(concept.get("visual") or "").strip()
        instruments = ", ".join(str(item) for item in (concept.get("instruments") or [])[:4])
        ambience = ", ".join(str(item) for item in (concept.get("ambience") or [])[:4])
        if language == "en":
            return (
                "English vocal song, clear lead singer, sung English lyrics, singer-songwriter, "
                "lead vocals throughout, memorable chorus. "
                "Style: cinematic Turkish night song, acoustic Anatolian texture, 65-75 BPM, soft modern vocal delivery, "
                f"{instruments}, warm tape saturation, vinyl crackle, reverb. "
                f"Song topic: {topic}. Mood: {mood}. Visual imagery: {visual}. Ambience: {ambience}. "
                "The song should contain natural sung lyrics from beginning to end."
            )[:1800]
        return (
            "Turkish vocal song, clear lead singer, sung Turkish lyrics, singer-songwriter, "
            "lead vocals throughout, memorable chorus. "
            "Style: cinematic Istanbul night song, acoustic Anatolian texture, 65-75 BPM, soft modern vocal delivery, "
            f"{instruments}, warm tape saturation, vinyl crackle, reverb. "
            f"Song topic: {topic}. Mood: {mood}. Visual imagery: {visual}. Ambience: {ambience}. "
            "The song should contain natural sung Turkish lyrics from beginning to end."
        )[:1800]

    @staticmethod
    def _force_lyrical_concept(song: Song) -> None:
        concept = song.get_concept()
        concept["track_type"] = "lyrical"
        concept["vocal"] = "atmospheric Turkish vocals, soft modern delivery"
        song.set_concept(concept)

    @staticmethod
    def _publish_after_studio_upload(yt: YouTubeClient, video_id: str) -> None:
        try:
            yt.publish_video(video_id)
        except HttpError as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            text = str(exc).lower()
            if status == 403 and "forbidden" in text:
                logger.warning(
                    "YouTube API publish returned 403 for %s after Studio upload; "
                    "continuing because Studio already selected Public and clicked Publish.",
                    video_id,
                )
                return
            raise

    @staticmethod
    def _verify_uploaded_channel(yt: YouTubeClient, video_id: str) -> None:
        expected_channel_id = (settings.youtube.channel_id or "").strip()
        if not expected_channel_id:
            return
        actual_channel_id = yt.get_video_channel_id(video_id)
        if actual_channel_id and actual_channel_id != expected_channel_id:
            raise PermissionError(
                f"YouTube Studio uploaded video {video_id} to channel {actual_channel_id}, "
                f"but configured channel is {expected_channel_id}. "
                "Stop using this browser profile until it is switched to the correct channel."
            )

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
            logger.warning(
                "Playlist API quota/rate limit reached; skipping playlist creation for now and continuing upload without playlist."
            )
            playlist_id = None

        if not playlist_id:
            logger.warning("Playlist id is unavailable for '%s'; continuing with Studio playlist title selection.", title)
            return None

        city.playlist_id = playlist_id
        return playlist_id

    def _ensure_concept_playlist(self, yt: YouTubeClient, concept_playlist: ConceptPlaylist) -> str | None:
        if concept_playlist.playlist_id:
            return concept_playlist.playlist_id

        title = self._concept_playlist_title(concept_playlist)
        description = f"{concept_playlist.title} konseptinde üretilen Anadolu türküleri."
        try:
            playlist_id = yt.ensure_playlist(title, description)
        except HttpError as exc:
            if not self._is_youtube_quota_error(exc):
                raise
            logger.warning(
                "Playlist API quota/rate limit reached; skipping concept playlist creation for now and continuing upload without playlist."
            )
            playlist_id = None

        if not playlist_id:
            logger.warning("Playlist id is unavailable for '%s'; continuing with Studio playlist title selection.", title)
            return None

        concept_playlist.playlist_id = playlist_id
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
    def _concept_playlist_title(concept_playlist: ConceptPlaylist) -> str:
        return f"{concept_playlist.title} | Anadolu Türküleri Ezgileri"

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

    def _get_context_slug(self, song: Song) -> str:
        with get_session() as s:
            from src.storage.models import City, ConceptPlaylist
            if song.concept_playlist_id:
                concept_playlist = s.get(ConceptPlaylist, song.concept_playlist_id)
                if concept_playlist:
                    return concept_playlist.slug
            city = s.get(City, song.city_id)
            return city.slug if city else "unknown"

    def _get_context_name(self, song: Song) -> str:
        with get_session() as s:
            from src.storage.models import City, ConceptPlaylist
            if song.concept_playlist_id:
                concept_playlist = s.get(ConceptPlaylist, song.concept_playlist_id)
                if concept_playlist:
                    return concept_playlist.title
            city = s.get(City, song.city_id)
            return city.name if city else ""

    def _ensure_english_title(self, song: Song) -> None:
        current = (song.title or "").strip()
        if not current:
            return
        concept = song.get_concept() or {}
        playlist_title = self._get_context_name(song) or "Anatolian Nights"
        preview = self._metadata_agent.generate_for_playlist(
            song_title=current,
            playlist_title=playlist_title,
            concept=concept,
            lyrics=song.lyrics or "",
            language="en",
        )
        candidate = (preview.get("title") or "").strip()
        if not candidate:
            return
        translated = candidate.split("|", 1)[0].strip()
        if translated:
            song.title = translated
