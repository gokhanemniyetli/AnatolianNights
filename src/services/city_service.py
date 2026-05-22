"""
CityService — loads city data from the DB and cultural profiles from disk.
"""

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from src.storage.models import City

logger = logging.getLogger(__name__)

_PROFILES_DIR = Path(__file__).parent.parent.parent / "data" / "cities" / "cultural_profiles"
_CITIES_JSON = Path(__file__).parent.parent.parent / "data" / "cities" / "cities.json"
_DIALECT_GUIDANCE_JSON = Path(__file__).parent.parent.parent / "data" / "cities" / "dialect_guidance.json"


class CityService:
    def __init__(self, session: Session):
        self.session = session

    # ── Seeding ───────────────────────────────────────────────────────

    def seed_cities(self) -> int:
        """Seed all 81 cities from cities.json. Skips already-existing rows. Returns inserted count."""
        raw = json.loads(_CITIES_JSON.read_text(encoding="utf-8"))
        inserted = 0
        for item in raw:
            exists = self.session.get(City, item["id"])
            if exists:
                continue
            city = City(
                id=item["id"],
                name=item["name"],
                slug=item["slug"],
                region=item["region"],
                sort_order=item.get("sort_order", item["id"]),
                is_active=True,
            )
            # Load cultural profile if available
            profile_path = _PROFILES_DIR / f"{item['slug']}.json"
            if profile_path.exists():
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                city.set_cultural_profile(profile)
            self.session.add(city)
            inserted += 1
        self.session.flush()
        logger.info("Seeded %d cities", inserted)
        return inserted

    # ── Queries ───────────────────────────────────────────────────────

    def get_by_slug(self, slug: str) -> City | None:
        return self.session.query(City).filter_by(slug=slug, is_active=True).first()

    def get_by_id(self, city_id: int) -> City | None:
        return self.session.get(City, city_id)

    def get_all_active(self) -> list[City]:
        return self.session.query(City).filter_by(is_active=True).order_by(City.sort_order).all()

    def get_next_city(self, exclude_slugs: list[str] | None = None) -> City | None:
        """Return the active city with fewest songs (for round-robin distribution)."""
        from sqlalchemy import func
        from src.storage.models import Song

        exclude_slugs = exclude_slugs or []

        # Subquery: count songs per city
        song_counts = (
            self.session.query(Song.city_id, func.count(Song.id).label("cnt"))
            .group_by(Song.city_id)
            .subquery()
        )

        city = (
            self.session.query(City)
            .outerjoin(song_counts, City.id == song_counts.c.city_id)
            .filter(City.is_active == True)
            .filter(~City.slug.in_(exclude_slugs))
            .order_by(func.coalesce(song_counts.c.cnt, 0).asc(), City.sort_order.asc())
            .first()
        )
        return city

    # ── Cultural profile ──────────────────────────────────────────────

    def load_cultural_profile(self, slug: str) -> dict:
        """Load cultural profile from disk. Falls back to empty dict."""
        profile_path = _PROFILES_DIR / f"{slug}.json"
        if profile_path.exists():
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            return self._with_dialect_guidance(slug, profile)
        logger.warning("No cultural profile found for %s", slug)
        return self._with_dialect_guidance(slug, {})

    def refresh_profile_in_db(self, slug: str) -> bool:
        """Re-read cultural profile from disk and update the City row."""
        city = self.get_by_slug(slug)
        if not city:
            return False
        profile = self.load_cultural_profile(slug)
        city.set_cultural_profile(profile)
        self.session.flush()
        return True

    @staticmethod
    def _with_dialect_guidance(slug: str, profile: dict) -> dict:
        if not _DIALECT_GUIDANCE_JSON.exists():
            return profile
        guidance = json.loads(_DIALECT_GUIDANCE_JSON.read_text(encoding="utf-8"))
        cities = json.loads(_CITIES_JSON.read_text(encoding="utf-8")) if _CITIES_JSON.exists() else []
        city_info = next((item for item in cities if item.get("slug") == slug), {})
        region = profile.get("region") or city_info.get("region")
        regional = guidance.get("regional_defaults", {}).get(region, {})
        city_specific = guidance.get("city_overrides", {}).get(slug, {})
        merged = {**regional, **city_specific}
        if merged:
            profile["dialect_guidance"] = merged
        if guidance.get("sources"):
            profile["dialect_guidance_sources"] = guidance["sources"]
        return profile
