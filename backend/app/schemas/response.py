from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.config import utcnow


class BaseResponse(BaseModel):
    status: str = Field(default="success")
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=utcnow)


class DetectResponse(BaseResponse):
    is_scam: bool
    scam_probability: float
    scam_type: Optional[str] = None
    confidence_scores: Dict


class EngageResponse(BaseResponse):
    transcript: str
    agent_response_text: str
    agent_response_audio: Optional[str] = None
    session_id: str
    turn_number: int
    terminated: bool = False
    extracted_intelligence: Optional[List[Dict[str, Any]]] = None


class ExtractResponse(BaseResponse):
    entities: Dict
    scammer_intelligence: Dict
    confidence_scores: Dict


class FullPipelineResponse(BaseResponse):
    transcript: str
    scam_detection: DetectResponse
    agent_response: EngageResponse
    extracted_entities: ExtractResponse
    risk_score: float
    processing_time_ms: int


class VoiceDetectResponse(BaseResponse):
    """Response model for PS1 voice detection endpoint."""
    language: str
    classification: str = Field(..., description="AI_GENERATED or HUMAN")
    confidenceScore: float = Field(..., ge=0.0, le=1.0, description="Confidence between 0.0 and 1.0")
    explanation: str = Field(..., description="Reason for the classification")


class ErrorResponse(BaseModel):
    """Generic error response for all endpoints."""
    status: str = Field(default="error")
    message: str = Field(..., description="Error message")


class HoneypotResponse(BaseResponse):
    """Response model for PS2 honeypot endpoint."""
    reply: str = Field(..., description="Agent's response text")


class ExtractedIntelligence(BaseModel):
    bankAccounts: List[str] = Field(default_factory=list)
    upiIds: List[str] = Field(default_factory=list)
    phishingLinks: List[str] = Field(default_factory=list)
    phoneNumbers: List[str] = Field(default_factory=list)
    suspiciousKeywords: List[str] = Field(default_factory=list)


class HoneypotCallbackPayload(BaseModel):
    sessionId: str
    scamDetected: bool
    totalMessagesExchanged: int
    extractedIntelligence: ExtractedIntelligence
    agentNotes: Optional[str] = None
