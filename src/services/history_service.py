"""
HistoryService — tracks per-city generation history for deduplication.
Uses rapidfuzz for fuzzy similarity checks.
"""

import logging

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from src.storage.models import ConceptGenerationHistory, GenerationHistory, Song

logger = logging.getLogger(__name__)

# Similarity threshold (0-100). Values above this are considered duplicates.
SIMILARITY_THRESHOLD = 60


class HistoryService:
    def __init__(self, session: Session):
        self.session = session

    # ── Get / create ──────────────────────────────────────────────────

    def get_or_create(self, city_id: int) -> GenerationHistory:
        history = self.session.query(GenerationHistory).filter_by(city_id=city_id).first()
        if not history:
            history = GenerationHistory(city_id=city_id)
            self.session.add(history)
            self.session.flush()
        return history

    def get_or_create_concept(self, concept_playlist_id: int) -> ConceptGenerationHistory:
        history = (
            self.session.query(ConceptGenerationHistory)
            .filter_by(concept_playlist_id=concept_playlist_id)
            .first()
        )
        if not history:
            history = ConceptGenerationHistory(concept_playlist_id=concept_playlist_id)
            self.session.add(history)
            self.session.flush()
        return history

    # ── Update ────────────────────────────────────────────────────────

    def record_song(self, city_id: int, concept: dict, lyrics_keywords: list[str]) -> None:
        """Record a successfully generated song's attributes into history."""
        history = self.get_or_create(city_id)
        history.append("used_themes", concept.get("theme", ""))
        history.append("used_titles", concept.get("title", ""))
        history.append("used_tempos", concept.get("tempo", ""))
        history.append("used_moods", concept.get("mood", ""))
        for inst in concept.get("instruments", []):
            history.append("used_instruments", inst)
        for hook in lyrics_keywords:
            history.append("used_hooks", hook)
        self.session.flush()
        logger.debug("Recorded history for city_id=%d", city_id)

    def record_concept_song(
        self,
        concept_playlist_id: int,
        concept: dict,
        lyrics_keywords: list[str],
    ) -> None:
        """Record a generated song's attributes into concept-playlist history."""
        history = self.get_or_create_concept(concept_playlist_id)
        history.append("used_themes", concept.get("theme", ""))
        history.append("used_titles", concept.get("title", ""))
        history.append("used_tempos", concept.get("tempo", ""))
        history.append("used_moods", concept.get("mood", ""))
        for inst in concept.get("instruments", []):
            history.append("used_instruments", inst)
        for hook in lyrics_keywords:
            history.append("used_hooks", hook)
        self.session.flush()
        logger.debug("Recorded history for concept_playlist_id=%d", concept_playlist_id)

    # ── Similarity checks ─────────────────────────────────────────────

    def is_title_duplicate(self, city_id: int, title: str) -> bool:
        history = self.get_or_create(city_id)
        used = history.get("used_titles") or []
        return self._is_similar_to_any(title, used)

    def is_theme_duplicate(self, city_id: int, theme: str) -> bool:
        history = self.get_or_create(city_id)
        used = history.get("used_themes") or []
        return self._is_similar_to_any(theme, used)

    def is_style_prompt_duplicate(self, city_id: int, style_prompt: str) -> bool:
        history = self.get_or_create(city_id)
        used = history.get("used_style_prompts") or []
        return self._is_similar_to_any(style_prompt, used)

    def get_history_dict(self, city_id: int) -> dict:
        """Return full history as a plain dict for passing to agents."""
        history = self.get_or_create(city_id)
        recent_global = self.get_recent_global_history()
        return {
            "used_themes": history.get("used_themes") or [],
            "used_titles": history.get("used_titles") or [],
            "used_tempos": history.get("used_tempos") or [],
            "used_moods": history.get("used_moods") or [],
            "used_instruments": history.get("used_instruments") or [],
            "used_hooks": history.get("used_hooks") or [],
            "used_style_prompts": history.get("used_style_prompts") or [],
            "recent_global_themes": recent_global["themes"],
            "recent_global_titles": recent_global["titles"],
        }

    def get_concept_history_dict(self, concept_playlist_id: int) -> dict:
        """Return concept-playlist history plus recent channel-wide history."""
        history = self.get_or_create_concept(concept_playlist_id)
        recent_global = self.get_recent_global_history()
        return {
            "used_themes": history.get("used_themes") or [],
            "used_titles": history.get("used_titles") or [],
            "used_tempos": history.get("used_tempos") or [],
            "used_moods": history.get("used_moods") or [],
            "used_instruments": history.get("used_instruments") or [],
            "used_hooks": history.get("used_hooks") or [],
            "used_style_prompts": history.get("used_style_prompts") or [],
            "recent_global_themes": recent_global["themes"],
            "recent_global_titles": recent_global["titles"],
        }

    def get_recent_global_history(self, limit: int = 30) -> dict[str, list[str]]:
        """Return recent channel-wide titles and themes to prevent cross-city repetition."""
        songs = (
            self.session.query(Song)
            .order_by(Song.id.desc())
            .limit(limit)
            .all()
        )
        titles: list[str] = []
        themes: list[str] = []
        for song in songs:
            if song.title:
                titles.append(song.title)
            concept = song.get_concept()
            if concept.get("title"):
                titles.append(str(concept["title"]))
            if concept.get("theme"):
                themes.append(str(concept["theme"]))
        return {
            "titles": self._dedupe_keep_order(titles),
            "themes": self._dedupe_keep_order(themes),
        }

    # ── Internal ──────────────────────────────────────────────────────

    @staticmethod
    def _is_similar_to_any(candidate: str, existing: list[str]) -> bool:
        if not candidate or not existing:
            return False
        candidate_lower = candidate.lower().strip()
        for item in existing:
            score = fuzz.token_sort_ratio(candidate_lower, item.lower().strip())
            if score >= SIMILARITY_THRESHOLD:
                logger.debug("Similarity %.0f%% ≥ threshold: '%s' ~ '%s'", score, candidate, item)
                return True
        return False

    @staticmethod
    def _dedupe_keep_order(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            value = str(item or "").strip()
            key = value.casefold()
            if not value or key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result
