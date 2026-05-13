"""
ThumbnailRenderer — creates a YouTube thumbnail (1280×720 PNG)
using FFmpeg: background image + city/title text overlay.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class ThumbnailRenderer:
    WIDTH = 1280
    HEIGHT = 720

    def render(
        self,
        background_path: Path,
        title: str,
        city_name: str,
        output_path: Path,
    ) -> Path:
        """
        Render thumbnail PNG using FFmpeg drawtext filter.
        Returns output_path.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Escape special characters for FFmpeg drawtext
        def esc(text: str) -> str:
            return text.replace("'", "\\'").replace(":", "\\:").replace("\\", "\\\\")

        title_esc = esc(title[:50])  # Truncate long titles
        city_esc = esc(city_name)

        cmd = [
            "ffmpeg", "-y",
            "-i", str(background_path),
            "-vf", (
                f"scale={self.WIDTH}:{self.HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={self.WIDTH}:{self.HEIGHT},"
                # Semi-transparent bottom bar
                f"drawbox=x=0:y={self.HEIGHT - 120}:w={self.WIDTH}:h=120:color=black@0.55:t=fill,"
                # City name
                f"drawtext=text='{city_esc}':fontsize=32:fontcolor=white@0.9"
                f":x=40:y={self.HEIGHT - 100}:font=Sans:style=Bold,"
                # Song title
                f"drawtext=text='{title_esc}':fontsize=44:fontcolor=white"
                f":x=40:y={self.HEIGHT - 60}:font=Sans:style=Bold"
            ),
            "-vframes", "1",
            "-q:v", "2",
            str(output_path),
        ]

        logger.info("Rendering thumbnail: %s", output_path)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg thumbnail failed:\n{result.stderr}")

        return output_path
