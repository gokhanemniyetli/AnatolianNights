"""
AudioDuration helper — gets audio duration in seconds using ffprobe.
Used by SubtitleBuilder and any pipeline step that needs duration.
"""

import logging
from pathlib import Path
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


def trim_audio_to_max_duration(audio_path, max_duration_seconds: float) -> Path:
    """Trim an audio file in place when it exceeds max_duration_seconds."""
    audio_path = Path(audio_path)
    duration = get_audio_duration(audio_path)
    if duration <= max_duration_seconds:
        return audio_path

    tmp_path = audio_path.with_suffix(f".trimmed{audio_path.suffix}")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_path),
        "-t",
        str(max_duration_seconds),
        "-c:a",
        "pcm_s16le",
        str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio trim failed: {result.stderr}")
    tmp_path.replace(audio_path)
    logger.info(
        "Trimmed audio %s from %.1fs to %.1fs",
        audio_path,
        duration,
        max_duration_seconds,
    )
    return audio_path
