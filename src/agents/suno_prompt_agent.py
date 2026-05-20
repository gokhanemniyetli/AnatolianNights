"""SunoPromptAgent — builds one deterministic simple-mode Suno description."""

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
        theme = str(concept.get("theme") or "").strip()
        story = str(concept.get("story") or "").strip()
        instruments = cultural_profile.get("instruments", {}).get("primary", [])[:2]
        instrument_text = ", ".join(str(item) for item in instruments if str(item).strip())
        if instrument_text:
            instrument_sentence = f" Bu yöreye özgü {instrument_text} gibi çalgılarla çalınsın."
        else:
            instrument_sentence = " Bu yöreye özgü geleneksel çalgılarla çalınsın."
        simple_prompt = (
            f"{city} yöresine özgü bir türkü olsun. "
            f"{city} yöresinin ağız ve söyleyiş hissi duyulsun; İstanbul ağzı gibi düz okunmasın, "
            "ama şive abartılı veya karikatürize olmasın. "
            f"{instrument_sentence} "
            f"Şarkının adı '{title}' olsun. "
            f"Ana konu {theme} olsun; hikaye şu duygu etrafında kurulsun: {story} "
            "Şarkının başlığı ve ana konusu dağ, tepe, yol, sır, kale, göl, ova, nehir, su veya başka bir yer/nesne olmasın; "
            "bunlar geçerse sadece kısa arka plan imgesi olarak geçsin. "
            "Aşk, sevda, gurbet, ayrılık, kavuşma, aile özlemi, sitem, umut veya emek gibi insan duygusu önde olsun. "
            "Anadolu türküsü karakterinde, doğal, içten ve geleneksel bir yorum olsun. "
            "Şarkı en fazla 5 dakika olsun; sözleri gereksiz uzatma, iki veya üç kısa bölüm ve tekrar edilebilir kısa bir nakarat yeterli. "
            "Şarkı sözlerini kendin yaz. "
            f"{_LYRIC_QUALITY_GUIDANCE}"
        ).strip()
        lowered = simple_prompt.lower()
        forbidden = [term for term in _FORBIDDEN_STYLE_TERMS if term in lowered]
        if forbidden:
            raise ValueError(
                "Suno prompt contains forbidden modern/western style terms: "
                + ", ".join(forbidden)
            )
        result: dict[str, str] = {}
        result["simple_prompt"] = simple_prompt
        return result
