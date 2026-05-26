"""
SQLAlchemy ORM models.
Song.status drives the entire pipeline — never update it directly,
use song_service.advance_status() instead.
"""

import json
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SongStatus(str, Enum):
    PENDING = "pending"
    CONCEPT_READY = "concept_ready"
    LYRICS_READY = "lyrics_ready"
    QUALITY_APPROVED = "quality_approved"
    QUALITY_REJECTED = "quality_rejected"
    PERMANENTLY_REJECTED = "permanently_rejected"
    SUNO_READY = "suno_ready"
    AUDIO_IMPORTED = "audio_imported"
    IMAGE_READY = "image_ready"
    VIDEO_READY = "video_ready"
    UPLOADED = "uploaded"


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    playlist_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cultural_profile: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    songs: Mapped[list["Song"]] = relationship("Song", back_populates="city")
    generation_history: Mapped["GenerationHistory | None"] = relationship(
        "GenerationHistory", back_populates="city", uselist=False
    )

    def get_cultural_profile(self) -> dict:
        if self.cultural_profile:
            return json.loads(self.cultural_profile)
        return {}

    def set_cultural_profile(self, profile: dict) -> None:
        self.cultural_profile = json.dumps(profile, ensure_ascii=False)


class ConceptPlaylist(Base):
    __tablename__ = "concept_playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    group: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    playlist_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    research: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    style_profile: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    anchor_city_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cities.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    songs: Mapped[list["Song"]] = relationship("Song", back_populates="concept_playlist")
    generation_history: Mapped["ConceptGenerationHistory | None"] = relationship(
        "ConceptGenerationHistory", back_populates="concept_playlist", uselist=False
    )

    def get_research(self) -> dict:
        if self.research:
            return json.loads(self.research)
        return {}

    def set_research(self, research: dict) -> None:
        self.research = json.dumps(research, ensure_ascii=False)

    def get_style_profile(self) -> dict:
        if self.style_profile:
            return json.loads(self.style_profile)
        return {}

    def set_style_profile(self, profile: dict) -> None:
        self.style_profile = json.dumps(profile, ensure_ascii=False)


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_id: Mapped[int] = mapped_column(Integer, ForeignKey("cities.id"), nullable=False)
    concept_playlist_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("concept_playlists.id"), nullable=True
    )

    # Concept
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    theme: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mood: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tempo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vocal_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    style_variant: Mapped[str | None] = mapped_column(String(100), nullable=True)
    concept: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    # Lyrics
    lyrics: Mapped[str | None] = mapped_column(Text, nullable=True)
    lyric_attempt: Mapped[int] = mapped_column(Integer, default=0)

    # Quality
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_report: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    # Lyrics
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Suno
    suno_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Suno clip/job ID
    suno_style_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    suno_full_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    suno_lyrics: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Image
    image_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # YouTube
    youtube_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    youtube_video_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    youtube_short_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    youtube_long_video_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    youtube_short_video_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # File paths (relative to outputs dir)
    audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    short_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    background_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    long_video_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    short_video_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    background_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    subtitles_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(50), default=SongStatus.CONCEPT_READY)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    city: Mapped["City"] = relationship("City", back_populates="songs")
    concept_playlist: Mapped["ConceptPlaylist | None"] = relationship(
        "ConceptPlaylist", back_populates="songs"
    )
    quality_reports: Mapped[list["QualityReport"]] = relationship(
        "QualityReport", back_populates="song"
    )

    def get_concept(self) -> dict:
        if self.concept:
            return json.loads(self.concept)
        return {}

    def set_concept(self, data: dict) -> None:
        self.concept = json.dumps(data, ensure_ascii=False)

    def get_youtube_metadata(self) -> dict:
        if self.youtube_metadata:
            return json.loads(self.youtube_metadata)
        return {}

    def set_youtube_metadata(self, data: dict) -> None:
        self.youtube_metadata = json.dumps(data, ensure_ascii=False)

    def get_quality_report(self) -> dict:
        if self.quality_report:
            return json.loads(self.quality_report)
        return {}

    def set_quality_report(self, data: dict) -> None:
        self.quality_report = json.dumps(data, ensure_ascii=False)


class GenerationHistory(Base):
    __tablename__ = "generation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_id: Mapped[int] = mapped_column(Integer, ForeignKey("cities.id"), nullable=False, unique=True)

    used_themes: Mapped[str] = mapped_column(Text, default="[]")        # JSON list
    used_titles: Mapped[str] = mapped_column(Text, default="[]")        # JSON list
    used_hooks: Mapped[str] = mapped_column(Text, default="[]")         # JSON list
    used_keywords: Mapped[str] = mapped_column(Text, default="[]")      # JSON list
    used_instruments: Mapped[str] = mapped_column(Text, default="[]")   # JSON list of lists
    used_moods: Mapped[str] = mapped_column(Text, default="[]")         # JSON list
    used_tempos: Mapped[str] = mapped_column(Text, default="[]")        # JSON list
    used_style_prompts: Mapped[str] = mapped_column(Text, default="[]") # JSON list

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    city: Mapped["City"] = relationship("City", back_populates="generation_history")

    def get(self, field: str) -> list:
        raw = getattr(self, field, "[]")
        return json.loads(raw)

    def append(self, field: str, value) -> None:
        current = self.get(field)
        current.append(value)
        setattr(self, field, json.dumps(current, ensure_ascii=False))


class ConceptGenerationHistory(Base):
    __tablename__ = "concept_generation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    concept_playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("concept_playlists.id"), nullable=False, unique=True
    )

    used_themes: Mapped[str] = mapped_column(Text, default="[]")
    used_titles: Mapped[str] = mapped_column(Text, default="[]")
    used_hooks: Mapped[str] = mapped_column(Text, default="[]")
    used_keywords: Mapped[str] = mapped_column(Text, default="[]")
    used_instruments: Mapped[str] = mapped_column(Text, default="[]")
    used_moods: Mapped[str] = mapped_column(Text, default="[]")
    used_tempos: Mapped[str] = mapped_column(Text, default="[]")
    used_style_prompts: Mapped[str] = mapped_column(Text, default="[]")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    concept_playlist: Mapped["ConceptPlaylist"] = relationship(
        "ConceptPlaylist", back_populates="generation_history"
    )

    def get(self, field: str) -> list:
        raw = getattr(self, field, "[]")
        return json.loads(raw)

    def append(self, field: str, value) -> None:
        current = self.get(field)
        current.append(value)
        setattr(self, field, json.dumps(current, ensure_ascii=False))


class QualityReport(Base):
    __tablename__ = "quality_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    song_id: Mapped[int] = mapped_column(Integer, ForeignKey("songs.id"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    issues: Mapped[str] = mapped_column(Text, default="[]")   # JSON list of strings
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_model: Mapped[str] = mapped_column(String(100), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    song: Mapped["Song"] = relationship("Song", back_populates="quality_reports")

    def get_issues(self) -> list[str]:
        return json.loads(self.issues)

    def set_issues(self, issues: list[str]) -> None:
        self.issues = json.dumps(issues, ensure_ascii=False)


class RunLog(Base):
    __tablename__ = "run_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(100), nullable=False)
    city_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cities.id"), nullable=True)
    song_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("songs.id"), nullable=True)
    stage: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # success | failure | skipped
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class YouTubeQuotaLog(Base):
    __tablename__ = "youtube_quota_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    cost: Mapped[int] = mapped_column(Integer, nullable=False)
    song_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("songs.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
