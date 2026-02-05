from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from fastapi import UploadFile
from pydantic import BaseModel, Field, field_validator, model_validator

_ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}


class DetectRequest(BaseModel):
    transcript: str = Field(..., min_length=1)
    audio_metadata: Optional[Dict] = None


class EngageRequest(BaseModel):
    audio: Optional[UploadFile] = None
    text: Optional[str] = Field(default=None, min_length=1)
    session_id: str = Field(..., min_length=1)
    conversation_history: Optional[List[Dict]] = None

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("audio")
    @classmethod
    def _validate_audio_extension(cls, value: Optional[UploadFile]):
        if value is None:
            return value
        suffix = Path(value.filename).suffix.lower() if value.filename else ""
        if suffix and suffix not in _ALLOWED_AUDIO_EXTENSIONS:
            raise ValueError("Unsupported audio format")
        return value

    @model_validator(mode="after")
    def _validate_audio_xor_text(self):
        if bool(self.audio) == bool(self.text):
            raise ValueError("Provide either audio or text, but not both")
        return self


class ExtractRequest(BaseModel):
    transcript: str = Field(..., min_length=1)


class FullPipelineRequest(BaseModel):
    audio: UploadFile
    session_id: Optional[str] = None
    demo_mode: bool = False

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("audio")
    @classmethod
    def _validate_audio_extension(cls, value: UploadFile):
        suffix = Path(value.filename).suffix.lower() if value.filename else ""
        if suffix and suffix not in _ALLOWED_AUDIO_EXTENSIONS:
            raise ValueError("Unsupported audio format")
        return value


class VoiceDetectRequest(BaseModel):
    """Request model for PS1 voice detection endpoint."""
    language: str = Field(..., description="One of: Tamil, English, Hindi, Malayalam, Telugu")
    audioFormat: str = Field(..., description="Audio format (must be 'mp3')")
    audioBase64: str = Field(..., min_length=1, description="Base64-encoded MP3 audio")

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        allowed = {"Tamil", "English", "Hindi", "Malayalam", "Telugu"}
        if v not in allowed:
            raise ValueError(f"Language must be one of: {', '.join(allowed)}")
        return v

    @field_validator("audioFormat")
    @classmethod
    def validate_format(cls, v: str) -> str:
        if v.lower() != "mp3":
            raise ValueError("audioFormat must be 'mp3'")
        return v.lower()


class HoneypotMessage(BaseModel):
    """Single message in honeypot conversation."""
    sender: str = Field(..., description="'scammer' or 'user'")
    text: str = Field(..., min_length=1, description="Message content")
    timestamp: int = Field(..., description="Epoch time in milliseconds")


class HoneypotMetadata(BaseModel):
    """Optional metadata for honeypot request."""
    channel: Optional[str] = Field(None, description="SMS, WhatsApp, Email, Chat")
    language: Optional[str] = Field(None, description="Language used")
    locale: Optional[str] = Field(None, description="Country/region code")


class HoneypotRequest(BaseModel):
    """Request model for PS2 honeypot endpoint."""
    sessionId: str = Field(..., min_length=1, description="Unique session identifier")
    message: HoneypotMessage = Field(..., description="Latest incoming message")
    conversationHistory: List[HoneypotMessage] = Field(
        default_factory=list,
        description="Previous messages in conversation",
    )
    metadata: Optional[HoneypotMetadata] = None
