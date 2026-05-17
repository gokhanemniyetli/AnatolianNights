"""
SunoPromptAgent — generates a single Turkish simple-mode Suno prompt.
"""

import json
from pathlib import Path

from src.agents.base_agent import BaseAgent
from src.config.models_config import get_model

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "suno_style.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
_FORBIDDEN_STYLE_TERMS = (
    "german",
    "rap",
    "pop",
    "rock",
    "country",
    "trap",
    "hip-hop",
    "hip hop",
    "r&b",
    "electro",
    "electronic",
    "synth",
    "western folk",
    "irish",
    "scottish",
    "english folk",
)


class SunoPromptAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            task="suno_prompt",
            model=get_model("suno_prompt"),
            system_prompt=_SYSTEM_PROMPT,
        )

    def generate(self, concept: dict, cultural_profile: dict) -> dict:
        """
        Returns dict with key: simple_prompt (str)
        """
        place_names = cultural_profile.get("place_names", [])[:6]
        foods = cultural_profile.get("foods", [])[:4]
        crafts = cultural_profile.get("crafts", [])[:4]
        landmarks = cultural_profile.get("landmarks", [])[:6]
        themes = concept.get("themes", []) if isinstance(concept, dict) else []
        themes = themes[:4] if isinstance(themes, list) else []

        user_prompt = f"""
SONG CONCEPT:
{json.dumps(concept, ensure_ascii=False, indent=2)}

CITY/REGION:
{json.dumps({'city': cultural_profile.get('city', ''), 'region': cultural_profile.get('region', '')}, ensure_ascii=False)}

ALLOWED INSTRUMENTS (region-specific):
{json.dumps(cultural_profile.get('instruments', {}).get('primary', []), ensure_ascii=False)}

AVOID INSTRUMENTS (region-specific):
{json.dumps(cultural_profile.get('instruments', {}).get('avoid', []), ensure_ascii=False)}

LOCAL DETAIL OPTIONS (choose only the ones that fit the concept):
{json.dumps({'place_names': place_names, 'landmarks': landmarks, 'foods': foods, 'crafts': crafts, 'themes': themes}, ensure_ascii=False)}

Write exactly one detailed Turkish simple-mode command for Suno.
Suno must write the lyrics itself; do not provide lyrics.
Make the subject specific enough that another song from the same city would feel different.
Include the city/dialect, narrator, central story, mood, tempo, 1-3 local images, and region-appropriate instruments.
No lists. No alternatives.
"""
        result = self.call(user_prompt)
        simple_prompt = str(result.get("simple_prompt", "")).strip()
        lowered = simple_prompt.lower()
        forbidden = [term for term in _FORBIDDEN_STYLE_TERMS if term in lowered]
        if forbidden:
            raise ValueError(
                "Suno prompt contains forbidden modern/western style terms: "
                + ", ".join(forbidden)
            )
        result["simple_prompt"] = simple_prompt
        return result
