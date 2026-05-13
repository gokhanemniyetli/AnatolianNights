"""
ImagePromptAgent — generates a detailed SDXL image generation prompt
for the song's background visual.
"""

import json
from pathlib import Path

from src.agents.base_agent import BaseAgent
from src.config.models_config import get_model

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "image_prompt.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


class ImagePromptAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            task="image_prompt",
            model=get_model("image_prompt"),
            system_prompt=_SYSTEM_PROMPT,
        )

    def generate(self, concept: dict, city_name: str, cultural_profile: dict) -> dict:
        """
        Returns dict with keys: image_prompt (str), negative_prompt (str), style_tags (list)
        """
        visual = cultural_profile.get("visual_atmosphere", {})
        user_prompt = f"""
SONG:
- City: {city_name}
- Theme: {concept.get('theme', '')}
- Mood: {concept.get('mood', '')}
- Season: {concept.get('season', '')}
- Story: {concept.get('story', '')}

VISUAL ATMOSPHERE FROM CULTURAL PROFILE:
- Colors: {visual.get('colors', [])}
- Landscape: {visual.get('landscape', '')}
- Season suggestions: {visual.get('season_suggestions', [])}
- Lighting: {visual.get('lighting', '')}

Generate a 1920x1080 landscape background image prompt for this Turkish folk song.
No faces, no text in image.
"""
        return self.call(user_prompt)
