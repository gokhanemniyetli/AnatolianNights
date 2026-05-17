"""
CycleRunner — runs one or more pipeline cycles.
A cycle = generate K songs (default 1) for the top cities.
"""

import logging
import time

from src.config.settings import settings
from src.scheduler.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class CycleRunner:
    def __init__(self, k: int = 1, dry_run: bool = False):
        self.k = k
        self.dry_run = dry_run
        self.orchestrator = Orchestrator(dry_run=dry_run)

    def run_cycle(self, city_slug: str | None = None) -> list[str]:
        """
        Run one cycle: generate up to K songs.
        Returns list of created song_ids.
        """
        if self.k > settings.pipeline.max_daily_uploads:
            logger.warning(
                "Requested k=%d exceeds max_daily_uploads=%d; limiting this cycle.",
                self.k,
                settings.pipeline.max_daily_uploads,
            )
            self.k = settings.pipeline.max_daily_uploads

        created = []
        for i in range(self.k):
            logger.info("Cycle: generating song %d/%d", i + 1, self.k)
            song_id = self.orchestrator.run_one(city_slug=city_slug)
            if song_id:
                created.append(song_id)
            else:
                logger.warning("Song generation %d/%d failed or skipped", i + 1, self.k)
                break
            if i < self.k - 1:
                wait_seconds = max(settings.pipeline.publish_interval_minutes, 0) * 60
                if wait_seconds:
                    logger.info(
                        "Waiting %d minutes before next upload to avoid back-to-back publishing...",
                        settings.pipeline.publish_interval_minutes,
                    )
                    time.sleep(wait_seconds)
                else:
                    time.sleep(2)

        logger.info("Cycle complete. Songs created: %s", created)
        return created

    def run_n_cycles(self, n: int, interval_seconds: int = 0) -> list[list[str]]:
        """
        Run N cycles with optional interval between them.
        Returns list of cycle results.
        """
        all_results = []
        for cycle_num in range(1, n + 1):
            logger.info("=== Starting cycle %d/%d ===", cycle_num, n)
            result = self.run_cycle()
            all_results.append(result)
            if cycle_num < n and interval_seconds > 0:
                logger.info("Waiting %ds before next cycle...", interval_seconds)
                time.sleep(interval_seconds)
        return all_results
