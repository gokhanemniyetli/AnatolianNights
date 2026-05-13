"""
AudioDuration helper — gets audio duration in seconds using ffprobe.
Used by SubtitleBuilder and any pipeline step that needs duration.
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


def get_audio_duration(audio_path) -> float:
    """Return duration of audio file in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())
