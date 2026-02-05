"""API routes for scam detection honeypot."""

from __future__ import annotations

import base64
import json
import tempfile
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
try:
    import soundfile as sf
except Exception:
    sf = None
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status, Depends, Body, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logger import get_logger
from app.pipeline.agent import get_agentic_controller
from app.pipeline.asr import get_whisper_asr
from app.pipeline.detector import get_scam_detector
from app.pipeline.extractor import get_entity_extractor
from app.pipeline.tts import get_coqui_tts
from app.pipeline.voice_detector import get_voice_detector
from app.schemas.request import (
    DetectRequest,
    EngageRequest,
    ExtractRequest,
    VoiceDetectRequest,
    HoneypotRequest,
)
from app.schemas.response import (
    DetectResponse,
    EngageResponse,
    ExtractResponse,
    FullPipelineResponse,
    VoiceDetectResponse,
    HoneypotResponse,
    ErrorResponse,
)
from app.core.auth import get_current_api_key

router = APIRouter(prefix="/api/v1", tags=["scam-honeypot"])
# Alias router so we can expose a non-versioned path for compatibility
alias_router = APIRouter(prefix="/api", tags=["scam-honeypot"])
logger = get_logger("api.routes")


# ============================================================================
# Helper Functions
# ============================================================================


def _save_uploaded_file(upload_file: UploadFile) -> Path:
    """Save uploaded file to temporary location.

    Args:
        upload_file: FastAPI UploadFile object

    Returns:
        Path to saved temporary file

    Raises:
        HTTPException: If file cannot be saved
    """
    try:
        # Get file extension
        file_ext = Path(upload_file.filename or "file").suffix or ".wav"

        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(suffix=file_ext, delete=False)
        temp_path = Path(temp_file.name)

        # Write uploaded content
        content = upload_file.file.read()
        temp_file.write(content)
        temp_file.close()

        logger.info(f"Uploaded file saved to {temp_path} ({len(content)} bytes)")
        return temp_path

    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to save uploaded file: {str(e)}",
        )


def _cleanup_temp_file(file_path: Path) -> None:
    """Clean up temporary file.

    Args:
        file_path: Path to file to delete
    """
    try:
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Cleaned up temp file: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to clean up temp file {file_path}: {e}")


def _encode_audio_to_base64(audio_array: np.ndarray, sample_rate: int) -> str:
    """Encode audio array to base64 string.

    Args:
        audio_array: Audio samples (numpy array)
        sample_rate: Sample rate in Hz

    Returns:
        Base64 encoded WAV data

    Raises:
        HTTPException: If encoding fails
    """
    if sf is None:
        logger.error("Missing dependency: soundfile (PySoundFile) is not installed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Missing Python dependency 'soundfile'. "
                "Install it in your environment: `python -m pip install soundfile` "
                "or `python -m pip install -r backend/requirements.txt`."
            ),
        )

    try:
        # Write to BytesIO buffer as WAV
        buffer = BytesIO()
        sf.write(buffer, audio_array, sample_rate, format="WAV")
        buffer.seek(0)

        # Encode to base64
        audio_bytes = buffer.read()
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

        logger.info(f"Encoded audio to base64 ({len(audio_base64)} chars)")
        return audio_base64

    except Exception as e:
        logger.error(f"Failed to encode audio to base64: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to encode audio: {str(e)}",
        )


