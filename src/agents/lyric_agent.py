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

    def generate(self, concept: dict, city_name: str, cultural_profile: dict) -> dict:
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

        user_prompt = f"""
TRACK CONCEPT:
{json.dumps(concept, ensure_ascii=False, indent=2)}

Track type: {track_type}
{'Write 4-8 minimal atmospheric lines. No verse/chorus structure needed. Dreamy and almost wordless.' if track_type == 'ambient_vocal' else 'Write 2 short verses (3-4 lines each) + 1 short chorus (2-3 lines). Minimal, poetic, atmospheric.'}
Language: Turkish preferred for authentic Anatolian texture, or English if the concept calls for it.
"""
        return self.call(user_prompt)
