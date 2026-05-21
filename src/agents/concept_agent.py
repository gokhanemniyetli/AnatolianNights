"""
ConceptAgent — generates a unique song concept for a given city.
Receives city cultural profile + generation history to avoid repetition.
"""

import json
import re
from pathlib import Path

from src.agents.base_agent import BaseAgent
from src.config.models_config import get_model

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "concept.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_EMOTION_RE = re.compile(
    r"(aşk|sevda|gurbet|ayrılık|hasret|özlem|kavuş|düğün|ana|baba|asker|göç|hasat|umut|bekleyiş|sitem|emek|bereket|dönüş|y[aâ]r|barış|kırgın|naz|ağıt|bayram|nişan|kına|mektup|dua|helallik|komşu|kardeş|çocuk|ocak|sofra|pazar|yayla|imece|yolcu|emanet|rüya|söz|gönül|mahcup|pişman)",
    re.IGNORECASE,
)

_TITLE_SIGNAL_RE = re.compile(
    r"(aşk|sevda|gurbet|ayrılık|hasret|özlem|kavuş|düğün|ana|baba|asker|göç|hasat|umut|bekleyiş|sitem|emek|bereket|dönüş|y[aâ]r|barış|kırgın|naz|bayram|nişan|kına|mektup|dua|helallik|komşu|kardeş|çocuk|ocak|sofra|pazar|imece|yolcu|emanet|rüya|söz|gönül|mahcup|pişman)",
    re.IGNORECASE,
)
_OBJECT_RE = re.compile(
    r"(dağ|tepe|göl|nehir|dere|çay|su|ova|kale|kule|yol|sır|köprü|saray|orman|yayla|vadi|boğaz|deniz)",
    re.IGNORECASE,
)

_FALLBACK_CONCEPTS = [
    ("Gurbet Mektubu", "gurbet mektubu", "Gurbete giden birinin evde bıraktığı yârine ve ailesine yazdığı mektubu anlatır. Yöresel imgeler yalnızca hatıra olarak geçer; ana duygu hasret ve eve dönme isteğidir."),
    ("Yâr Kapıda Bekler", "bekleyiş", "Sevdiğinden haber bekleyen bir anlatıcının iç sızısını işler. Türkü, sabır ve kavuşma ihtimalinin verdiği ince heyecan üzerine kurulur."),
    ("Anamın Duası", "ana duası", "Uzakta kalan bir evladın annesinin sesini, duasını ve baba ocağını özlemesini anlatır. Ana duygu şefkat, pişmanlık ve eve dönme arzusudur."),
    ("Kavuşma Sabahı", "kavuşma", "Ayrı düşen iki sevgilinin bütün zorluğa rağmen yeniden buluşma umudunu anlatır. Türküde ana eksen sevda, sabır ve umut olur."),
    ("Kına Gecesi", "kına", "Bir kına gecesinde gelinin içindeki sevinç ve ince hüznü konu alır. Ana duygu aile, vedalaşma ve yeni hayata adım atmaktır."),
    ("Sitemli Yâr", "sitem", "Söz verip giden bir sevgiliye duyulan kırgınlığı ve içten sitemi anlatır. Türkü, gururlu ama yaralı bir anlatıcının dilinden söylenir."),
    ("Helal Sofra", "emek", "Alın teriyle geçinen insanların günlük emeğini ve sofradaki bereketi anlatır. Ana duygu dayanışma, sabır ve helal kazançtır."),
    ("Asker Yolu", "asker bekleyişi", "Askere giden bir gencin ardında kalan yârinin ve ailesinin bekleyişini anlatır. Ana duygu özlem, dua ve dönüş umududur."),
    ("Barış Elçisi", "barışma", "Küskün iki ailenin bir büyüğün sözüyle yeniden barışmasını anlatır. Ana duygu olgunluk, bağışlama ve birliktir."),
    ("Pazar Sabahı", "gündelik hayat", "Sabah pazarına inen insanların telaşını, komşuluğunu ve küçük sevinçlerini anlatır. Türkü sıcak, canlı ve insan hikayesi merkezlidir."),
    ("İmece Türküsü", "dayanışma", "Bir köyde herkesin birbirine omuz verip işi birlikte bitirmesini anlatır. Ana duygu yardımlaşma, emek ve ortak sevinçtir."),
    ("Mahcup Sevda", "utangaç aşk", "Sevdiğini açıkça söyleyemeyen bir anlatıcının mahcup ama derin sevdasını anlatır. Türkü ince, zarif ve içtendir."),
    ("Baba Ocağı", "eve dönüş", "Yıllar sonra baba ocağına dönen birinin çocukluk hatıralarıyla yüzleşmesini anlatır. Ana duygu dönüş, pişmanlık ve sıcaklık olur."),
    ("Bayram Sabahı", "bayram", "Bayram sabahında ev halkının hazırlığını, büyüklerin duasını ve çocukların sevincini anlatır. Türkü neşeli ama geleneksel bir sıcaklık taşır."),
    ("Emanet Mendil", "emanet sevda", "Sevdiğinden kalan küçük bir emaneti saklayan anlatıcının hatırasını anlatır. Ana duygu sadakat, sevda ve sabırdır."),
]

