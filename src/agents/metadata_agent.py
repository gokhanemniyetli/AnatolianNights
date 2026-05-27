"""
MetadataAgent — generates YouTube title, description, tags, and Shorts metadata
for the ANATOLIAN NIGHTS channel.
"""

import re
from pathlib import Path

from src.agents.base_agent import BaseAgent
from src.config.models_config import get_model

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "youtube_metadata.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
_SECTION_RE = re.compile(r"^\s*\[[^\]]+\]\s*$")

_BASE_TAGS = [
    "#AnatolianNights",
    "#TurkishLofi",
    "#IstanbulNight",
    "#AmbientMusic",
    "#LofiMusic",
    "#ChillMusic",
    "#AtmosphericMusic",
    "#TurkishAmbient",
]


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
        language: str = "tr",
    ) -> dict:
        """Generate YouTube metadata for a city-based track."""
        return self.generate_for_playlist(
            song_title=song_title,
            playlist_title=f"{city_name} Nights",
            concept=concept,
            lyrics=lyrics,
            language=language,
        )

    def generate_for_playlist(
        self,
        song_title: str,
        playlist_title: str,
        concept: dict,
        lyrics: str,
        language: str = "tr",
    ) -> dict:
        """Generate YouTube metadata for a playlist-based track."""
        if language == "en":
            lang_note = (
                "\nLANGUAGE: Generate ALL metadata in English. "
                "Translate the song title to English if it is in Turkish. "
                "The title, description, short_title, and short_description must all be in English."
            )
        else:
            lang_note = ""
        user_prompt = f"""
TRACK:
- Title: {song_title}
- Playlist: {playlist_title}
- Theme: {concept.get('theme', '')}
- Mood: {concept.get('mood', '')}
- Track type: {concept.get('track_type', 'instrumental')}
- Story: {concept.get('story', '')}

LYRICS:
{self._format_lyrics_for_description(lyrics) if lyrics and lyrics.strip() else '(instrumental — no lyrics)'}
{lang_note}
Generate cinematic atmospheric YouTube metadata for the ANATOLIAN NIGHTS channel.
Title must follow format: "{song_title} | Anatolian Nights" or a variant.
Description must feel premium and atmospheric — like liner notes for a cinematic music release.
Tags should be relevant and natural, not spammy.
"""
        result = self.call(user_prompt)

        # Ensure minimum required fields are present
        if not result.get("title"):
            result["title"] = f"{song_title} | Anatolian Nights"
        if not result.get("short_title"):
            result["short_title"] = f"{song_title} | Anatolian Nights"[:100]
        if not result.get("tags"):
            result["tags"] = self._build_tags(song_title)
        if not result.get("description"):
            result["description"] = self._fallback_description(song_title, playlist_title, lyrics, language=language)
        if not result.get("short_description"):
            if language == "en":
                result["short_description"] = f"{song_title} - atmospheric Turkish lo-fi. #AnatolianNights"[:150]
            else:
                result["short_description"] = f"{song_title} - atmosferik Turkce lo-fi. #AnatolianNights"[:150]

        if language == "en":
            result["title"] = self._ensure_english_title(result.get("title", ""), song_title)
            result["short_title"] = self._ensure_english_title(result.get("short_title", ""), song_title)[:100]

        return result

    def _fallback_description(self, song_title: str, playlist_title: str, lyrics: str, language: str = "tr") -> str:
        clean_lyrics = self._format_lyrics_for_description(lyrics)
        hashtags = " ".join(self._build_tags(song_title)[:6])
        if language == "en":
            intro = f"{song_title} - from the {playlist_title} collection by Anatolian Nights."
        else:
            intro = f"{song_title} - Anatolian Nights tarafindan {playlist_title} koleksiyonundan."
        if not clean_lyrics:
            return f"{intro}\n\n{hashtags}".strip()
        return f"{intro}\n\n{clean_lyrics}\n\n{hashtags}".strip()

    @staticmethod
    def _ensure_english_title(candidate_title: str, fallback_song_title: str) -> str:
        title = (candidate_title or "").strip()
        if not title:
            return f"{fallback_song_title} | Anatolian Nights"
        if "|" not in title:
            return f"{title} | Anatolian Nights"
        return title

    @staticmethod
    def _build_tags(song_title: str) -> list[str]:
        title_tag = "#" + re.sub(r"[^\w]", "", song_title or "")
        tags = [title_tag] + _BASE_TAGS if title_tag != "#" else list(_BASE_TAGS)
        # Deduplicate while preserving order
        seen: set[str] = set()
        result = []
        for tag in tags:
            if tag not in seen:
                seen.add(tag)
                result.append(tag)
        return result

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
