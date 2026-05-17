from pathlib import Path
from typing import Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_yaml_config() -> dict:
    config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


_yaml = _load_yaml_config()


class OllamaSettings(BaseSettings):
    base_url: str = Field(default=_yaml.get("ollama", {}).get("base_url", "http://localhost:11434"))
    timeout_seconds: int = Field(default=_yaml.get("ollama", {}).get("timeout_seconds", 120))
    max_retries: int = Field(default=_yaml.get("ollama", {}).get("max_retries", 3))
    retry_delay_seconds: float = Field(default=_yaml.get("ollama", {}).get("retry_delay_seconds", 2))


class YouTubeSettings(BaseSettings):
    client_secrets_file: str = Field(default="config/youtube_client_secrets.json", alias="YOUTUBE_CLIENT_SECRETS_FILE")
    channel_id: str = Field(default="", alias="YOUTUBE_CHANNEL_ID")
    daily_quota_limit: int = Field(default=_yaml.get("youtube", {}).get("daily_quota_limit", 10000))
    upload_cost: int = Field(default=_yaml.get("youtube", {}).get("upload_cost", 1600))
    playlist_insert_cost: int = Field(default=_yaml.get("youtube", {}).get("playlist_insert_cost", 50))
    category_id: str = Field(default=_yaml.get("youtube", {}).get("category_id", "10"))

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
        protected_namespaces=(),
    )


class SunoSettings(BaseSettings):
    client: str = Field(default="manual", alias="SUNO_CLIENT")
    model_version: str = Field(default=_yaml.get("suno", {}).get("model_version", "chirp-fenix"), alias="SUNO_MODEL_VERSION")
    email: Optional[str] = Field(default=None, alias="SUNO_EMAIL")
    password: Optional[str] = Field(default=None, alias="SUNO_PASSWORD")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
        protected_namespaces=(),
    )


class PipelineSettings(BaseSettings):
    quality_threshold: float = Field(default=_yaml.get("pipeline", {}).get("quality_threshold", 8.0))
    max_lyric_retries: int = Field(default=_yaml.get("pipeline", {}).get("max_lyric_retries", 3))
    default_k: int = Field(default=_yaml.get("pipeline", {}).get("default_k", 1))
    max_daily_uploads: int = Field(default=_yaml.get("pipeline", {}).get("max_daily_uploads", 4))
    publish_interval_minutes: int = Field(default=_yaml.get("pipeline", {}).get("publish_interval_minutes", 180))
    dry_run: bool = Field(default=False, alias="DRY_RUN")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)


class VideoSettings(BaseSettings):
    short_hook_duration: int = Field(
        default=_yaml.get("video", {}).get("short", {}).get("hook_duration_seconds", 40),
        alias="SHORT_HOOK_DURATION_SECONDS",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)


class StorageSettings(BaseSettings):
    outputs_dir: str = Field(default="outputs", alias="OUTPUTS_DIR")
    database_url: str = Field(default="sqlite:///data/anadolu.db", alias="DATABASE_URL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)


class Settings(BaseSettings):
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    youtube: YouTubeSettings = Field(default_factory=YouTubeSettings)
    suno: SunoSettings = Field(default_factory=SunoSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    video: VideoSettings = Field(default_factory=VideoSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)


settings = Settings()