def _calculate_risk_score(
    scam_prob: float, entity_count: int, high_risk_indicators: List[str]
) -> float:
    """Calculate composite risk score.

    Args:
        scam_prob: Scam probability (0-1)
        entity_count: Total entities found
        high_risk_indicators: List of high-risk flags

    Returns:
        Risk score between 0.0 and 1.0
    """
    # Normalize entity count to 0-1 scale (assume max ~50 entities)
    entity_score = min(entity_count / 50.0, 1.0)

    # High-risk indicator penalty (each indicator adds ~0.1)
    risk_penalty = min(len(high_risk_indicators) * 0.1, 1.0)

    # Weighted combination
    risk_score = (scam_prob * 0.6) + (entity_score * 0.2) + (risk_penalty * 0.2)

    return min(risk_score, 1.0)


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/detect", response_model=DetectResponse)
async def detect_scam(request: DetectRequest) -> DetectResponse:
    """Detect if transcript contains scam indicators.

    Args:
        request: DetectRequest with transcript

    Returns:
        DetectResponse with scam classification

    Raises:
        HTTPException: If processing fails
    """
    logger.info(f"POST /detect - transcript length: {len(request.transcript)}")

    try:
        # Validate input
        if not request.transcript or not request.transcript.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transcript cannot be empty",
            )

        # Get detector
        detector = get_scam_detector()

        # Check demo mode
        if settings.DEMO_MODE:
            logger.info("Using detector demo mode")
            result = detector.detect_demo(request.transcript, mock_result=True)
        else:
            result = detector.detect(request.transcript)

        # Extract results
        is_scam = result["is_scam"]
        scam_probability = result["scam_probability"]
        scam_type = result["scam_type"]
        confidence_scores = result["confidence_scores"]

        response = DetectResponse(
            transcript=request.transcript,
            is_scam=is_scam,
            scam_probability=scam_probability,
            scam_type=scam_type,
            confidence_scores=confidence_scores,
        )

        logger.info(
            f"Detection complete - is_scam: {is_scam}, "
            f"prob: {scam_probability:.2f}, type: {scam_type}"
        )

        return response

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error in detect: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error in detect endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing error",
        )


@router.post("/engage", response_model=EngageResponse)
async def engage_conversation(
    session_id: str = Form(...),
    audio: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    conversation_history: Optional[str] = Form(None),
) -> EngageResponse:
    """Engage in conversation with agent and synthesize response.

    Args:
        session_id: Unique session identifier
        audio: Optional audio file upload
        text: Optional text transcript
        conversation_history: Optional JSON string of previous messages

    Returns:
        EngageResponse with agent response and audio

    Raises:
        HTTPException: If processing fails
    """
    logger.info(f"POST /engage - session_id: {session_id}")

    temp_file_path: Optional[Path] = None

    try:
        # Validate exactly one of audio or text is provided
        if not audio and not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either audio or text must be provided",
            )

        if audio and text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only one of audio or text can be provided",
            )

        # Parse conversation history
        history: List[Dict[str, str]] = []
        if conversation_history:
            try:
                history = json.loads(conversation_history)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON format for conversation_history",
                )

        transcript = ""

        # ---- Stage 1: ASR (if audio provided) ----
        if audio:
            logger.info("Processing audio input")
            temp_file_path = _save_uploaded_file(audio)

            asr = get_whisper_asr()

            if settings.DEMO_MODE:
                logger.info("Using ASR demo mode")
                asr_result = asr.transcribe_demo(mock_transcript="Demo transcript")
            else:
                asr_result = asr.transcribe(str(temp_file_path))

            transcript = asr_result["transcript"]
            logger.info(f"ASR complete - transcript length: {len(transcript)}")

        else:
            # Text provided
            if not text or not text.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Text input cannot be empty",
                )
            transcript = text
            logger.info(f"Using text input - length: {len(transcript)}")

        # ---- Stage 2: Agent Engagement ----
        logger.info("Starting agent engagement")
        agent = get_agentic_controller()

        if settings.DEMO_MODE:
            logger.info("Using agent demo mode")
            agent_result = agent.engage_demo(session_id, transcript)
        else:
            agent_result = agent.engage(session_id, transcript, history)

        agent_response_text = agent_result["agent_response_text"]
        turn_number = agent_result["turn_number"]
        terminated = agent_result["terminated"]
        extracted_intelligence = agent_result["extracted_intelligence"]

        logger.info(
            f"Agent engagement complete - turn: {turn_number}, "
            f"terminated: {terminated}"
        )

        # ---- Stage 3: TTS Synthesis ----
        logger.info("Synthesizing response audio")
        tts = get_coqui_tts()

        if settings.DEMO_MODE:
            logger.info("Using TTS demo mode")
            tts_result = tts.synthesize_demo(agent_response_text, mock_audio=True)
        else:
            tts_result = tts.synthesize(agent_response_text)

        # Support both legacy key `audio` and current `audio_array` returned
        # by the TTS pipeline. Be defensive and provide a clear error
        # if neither is present.
        if "audio" in tts_result:
            audio_array = tts_result["audio"]
        elif "audio_array" in tts_result:
            audio_array = tts_result["audio_array"]
        else:
            logger.error(
                "TTS result missing audio key; keys: %s",
                list(tts_result.keys()),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="TTS synthesis returned no audio",
            )

        sample_rate = tts_result.get("sample_rate", getattr(tts, "sample_rate", 22050))

        # Encode audio to base64
        audio_base64 = _encode_audio_to_base64(audio_array, sample_rate)

        logger.info("TTS synthesis complete")

        # ---- Return Response ----
        response = EngageResponse(
            session_id=session_id,
            transcript=transcript,
            agent_response_text=agent_response_text,
            agent_response_audio=audio_base64,
            turn_number=turn_number,
            terminated=terminated,
            extracted_intelligence=extracted_intelligence,
        )

        return response

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error in engage: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error in engage endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing error",
        )
    finally:
        # Clean up temp file
        if temp_file_path:
            _cleanup_temp_file(temp_file_path)


