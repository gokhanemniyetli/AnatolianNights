"""
ConceptPlaylistService — manages non-city playlist concepts and their research notes.
"""

import json
import logging
import re
from datetime import datetime
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
            "instruments": {"primary": style_profile.get("instruments", ["bağlama"])},
            "visual_atmosphere": style_profile.get("visual_atmosphere", {}),
        }

    @staticmethod
    def _research_from_web(title: str) -> dict:
        query = f"{title} Türk halk müziği özellikleri yöre tavır enstrüman"
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
                f"{title} konsepti için kayıtlı web araştırması; yöre/tavır, duygu, "
                "ritim ve çalgı ipuçlarını üretim promptuna bağlamak için kullanılır."
            )
        return (
            f"{title} konsepti için web sonucu alınamadı; üretim, katalogdaki tarz profili "
            "ve Anadolu türkü formu kurallarına göre yapılır."
        )

    @staticmethod
    def _style_notes(title: str, source_text: str) -> list[str]:
        notes = [
            "Türkü kısa tutulur; toplam süre hedefi 3-4 dakikayı geçmez.",
            "Her üretimde yeni bir insan hikayesi, yeni başlık ve farklı duygu ekseni seçilir.",
            f"Ana playlist kimliği açıkça {title} konseptine bağlı kalır.",
        ]
        lowered = f"{title} {source_text}".casefold()
        if "zeybek" in lowered:
            notes.append("Ağırbaşlı zeybek tavrı, dokuz zamanlı his ve efe vakarını öne çıkar.")
        if "halay" in lowered:
            notes.append("Toplu oyun enerjisi, davul-zurna hissi ve ritmik canlılık korunur.")
        if "bozlak" in lowered or "uzun hava" in lowered:
            notes.append("Serbest uzun hava tavrı, geniş nefesli vokal ve içli anlatım öne çıkar.")
        if "karadeniz" in lowered or "kemençe" in lowered:
            notes.append("Kemençe, hızlı kıvraklık, yayla/deniz/dağ imgeleri dengeli kullanılır.")
        if "ege" in lowered:
            notes.append("Zeybek, efe, ova, zeytinlik ve deniz imgesi doğal bir arka plan sağlar.")
        if "iç anadolu" in lowered or "ic anadolu" in lowered:
            notes.append("Bozkır, bağlama, bozlak/kırık hava tavrı ve sade hikaye dili öne çıkar.")
        return notes

    @staticmethod
    def _story_angles(title: str) -> list[str]:
        base = [
            "gurbetten eve dönme isteği",
            "kavuşamayan iki sevenin bekleyişi",
            "aile sofrası ve emek",
            "yolculukta hatırlanan eski söz",
            "köyden kente taşınan bir hatıra",
            "düğün, kına veya bayram telaşı",
            "ustaya, toprağa veya geçmişe vefa",
        ]
        lowered = title.casefold()
        if "asker" in lowered:
            return ["asker yolu bekleyen yâr", "ana duası", "terhis günü umudu", *base[:2]]
        if "gurbet" in lowered or "hasret" in lowered:
            return ["gurbette yazılan mektup", "tren garında bekleyiş", "baba ocağına dönüş", *base]
        if "düğün" in lowered or "gelin" in lowered or "kına" in lowered:
            return ["gelin alma sabahı", "kına gecesinde vedalaşma", "çeyiz sandığı hatırası", *base]
        return base

    @staticmethod
    def _default_style_profile(title: str, group: str) -> dict:
        lowered = title.casefold()
        instruments = ["bağlama", "kaval"]
        tempo = "orta-yavaş"
        vocal = "duygulu Türk halk müziği vokali"
        if "karadeniz" in lowered or "kemençe" in lowered:
            instruments = ["kemençe", "tulum", "bağlama"]
            tempo = "orta-hareketli"
        elif "ege" in lowered or "zeybek" in lowered:
            instruments = ["bağlama", "cura", "davul"]
            tempo = "ağır zeybek"
        elif "halay" in lowered:
            instruments = ["davul", "zurna", "bağlama"]
            tempo = "hareketli"
        elif "ney" in lowered or "ambient" in lowered or "ottoman" in lowered:
            instruments = ["ney", "bağlama", "bendir"]
            tempo = "yavaş atmosferik"
        elif "rock" in lowered:
            instruments = ["elektro bağlama", "bağlama", "davul"]
            tempo = "orta tempolu modern"
        elif any(term in lowered for term in ["elektronik", "synthwave", "cyber", "edm", "trap", "phonk"]):
            instruments = ["elektro bağlama", "synth pad", "ritmik davul"]
            tempo = "modern ritmik"
        if "kadın vokal" in lowered:
            vocal = "duygulu kadın Türk halk müziği vokali"
        elif "erkek vokal" in lowered:
            vocal = "duygulu erkek Türk halk müziği vokali"
        elif "düet" in lowered:
            vocal = "kadın ve erkek düet vokal"

        return {
            "tempo": tempo,
            "vocal": vocal,
            "instruments": instruments,
            "avoid": [
                "konsept dışına çıkan şehir tanıtımı",
                "aynı başlık ve aynı hikaye tekrarı",
                "4 dakikayı aşan uzun yapı",
            ],
            "visual_atmosphere": {
                "colors": ["toprak tonları", "gün batımı altını", "gece mavisi"],
                "landscape": "Anadolu coğrafyasına uygun sinematik doğal manzara",
                "lighting": "doğal, şiirsel, kontrastı dengeli ışık",
                "season_suggestions": ["bahar", "sonbahar", "kış akşamı"],
            },
            "group": group,
        }
