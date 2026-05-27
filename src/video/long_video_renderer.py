"""
LongVideoRenderer — renders the final long-form YouTube video.
Output: 1920×1080 H.264 MP4 with AAC audio.

Cinematic effects (all via FFmpeg, no extra deps):
  - Slow Ken Burns zoom via progressive crop
  - Film grain via noise filter
  - Vignette via vignette filter
  - Subtle cool/blue color grade via colorbalance

Pipeline:
  background.png (looped to audio length) + audio.mp3
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
    CRF = "23"
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
        Render long video with cinematic effects. Returns output_path.
        Raises RuntimeError on FFmpeg failure.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path = output_path.with_name("hook_long.png")
        HookOverlayRenderer().render_long(city_name, title, hook_path)

        W = self.VIDEO_WIDTH
        H = self.VIDEO_HEIGHT
        # Ken Burns: scale to 110% then progressively crop from outer edge toward center
        # Using expr-based crop for smooth drift. Keep computation simple for speed.
        zoom_scale_w = int(W * 1.10)
        zoom_scale_h = int(H * 1.10)
        max_crop_x = zoom_scale_w - W   # = 0.10 * W
        max_crop_y = zoom_scale_h - H

        cinematic_filter = (
            # Scale to 110%
            f"[0:v]scale={zoom_scale_w}:{zoom_scale_h}:force_original_aspect_ratio=increase,"
            f"crop={zoom_scale_w}:{zoom_scale_h},"
            # Slow zoom: crop drifts from (max_x, max_y) toward (0, 0) over the duration
            f"crop=w={W}:h={H}:x='{max_crop_x}*(1-t/120)':y='{max_crop_y}*(1-t/120)',"
            # Film grain — subtle base layer
            "noise=alls=8:allf=t,"
            # Subtle cool color grade (slight blue boost in shadows and highlights)
            "colorbalance=bs=0.04:bm=0.02:bh=0.03,"
            # VHS/tape saturation — slight desaturation + warm shadow crush
            "eq=saturation=0.92:contrast=1.05:brightness=-0.02,"
            # Vignette
            "vignette='PI/4',"
            # Film grain layer 2 — adds subtle temporal shimmer (replaces geq rain)
            "noise=alls=4:allf=t"
            "[bg];"
            "[bg][2:v]overlay=0:0[v]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(background_path),
            "-i", str(audio_path),
            "-loop", "1",
            "-i", str(hook_path),
            "-filter_complex", cinematic_filter,
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

        logger.info("Rendering long video (cinematic): %s", output_path)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg long video render failed:\n{result.stderr[-2000:]}")

        logger.info("Long video ready: %s", output_path)
        return output_path

