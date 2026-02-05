"""Voice deepfake detection module using wav2vec2-based classifier."""

from __future__ import annotations

import base64
import io
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import torch

from app.core.config import settings
from app.core.logger import get_logger
from app.models.model_loader import get_model_loader

logger = get_logger("pipeline.voice_detector")


class VoiceDetector:
    """
    AI-generated voice detection using wav2vec2-based classifier.
    """

    # Supported languages are configured via settings to keep behavior configurable
    # and avoid hard-coded lists in the code.
    LABEL_MAPPING = {0: "AI_GENERATED", 1: "HUMAN"}
    SAMPLE_RATE = 16000

    def __init__(self, device: Optional[str] = None) -> None:
        self.device = device or settings.DEVICE
        self.logger = get_logger("pipeline.voice_detector")
        self._model: Optional[Any] = None
        self._processor: Optional[Any] = None
        # Initialize supported languages from configuration
        self.supported_languages = getattr(settings, "VOICE_DETECTOR_SUPPORTED_LANGUAGES", ["Tamil", "English", "Hindi", "Malayalam", "Telugu"])
        self.logger.info(f"VoiceDetector initialized with device: {self.device}")

    def _load_model(self) -> None:
        if self._model is not None and self._processor is not None:
            return

        try:
            self.logger.info("Loading voice detector model...")
            model_loader = get_model_loader()
            self._model, self._processor = model_loader.get_voice_detector_model()
            self.logger.info("Voice detector model loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load voice detector model: {e}")
            raise RuntimeError(f"Could not load voice detector model: {e}") from e

    def _validate_language(self, language: str) -> None:
        if language not in self.supported_languages:
            raise ValueError(
                f"Unsupported language: {language}. Supported languages: {', '.join(self.supported_languages)}"
            )

    def decode_base64_mp3(self, audio_base64: str) -> np.ndarray:
        try:
            audio_bytes = base64.b64decode(audio_base64)

            import librosa

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                tmp_file.write(audio_bytes)
                tmp_path = tmp_file.name

            try:
                waveform, sr = librosa.load(tmp_path, sr=self.SAMPLE_RATE, mono=True)
                if waveform is None or len(waveform) == 0:
                    raise ValueError("Decoded audio is empty")
                self.logger.debug(f"Decoded audio: {len(waveform)} samples at {sr}Hz")
                return waveform
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        except base64.binascii.Error as e:
            raise ValueError(f"Invalid base64 encoding: {e}") from e
        except Exception as e:
            self.logger.error(f"Failed to decode audio: {e}")
            raise ValueError(f"Audio decoding failed: {e}") from e

    def _generate_explanation(self, classification: str, confidence: float, language: str) -> str:
        if classification == "AI_GENERATED":
            if confidence > 0.9:
                return f"High confidence AI-generated voice detected in {language}. Strong synthetic patterns identified."
            elif confidence > 0.7:
                return f"AI-generated voice detected in {language}. Unnatural pitch consistency and robotic speech patterns."
            else:
                return f"Likely AI-generated voice in {language}. Some synthetic characteristics detected."
        else:
            if confidence > 0.9:
                return f"High confidence human voice detected in {language}. Natural speech patterns confirmed."
            elif confidence > 0.7:
                return f"Human voice detected in {language}. Natural variations and organic speech characteristics."
            else:
                return f"Likely human voice in {language}. Predominantly natural speech patterns."

    def classify(self, audio_path: Optional[str] = None, audio_waveform: Optional[np.ndarray] = None, language: str = "English") -> Dict[str, Any]:
        self._validate_language(language)
        self._load_model()

        if audio_path is None and audio_waveform is None:
            raise ValueError("Either audio_path or audio_waveform must be provided")
        if audio_path is not None and audio_waveform is not None:
            raise ValueError("Provide only one of audio_path or audio_waveform")

        try:
            if audio_path is not None:
                import librosa
                waveform, sr = librosa.load(audio_path, sr=self.SAMPLE_RATE, mono=True)
            else:
                waveform = audio_waveform

            if waveform is None or len(waveform) == 0:
                raise ValueError("Audio waveform is empty")

            self.logger.debug(f"Processing audio: {len(waveform)} samples, language={language}")

            inputs = self._processor(waveform, sampling_rate=self.SAMPLE_RATE, return_tensors="pt", padding=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model(**inputs)
                logits = outputs.logits
                probabilities = torch.nn.functional.softmax(logits, dim=-1)
                predicted_class = torch.argmax(probabilities, dim=-1).item()
                confidence = probabilities[0][predicted_class].item()

            classification = self.LABEL_MAPPING.get(predicted_class, "HUMAN")
            explanation = self._generate_explanation(classification, confidence, language)

            result = {
                "classification": classification,
                "confidence": float(confidence),
                "explanation": explanation,
                "language": language,
            }

            self.logger.info(f"Classification: {classification}, confidence={confidence:.3f}, language={language}")
            return result

        except Exception as e:
            self.logger.error(f"Voice classification failed: {e}", exc_info=True)
            raise RuntimeError(f"Voice classification error: {e}") from e

    def classify_demo(self, audio_path: Optional[str] = None, audio_waveform: Optional[np.ndarray] = None, language: str = "English", mock_result: bool = False) -> Dict[str, Any]:
        if settings.DEMO_MODE and mock_result:
            self.logger.info("Returning mock voice detection result (demo mode)")
            import random
            is_ai = random.choice([True, False])
            if is_ai:
                return {
                    "classification": "AI_GENERATED",
                    "confidence": 0.91,
                    "explanation": f"Unnatural pitch consistency and robotic speech patterns detected in {language}",
                    "language": language,
                }
            else:
                return {
                    "classification": "HUMAN",
                    "confidence": 0.88,
                    "explanation": f"Natural variations and organic speech characteristics detected in {language}",
                    "language": language,
                }

        return self.classify(audio_path=audio_path, audio_waveform=audio_waveform, language=language)


# Module-level singleton
_voice_detector_instance: Optional[VoiceDetector] = None


def get_voice_detector() -> VoiceDetector:
    global _voice_detector_instance
    if _voice_detector_instance is None:
        _voice_detector_instance = VoiceDetector()
    return _voice_detector_instance
