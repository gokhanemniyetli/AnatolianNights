"""
MetadataAgent — generates YouTube title, description, tags, and Shorts metadata.
"""

import json
from pathlib import Path

from src.agents.base_agent import BaseAgent
from src.config.models_config import get_model

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "youtube_metadata.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


class MetadataAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            task="metadata",
            model=get_model("metadata"),
            system_prompt=_SYSTEM_PROMPT,
        )

    def generate(
        self,
        song_title: str,
        city_name: str,
        concept: dict,
        lyrics: str,
    ) -> dict:
        """
        Returns dict with keys:
        title, description, tags, short_title, short_description
        """
        user_prompt = f"""
Kanal: Anadolu Türküleri Ezgileri
Şehir: {city_name}
Şarkı Adı: {song_title}

KONSEPT:
{json.dumps(concept, ensure_ascii=False, indent=2)}

ŞARKI SÖZLERİ:
{lyrics}

YouTube için başlık, açıklama ve etiketler oluştur.
Açıklamada şarkı sözlerini ekle.
Bu içeriğin yapay zeka tarafından üretildiğini belirt.
"""
        return self.call(user_prompt)
