"""
TitleBankService — manages the pre-defined song title bank.
Picks the next unused title from data/song_titles.json.
"""

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from src.storage.models import Song

logger = logging.getLogger(__name__)

_TITLE_BANK_PATH = Path(__file__).parent.parent.parent / "data" / "song_titles.json"


class TitleBankService:
    def __init__(self, session: Session):
        self.session = session

    def get_next_title(self) -> str | None:
        """Return the next unused title from the bank, or None if all are used."""
        bank = self._load_bank()
        used = self._get_used_titles()
        for title in bank:
            if title not in used:
                logger.info("Title bank: selected '%s'", title)
                return title
        logger.warning("Title bank exhausted — all %d titles have been used.", len(bank))
        return None

    def _load_bank(self) -> list[str]:
        return json.loads(_TITLE_BANK_PATH.read_text(encoding="utf-8"))

    def _get_used_titles(self) -> set[str]:
        rows = self.session.query(Song.title).filter(Song.title.isnot(None)).all()
        return {row[0] for row in rows if row[0]}
