"""
Orchestrator — selects the next city, creates a song, and hands it
off to the PipelineService.
"""

import logging

from src.services.city_service import CityService
from src.services.pipeline_service import PipelineService
from src.services.song_service import SongService
from src.storage.database import get_session

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.pipeline = PipelineService(dry_run=dry_run)

    def run_one(self, city_slug: str | None = None) -> str | None:
        """
        Select a city (or use the given slug), create a new song, run the pipeline.
        Returns the song_id or None on failure.
        """
        with get_session() as session:
            city_svc = CityService(session)
            song_svc = SongService(session)

            if city_slug:
                city = city_svc.get_by_slug(city_slug)
                if not city:
                    logger.error("City not found: %s", city_slug)
                    return None
            else:
                city = city_svc.get_next_city()
                if not city:
                    logger.error("No active cities found")
                    return None

            song = song_svc.create_song(city.id)
            song_id = song.id
            logger.info("Created song %s for city: %s", song_id, city.name)

        # Run outside the session above (pipeline opens its own sessions)
        try:
            self.pipeline.run_song(song_id)
        except Exception as exc:
            logger.exception("Pipeline failed for song %s: %s", song_id, exc)
            return None

        return song_id

    def resume(self, song_id: str) -> str:
        """Resume an existing song from its current status."""
        self.pipeline.run_song(song_id)
        return song_id
