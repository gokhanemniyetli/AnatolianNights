"""
ConceptAgent — generates a unique atmospheric track concept for Anatolian Nights channel.
Receives playlist/concept profile and generation history to avoid repetition.
"""

import json
import re
from pathlib import Path

from src.agents.base_agent import BaseAgent
from src.config.models_config import get_model

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "concept.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_VALID_TRACK_TYPES = {"instrumental", "ambient_vocal", "lyrical"}

_GENERIC_TITLE_RE = re.compile(
    r"^(ambient track|lo.?fi track|turkish track|anatolian track|track \d+|untitled|song \d+)$",
    re.IGNORECASE,
)

_FALLBACK_CONCEPTS = [
    {
        "title": "Rain Over Galata",
        "theme": "urban loneliness",
        "story": "A rainy night walk through old Istanbul streets — distant ferry horns and wet cobblestones echoing with memory.",
        "mood": "melancholic, dreamy, reflective",
        "tempo": "slow, 72 BPM, lo-fi groove",
        "track_type": "lyrical",
        "vocal": "atmospheric Turkish vocals, soft modern delivery, 2 verses and 1 chorus",
        "instruments": ["soft bağlama", "warm synth pads", "lo-fi drums", "vinyl crackle"],
        "ambience": ["rain", "distant ferry horn", "wet streets"],
        "visual": "rainy Istanbul at night, neon reflections on wet cobblestones, Galata Tower silhouette in mist",
        "avoid": ["upbeat tempos", "folk stage feeling", "loud vocals"],
    },
    {
        "title": "Bosphorus After Midnight",
        "theme": "quiet solitude",
        "story": "The Bosphorus at 2am — empty ferries drifting, city lights blurred by fog, time suspended.",
        "mood": "peaceful, lonely, nostalgic",
        "tempo": "very slow, 65 BPM, ambient",
        "track_type": "lyrical",
        "vocal": "atmospheric Turkish vocals, soft modern delivery, 2 verses and 1 chorus",
        "instruments": ["analog synths", "soft ney flute", "ambient guitar", "field recording"],
        "ambience": ["Bosphorus waves", "distant traffic", "foghorn"],
        "visual": "Bosphorus at midnight, city lights reflecting on dark water, a lone ferry disappearing into fog",
        "avoid": ["energetic rhythms", "traditional folk feel", "vocals"],
    },
    {
        "title": "Neon Reflections on the Tram",
        "theme": "midnight city drift",
        "story": "A late-night tram ride through the illuminated streets of Istanbul — neon signs blurring in the rain.",
        "mood": "dreamy, urban, atmospheric",
        "tempo": "slow-medium, 78 BPM, lo-fi",
        "track_type": "lyrical",
        "vocal": "atmospheric Turkish vocals, soft modern delivery, 2 verses and 1 chorus",
        "instruments": ["electric piano", "lo-fi drums", "warm bass", "vinyl texture"],
        "ambience": ["tram sounds", "rain", "neon city hum"],
        "visual": "empty Istanbul tram at night, neon lights reflecting on rain-soaked tracks, fog-lit windows",
        "avoid": ["folk instruments", "traditional style", "upbeat energy"],
    },
    {
        "title": "Anatolian Night Drive",
        "theme": "solitary road journey",
        "story": "Driving through the Anatolian plateau at night — endless dark roads, distant village lights, thoughts wandering.",
        "mood": "reflective, lonely, serene",
        "tempo": "medium, 80 BPM, chill lo-fi",
        "track_type": "lyrical",
        "vocal": "atmospheric Turkish vocals, soft modern delivery, 2 verses and 1 chorus",
        "instruments": ["soft bağlama texture", "synth pads", "lo-fi drums", "ambient guitar"],
        "ambience": ["highway wind", "distant crickets", "vinyl crackle"],
        "visual": "dark Anatolian highway at night, headlights illuminating empty road, vast starry sky above",
        "avoid": ["energetic", "pop production", "loud mix"],
    },
    {
        "title": "Istanbul Fog Sessions",
        "theme": "foggy urban morning",
        "story": "Istanbul at 5am in dense fog — the city barely visible, a silence broken only by distant mosque calls.",
        "mood": "serene, ethereal, contemplative",
        "tempo": "slow, 68 BPM, ambient",
        "track_type": "lyrical",
        "vocal": "soft breathy Turkish vocals, minimal lyrics, reverb-heavy delivery",
        "instruments": ["ney flute", "minimal piano", "ambient synth wash", "soft percussion"],
        "ambience": ["fog", "distant adhan", "light rain"],
        "visual": "Istanbul skyline disappearing into thick morning fog, mosques barely visible, golden light filtering through mist",
        "avoid": ["high energy", "loud drums", "folk stage performance"],
    },
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
        forced_title: str | None = None,
    ) -> dict:
        """Generate a track concept using city as the anchor atmosphere."""
        concept_profile = {
            "concept_title": f"{city_name} Night Atmosphere",
            "group": "istanbul-night",
            "style_profile": {
                "instruments": ["soft bağlama", "synth pads", "lo-fi drums"],
                "mood": "atmospheric, night, cinematic",
            },
        }
        return self.generate_for_playlist(
            playlist_title=f"{city_name} Nights",
            concept_profile=concept_profile,
            generation_history=generation_history,
            forced_title=forced_title,
        )

    def generate_for_playlist(
        self,
        playlist_title: str,
        concept_profile: dict,
        generation_history: dict,
        forced_title: str | None = None,
    ) -> dict:
        """Generate a track concept for a playlist atmosphere."""
        style_profile = concept_profile.get("style_profile", {}) or {}
        group = concept_profile.get("group", "")

        if forced_title:
            title_instruction = f"""SONG TITLE (FIXED — YOU MUST USE EXACTLY THIS, DO NOT CHANGE IT): "{forced_title}"

This is a modern Turkish title evoking Istanbul nights, rain, neon lights, ferries, trams, and urban solitude.
Build the ENTIRE concept around this title. The genre is Turkish Lo-fi / Anatolian Ambient — NOT folk, NOT türkü."""
        else:
            title_instruction = "Generate a cinematic Turkish title (2-5 words) that evokes Istanbul nights, rain, neon, ferries, or urban solitude."

        user_prompt = f"""
PLAYLIST: {playlist_title}
GROUP: {group}

{title_instruction}

STYLE PROFILE:
{json.dumps(style_profile, ensure_ascii=False, indent=2)}

PREVIOUSLY USED — DO NOT REPEAT:
- Themes: {generation_history.get('used_themes', [])}
- Moods: {generation_history.get('used_moods', [])}
- Instruments: {generation_history.get('used_instruments', [])}
- Titles: {generation_history.get('used_titles', [])}

RECENTLY USED ACROSS CHANNEL — AVOID:
- Recent themes: {generation_history.get('recent_global_themes', [])}
- Recent titles: {generation_history.get('recent_global_titles', [])}

Generate a NEW, UNIQUE atmospheric track concept that perfectly matches this playlist's atmosphere.
GENRE: Turkish Lo-fi / Anatolian Ambient. NOT folk. NOT türkü. NOT traditional performance.
Set track_type to "lyrical" for every new song, with atmospheric Turkish vocals and a short 2-verse + 1-chorus lyric structure.
"""
        last_result: dict = {}
        for attempt in range(3):
            retry_note = ""
            if attempt:
                retry_note = (
                    "\nPREVIOUS ATTEMPT REJECTED: Concept didn't match channel identity. "
                    "GENRE = Turkish Lo-fi / Anatolian Ambient. NOT folk, NOT türkü. "
                    "Mood must be: atmospheric, cinematic, dreamy, urban night. NOT 'içli, samimi, geleneksel'.\n"
                )
                if forced_title:
                    retry_note += f'Remember: use EXACTLY this title: "{forced_title}"\n'
            result = self.call(user_prompt + retry_note)
            last_result = result
            # If forced_title, override whatever title the LLM produced
            if forced_title:
                result["title"] = forced_title
            result["track_type"] = "lyrical"
            result["vocal"] = "atmospheric Turkish vocals, soft modern delivery, 2 verses and 1 chorus"
            if self._is_valid_concept(result, generation_history if not forced_title else None):
                result.setdefault("playlist_concept", playlist_title)
                return result
        # Fallback
        if forced_title:
            last_result["title"] = forced_title
            last_result.setdefault("playlist_concept", playlist_title)
            if last_result.get("track_type") not in _VALID_TRACK_TYPES:
                last_result["track_type"] = "lyrical"
            last_result["track_type"] = "lyrical"
            last_result["vocal"] = "atmospheric Turkish vocals, soft modern delivery, 2 verses and 1 chorus"
            last_result.setdefault("theme", "urban night atmosphere")
            return last_result
        fallback = self._fallback_concept(playlist_title, generation_history)
        fallback["playlist_concept"] = playlist_title
        fallback["track_type"] = "lyrical"
        fallback["vocal"] = "atmospheric Turkish vocals, soft modern delivery, 2 verses and 1 chorus"
        return fallback

    @staticmethod
    def _is_valid_concept(concept: dict, generation_history: dict | None = None) -> bool:
        title = str(concept.get("title") or "").strip()
        theme = str(concept.get("theme") or "").strip()
        track_type = str(concept.get("track_type") or "").strip().lower()

        if not title or len(title.split()) < 2:
            return False
        if _GENERIC_TITLE_RE.match(title):
            return False
        if track_type not in _VALID_TRACK_TYPES:
            return False
        if not theme:
            return False

        if generation_history:
            used_titles = {str(t).casefold() for t in generation_history.get("used_titles", [])}
            used_titles.update(str(t).casefold() for t in generation_history.get("recent_global_titles", []))
            if title.casefold() in used_titles:
                return False

        return True

    @staticmethod
    def _fallback_concept(playlist_title: str, generation_history: dict) -> dict:
        used_titles = {
            str(item).casefold()
            for item in [
                *generation_history.get("used_titles", []),
                *generation_history.get("recent_global_titles", []),
            ]
        }
        selected = next(
            (c for c in _FALLBACK_CONCEPTS if c["title"].casefold() not in used_titles),
            _FALLBACK_CONCEPTS[0],
        )
        return dict(selected)


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
    ("Yayla Dönüşü", "yayla dönüşü", "Yaz yaylasından köye dönen ailelerin telaşını ve içlerinde kalan ferahlığı anlatır. Ana duygu eve varma sevinci, emek ve komşuluk sıcaklığıdır."),
    ("Harman Sevinci", "hasat bereketi", "Harman sonunda köy meydanında paylaşılan ekmeği ve emeğin karşılığını anlatır. Türküde yorgunluk değil, bereket ve dayanışma öne çıkar."),
    ("Komşu Kapısı", "komşuluk", "Dar günde birbirinin kapısını çalan komşuların hal hatırını anlatır. Ana duygu dayanışma, vefa ve küçük iyiliklerin büyüklüğüdür."),
    ("Söz Mendili", "nişan heyecanı", "Nişan günü saklanan bir mendilin iki gencin mahcup sevincine dönüşmesini anlatır. Ana duygu utangaç sevda ve aile rızasıdır."),
    ("Ocak Başında", "aile sohbeti", "Kış akşamı ocak başında toplanan ailenin eski günleri ve gelecek umudunu konuşmasını anlatır. Ana duygu sıcaklık, aidiyet ve huzurdur."),
]

