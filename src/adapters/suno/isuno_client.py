"""
ISunoClient — Protocol (interface) for all Suno client implementations.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ISunoClient(Protocol):
    def generate(self, style_prompt: str, suno_lyrics: str, song_id: str) -> str:
        """
        Submit a generation request to Suno.
        Returns a task_id or job_id string.
        """
        ...

    def get_status(self, task_id: str) -> dict:
        """
        Poll the status of a generation task.
        Returns: {"status": "pending"|"complete"|"failed", "audio_url": str|None}
        """
        ...

    def download_audio(self, task_id: str, destination: Path) -> Path:
        """
        Download the generated audio to destination.
        Returns the path where the file was saved.
        """
        ...
