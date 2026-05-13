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

logger = logging.getLogger(__name__)


class ShortRenderer:
    SHORT_WIDTH = 1080
    SHORT_HEIGHT = 1920
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
    ) -> Path:
        """
        Render Short video (portrait, first hook_duration seconds).
        Returns output_path.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        duration = hook_duration or settings.video.short_hook_duration
        srt_escaped = str(subtitles_path).replace("\\", "/").replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(background_path),
            "-i", str(audio_path),
            "-t", str(duration),
            "-vf", (
                # Crop center square from 1920x1080, then scale to 1080x1920
                f"crop=1080:1080:(iw-1080)/2:(ih-1080)/2,"
                f"scale={self.SHORT_WIDTH}:{self.SHORT_HEIGHT}:force_original_aspect_ratio=disable,"
                f"pad={self.SHORT_WIDTH}:{self.SHORT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
                f"subtitles='{srt_escaped}':force_style='FontSize=26,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Shadow=1,Alignment=2'"
            ),
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
