"""
Task → Ollama model mapping.
Change model names here without touching agent code.
"""

MODELS: dict[str, str] = {
    # Lyric writing — needs best Turkish quality
    "lyric_writer": "qwen2.5:7b",

    # Lyric quality review — separate call for objectivity
    "lyric_reviewer": "qwen2.5:7b",

    # Song concept generation — fast is fine
    "concept": "qwen2.5:7b",

    # Suno style prompt generation
    "suno_prompt": "qwen2.5:7b",

    # Image / thumbnail prompt generation
    "image_prompt": "qwen2.5:7b",

    # YouTube metadata (title, description, hashtags)
    "metadata": "qwen2.5:7b",
}


def get_model(task: str) -> str:
    """Return the configured model name for a given task."""
    if task not in MODELS:
        raise ValueError(f"Unknown task '{task}'. Available: {list(MODELS.keys())}")
    return MODELS[task]