_BANNED_TITLE_RE = re.compile(
    r"^(yas|yas\s*\d+|veda|ağıt|hüzün|hasret|sevda|aşk|umut|gurbet|ayrılık)$",
    re.IGNORECASE,
)

_OVERUSED_RECENT_RE = re.compile(
    r"\b(yas|veda|ağıt|hüzün)\b|ağlı|ağla|vedal|yaslı|yasam",
    re.IGNORECASE,
)

_BANNED_MAIN_THEME_RE = re.compile(
    r"^(yas|veda|ağıt|hüzün|ölüm|matem|felaket)$",
    re.IGNORECASE,
)

_AWKWARD_TITLE_RE = re.compile(
    r"\b(duygu|hikaye|öykü|konu|tema|sevinci\s+sevinci|hüznü)\b",
    re.IGNORECASE,
)

_AWKWARD_STORY_RE = re.compile(
    r"\bözlemedikleri\b|\bduygu\s+sevinci\b|\bhikayesi\b.*\bhikaye\b",
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
    "harman sevinci",
    "su başı sohbeti",
    "çeyiz hazırlığı",
    "pazar dönüşü",
    "toy daveti",
    "yayla dönüşü",
    "sürmeli sevda",
    "gelin alma",
    "el emeği",
    "ustaya saygı",
    "çoban türküsü",
    "bahar karşılaması",
    "tarla dönüşü",
    "kardeş barışması",
    "komşu kapısı",
    "söz mendili",
]


# ─ End of ConceptAgent ─
