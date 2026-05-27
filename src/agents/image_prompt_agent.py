"""
ImagePromptAgent — generates a cinematic atmospheric image prompt for Anatolian Nights.
"""

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

    def generate(self, concept: dict, city_name: str, cultural_profile: dict, language: str = "tr") -> dict:
        """
        Returns dict with keys: image_prompt (str), negative_prompt (str), style_tags (list)
        City-based generate delegates to the playlist method.
        """
        concept_profile = {
            "group": "istanbul-night",
            "style_profile": {"mood": "atmospheric night, cinematic"},
        }
        return self.generate_for_playlist(concept, f"{city_name} Nights", concept_profile, language=language)

    def generate_for_playlist(
        self,
        concept: dict,
        playlist_title: str,
        concept_profile: dict,
        language: str = "tr",
    ) -> dict:
        """Generate a cinematic atmospheric background prompt for Anatolian Nights."""
        group = concept_profile.get("group", "")
        lang_note = ""
        if (language or "tr").lower() == "en":
            lang_note = (
                "\nLANGUAGE: Write the full image prompt and style wording in English only. "
                "If any source text is Turkish, translate it to natural English."
            )
        user_prompt = f"""
TRACK:
- Playlist: {playlist_title}
- Group: {group}
- Theme: {concept.get('theme', '')}
- Mood: {concept.get('mood', '')}
- Visual: {concept.get('visual', '')}
- Ambience: {concept.get('ambience', [])}
- Story: {concept.get('story', '')}
{lang_note}

Generate a 1920x1080 cinematic atmospheric background image prompt.
The scene must feel premium and moody — like a movie still or atmospheric album cover.
No people, no human figures, no faces, no musicians, no musical instruments.
Set the scene in Istanbul or Anatolia at night — rain, neon reflections, Bosphorus, old city architecture.
First sentence: main visual subject + time of day + weather atmosphere.
No text in the image.
"""
        result = self.call(user_prompt)

        # Enforce no-humans constraint at the start of the prompt (CLIP encoder truncation safety)
        forced_opening = (
            "Cinematic atmospheric night scene, Istanbul or Anatolia, "
            "no people, no human figures, no faces, no hands, no musicians, no musical instruments."
        )
        image_prompt = (result.get("image_prompt") or "").strip()
        if "no people" not in image_prompt.lower():
            result["image_prompt"] = f"{forced_opening} {image_prompt}".strip()

        extra_negative = (
            "people, person, human figure, face, hands, body, portrait, crowd, "
            "musician, singer, dancer, silhouette of a person, "
            "baglama, saz, guitar, kaval, flute, drum, musical instrument, "
            "text, watermark, logo, daylight, bright sunlight, cheerful, tourist postcard, "
            "anime, cartoon, illustration, malformed, blurry, low quality"
        )
        existing_neg = (result.get("negative_prompt") or "").strip()
        result["negative_prompt"] = (
            f"{existing_neg}, {extra_negative}" if existing_neg else extra_negative
        )
        return result
