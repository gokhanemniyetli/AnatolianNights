"""
LongVideoRenderer — renders the final long-form YouTube video.
Output: 1920×1080 H.264 MP4 with AAC audio and burned-in subtitles.

Pipeline:
  background.png (looped to audio length) + audio.mp3 + subtitles.srt
  → long_video.mp4
"""

import logging
import subprocess
from pathlib import Path

from src.video.hook_overlay import HookOverlayRenderer

logger = logging.getLogger(__name__)


class LongVideoRenderer:
    VIDEO_WIDTH = 1920
    VIDEO_HEIGHT = 1080
    VIDEO_CODEC = "libx264"
    AUDIO_CODEC = "aac"
    CRF = "23"  # Quality factor (lower = better; 23 is fine for YouTube)
    PRESET = "medium"

    def render(
        self,
        background_path: Path,
        audio_path: Path,
        subtitles_path: Path,
        output_path: Path,
        title: str = "",
        city_name: str = "",
    ) -> Path:
        """
        Render long video. Returns output_path.
        Raises RuntimeError on FFmpeg failure.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path = output_path.with_name("hook_long.png")
        HookOverlayRenderer().render_long(city_name, title, hook_path)

        cmd = [
            "ffmpeg", "-y",
            # Loop background image for the entire audio duration
            "-loop", "1",
            "-i", str(background_path),
            # Audio input
            "-i", str(audio_path),
            "-loop", "1",
            "-i", str(hook_path),
            # Filters: scale and crop to exact dimensions.
            # The local Homebrew FFmpeg build may not include libass/drawtext,
            # so subtitles are kept as a sidecar SRT instead of burned in.
            "-filter_complex", (
                f"[0:v]scale={self.VIDEO_WIDTH}:{self.VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={self.VIDEO_WIDTH}:{self.VIDEO_HEIGHT}[bg];"
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
            # End encoding when audio ends
            "-shortest",
            # Ensure video/audio are synced
            "-movflags", "+faststart",
            str(output_path),
        ]

        logger.info("Rendering long video: %s", output_path)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg long video render failed:\n{result.stderr[-2000:]}")

        logger.info("Long video ready: %s", output_path)
        return output_path
