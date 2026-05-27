"""
LyricAgent — writes Turkish folk song lyrics based on a song concept.
"""

import json
from pathlib import Path

from src.agents.base_agent import BaseAgent
from src.config.models_config import get_model

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "lyrics.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


class LyricAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            task="lyric_writer",
            model=get_model("lyric_writer"),
            system_prompt=_SYSTEM_PROMPT,
        )

    def generate(self, concept: dict, city_name: str, cultural_profile: dict, language: str = "tr") -> dict:
        """
        Returns dict with keys: lyrics, first_line, chorus_line, keywords
        For instrumental tracks, returns empty lyrics.
        """
        track_type = concept.get("track_type", "instrumental")

        # Instrumental tracks need no lyrics
        if track_type == "instrumental":
            return {
                "lyrics": "",
                "first_line": "",
                "chorus_line": "",
                "keywords": concept.get("instruments", []),
            }

        if language == "en":
            lang_instruction = (
                "Write atmospheric English lyrics for this track.\n"
                "The language must be English only — do NOT use Turkish words."
            )
        else:
            lang_instruction = (
                "Write atmospheric Turkish lyrics for this track.\n"
                "Language: Turkish only."
            )

        user_prompt = f"""
TRACK CONCEPT:
{json.dumps(concept, ensure_ascii=False, indent=2)}

Track type: {track_type}
{lang_instruction}
Use section tags ([Verse], [Chorus], [Bridge] etc.) as feels natural for the song.
Each section should have 3-5 short, evocative lines.

Keep it minimal, poetic, atmospheric, modern, and easy for Suno to sing.
"""
        return self.call(user_prompt)
