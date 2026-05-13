"""
SubtitleBuilder — generates SRT subtitle file from lyrics and audio duration.
Distributes lines evenly across the audio duration.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp: HH:MM:SS,mmm"""
    ms = int((seconds % 1) * 1000)
    s = int(seconds) % 60
    m = int(seconds) // 60 % 60
    h = int(seconds) // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _extract_lyric_lines(lyrics: str) -> list[str]:
    """Strip structural tags, return only content lines."""
    lines = []
    for raw_line in lyrics.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if re.match(r"^\[.*?\]$", stripped):
            continue  # skip [Verse], [Chorus], etc.
        lines.append(stripped)
    return lines


class SubtitleBuilder:
    def build(self, lyrics: str, audio_duration_seconds: float, output_path: Path) -> Path:
        """
        Build an SRT file from lyrics and audio duration.
        Lines are distributed evenly. Returns output_path.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = _extract_lyric_lines(lyrics)
        if not lines:
            raise ValueError("No lyric lines found to build subtitles")

        # Leave 1s padding at start and end
        usable = max(audio_duration_seconds - 2.0, len(lines) * 2.0)
        line_duration = usable / len(lines)

        srt_blocks = []
        for idx, line in enumerate(lines):
            start = 1.0 + idx * line_duration
            end = start + line_duration - 0.2  # 200ms gap between lines
            block = (
                f"{idx + 1}\n"
                f"{_format_srt_time(start)} --> {_format_srt_time(end)}\n"
                f"{line}\n"
            )
            srt_blocks.append(block)

        output_path.write_text("\n".join(srt_blocks), encoding="utf-8")
        logger.info("Subtitles written to %s (%d lines)", output_path, len(lines))
        return output_path
