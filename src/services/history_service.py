"""
HistoryService — tracks per-city generation history for deduplication.
Uses rapidfuzz for fuzzy similarity checks.
"""

import logging

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from src.storage.models import GenerationHistory

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
        return {
            "used_themes": history.get("used_themes") or [],
            "used_titles": history.get("used_titles") or [],
            "used_tempos": history.get("used_tempos") or [],
            "used_moods": history.get("used_moods") or [],
            "used_instruments": history.get("used_instruments") or [],
            "used_hooks": history.get("used_hooks") or [],
            "used_style_prompts": history.get("used_style_prompts") or [],
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
