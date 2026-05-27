"""SunoPromptAgent — builds deterministic simple-mode Suno prompts."""


def _clean_items(items: list | tuple | None, limit: int = 4) -> str:
    if not items:
        return ""
    return ", ".join(str(item).strip() for item in items[:limit] if str(item).strip())


def _compact(value: object) -> str:
    return " ".join(str(value or "").split())


class SunoPromptAgent:
    def __init__(self):
        pass

    def generate(self, concept: dict, cultural_profile: dict) -> dict:
        """
        Returns dict with key: simple_prompt (str)
        """
        return self._build_prompt(concept, concept_profile=None)

    def generate_for_playlist(self, concept: dict, concept_profile: dict) -> dict:
        """Build a Suno simple-mode prompt for a playlist concept."""
        return self._build_prompt(concept, concept_profile=concept_profile)

    def _build_prompt(self, concept: dict, concept_profile: dict | None) -> dict:
        style_profile = {}
        if concept_profile:
            style_profile = concept_profile.get("style_profile", {}) or {}

        title = _compact(concept.get("title"))
        theme = _compact(concept.get("theme"))
        story = _compact(concept.get("story"))
        mood = _compact(concept.get("mood"))
        tempo = _compact(concept.get("tempo") or style_profile.get("tempo") or "65-75 BPM")
        visual = _compact(concept.get("visual"))
        instruments = _clean_items(concept.get("instruments") or style_profile.get("instruments"))
        ambience = _clean_items(concept.get("ambience"))

        if not instruments:
            instruments = "soft baglama textures, warm electric piano, ambient guitar, lo-fi drums"
        if not ambience:
            ambience = "rain on streets, distant ferry horn, tram sounds, soft city night noise"

        simple_prompt = (
            "Turkish vocal song with a clear lead singer and sung Turkish lyrics throughout. "
            "Style: cinematic Istanbul night song, lo-fi chill rhythm, Anatolian texture, "
            f"{tempo}, soft modern vocal delivery, {instruments}, warm tape saturation, "
            f"vinyl crackle, deep reverb. Title: '{title}'. "
            f"Song topic: {theme}. Story and emotion: {story}. Mood: {mood}. "
            f"Visual imagery: {visual}. Ambience: {ambience}. "
            "The lyrics should be poetic, natural Turkish, about rainy streets, neon reflections, "
            "Bosphorus solitude, late-night longing, with two verses and one memorable chorus."
        )
        return {"simple_prompt": simple_prompt[:1800]}
