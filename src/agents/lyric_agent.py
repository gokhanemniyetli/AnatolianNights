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
        """
        user_prompt = f"""
Şehir: {city_name}

ŞARKI KONSEPTİ:
{json.dumps(concept, ensure_ascii=False, indent=2)}

YÖRESEL KISITLAMALAR:
- Kullan: {cultural_profile.get('instruments', {}).get('primary', [])}
- Kaçın: {cultural_profile.get('instruments', {}).get('avoid', [])}
- Yasak stiller: {cultural_profile.get('lyric_style', {}).get('forbidden_styles', [])}
- Yasak kelimeler: {cultural_profile.get('lyric_style', {}).get('forbidden_words', [])}
- Dil notu: {cultural_profile.get('lyric_style', {}).get('language_notes', '')}

Bu konsepte uygun, doğal Türkçe, kaliteli türkü sözleri yaz.
"""
        return self.call(user_prompt)
