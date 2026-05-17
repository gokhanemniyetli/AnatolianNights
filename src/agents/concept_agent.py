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
    r"(aşk|sevda|gurbet|ayrılık|hasret|özlem|kavuş|düğün|ana|baba|asker|göç|hasat|yas|umut|bekleyiş|sitem|emek|bereket|veda|dönüş|y[aâ]r|barış|kırgın)",
    re.IGNORECASE,
)
_OBJECT_RE = re.compile(
    r"(dağ|tepe|göl|nehir|dere|çay|su|ova|kale|kule|yol|sır|köprü|saray|orman|yayla|vadi|boğaz|deniz)",
    re.IGNORECASE,
)

_FALLBACK_CONCEPTS = [
    ("Gurbet Hasreti", "gurbet", "Gurbete giden birinin evde bıraktığı yârine ve ailesine duyduğu özlemi anlatır. Yöresel imgeler yalnızca hatıra olarak geçer; ana duygu hasret ve eve dönme isteğidir."),
    ("Yâr Bekleyişi", "bekleyiş", "Sevdiğinden haber bekleyen bir anlatıcının iç sızısını işler. Türkü, sabır, umut ve kavuşma ihtimalinin verdiği ince heyecan üzerine kurulur."),
    ("Ana Özlemi", "ana özlemi", "Uzakta kalan bir evladın annesinin sesini, duasını ve baba ocağını özlemesini anlatır. Ana duygu şefkat, pişmanlık ve eve dönme arzusudur."),
    ("Kavuşma Umudu", "kavuşma", "Ayrı düşen iki sevgilinin bütün zorluğa rağmen yeniden buluşma umudunu anlatır. Türküde ana eksen sevda, sabır ve umut olur."),
    ("Düğün Sevinci", "düğün", "Bir köy düğününde iki ailenin barışıp sevinci paylaşmasını konu alır. Ana duygu neşe, birlik ve berekettir."),
    ("Ayrılık Sitemi", "ayrılık", "Söz verip giden bir sevgiliye duyulan kırgınlığı ve içten sitemi anlatır. Türkü, gururlu ama yaralı bir anlatıcının dilinden söylenir."),
    ("Emek Bereketi", "emek", "Alın teriyle geçinen insanların günlük emeğini ve sofradaki bereketi anlatır. Ana duygu dayanışma, sabır ve helal kazançtır."),
    ("Asker Hasreti", "hasret", "Askere giden bir gencin ardında kalan yârinin ve ailesinin bekleyişini anlatır. Ana duygu özlem, dua ve dönüş umududur."),
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

Bu şehir için YENİ ve FARKLI bir türkü konsepti oluştur.
Öncelik duygu/insan hikayesi olsun; yöresel yerler, yemekler, doğa ve tarihi dokular sadece sahne ve imge olarak kalsın.
Bu kez ana tema olarak şu ailelerden birini seç ve bunu açıkça işle: aşk/sevda, gurbet, ayrılık, kavuşma, düğün, ana-baba özlemi, göç, hasat, yas, umut, bekleyiş, sitem, emek, bereket.
Başlığı sadece dağ, göl, yol, sır, kale, kule, ova, nehir gibi bir nesne/yer adı yapma; başlık duygu veya olay anlatmalı.
"""
        last_result: dict = {}
        for attempt in range(3):
            retry_note = ""
            if attempt:
                retry_note = (
                    "\nÖNCEKİ DENEME REDDEDİLDİ: Başlık/tema fazla yer-nesne merkezliydi. "
                    "Yeni denemede başlıkta ve temada açık duygu/olay kullan.\n"
                )
            result = self.call(user_prompt + retry_note)
            last_result = result
            if self._is_valid_concept(result):
                return result
        return self._fallback_concept(city_name, generation_history, last_result)

    @staticmethod
    def _is_valid_concept(concept: dict) -> bool:
        title = str(concept.get("title") or "")
        theme = str(concept.get("theme") or "")
        story = str(concept.get("story") or "")
        combined = " ".join([title, theme, story])
        has_emotion = bool(_EMOTION_RE.search(combined))
        object_title = bool(_OBJECT_RE.search(title))
        emotion_in_title = bool(_EMOTION_RE.search(title))
        if object_title:
            return False
        return has_emotion

    @staticmethod
    def _fallback_concept(city_name: str, generation_history: dict, last_result: dict) -> dict:
        used_titles = {str(item).casefold() for item in generation_history.get("used_titles", [])}
        selected = next(
            (item for item in _FALLBACK_CONCEPTS if item[0].casefold() not in used_titles),
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
