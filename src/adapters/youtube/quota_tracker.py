"""
QuotaTracker — tracks YouTube Data API quota usage in SQLite.
Prevents exceeding the 10,000 unit/day limit.
"""

import logging
from datetime import date

from sqlalchemy.orm import Session

from src.storage.models import YouTubeQuotaLog

logger = logging.getLogger(__name__)

# Operation costs (units)
COST_UPLOAD = 1600
COST_LIST = 1
COST_INSERT = 50  # playlist insert


class QuotaTracker:
    def __init__(self, session: Session, daily_limit: int = 10_000):
        self.session = session
        self.daily_limit = daily_limit

    def _today(self) -> str:
        return date.today().isoformat()

    def _used_today(self) -> int:
        today = self._today()
        rows = self.session.query(YouTubeQuotaLog).filter_by(date=today).all()
        return sum(r.cost for r in rows)

    def can_afford(self, operation: str) -> bool:
        cost = self._cost_for(operation)
        used = self._used_today()
        remaining = self.daily_limit - used
        if remaining < cost:
            logger.warning(
                "Quota check failed: %s costs %d but only %d remaining today",
                operation, cost, remaining,
            )
            return False
        return True

    def record(self, operation: str, song_id: str | None = None) -> None:
        cost = self._cost_for(operation)
        log = YouTubeQuotaLog(
            date=self._today(),
            operation=operation,
            cost=cost,
            song_id=song_id,
        )
        self.session.add(log)
        self.session.flush()
        logger.debug("Quota recorded: %s cost=%d", operation, cost)

    def remaining_today(self) -> int:
        return self.daily_limit - self._used_today()

    @staticmethod
    def _cost_for(operation: str) -> int:
        mapping = {
            "upload": COST_UPLOAD,
            "upload_short": COST_UPLOAD,
            "list": COST_LIST,
            "playlist_insert": COST_INSERT,
        }
        return mapping.get(operation, 1)