@router.post("/voice-detection", response_model=VoiceDetectResponse)
async def voice_detection(
    request: VoiceDetectRequest, api_key: str = Depends(get_current_api_key)
    ) -> VoiceDetectResponse:
    """AI-generated voice detection endpoint (Problem Statement 1).

    Detects whether a voice sample is AI-generated or human across
    Tamil, English, Hindi, Malayalam, and Telugu languages.
    """
    logger.info(
        f"POST /voice-detection - language: {request.language}, "
        f"audio_size: {len(request.audioBase64)} chars"
    )

    temp_file_path: Optional[Path] = None

    try:
        # Get voice detector
        voice_detector = get_voice_detector()

        # Demo mode support
        if settings.DEMO_MODE:
            logger.info("Using voice detector demo mode")
            result = voice_detector.classify_demo(
                audio_waveform=None, language=request.language, mock_result=True
            )
        else:
            # Decode base64 MP3 to waveform
            logger.info("Decoding base64 MP3 audio")
            waveform = voice_detector.decode_base64_mp3(request.audioBase64)

            # Classify the audio
            logger.info(f"Classifying voice for language: {request.language}")
            result = voice_detector.classify(audio_waveform=waveform, language=request.language)

        # Build response
        response = VoiceDetectResponse(
            language=result["language"],
            classification=result["classification"],
            confidenceScore=result["confidence"],
            explanation=result["explanation"],
        )

        logger.info(
            f"Voice detection complete - classification: {response.classification}, "
            f"confidence: {response.confidenceScore:.3f}"
        )

        return response

    except ValueError as e:
        logger.error(f"Validation error in voice detection: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in voice detection endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Voice detection processing failed")
    finally:
        if temp_file_path:
            _cleanup_temp_file(temp_file_path)


# Expose non-versioned alias for voice-detection for backward compatibility.
# This route is hidden from OpenAPI schema to avoid duplication.
@alias_router.post(
    "/voice-detection",
    include_in_schema=False,
    response_model=VoiceDetectResponse,
    responses={400: {"model": ErrorResponse}},
)
async def voice_detection_alias(
    request: VoiceDetectRequest, api_key: str = Depends(get_current_api_key)
) -> VoiceDetectResponse:
    return await voice_detection(request, api_key)


# Alias for honeypot on non-versioned router for backward compatibility
@alias_router.post(
    "/honeypot",
    include_in_schema=False,
    response_model=HoneypotResponse,
    responses={400: {"model": ErrorResponse}},
    dependencies=[Depends(get_current_api_key)],
)
async def honeypot_alias(request: HoneypotRequest, api_key: str = Depends(get_current_api_key)) -> HoneypotResponse:
    return await honeypot(request, api_key)


