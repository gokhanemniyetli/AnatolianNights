"""SunoPromptAgent — builds one deterministic simple-mode Suno description."""

import re

_FORBIDDEN_STYLE_TERMS = (
    "german",
    "rap",
    "pop",
    "rock",
    "country",
    "trap",
    "hip-hop",
    "hip hop",
    "r&b",
    "electro",
    "electronic",
    "synth",
    "western folk",
    "irish",
    "scottish",
    "english folk",
)

_LYRIC_QUALITY_GUIDANCE = (
    "Emotional modern Anatolian folk-inspired song with heartfelt storytelling, "
    "warm acoustic instruments, emotional male vocals, melodic traditional feeling "
    "blended with modern production. Use natural, meaningful, emotionally connected "
    "Turkish lyrics with realistic storytelling. Avoid random word combinations, "
    "broken grammar, surreal AI-style poetry, and awkward sentence structures. "
    "Every line should logically continue the previous one. Create authentic "
    "Anatolian folk emotion and atmosphere, but use clear and natural modern Turkish. "
    "Do not use exaggerated regional dialects, caricature village speech, or overly "
    "local slang. Keep the language nationally understandable, human-like, warm, "
    "and emotionally sincere. Write like a real Turkish folk songwriter, not like "
    "abstract AI poetry. Maintain natural rhyme, emotional continuity, and smooth "
    "lyrical flow."
)


