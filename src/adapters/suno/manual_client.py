"""
ManualSunoClient — Phase 1 implementation.
Writes the Suno prompt to a file and waits for the operator to
import the downloaded audio via `python -m cli import-audio`.

No browser automation, no API calls. Pure manual workflow.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path("outputs") / "_suno_prompts"


class ManualSunoClient:
    """
    Implements the ISunoClient Protocol via manual workflow:
    1. generate() writes a single simple-mode prompt to a text file
    2. Operator generates audio on suno.com manually
    3. Operator runs `import-audio` CLI to copy the file into the pipeline
    4. get_status() just returns 'pending' (no real check)
    5. download_audio() is a no-op (operator already placed the file)
    """

    def generate(self, style_prompt: str, suno_lyrics: str, song_id: str) -> str:
        """
        Write prompt files for the operator. Returns song_id as the task_id.
        """
        _PROMPT_DIR.mkdir(parents=True, exist_ok=True)
        prompt_file = _PROMPT_DIR / f"{song_id}.txt"

        content = (
            f"=== SUNO SIMPLE PROMPT ===\n"
            f"{style_prompt}\n\n"
            f"=== INSTRUCTIONS ===\n"
            f"1. Go to suno.com and create a new song.\n"
            f"2. Use Simple mode.\n"
            f"3. Paste the SIMPLE PROMPT into the main prompt box.\n"
            f"4. Generate the song and download the best version as MP3.\n"
            f"5. Run: python -m cli import-audio --song-id {song_id} --file /path/to/audio.mp3\n"
        )

        prompt_file.write_text(content, encoding="utf-8")
        logger.info("Suno prompt written to %s", prompt_file)
        return song_id  # task_id == song_id in manual mode

    def get_status(self, task_id: str) -> dict:
        """Always returns 'pending' — operator must use import-audio CLI."""
        return {"status": "pending", "audio_url": None}

    def download_audio(self, task_id: str, destination: Path) -> Path:
        """No-op in manual mode. Audio is placed by the operator via import-audio."""
        if destination.exists():
            return destination
        raise FileNotFoundError(
            f"Audio not yet imported for song {task_id}. "
            f"Run: python -m cli import-audio --song-id {task_id} --file /path/to/audio.mp3"
        )
