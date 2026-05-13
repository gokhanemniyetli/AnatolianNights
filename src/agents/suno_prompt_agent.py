"""
SunoPromptAgent — generates a single Turkish simple-mode Suno prompt.
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
        Returns dict with key: simple_prompt (str)
        """
        place_names = cultural_profile.get("place_names", [])[:3]
        themes = concept.get("themes", []) if isinstance(concept, dict) else []
        themes = themes[:3] if isinstance(themes, list) else []

        user_prompt = f"""
SONG CONCEPT:
{json.dumps(concept, ensure_ascii=False, indent=2)}

    CITY/REGION:
    {json.dumps({'city': cultural_profile.get('city', ''), 'region': cultural_profile.get('region', '')}, ensure_ascii=False)}

ALLOWED INSTRUMENTS (region-specific):
{json.dumps(cultural_profile.get('instruments', {}).get('primary', []), ensure_ascii=False)}

AVOID INSTRUMENTS (region-specific):
{json.dumps(cultural_profile.get('instruments', {}).get('avoid', []), ensure_ascii=False)}

    PRIORITY PLACE/THEME HINTS (use at most 1-3 total words):
    {json.dumps({'place_names': place_names, 'themes': themes}, ensure_ascii=False)}

    Write exactly one Turkish simple-mode prompt sentence for Suno.
    No lyrics. No lists. No alternatives.
"""
        return self.call(user_prompt)
