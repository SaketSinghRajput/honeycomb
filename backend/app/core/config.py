from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Model paths
    MODELS_DIR: Path = Field(default=Path("./models"))
    WHISPER_MODEL_NAME: str = Field(default="base")
    DISTILBERT_MODEL_NAME: str = Field(default="facebook/bart-large-mnli")
    SPACY_MODEL_NAME: str = Field(default="en_core_web_sm")
    TTS_MODEL_NAME: str = Field(default="tts_models/en/ek1/tacotron2")
    TTS_LANGUAGE: Optional[str] = Field(default="en")
    TTS_SPEAKER: Optional[str] = Field(default=None)
    LLM_MODEL_NAME: str = Field(default="microsoft/phi-2")
    # Voice detector configuration
    VOICE_DETECTOR_MODEL_NAME: str = Field(default="MelodyMachine/Deepfake-audio-detection-V2")
    VOICE_DETECTOR_SUPPORTED_LANGUAGES: List[str] = Field(
        default_factory=lambda: ["Tamil", "English", "Hindi", "Malayalam", "Telugu"]
    )

    # LLM settings
    LLM_USE_API: bool = Field(default=False)
    LLM_API_BASE_URL: Optional[str] = Field(default=None)
    LLM_API_KEY: Optional[str] = Field(default=None)
    LLM_MAX_TOKENS: int = Field(default=256)
    LLM_TEMPERATURE: float = Field(default=0.7)
    AGENT_MAX_MEMORY_TURNS: int = Field(default=10)
    AGENT_TERMINATION_KEYWORDS: List[str] = Field(
        default_factory=lambda: ["terminate", "end_call", "stop"]
    )

    # API configuration
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)
    API_WORKERS: int = Field(default=1)
    CORS_ORIGINS: List[str] = Field(default_factory=list)
    # API authentication key (used to protect hackathon endpoints)
    API_SECRET_KEY: str = Field(default="sk_test_123456789")

    # Runtime settings
    DEVICE: str = Field(default="cpu")
    LOG_LEVEL: str = Field(default="INFO")
    DEMO_MODE: bool = Field(default=False)
    # GUVI callback settings for honeypot final result reporting
    GUVI_CALLBACK_URL: str = Field(default="https://hackathon.guvi.in/api/updateHoneyPotFinalResult")
    GUVI_CALLBACK_ENABLED: bool = Field(default=True)
    GUVI_CALLBACK_TIMEOUT: int = Field(default=10)
    AGENT_MIN_TURNS_FOR_CALLBACK: int = Field(default=3)
    AGENT_MAX_TURNS_FOR_CALLBACK: int = Field(default=10)

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("MODELS_DIR", mode="before")
    @classmethod
    def _expand_models_dir(cls, value: str | Path) -> Path:
        path = Path(value).expanduser().resolve()
        return path

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("AGENT_TERMINATION_KEYWORDS", mode="before")
    @classmethod
    def _parse_termination_keywords(cls, value):
        if value is None:
            return ["terminate", "end_call", "stop"]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("DEVICE", mode="before")
    @classmethod
    def _normalize_device(cls, value: str) -> str:
        if not value:
            return "cpu"
        normalized = value.lower().strip()
        if normalized not in {"cpu", "cuda"}:
            return "cpu"
        return normalized

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        if not value:
            return "INFO"
        return value.upper().strip()

    @model_validator(mode="after")
    def _auto_detect_device(self):
        try:
            import torch  # noqa: PLC0415

            if self.DEVICE == "cuda" and not torch.cuda.is_available():
                self.DEVICE = "cpu"
        except Exception:
            self.DEVICE = "cpu"
        return self

    @property
    def whisper_model_path(self) -> Path:
        return self.MODELS_DIR / "whisper" / self.WHISPER_MODEL_NAME

    @property
    def distilbert_model_path(self) -> Path:
        return self.MODELS_DIR / "distilbert" / self.DISTILBERT_MODEL_NAME

    @property
    def spacy_model_path(self) -> Path:
        return self.MODELS_DIR / "spacy" / self.SPACY_MODEL_NAME

    @property
    def tts_model_path(self) -> Path:
        return self.MODELS_DIR / "tts" / self.TTS_MODEL_NAME

    @property
    def llm_model_path(self) -> Path:
        return self.MODELS_DIR / "llm" / self.LLM_MODEL_NAME

    @property
    def voice_detector_model_path(self) -> Path:
        return self.MODELS_DIR / "voice_detector" / self.VOICE_DETECTOR_MODEL_NAME


settings = Settings()


def get_settings() -> Settings:
    return settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