_GENERIC_TITLE_RE = re.compile(
    r"^(yas|veda|ağıt|hasret|sevda|aşk|umut|gurbet|ayrılık)$",
    re.IGNORECASE,
)

_OVERUSED_RECENT_RE = re.compile(
    r"\b(yas|veda|ağıt|hüzün)\b|ağlı|ağla|vedal|yaslı|yasam",
    re.IGNORECASE,
)

_THEME_FAMILIES = [
    "utangaç sevda",
    "karşılıksız aşk",
    "gurbet mektubu",
    "asker bekleyişi",
    "kına gecesi",
    "düğün sevinci",
    "ana duası",
    "baba ocağına dönüş",
    "kardeş özlemi",
    "komşu dayanışması",
    "imece ve emek",
    "hasat bereketi",
    "pazar sabahı",
    "yayla göçü",
    "bayram sabahı",
    "barışma",
    "sitemli yâr",
    "helallik",
    "emanet sevda",
    "çocukluk hatırası",
    "pişmanlık",
    "yolcu uğurlama",
    "kavuşma sabahı",
    "nazlı yâr",
    "ev kurma telaşı",
    "ocak başı sohbeti",
]


class ConceptAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            task="concept",
            model=get_model("concept"),
            system_prompt=_SYSTEM_PROMPT,
        )

    def generate(
        self,
        city_name: str,
        cultural_profile: dict,
        generation_history: dict,
    ) -> dict:
        """
        Returns a concept dict with keys:
        title, theme, story, mood, tempo, vocal, instruments, avoid, season, narrator
        """
        user_prompt = f"""
Şehir: {city_name}

KÜLTÜREL PROFİL:
{json.dumps(cultural_profile, ensure_ascii=False, indent=2)}

DAHA ÖNCE KULLANILAN (BUNLARI TEKRARLAMA):
- Temalar: {generation_history.get('used_themes', [])}
- Tempolar: {generation_history.get('used_tempos', [])}
- Duygular: {generation_history.get('used_moods', [])}
- Enstrümanlar: {generation_history.get('used_instruments', [])}
- Başlıklar: {generation_history.get('used_titles', [])}

KANAL GENELİNDE SON KULLANILANLAR (BUNLARI DA TEKRARLAMA):
- Son temalar: {generation_history.get('recent_global_themes', [])}
- Son başlıklar: {generation_history.get('recent_global_titles', [])}

GENİŞ TEMA HAVUZU:
{", ".join(_THEME_FAMILIES)}

Bu şehir için YENİ ve FARKLI bir türkü konsepti oluştur.
Öncelik duygu/insan hikayesi olsun; yöresel yerler, yemekler, doğa ve tarihi dokular sadece sahne ve imge olarak kalsın.
Bu kez ana tema olarak GENİŞ TEMA HAVUZU'ndan son kullanılanlara benzemeyen bir aile seç ve bunu açıkça işle.
Son kayıtlarda çok tekrar ettiği için "yas" ve "veda" ana tema veya başlık olarak kullanma; ancak hikayenin içinde küçük bir duygu tonu olarak geçebilir.
Başlığı sadece dağ, göl, yol, sır, kale, kule, ova, nehir gibi bir nesne/yer adı yapma; başlık duygu veya olay anlatmalı.
Başlık tek kelimelik genel bir ad olmasın; "Yas", "Veda", "Umut", "Hasret", "Sevda" gibi çıplak/generic başlıklar yasaktır.
Başlık 2-4 kelimelik, doğal ve yeni olmalı: örn. "Kına Gecesi", "Gurbet Mektubu", "Mahcup Sevda" gibi ama verilen geçmişte varsa aynısını kullanma.
"""
        last_result: dict = {}
        for attempt in range(3):
            retry_note = ""
            if attempt:
                retry_note = (
                    "\nÖNCEKİ DENEME REDDEDİLDİ: Başlık/tema fazla tekrar eden, generic veya yer-nesne merkezliydi. "
                    "Yeni denemede son kullanılan başlıklara/temalara benzemeyen 2-4 kelimelik özgün bir başlık ve farklı bir tema ailesi kullan.\n"
                )
            result = self.call(user_prompt + retry_note)
            last_result = result
            if self._is_valid_concept(result, generation_history):
                return result
        return self._fallback_concept(city_name, generation_history, last_result)

    @staticmethod
    def _is_valid_concept(concept: dict, generation_history: dict | None = None) -> bool:
        title = str(concept.get("title") or "")
        theme = str(concept.get("theme") or "")
        story = str(concept.get("story") or "")
        combined = " ".join([title, theme, story])
        has_emotion = bool(_EMOTION_RE.search(combined))
        object_title = bool(_OBJECT_RE.search(title))
        title_has_signal = bool(_TITLE_SIGNAL_RE.search(title))
        if object_title or _GENERIC_TITLE_RE.search(title.strip()):
            return False
        if len(title.split()) < 2:
            return False
        if not title_has_signal:
            return False
        if _OVERUSED_RECENT_RE.search(" ".join([title, theme, story])):
            return False
        if generation_history and ConceptAgent._duplicates_recent(title, theme, generation_history):
            return False
        return has_emotion

    @staticmethod
    def _duplicates_recent(title: str, theme: str, generation_history: dict) -> bool:
        recent_titles = generation_history.get("recent_global_titles", [])
        recent_themes = generation_history.get("recent_global_themes", [])
        local_titles = generation_history.get("used_titles", [])
        local_themes = generation_history.get("used_themes", [])
        for candidate, existing in (
            (title, [*recent_titles, *local_titles]),
            (theme, [*recent_themes, *local_themes]),
        ):
            candidate_norm = candidate.casefold().strip()
            if not candidate_norm:
                continue
            for item in existing:
                item_norm = str(item or "").casefold().strip()
                if not item_norm:
                    continue
                if candidate_norm == item_norm:
                    return True
        return False

    @staticmethod
    def _fallback_concept(city_name: str, generation_history: dict, last_result: dict) -> dict:
        used_titles = {
            str(item).casefold()
            for item in [
                *generation_history.get("used_titles", []),
                *generation_history.get("recent_global_titles", []),
            ]
        }
        used_themes = {
            str(item).casefold()
            for item in [
                *generation_history.get("used_themes", []),
                *generation_history.get("recent_global_themes", []),
            ]
        }
        selected = next(
            (
                item
                for item in _FALLBACK_CONCEPTS
                if item[0].casefold() not in used_titles
                and item[1].casefold() not in used_themes
            ),
            _FALLBACK_CONCEPTS[0],
        )
        title, theme, story = selected
        instruments = last_result.get("instruments") if isinstance(last_result, dict) else None
        avoid = last_result.get("avoid") if isinstance(last_result, dict) else None
        return {
            "title": title,
            "theme": theme,
            "story": f"{city_name} yöresinde geçen bu türkü, {story}",
            "mood": "içli, doğal, samimi",
            "tempo": "orta-yavaş geleneksel türkü",
            "vocal": "emotional Turkish folk vocal",
            "instruments": instruments if isinstance(instruments, list) and instruments else ["bağlama", "kaval"],
            "avoid": avoid if isinstance(avoid, list) else [],
            "season": "zamansız",
            "narrator": "duygusunu doğrudan anlatan kişi",
        }
