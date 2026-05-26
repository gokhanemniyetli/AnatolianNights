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
    ) -> dict:
        """Generate YouTube metadata for a city-based track."""
        return self.generate_for_playlist(
            song_title=song_title,
            playlist_title=f"{city_name} Nights",
            concept=concept,
            lyrics=lyrics,
        )

    def generate_for_playlist(
        self,
        song_title: str,
        playlist_title: str,
        concept: dict,
        lyrics: str,
    ) -> dict:
        """Generate YouTube metadata for a playlist-based track."""
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
            result["description"] = self._fallback_description(song_title, playlist_title, lyrics)
        if not result.get("short_description"):
            result["short_description"] = f"{song_title} — atmospheric Turkish lo-fi. #AnatolianNights"[:150]

        return result

    def _fallback_description(self, song_title: str, playlist_title: str, lyrics: str) -> str:
        clean_lyrics = self._format_lyrics_for_description(lyrics)
        hashtags = " ".join(self._build_tags(song_title)[:6])
        intro = f"{song_title} — from the {playlist_title} collection by Anatolian Nights."
        if not clean_lyrics:
            return f"{intro}\n\n{hashtags}".strip()
        return f"{intro}\n\n{clean_lyrics}\n\n{hashtags}".strip()

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
        result = {
            "tags": self._hashtags(song_title, city_name),
        }
        result["title"] = f"{song_title} | {city_name} Yöresi | Anadolu Türküleri Ezgileri"
        result["description"] = self._format_description(
            song_title,
            city_name,
            lyrics,
        )
        result["short_title"] = song_title[:100]
        result["short_description"] = self._format_short_description(song_title, city_name)
        return result

    def generate_for_playlist(
        self,
        song_title: str,
        playlist_title: str,
        concept: dict,
        lyrics: str,
    ) -> dict:
        result = {
            "tags": self._hashtags(song_title, playlist_title),
        }
        result["title"] = f"{song_title} | {playlist_title} | Anadolu Türküleri Ezgileri"
        result["description"] = self._format_playlist_description(song_title, playlist_title, lyrics)
        result["short_title"] = song_title[:100]
        result["short_description"] = self._format_playlist_short_description(song_title, playlist_title)
        return result

    def _format_playlist_description(self, song_title: str, playlist_title: str, lyrics: str) -> str:
        clean_lyrics = self._format_lyrics_for_description(lyrics)
        intro = f"{song_title} - {playlist_title} konseptinde yeni bir türkü."
        hashtags = self._format_hashtags(song_title, playlist_title)
        if not clean_lyrics:
            return f"{intro}\n\n{hashtags}".strip()
        return f"{intro}\n\nŞarkı Sözleri:\n\n{clean_lyrics}\n\n{hashtags}".strip()

    def _format_playlist_short_description(self, song_title: str, playlist_title: str) -> str:
        hashtags = " ".join(self._hashtags(song_title, playlist_title)[:3])
        description = f"{song_title} - {playlist_title} kısa türkü. {hashtags}"
        return description[:150].strip()

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
