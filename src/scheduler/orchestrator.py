"""
Orchestrator — selects the next city, creates a song, and hands it
off to the PipelineService.
"""

import logging

from src.services.city_service import CityService
from src.services.concept_playlist_service import ConceptPlaylistService
from src.services.pipeline_service import PipelineService
from src.services.song_service import SongService
from src.storage.database import get_session

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.pipeline = PipelineService(dry_run=dry_run)

    def run_one(self, city_slug: str | None = None, concept_slug: str | None = None) -> str | None:
        """
        Select a city/concept (or use the given slug), create a new song, run the pipeline.
        Returns the song_id or None on failure.
        """
        with get_session() as session:
            city_svc = CityService(session)
            concept_playlist_svc = ConceptPlaylistService(session)
            song_svc = SongService(session)

            if concept_slug:
                concept_playlist = concept_playlist_svc.get_by_slug(concept_slug)
                if not concept_playlist:
                    logger.error("Concept playlist not found: %s", concept_slug)
                    return None
                city = city_svc.get_by_id(concept_playlist.anchor_city_id) if concept_playlist.anchor_city_id else None
                if not city:
                    city = city_svc.get_next_city()
                if not city:
                    logger.error("No anchor city found for concept: %s", concept_slug)
                    return None
                concept_playlist_svc.ensure_research(concept_playlist)
                song = song_svc.create_concept_song(city.id, concept_playlist.id)
                song_id = song.id
                logger.info("Created song %s for concept: %s", song_id, concept_playlist.title)
            elif city_slug:
                city = city_svc.get_by_slug(city_slug)
                if not city:
                    logger.error("City not found: %s", city_slug)
                    return None
                song = song_svc.create_song(city.id)
                song_id = song.id
                logger.info("Created song %s for city: %s", song_id, city.name)
            else:
                target = self._next_target(city_svc, concept_playlist_svc)
                if not target:
                    logger.error("No active cities or concepts found")
                    return None
                target_type, target_obj = target
                if target_type == "concept":
                    concept_playlist = target_obj
                    city = city_svc.get_by_id(concept_playlist.anchor_city_id) if concept_playlist.anchor_city_id else None
                    if not city:
                        city = city_svc.get_next_city()
                    if not city:
                        logger.error("No anchor city found for concept: %s", concept_playlist.slug)
                        return None
                    concept_playlist_svc.ensure_research(concept_playlist)
                    song = song_svc.create_concept_song(city.id, concept_playlist.id)
                    song_id = song.id
                    logger.info("Created song %s for concept: %s", song_id, concept_playlist.title)
                else:
                    city = target_obj
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

    @staticmethod
    def _next_target(city_svc: CityService, concept_playlist_svc: ConceptPlaylistService):
        """Choose the active city or concept playlist with the fewest generated songs."""
        from sqlalchemy import func
        from src.storage.models import City, ConceptPlaylist, Song

        city_counts = dict(
            city_svc.session.query(Song.city_id, func.count(Song.id))
            .filter(Song.concept_playlist_id.is_(None))
            .group_by(Song.city_id)
            .all()
        )
        concept_counts = dict(
            city_svc.session.query(Song.concept_playlist_id, func.count(Song.id))
            .filter(Song.concept_playlist_id.isnot(None))
            .group_by(Song.concept_playlist_id)
            .all()
        )
        candidates = []
        for city in city_svc.session.query(City).filter_by(is_active=True).all():
            candidates.append(("city", city, city_counts.get(city.id, 0), city.sort_order))
        for concept in concept_playlist_svc.get_all_active():
            candidates.append(("concept", concept, concept_counts.get(concept.id, 0), concept.sort_order))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[2], item[3], item[0]))
        target_type, target_obj, _, _ = candidates[0]
        return target_type, target_obj
