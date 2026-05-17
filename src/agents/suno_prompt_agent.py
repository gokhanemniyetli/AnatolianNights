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
            f"{city} şivesinde söylensin."
            f"{instrument_sentence} "
            f"Şarkının adı '{title}' olsun. "
            f"Ana konu {theme} olsun; hikaye şu duygu etrafında kurulsun: {story} "
            "Şarkının başlığı ve ana konusu dağ, tepe, yol, sır, kale, göl, ova, nehir, su veya başka bir yer/nesne olmasın; "
            "bunlar geçerse sadece kısa arka plan imgesi olarak geçsin. "
            "Aşk, sevda, gurbet, ayrılık, kavuşma, aile özlemi, sitem, umut veya emek gibi insan duygusu önde olsun. "
            "Anadolu türküsü karakterinde, doğal, içten ve geleneksel bir yorum olsun. "
            "Şarkı sözlerini kendin yaz."
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
