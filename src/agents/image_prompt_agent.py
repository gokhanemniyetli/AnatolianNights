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
Use only scenery, landmarks, architecture, weather, water, terrain, animals, and regional atmosphere.
Do not include people, human figures, musicians, faces, hands, bodies, silhouettes, or musical instruments.
The first sentence must mention the main regional landscape/place and the season or weather.
No text in image.
"""
        result = self.call(user_prompt)

        # SDXL's CLIP encoder truncates long prompts, so keep the non-negotiable
        # "no humans/instruments" constraint at the front where it cannot be dropped.
        forced_opening = (
            f"Empty cinematic landscape of {city_name}, no people, no human figures, "
            "no faces, no hands, no musicians, no musical instruments."
        )
        image_prompt = (result.get("image_prompt") or "").strip()
        if forced_opening.lower() not in image_prompt.lower():
            result["image_prompt"] = f"{forced_opening} {image_prompt}".strip()

        negative_prompt = (result.get("negative_prompt") or "").strip()
        extra_negative = (
            "people, person, human figure, face, hands, body, portrait, crowd, "
            "musician, singer, dancer, shepherd, villager, fisherman, worker, "
            "silhouette of a person, baglama, saz, lute, guitar, kaval, flute, "
            "drum, zurna, musical instrument, malformed faces, extra fingers"
        )
        result["negative_prompt"] = (
            f"{negative_prompt}, {extra_negative}" if negative_prompt else extra_negative
        )

        return result