@router.post("/honeypot", response_model=HoneypotResponse)
async def honeypot(
    request: HoneypotRequest, api_key: str = Depends(get_current_api_key)
) -> HoneypotResponse:
    """Agentic honeypot endpoint for scam detection and engagement (PS2).

    Detects scam intent from incoming messages and autonomously engages
    scammers to extract intelligence without revealing detection.
    """
    logger.info(
        f"POST /honeypot - sessionId: {request.sessionId}, "
        f"sender: {request.message.sender}, "
        f"history_length: {len(request.conversationHistory)}"
    )

    try:
        # Extract the incoming message text
        incoming_text = request.message.text

        # Stage 1: Scam Detection
        logger.info("Running scam detection on incoming message")
        detector = get_scam_detector()

        if settings.DEMO_MODE:
            logger.info("Using detector demo mode")
            detection_result = detector.detect_demo(incoming_text, mock_result=True)
        else:
            detection_result = detector.detect(incoming_text)

        scam_probability = detection_result.get("scam_probability", 0.0)
        is_scam = detection_result.get("is_scam", False)

        logger.info(
            f"Detection complete - is_scam: {is_scam}, "
            f"probability: {scam_probability:.3f}"
        )

        # Stage 2: Decide whether to engage agent
        SCAM_THRESHOLD = 0.7

        if scam_probability < SCAM_THRESHOLD:
            # Not a scam - return neutral response
            logger.info(f"Scam probability {scam_probability:.3f} below threshold {SCAM_THRESHOLD}")
            reply_text = "I'm not sure I understand. Could you clarify?"
        else:
            # Scam detected - engage agent
            logger.info(f"Scam detected (prob: {scam_probability:.3f}), engaging agent")

            # Convert conversationHistory to agent-compatible format
            agent_history: List[Dict[str, str]] = []
            for msg in request.conversationHistory:
                if msg.sender == "scammer":
                    agent_history.append({"user": msg.text, "assistant": ""})
                elif msg.sender == "user":
                    if agent_history and not agent_history[-1]["assistant"]:
                        agent_history[-1]["assistant"] = msg.text
                    else:
                        agent_history.append({"user": "", "assistant": msg.text})

            # Remove incomplete turns (no assistant response)
            agent_history = [turn for turn in agent_history if turn["user"] and turn["assistant"]]

            # Stage 3: Agent Engagement
            logger.info("Starting agent engagement")
            agent = get_agentic_controller()

            if settings.DEMO_MODE:
                logger.info("Using agent demo mode")
                agent_result = agent.engage_demo(request.sessionId, incoming_text)
            else:
                agent_result = agent.engage(
                    session_id=request.sessionId,
                    user_input=incoming_text,
                    conversation_history=agent_history,
                )

            reply_text = agent_result.get("agent_response_text", "")

            logger.info(
                f"Agent engagement complete - turn: {agent_result.get('turn_number')}, "
                f"terminated: {agent_result.get('terminated')}"
            )

        # Return response
        response = HoneypotResponse(reply=reply_text)

        logger.info(f"Honeypot response generated - reply length: {len(reply_text)}")
        return response

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error in honeypot: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error in honeypot endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Honeypot processing failed")


@router.post("/extract", response_model=ExtractResponse)
async def extract_entities(request: ExtractRequest) -> ExtractResponse:
    """Extract entities and scammer intelligence from transcript.

    Args:
        request: ExtractRequest with transcript

    Returns:
        ExtractResponse with entities and intelligence

    Raises:
        HTTPException: If processing fails
    """
    logger.info(f"POST /extract - transcript length: {len(request.transcript)}")

    try:
        # Validate input
        if not request.transcript or not request.transcript.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transcript cannot be empty",
            )

        # Get extractor
        extractor = get_entity_extractor()

        # Check demo mode
        if settings.DEMO_MODE:
            logger.info("Using extractor demo mode")
            result = extractor.extract_demo(request.transcript, mock_result=True)
        else:
            result = extractor.extract(request.transcript)

        # Extract results
        entities = result["entities"]
        scammer_intelligence = result["scammer_intelligence"]
        confidence_scores = result["confidence_scores"]

        response = ExtractResponse(
            transcript=request.transcript,
            entities=entities,
            scammer_intelligence=scammer_intelligence,
            confidence_scores=confidence_scores,
        )

        logger.info(
            f"Extraction complete - entities found: "
            f"{scammer_intelligence.get('total_entities_found', 0)}"
        )

        return response

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error in extract: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error in extract endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing error",
        )


