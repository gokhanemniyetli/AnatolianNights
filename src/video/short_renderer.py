"""
ShortRenderer — extracts the first N seconds of the song as a YouTube Short.
Output: 1080×1920 (portrait) MP4, hook_duration seconds.

Pipeline:
  background.png (cropped to 9:16) + audio.mp3 (first N seconds) + subtitles.srt
  → short_video.mp4
"""

import logging
import subprocess
from pathlib import Path

from src.config.settings import settings
from src.video.hook_overlay import HookOverlayRenderer

logger = logging.getLogger(__name__)


class ShortRenderer:
    SHORT_WIDTH = 1080
    SHORT_HEIGHT = 1920
    MAX_DURATION_SECONDS = 12
    VIDEO_CODEC = "libx264"
    AUDIO_CODEC = "aac"
    CRF = "23"
    PRESET = "medium"

    def render(
        self,
        background_path: Path,
        audio_path: Path,
        subtitles_path: Path,
        output_path: Path,
        hook_duration: int | None = None,
        title: str = "",
        city_name: str = "",
    ) -> Path:
        """
        Render Short video (portrait, first hook_duration seconds).
        Returns output_path.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path = output_path.with_name("hook_short.png")
        HookOverlayRenderer().render_short(city_name, title, hook_path)

        requested_duration = hook_duration or settings.video.short_hook_duration
        duration = min(requested_duration, self.MAX_DURATION_SECONDS)
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(background_path),
            "-i", str(audio_path),
            "-loop", "1",
            "-i", str(hook_path),
            "-t", str(duration),
            "-filter_complex", (
                # Preserve image proportions for Shorts. If the input is already
                # 9:16 this is a clean resize; otherwise it crops, never squeezes.
                f"[0:v]scale={self.SHORT_WIDTH}:{self.SHORT_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={self.SHORT_WIDTH}:{self.SHORT_HEIGHT}[bg];"
                f"[bg][2:v]overlay=0:0[v]"
            ),
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", self.VIDEO_CODEC,
            "-preset", self.PRESET,
            "-crf", self.CRF,
            "-c:a", self.AUDIO_CODEC,
            "-b:a", "192k",
            "-ar", "44100",
            "-shortest",
            "-movflags", "+faststart",
            str(output_path),
        ]

        logger.info("Rendering Short (%ds): %s", duration, output_path)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg Short render failed:\n{result.stderr[-2000:]}")

        logger.info("Short ready: %s", output_path)
        return output_path
