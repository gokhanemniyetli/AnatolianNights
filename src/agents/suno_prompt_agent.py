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
