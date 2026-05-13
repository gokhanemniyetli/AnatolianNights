"""
SunoPromptAgent — generates English style prompt and formatted lyrics for Suno.
"""

import json
from pathlib import Path

from src.agents.base_agent import BaseAgent
from src.config.models_config import get_model

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "suno_style.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


class SunoPromptAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            task="suno_prompt",
            model=get_model("suno_prompt"),
            system_prompt=_SYSTEM_PROMPT,
        )

    def generate(self, concept: dict, lyrics: str, cultural_profile: dict) -> dict:
        """
        Returns dict with keys: style_prompt (str), suno_lyrics (str)
        """
        user_prompt = f"""
SONG CONCEPT:
{json.dumps(concept, ensure_ascii=False, indent=2)}

SUNO STYLE HINTS (from cultural profile):
{json.dumps(cultural_profile.get('suno_style_hints', []), ensure_ascii=False)}

TURKISH LYRICS:
{lyrics}

Write the Suno style prompt and format the lyrics for Suno input.
"""
        return self.call(user_prompt)
