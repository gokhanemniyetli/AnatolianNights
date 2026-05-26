"""
ConceptPlaylistService — manages non-city playlist concepts and their research notes.
"""

import json
import logging
import re
from datetime import date, datetime
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, urlopen

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.storage.models import City, ConceptPlaylist, Song

logger = logging.getLogger(__name__)

_CATALOG_JSON = Path(__file__).parent.parent.parent / "data" / "concepts" / "concept_playlists.json"
_RESEARCH_DIR = Path(__file__).parent.parent.parent / "data" / "concepts" / "research"


class ConceptPlaylistService:
    def __init__(self, session: Session):
        self.session = session

    def seed_concepts(self) -> int:
        raw = json.loads(_CATALOG_JSON.read_text(encoding="utf-8"))
        inserted = 0
        for item in raw:
            concept = self.session.query(ConceptPlaylist).filter_by(slug=item["slug"]).first()
            anchor_city = self.session.query(City).filter_by(slug=item.get("anchor_city_slug")).first()
            if concept:
                concept.title = item["title"]
                concept.group = item["group"]
                concept.sort_order = item["sort_order"]
                concept.anchor_city_id = anchor_city.id if anchor_city else concept.anchor_city_id
                continue
            concept = ConceptPlaylist(
                title=item["title"],
                slug=item["slug"],
                group=item["group"],
                sort_order=item["sort_order"],
                anchor_city_id=anchor_city.id if anchor_city else None,
                is_active=True,
            )
            concept.set_style_profile(self._default_style_profile(item["title"], item["group"]))
            self.session.add(concept)
            inserted += 1
        self.session.flush()
        logger.info("Seeded %d concept playlists", inserted)
        return inserted

    def get_by_slug(self, slug: str) -> ConceptPlaylist | None:
        return self.session.query(ConceptPlaylist).filter_by(slug=slug, is_active=True).first()

    def get_by_group(self, group: str) -> list[ConceptPlaylist]:
        return (
            self.session.query(ConceptPlaylist)
            .filter_by(group=group, is_active=True)
            .order_by(ConceptPlaylist.sort_order.asc())
            .all()
        )

    def get_all_active(self) -> list[ConceptPlaylist]:
        return (
            self.session.query(ConceptPlaylist)
            .filter_by(is_active=True)
            .order_by(ConceptPlaylist.sort_order.asc())
            .all()
        )

    def get_next_concept(self) -> ConceptPlaylist | None:
        counts = (
            self.session.query(Song.concept_playlist_id, func.count(Song.id).label("cnt"))
            .filter(Song.concept_playlist_id.isnot(None))
            .group_by(Song.concept_playlist_id)
            .subquery()
        )
        return (
            self.session.query(ConceptPlaylist)
            .outerjoin(counts, ConceptPlaylist.id == counts.c.concept_playlist_id)
            .filter(ConceptPlaylist.is_active == True)
            .order_by(func.coalesce(counts.c.cnt, 0).asc(), ConceptPlaylist.sort_order.asc())
            .first()
        )

    def ensure_research(self, concept: ConceptPlaylist) -> dict:
        existing = concept.get_research()
        if existing.get("summary") and existing.get("sources"):
            return existing

        _RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        path = _RESEARCH_DIR / f"{concept.slug}.json"
        if path.exists():
            research = json.loads(path.read_text(encoding="utf-8"))
            concept.set_research(research)
            self.session.flush()
            return research

        research = self._research_from_web(concept.title)
        path.write_text(json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8")
        concept.set_research(research)
        self.session.flush()
        return research

    def build_profile(self, concept: ConceptPlaylist) -> dict:
        research = self.ensure_research(concept)
        style_profile = concept.get_style_profile() or self._default_style_profile(concept.title, concept.group)
        return {
            "mode": "concept",
            "concept_title": concept.title,
            "concept_slug": concept.slug,
            "group": concept.group,
            "research": research,
            "style_profile": style_profile,
            "instruments": {"primary": style_profile.get("instruments", ["bağlama", "synth pad"])},
            "visual_atmosphere": style_profile.get("visual_atmosphere", {}),
        }

    def create_youtube_playlists_batch(
        self,
        daily_limit: int = 20,
        youtube_client=None,
    ) -> dict:
        """
        Gradually create YouTube playlists for concept playlists that don't have one yet.
        Respects daily_limit and tracks progress in data/playlist_creation_progress.json.
        Returns a summary dict: {created, skipped, remaining, daily_remaining}.
        """
        progress_path = Path(__file__).parent.parent.parent / "data" / "playlist_creation_progress.json"
        today = date.today().isoformat()

        if progress_path.exists():
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
        else:
            progress = {"last_creation_date": None, "created_today": 0, "total_created": 0, "daily_limit": daily_limit}

        if progress.get("last_creation_date") != today:
            progress["last_creation_date"] = today
            progress["created_today"] = 0

        progress["daily_limit"] = daily_limit
        slots_remaining = daily_limit - progress["created_today"]

        if slots_remaining <= 0:
            logger.info("Daily YouTube playlist creation limit (%d) reached for %s.", daily_limit, today)
            progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
            return {"created": 0, "skipped": 0, "remaining": 0, "daily_remaining": 0}

        pending = (
            self.session.query(ConceptPlaylist)
            .filter(ConceptPlaylist.is_active == True, ConceptPlaylist.playlist_id.is_(None))
            .order_by(ConceptPlaylist.sort_order.asc())
            .limit(slots_remaining)
            .all()
        )

        created = skipped = 0
        for concept in pending:
            if youtube_client is None:
                logger.warning("No YouTube client provided; skipping playlist creation for '%s'.", concept.title)
                skipped += 1
                continue
            try:
                yt_id = self._create_youtube_playlist(youtube_client, concept)
                concept.playlist_id = yt_id
                progress["created_today"] += 1
                progress["total_created"] += 1
                created += 1
                logger.info("Created YouTube playlist '%s' → %s", concept.title, yt_id)
            except Exception as exc:
                logger.error("Failed to create YouTube playlist for '%s': %s", concept.title, exc)
                skipped += 1

        self.session.flush()
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")

        total_pending = (
            self.session.query(ConceptPlaylist)
            .filter(ConceptPlaylist.is_active == True, ConceptPlaylist.playlist_id.is_(None))
            .count()
        )
        return {
            "created": created,
            "skipped": skipped,
            "remaining": total_pending,
            "daily_remaining": daily_limit - progress["created_today"],
        }

    @staticmethod
    def _create_youtube_playlist(youtube_client, concept: ConceptPlaylist) -> str:
        """
        Create a YouTube playlist via the YouTube Data API client.
        Returns the playlist ID.
        """
        body = {
            "snippet": {
                "title": f"{concept.title} | Anatolian Nights",
                "description": (
                    f"Atmospheric Turkish lo-fi and ambient music — {concept.title} collection.\n"
                    "#AnatolianNights #TurkishLofi #AmbientMusic"
                ),
                "defaultLanguage": "en",
            },
            "status": {"privacyStatus": "public"},
        }
        response = (
            youtube_client.playlists()
            .insert(part="snippet,status", body=body)
            .execute()
        )
        return response["id"]

    @staticmethod
    def _research_from_web(title: str) -> dict:
        query = f"{title} atmospheric Turkish lo-fi ambient music Istanbul night"
        sources = ConceptPlaylistService._duckduckgo_search(query)
        source_text = " ".join(item.get("snippet", "") for item in sources)
        summary = ConceptPlaylistService._summarize_research(title, source_text)
        return {
            "title": title,
            "query": query,
            "researched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "summary": summary,
            "style_notes": ConceptPlaylistService._style_notes(title, source_text),
            "story_angles": ConceptPlaylistService._story_angles(title),
            "sources": sources,
        }

    @staticmethod
    def _duckduckgo_search(query: str, limit: int = 5) -> list[dict]:
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            logger.warning("Concept web research failed for '%s': %s", query, exc)
            return []

        results: list[dict] = []
        pattern = re.compile(
            r'<a rel="nofollow" class="result__a" href="(?P<url>[^"]+)".*?>(?P<title>.*?)</a>.*?'
            r'<a class="result__snippet".*?>(?P<snippet>.*?)</a>',
            re.DOTALL,
        )
        for match in pattern.finditer(html):
            clean_title = ConceptPlaylistService._clean_html(match.group("title"))
            snippet = ConceptPlaylistService._clean_html(match.group("snippet"))
            href = ConceptPlaylistService._normalize_result_url(unescape(match.group("url")))
            results.append({"title": clean_title, "url": href, "snippet": snippet})
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _clean_html(value: str) -> str:
        value = re.sub(r"<.*?>", " ", value)
        value = unescape(value)
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _normalize_result_url(value: str) -> str:
        if value.startswith("//"):
            value = "https:" + value
        parsed = urlparse(value)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            uddg = parse_qs(parsed.query).get("uddg", [""])[0]
            if uddg:
                return uddg
        return value

    @staticmethod
    def _summarize_research(title: str, source_text: str) -> str:
        if source_text:
            return (
                f"Web research for '{title}' concept; used to anchor atmospheric texture, "
                "instrument palette, and mood for Anatolian Nights production prompts."
            )
        return (
            f"No web results for '{title}'; production follows catalog style profile "
            "and Anatolian Nights atmospheric defaults."
        )

    @staticmethod
    def _style_notes(title: str, source_text: str) -> list[str]:
        notes = [
            "Keep tracks instrumental-first; target 3-5 minute duration.",
            "Each production should have a unique emotional anchor and never repeat the same title or hook.",
            f"All output must feel consistent with the '{title}' playlist atmosphere.",
        ]
        lowered = f"{title} {source_text}".casefold()
        if any(w in lowered for w in ["rain", "yağmur", "storm"]):
            notes.append("Emphasize wet ambience: rain on cobblestones, dripping eaves, distant thunder.")
        if any(w in lowered for w in ["bosphorus", "boğaz", "sea", "deniz"]):
            notes.append("Include water texture: Bosphorus waves, foghorns, distant seagull echoes.")
        if any(w in lowered for w in ["neon", "city", "urban", "tram", "metro"]):
            notes.append("Urban night texture: neon reflections, tram bells, distant traffic hum.")
        if any(w in lowered for w in ["fog", "sis", "mist"]):
            notes.append("Use fog as a sonic metaphor: reverb trails, washed-out pads, low-visibility mood.")
        if any(w in lowered for w in ["synthwave", "synth", "electronic", "cyber"]):
            notes.append("Lean into synthwave fusion: retro synth pads layered over bağlama or ney textures.")
        return notes

    @staticmethod
    def _story_angles(title: str) -> list[str]:
        base = [
            "a solitary figure watching rain streak down a café window",
            "the Bosphorus at 3am, ferry lights dissolving into fog",
            "a neon sign reflected in a puddle on Istiklal Street",
            "the last tram running through empty Galata streets",
            "distant call to prayer heard through a half-open apartment window",
            "smoke curling in a dim tea house, late-night city hum outside",
            "the feeling of a city that never fully sleeps",
        ]
        lowered = title.casefold()
        if any(w in lowered for w in ["rain", "storm", "wet"]):
            return ["rain on the Galata Bridge", "sound of rain on a copper rooftop", *base[:4]]
        if any(w in lowered for w in ["bosphorus", "sea", "water"]):
            return ["fog rolling in from the Bosphorus", "a ferry crossing at dusk", *base[:4]]
        if any(w in lowered for w in ["neon", "city", "night drive"]):
            return ["highway lights at 2am", "neon kanji reflected in wet asphalt", *base[:4]]
        return base

    @staticmethod
    def _default_style_profile(title: str, group: str) -> dict:
        lowered = title.casefold()
        # Defaults by group
        group_instruments = {
            "istanbul-night": ["bağlama textures", "synth pad", "vinyl crackle", "ambient guitar"],
            "anatolian-ambient": ["ney flute", "bağlama", "synth pad", "bendir"],
            "lo-fi-chill": ["lo-fi drums", "ambient guitar", "bağlama", "vinyl crackle"],
            "synthwave-fusion": ["retro synth", "elektro bağlama", "lo-fi drums", "bass synth"],
            "radio-session": ["bağlama", "acoustic guitar", "brush drums", "room ambience"],
            "night-atmosphere": ["synth pad", "ney flute", "ambient texture", "sparse piano"],
        }
        instruments = group_instruments.get(group, ["bağlama", "synth pad", "ambient guitar"])

        # Override by keyword hints in title
        if any(w in lowered for w in ["rain", "storm", "fog"]):
            instruments = ["rain texture", "synth pad", "ney flute", "distant piano"]
        elif any(w in lowered for w in ["synthwave", "neon", "cyber", "drive"]):
            instruments = ["retro synth", "bass synth", "elektro bağlama", "lo-fi drums"]
        elif any(w in lowered for w in ["ney", "sufi", "mystic", "ottoman"]):
            instruments = ["ney", "bendir", "ambient pad", "bağlama"]
        elif any(w in lowered for w in ["jazz", "café", "cafe", "session"]):
            instruments = ["acoustic guitar", "brush drums", "bağlama", "room ambience"]

        return {
            "tempo": "slow-to-mid atmospheric",
            "vocal": "ambient vocal or instrumental",
            "instruments": instruments,
            "avoid": [
                "loud pop production",
                "traditional folk tavır",
                "upbeat dance rhythms",
                "explicit lyrics",
            ],
            "visual_atmosphere": {
                "colors": ["deep navy", "midnight blue", "neon cyan", "amber street light"],
                "landscape": "Istanbul or Anatolia at night — cinematic urban or misty natural",
                "lighting": "low-key, neon-lit, foggy, moody",
                "season_suggestions": ["rainy autumn", "winter night", "foggy spring"],
            },
            "group": group,
        }
