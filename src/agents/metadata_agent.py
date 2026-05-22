"""
MetadataAgent — generates YouTube title, description, tags, and Shorts metadata.
"""

import json
import re
from pathlib import Path

from src.agents.base_agent import BaseAgent
from src.config.models_config import get_model

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "youtube_metadata.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
_SECTION_RE = re.compile(r"^\s*\[[^\]]+\]\s*$")
_LYRICS_HEADING_RE = re.compile(r"(?:^|\n)(?:şarkı sözleri|sözler|lyrics)\s*:?\s*\n", re.IGNORECASE)


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
Başlık ve etiketler Türkçe, sade ve doğal olsun.
"""
        result = self.call(user_prompt)
        result["title"] = f"{song_title} | {city_name} Yöresi | Anadolu Türküleri Ezgileri"
        result["description"] = self._format_description(
            song_title,
            city_name,
            lyrics,
        )
        result["short_title"] = song_title[:100]
        result["short_description"] = self._format_short_description(song_title, city_name)
        return result

    def _format_description(self, song_title: str, city_name: str, lyrics: str) -> str:
        clean_lyrics = self._format_lyrics_for_description(lyrics)
        intro = f"{song_title} - {city_name} yöresinden yeni bir türkü."
        hashtags = self._format_hashtags(song_title, city_name)
        if not clean_lyrics:
            return f"{intro}\n\n{hashtags}".strip()
        return f"{intro}\n\nŞarkı Sözleri:\n\n{clean_lyrics}\n\n{hashtags}".strip()

    def _format_short_description(self, song_title: str, city_name: str) -> str:
        hashtags = " ".join(self._hashtags(song_title, city_name)[:3])
        description = f"{song_title} - {city_name} yöresinden kısa türkü. {hashtags}"
        return description[:150].strip()

    def _format_hashtags(self, song_title: str, city_name: str) -> str:
        return " ".join(self._hashtags(song_title, city_name))

    @classmethod
    def _hashtags(cls, song_title: str, city_name: str) -> list[str]:
        city_tag = cls._hashtag(city_name)
        title_tag = cls._hashtag(song_title)
        tags = [
            city_tag,
            title_tag,
            "#Türkü",
            "#AnadoluTürküleri",
            "#HalkMüziği",
            "#TürkHalkMüziği",
        ]
        return [tag for index, tag in enumerate(tags) if tag and tag not in tags[:index]]

    @staticmethod
    def _hashtag(text: str) -> str:
        tag = re.sub(r"[^\wçğıöşüÇĞİÖŞÜ]+", "", text or "", flags=re.UNICODE)
        return f"#{tag}" if tag else ""

    @classmethod
    def _format_lyrics_for_description(cls, lyrics: str) -> str:
        stanzas: list[list[str]] = []
        current: list[str] = []
        for raw in (lyrics or "").splitlines():
            line = raw.strip()
            if not line:
                if current:
                    stanzas.append(current)
                    current = []
                continue
            if _SECTION_RE.match(line):
                if current:
                    stanzas.append(current)
                    current = []
                continue
            line = cls._strip_suno_markers(line)
            if line:
                current.append(line)
        if current:
            stanzas.append(current)
        return "\n\n".join("\n".join(stanza) for stanza in stanzas)

    @staticmethod
    def _strip_suno_markers(text: str) -> str:
        text = re.sub(r"\[[^\]]+\]", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