@router.post("/full-pipeline", response_model=FullPipelineResponse)
async def full_pipeline(
    audio: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    demo_mode: bool = Form(False),
) -> FullPipelineResponse:
    """Execute full pipeline: ASR → Detect → Engage → TTS → Extract.

    Args:
        audio: Audio file to process
        session_id: Optional session identifier (generated if not provided)
        demo_mode: Override settings.DEMO_MODE for this request

    Returns:
        FullPipelineResponse with all pipeline results

    Raises:
        HTTPException: If any pipeline stage fails
    """
    logger.info("POST /full-pipeline")

    start_time = time.time()
    temp_file_path: Optional[Path] = None
    session_id = session_id or str(uuid.uuid4())

    try:
        logger.info(f"Starting full pipeline - session_id: {session_id}")

        # Save uploaded audio
        logger.info("Stage 0: Saving audio file")
        temp_file_path = _save_uploaded_file(audio)

        # ---- Stage 1: ASR (Speech-to-Text) ----
        logger.info("Stage 1: ASR transcription")
        asr = get_whisper_asr()

        use_demo = demo_mode or settings.DEMO_MODE
        if use_demo:
            logger.info("Using ASR demo mode")
            asr_result = asr.transcribe_demo(mock_transcript="Demo transcript")
        else:
            asr_result = asr.transcribe(str(temp_file_path))

        transcript = asr_result["transcript"]
        logger.info(f"ASR complete - transcript length: {len(transcript)}")

        # ---- Stage 2: Scam Detection ----
        logger.info("Stage 2: Scam detection")
        detector = get_scam_detector()

        if use_demo:
            logger.info("Using detector demo mode")
            detection_result = detector.detect_demo(transcript, mock_result=True)
        else:
            detection_result = detector.detect(transcript)

        detect_response = DetectResponse(
            transcript=transcript,
            is_scam=detection_result["is_scam"],
            scam_probability=detection_result["scam_probability"],
            scam_type=detection_result["scam_type"],
            confidence_scores=detection_result["confidence_scores"],
        )

        logger.info(
            f"Detection complete - is_scam: {detect_response.is_scam}, "
            f"prob: {detect_response.scam_probability:.2f}"
        )

        # ---- Stage 3: Agent Engagement ----
        logger.info("Stage 3: Agent engagement")
        agent = get_agentic_controller()

        if use_demo:
            logger.info("Using agent demo mode")
            agent_result = agent.engage_demo(session_id, transcript)
        else:
            agent_result = agent.engage(session_id, transcript)

        agent_response_text = agent_result["agent_response_text"]
        turn_number = agent_result["turn_number"]
        terminated = agent_result["terminated"]
        extracted_intelligence = agent_result["extracted_intelligence"]

        logger.info(
            f"Agent engagement complete - turn: {turn_number}, "
            f"terminated: {terminated}"
        )

        # ---- Stage 4: TTS Synthesis ----
        logger.info("Stage 4: TTS synthesis")
        tts = get_coqui_tts()

        if use_demo:
            logger.info("Using TTS demo mode")
            tts_result = tts.synthesize_demo(agent_response_text, mock_audio=True)
        else:
            tts_result = tts.synthesize(agent_response_text)

        audio_array = tts_result["audio"]
        sample_rate = tts_result["sample_rate"]
        audio_base64 = _encode_audio_to_base64(audio_array, sample_rate)

        engage_response = EngageResponse(
            session_id=session_id,
            transcript=transcript,
            agent_response_text=agent_response_text,
            agent_response_audio=audio_base64,
            turn_number=turn_number,
            terminated=terminated,
            extracted_intelligence=extracted_intelligence,
        )

        logger.info("TTS synthesis complete")

        # ---- Stage 5: Entity Extraction ----
        logger.info("Stage 5: Entity extraction")
        extractor = get_entity_extractor()

        if use_demo:
            logger.info("Using extractor demo mode")
            extraction_result = extractor.extract_demo(transcript, mock_result=True)
        else:
            extraction_result = extractor.extract(transcript)

        extract_response = ExtractResponse(
            transcript=transcript,
            entities=extraction_result["entities"],
            scammer_intelligence=extraction_result["scammer_intelligence"],
            confidence_scores=extraction_result["confidence_scores"],
        )

        logger.info(
            f"Extraction complete - entities found: "
            f"{extract_response.scammer_intelligence.get('total_entities_found', 0)}"
        )

        # ---- Calculate Metrics ----
        logger.info("Calculating metrics")
        risk_score = _calculate_risk_score(
            scam_prob=detect_response.scam_probability,
            entity_count=extract_response.scammer_intelligence.get(
                "total_entities_found", 0
            ),
            high_risk_indicators=extract_response.scammer_intelligence.get(
                "high_risk_indicators", []
            ),
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"Full pipeline complete - "
            f"risk_score: {risk_score:.2f}, "
            f"time: {processing_time_ms}ms"
        )

        # ---- Return Response ----
        response = FullPipelineResponse(
            transcript=transcript,
            scam_detection=detect_response,
            agent_response=engage_response,
            extracted_entities=extract_response,
            risk_score=risk_score,
            processing_time_ms=processing_time_ms,
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in full_pipeline endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline processing failed: {str(e)}",
        )
    finally:
        # Clean up temp file
        if temp_file_path:
            _cleanup_temp_file(temp_file_path)
