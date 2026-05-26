"""
QualityAgent — LLM-based lyrics quality reviewer.
Runs after the rule-based fast filter passes.
"""

from pathlib import Path

from src.agents.base_agent import BaseAgent
from src.config.models_config import get_model
from src.config.settings import settings

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "quality_review.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


class QualityAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            task="lyric_reviewer",
            model=get_model("lyric_reviewer"),
            system_prompt=_SYSTEM_PROMPT,
        )

    def review(self, lyrics: str, city_name: str, concept: dict) -> dict:
        """
        Returns dict with keys:
        is_approved (bool), score (float), issues (list), rejected_reason (str|None),
        positive_notes (list), reviewer_model (str)
        """
        track_type = concept.get("track_type", "instrumental")
        user_prompt = f"""
TRACK CONCEPT:
- Title: {concept.get('title', '')}
- Theme: {concept.get('theme', '')}
- Mood: {concept.get('mood', '')}
- Track type: {track_type}
- Instruments: {concept.get('instruments', [])}
- Ambience: {concept.get('ambience', [])}

LYRICS:
{lyrics if lyrics and lyrics.strip() else '(instrumental — no lyrics)'}

Review this track concept and lyrics (if any) against Anatolian Nights atmospheric standards.
Score threshold: {settings.pipeline.quality_threshold}
"""
        result = self.call(user_prompt)
        result["reviewer_model"] = self.model
        return result
