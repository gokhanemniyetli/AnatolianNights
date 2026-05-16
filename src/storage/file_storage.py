"""
File system layout for all generated song artifacts.

outputs/{city_slug}/{song_id}/
  concept.json
  lyrics.txt
  suno_prompt.txt
  style_prompt.txt
  quality_report.json
  image_prompt.txt
  background.png
  short_background.png
  thumbnail.png
  audio.mp3
  subtitles.srt
  video.mp4
  short.mp4
  youtube_metadata.json
"""

import json
import shutil
from pathlib import Path

from src.config.settings import settings


class FileStorage:
    def __init__(self):
        self.base = Path(settings.storage.outputs_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def song_dir(self, city_slug: str, song_id: int) -> Path:
        path = self.base / city_slug / str(song_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ── Write helpers ─────────────────────────────────────────────────

    def write_concept(self, city_slug: str, song_id: int, data: dict) -> Path:
        p = self.song_dir(city_slug, song_id) / "concept.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return p

    def write_lyrics(self, city_slug: str, song_id: int, text: str) -> Path:
        p = self.song_dir(city_slug, song_id) / "lyrics.txt"
        p.write_text(text, encoding="utf-8")
        return p

    def write_suno_prompt(self, city_slug: str, song_id: int, suno_lyrics: str, style_prompt: str) -> tuple[Path, Path]:
        d = self.song_dir(city_slug, song_id)
        lyrics_path = d / "suno_prompt.txt"
        style_path = d / "style_prompt.txt"
        lyrics_path.write_text(suno_lyrics, encoding="utf-8")
        style_path.write_text(style_prompt, encoding="utf-8")
        return lyrics_path, style_path

    def write_quality_report(self, city_slug: str, song_id: int, data: dict) -> Path:
        p = self.song_dir(city_slug, song_id) / "quality_report.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return p

    def write_image_prompt(self, city_slug: str, song_id: int, text: str) -> Path:
        p = self.song_dir(city_slug, song_id) / "image_prompt.txt"
        p.write_text(text, encoding="utf-8")
        return p

    def write_youtube_metadata(self, city_slug: str, song_id: int, data: dict) -> Path:
        p = self.song_dir(city_slug, song_id) / "youtube_metadata.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return p

    def write_subtitles(self, city_slug: str, song_id: int, srt_text: str) -> Path:
        p = self.song_dir(city_slug, song_id) / "subtitles.srt"
        p.write_text(srt_text, encoding="utf-8")
        return p

    # ── Import helpers ────────────────────────────────────────────────

    def import_audio(self, city_slug: str, song_id: int, source_path: str | Path) -> Path:
        source = Path(source_path)
        ext = source.suffix.lower() or ".wav"  # preserve .wav or .mp3
        dest = self.song_dir(city_slug, song_id) / f"audio{ext}"
        shutil.copy2(str(source), str(dest))
        return dest

    # ── Path accessors ────────────────────────────────────────────────

    def audio_path(self, city_slug: str, song_id: int) -> Path:
        """Return audio path. Prefer .wav if it exists, else .mp3 (or .wav as default dest)."""
        song_dir = self.song_dir(city_slug, song_id)
        wav = song_dir / "audio.wav"
        mp3 = song_dir / "audio.mp3"
        if wav.exists():
            return wav
        if mp3.exists():
            return mp3
        return wav  # default destination for new downloads

    def background_path(self, city_slug: str, song_id: int) -> Path:
        return self.song_dir(city_slug, song_id) / "background.png"

    def short_background_path(self, city_slug: str, song_id: int) -> Path:
        return self.song_dir(city_slug, song_id) / "short_background.png"

    def thumbnail_path(self, city_slug: str, song_id: int) -> Path:
        return self.song_dir(city_slug, song_id) / "thumbnail.png"

    def video_path(self, city_slug: str, song_id: int) -> Path:
        return self.song_dir(city_slug, song_id) / "video.mp4"

    def short_path(self, city_slug: str, song_id: int) -> Path:
        return self.song_dir(city_slug, song_id) / "short.mp4"

    def subtitles_path(self, city_slug: str, song_id: int) -> Path:
        return self.song_dir(city_slug, song_id) / "subtitles.srt"

    def rel(self, path: Path) -> str:
        """Return path relative to outputs_dir for storage in the DB."""
        try:
            return str(path.relative_to(self.base))
        except ValueError:
            return str(path)


file_storage = FileStorage()
