"""
ConceptAgent — generates a unique song concept for a given city.
Receives city cultural profile + generation history to avoid repetition.
"""

import json
from pathlib import Path

from src.agents.base_agent import BaseAgent
from src.config.models_config import get_model

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "concept.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


class ConceptAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            task="concept",
            model=get_model("concept"),
            system_prompt=_SYSTEM_PROMPT,
        )

    def generate(
        self,
        city_name: str,
        cultural_profile: dict,
        generation_history: dict,
    ) -> dict:
        """
        Returns a concept dict with keys:
        title, theme, story, mood, tempo, vocal, instruments, avoid, season, narrator
        """
        user_prompt = f"""
Şehir: {city_name}

KÜLTÜREL PROFİL:
{json.dumps(cultural_profile, ensure_ascii=False, indent=2)}

DAHA ÖNCE KULLANILAN (BUNLARI TEKRARLAMA):
- Temalar: {generation_history.get('used_themes', [])}
- Tempolar: {generation_history.get('used_tempos', [])}
- Duygular: {generation_history.get('used_moods', [])}
- Enstrümanlar: {generation_history.get('used_instruments', [])}
- Başlıklar: {generation_history.get('used_titles', [])}

Bu şehir için YENİ ve FARKLI bir türkü konsepti oluştur.
"""
        return self.call(user_prompt)