class SunoPromptAgent:
    def generate(self, concept: dict, cultural_profile: dict) -> dict:
        """
        Returns dict with key: simple_prompt (str)
        """
        city = str(cultural_profile.get("city") or concept.get("city") or "").strip()
        title = str(concept.get("title") or "").strip()
        theme = str(concept.get("theme") or concept.get("tema") or concept.get("konu") or "").strip()
        story = str(concept.get("story") or concept.get("hikaye") or concept.get("duygu") or "").strip()
        instruments = cultural_profile.get("instruments", {}).get("primary", [])[:2]
        dialect = cultural_profile.get("dialect_guidance", {}) or {}
        dialect_prompt = str(dialect.get("dialect_prompt") or "").strip()
        lyric_markers = [str(item).strip() for item in dialect.get("lyric_markers", []) if str(item).strip()]
        forms = [str(item).strip() for item in dialect.get("forms", []) if str(item).strip()]
        avoid = [
            re.sub(r"(?<!\w)pop(?!\w)", "ticari", str(item).strip(), flags=re.IGNORECASE)
            for item in dialect.get("avoid", [])
            if str(item).strip()
        ]
        instrument_text = ", ".join(str(item) for item in instruments if str(item).strip())
        if instrument_text:
            instrument_sentence = f" Bu yöreye özgü {instrument_text} gibi çalgılarla çalınsın."
        else:
            instrument_sentence = " Bu yöreye özgü geleneksel çalgılarla çalınsın."
        dialect_sentence = (
            f" Ağız ve söyleyiş hedefi: {dialect_prompt}"
            if dialect_prompt
            else (
                f" {city} yöresinin ağız ve söyleyiş hissi duyulsun; İstanbul ağzı gibi düz okunmasın, "
                "ama şive abartılı veya karikatürize olmasın."
            )
        )
        marker_sentence = (
            " Yöresel ağız izleri olarak "
            + ", ".join(lyric_markers[:4])
            + " gibi kelimeleri en fazla 2-4 yerde doğal kullan; her mısraya serpiştirme."
            if lyric_markers
            else ""
        )
        form_sentence = (
            " Yöreye uygun müzikal form/tavır seçenekleri: "
            + ", ".join(forms[:4])
            + ". Bu seçeneklerden birini belirgin hissettir."
            if forms
            else ""
        )
        avoid_sentence = (
            " Özellikle kaçın: " + ", ".join(avoid[:5]) + "."
            if avoid
            else ""
        )
        simple_prompt = (
            f"{city} yöresine özgü bir türkü olsun. "
            f"{dialect_sentence} "
            f"{marker_sentence} "
            f"{form_sentence} "
            f"{instrument_sentence} "
            f"Şarkının adı '{title}' olsun. "
            f"Ana konu {theme} olsun; hikaye şu duygu etrafında kurulsun: {story} "
            "Şarkı kısa ve türkü formunda olsun: en fazla 3 dörtlük yaz. "
            "Her dörtlükten sonra aynı kısa, vurucu nakarat söylensin. "
            "Nakarat 2-4 kısa dizeden oluşsun, akılda kalıcı ve tekrar edilebilir olsun. "
            "Dörtlükler olay örgüsü gibi uzamasın; her dize bağımsız türkü tadında, kısa ve ezgili olsun. "
            "Toplam söz 16-24 dizeyi geçmesin. "
            "Şarkının başlığı ve ana konusu dağ, tepe, yol, sır, kale, göl, ova, nehir, su veya başka bir yer/nesne olmasın; "
            "bunlar geçerse sadece kısa arka plan imgesi olarak geçsin. "
            "Aşk, sevda, gurbet, ayrılık, kavuşma, aile özlemi, sitem, umut veya emek gibi insan duygusu önde olsun. "
            "Anadolu türküsü karakterinde, doğal, içten ve geleneksel bir yorum olsun. "
            "Şarkı en fazla 3 dakika olsun; uzun hikaye anlatma, gereksiz bölüm ekleme. "
            f"{avoid_sentence} "
            "Şarkı sözlerini kendin yaz. "
            f"{_LYRIC_QUALITY_GUIDANCE}"
        ).strip()
        lowered = simple_prompt.lower()
        forbidden = [
            term
            for term in _FORBIDDEN_STYLE_TERMS
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered)
        ]
        if forbidden:
            raise ValueError(
                "Suno prompt contains forbidden modern/western style terms: "
                + ", ".join(forbidden)
            )
        result: dict[str, str] = {}
        result["simple_prompt"] = simple_prompt
        return result

    def generate_for_playlist(self, concept: dict, concept_profile: dict) -> dict:
        """Build a Suno simple-mode prompt for a non-city playlist concept."""
        playlist_title = str(concept_profile.get("concept_title") or concept.get("playlist_concept") or "").strip()
        title = str(concept.get("title") or "").strip()
        theme = str(concept.get("theme") or concept.get("tema") or concept.get("konu") or "").strip()
        story = str(concept.get("story") or concept.get("hikaye") or "").strip()
        style_profile = concept_profile.get("style_profile", {}) or {}
        research = concept_profile.get("research", {}) or {}
        style_notes = research.get("style_notes", []) or []
        story_angles = research.get("story_angles", []) or []
        instruments = style_profile.get("instruments", ["bağlama"])
        avoid = style_profile.get("avoid", [])
        instrument_text = ", ".join(str(item) for item in instruments if str(item).strip())
        style_text = "; ".join(str(item) for item in style_notes[:5] if str(item).strip())
        angle_text = ", ".join(str(item) for item in story_angles[:6] if str(item).strip())
        avoid_sentence = " Özellikle kaçın: " + ", ".join(avoid[:5]) + "." if avoid else ""

        simple_prompt = (
            f"{playlist_title} konseptine ait özgün bir Türkçe türkü üret. "
            f"Şarkının adı '{title}' olsun. "
            f"Ana konu {theme} olsun; hikaye şu duygu etrafında kurulsun: {story} "
            f"Tarz notları: {style_text} "
            f"Çalgı/tını hedefi: {instrument_text}. "
            f"Hikaye seçenekleri bu evrenden beslensin ama tekrar etmesin: {angle_text}. "
            "Sözler doğal, anlaşılır ve insan hikayesi merkezli Türkçe olsun. "
            "Şarkı kısa olsun: en fazla 3 dörtlük yaz, her dörtlükten sonra aynı kısa nakarat gelsin. "
            "Toplam söz 16-24 dizeyi geçmesin. "
            "Süre hedefi 3 dakika civarı, kesinlikle 4 dakikayı aşmayacak yapı olsun. "
            "Playlist konseptinin tavrı belirgin duyulsun; şehir tanıtımı veya ansiklopedik anlatım yapma. "
            "Sözleri kendin yaz; kaynak metni kopyalama. "
            f"{avoid_sentence} "
            f"{_LYRIC_QUALITY_GUIDANCE}"
        ).strip()
        return {"simple_prompt": simple_prompt}
