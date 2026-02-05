"""Scam detection module using zero-shot classification with DistilBERT."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.models.model_loader import get_model_loader

logger = get_logger("pipeline.detector")


class ScamDetector:
    """
    Scam detection using zero-shot classification.
    
    Uses a two-stage classification approach:
    1. Binary classification: scam vs legitimate
    2. Multi-class classification: specific scam types
    
    Examples:
        >>> detector = ScamDetector()
        >>> result = detector.detect("You've won a lottery! Send money to claim.")
        >>> print(result["is_scam"], result["scam_type"])
        True, "lottery scam"
    """

    # Primary classification labels
    PRIMARY_LABELS = ["scam", "legitimate"]

    # Scam type classification labels
    SCAM_TYPE_LABELS = [
        "phishing scam",
        "tech support scam",
        "lottery scam",
        "investment fraud",
        "romance scam",
        "impersonation scam",
        "refund scam",
        "job scam",
        "other scam",
    ]

    # Configuration thresholds
    SCAM_THRESHOLD = 0.5  # Minimum probability to classify as scam
    TYPE_CONFIDENCE_THRESHOLD = 0.3  # Minimum confidence for scam type
    MAX_TRANSCRIPT_LENGTH = 10000  # Maximum characters to process

    def __init__(self, device: Optional[str] = None) -> None:
        """
        Initialize the ScamDetector.
        
        Args:
            device: Optional device override ("cpu" or "cuda").
                    If None, uses device from settings.
        """
        self.device = device or settings.DEVICE
        self.logger = get_logger("pipeline.detector")
        self._pipeline: Optional[Any] = None
        
        self.logger.info(f"ScamDetector initialized with device: {self.device}")

    def _load_model(self) -> None:
        """
        Load the zero-shot classification pipeline (lazy loading).
        
        Raises:
            RuntimeError: If model loading fails.
        """
        if self._pipeline is not None:
            return

        try:
            self.logger.info("Loading zero-shot classification pipeline...")
            from transformers import pipeline

            # Get model and tokenizer from ModelLoader
            model_loader = get_model_loader()
            model, tokenizer = model_loader.get_distilbert_model()

            # Create zero-shot classification pipeline
            self._pipeline = pipeline(
                "zero-shot-classification",
                model=model,
                tokenizer=tokenizer,
                device=0 if self.device == "cuda" else -1,
            )

            self.logger.info("Zero-shot classification pipeline loaded successfully")

        except Exception as e:
            self.logger.error(f"Failed to load classification pipeline: {e}")
            raise RuntimeError(f"Could not load scam detection model: {e}") from e

    def _validate_transcript(self, transcript: str) -> None:
        """
        Validate transcript input.
        
        Args:
            transcript: The transcript to validate.
            
        Raises:
            ValueError: If transcript is invalid.
        """
        if not transcript or not isinstance(transcript, str):
            raise ValueError("Transcript must be a non-empty string")

        if not transcript.strip():
            raise ValueError("Transcript cannot be empty or whitespace only")

        if len(transcript) > self.MAX_TRANSCRIPT_LENGTH:
            raise ValueError(
                f"Transcript too long ({len(transcript)} chars). "
                f"Maximum length is {self.MAX_TRANSCRIPT_LENGTH} characters"
            )

    def detect_scam(self, transcript: str) -> Dict[str, Any]:
        """
        Perform binary scam detection (scam vs legitimate).
        
        Args:
            transcript: The text to classify.
            
        Returns:
            Dictionary containing:
                - is_scam: Boolean indicating if text is a scam
                - scam_probability: Float probability (0-1) of being a scam
                - confidence_scores: Dict mapping labels to probabilities
                
        Raises:
            ValueError: If transcript is invalid.
            RuntimeError: If classification fails.
        """
        self._validate_transcript(transcript)
        self._load_model()

        try:
            self.logger.debug(f"Running primary scam detection on transcript: {transcript[:100]}...")

            # Run zero-shot classification
            result = self._pipeline(
                transcript,
                candidate_labels=self.PRIMARY_LABELS,
                multi_label=False,
            )

            # Extract scores
            scores = dict(zip(result["labels"], result["scores"]))
            scam_probability = scores.get("scam", 0.0)
            is_scam = scam_probability >= self.SCAM_THRESHOLD

            self.logger.info(
                f"Primary detection: is_scam={is_scam}, "
                f"probability={scam_probability:.3f}"
            )

            return {
                "is_scam": is_scam,
                "scam_probability": float(scam_probability),
                "confidence_scores": {k: float(v) for k, v in scores.items()},
            }

        except Exception as e:
            self.logger.error(f"Scam detection failed: {e}")
            raise RuntimeError(f"Scam detection error: {e}") from e

    def classify_scam_type(self, transcript: str) -> Dict[str, Any]:
        """
        Classify the specific type of scam.
        
        Should only be called if transcript is classified as a scam.
        
        Args:
            transcript: The scam text to classify.
            
        Returns:
            Dictionary containing:
                - scam_type: String indicating the scam category (or None)
                - type_confidence: Float confidence score for the type
                - all_type_scores: Dict mapping all scam types to probabilities
                
        Raises:
            ValueError: If transcript is invalid.
            RuntimeError: If classification fails.
        """
        self._validate_transcript(transcript)
        self._load_model()

        try:
            self.logger.debug("Running scam type classification...")

            # Run zero-shot classification for scam types
            result = self._pipeline(
                transcript,
                candidate_labels=self.SCAM_TYPE_LABELS,
                multi_label=False,
            )

            # Extract scores
            all_scores = dict(zip(result["labels"], result["scores"]))
            top_type = result["labels"][0]
            top_confidence = result["scores"][0]

            # Only return type if confidence exceeds threshold
            scam_type = top_type if top_confidence >= self.TYPE_CONFIDENCE_THRESHOLD else None

            self.logger.info(
                f"Scam type: {scam_type or 'unknown'}, "
                f"confidence={top_confidence:.3f}"
            )

            return {
                "scam_type": scam_type,
                "type_confidence": float(top_confidence),
                "all_type_scores": {k: float(v) for k, v in all_scores.items()},
            }

        except Exception as e:
            self.logger.error(f"Scam type classification failed: {e}")
            raise RuntimeError(f"Scam type classification error: {e}") from e

    def detect(self, transcript: str) -> Dict[str, Any]:
        """
        Perform complete scam detection (binary + type classification).
        
        This is the main entry point for scam detection. It performs:
        1. Binary classification (scam vs legitimate)
        2. If scam, classifies the specific scam type
        
        Args:
            transcript: The text to analyze.
            
        Returns:
            Dictionary compatible with DetectResponse schema:
                - is_scam: Boolean
                - scam_probability: Float (0-1)
                - scam_type: String or None
                - confidence_scores: Dict with all classification scores
                
        Raises:
            ValueError: If transcript is invalid.
            RuntimeError: If detection fails.
            
        Examples:
            >>> detector = ScamDetector()
            >>> result = detector.detect("Call this number to fix your computer.")
            >>> result["is_scam"]
            True
            >>> result["scam_type"]
            "tech support scam"
        """
        try:
            # Stage 1: Binary scam detection
            primary_result = self.detect_scam(transcript)

            # Stage 2: Scam type classification (if detected as scam)
            scam_type = None
            type_scores = {}

            if primary_result["is_scam"]:
                type_result = self.classify_scam_type(transcript)
                scam_type = type_result["scam_type"]
                type_scores = type_result["all_type_scores"]

            # Combine results
            combined_scores = {
                **primary_result["confidence_scores"],
                **type_scores,
            }

            result = {
                "is_scam": primary_result["is_scam"],
                "scam_probability": primary_result["scam_probability"],
                "scam_type": scam_type,
                "confidence_scores": combined_scores,
            }

            self.logger.info(
                f"Detection complete: is_scam={result['is_scam']}, "
                f"type={result['scam_type']}, "
                f"prob={result['scam_probability']:.3f}"
            )

            return result

        except ValueError as e:
            # Re-raise validation errors
            raise

        except Exception as e:
            # Log error and return safe default
            self.logger.error(f"Detection pipeline failed: {e}", exc_info=True)

            # Return safe default response
            return {
                "is_scam": False,
                "scam_probability": 0.0,
                "scam_type": None,
                "confidence_scores": {},
            }

    def detect_batch(self, transcripts: List[str]) -> List[Dict[str, Any]]:
        """
        Perform scam detection on multiple transcripts (batch processing).
        
        Uses true batched inference for efficiency.
        
        Args:
            transcripts: List of texts to analyze.
            
        Returns:
            List of detection results in the same order as input.
            
        Raises:
            ValueError: If any transcript is invalid.
            
        Examples:
            >>> detector = ScamDetector()
            >>> results = detector.detect_batch([
            ...     "You won a prize!",
            ...     "Meeting at 3pm tomorrow."
            ... ])
            >>> len(results)
            2
        """
        if not transcripts:
            return []

        self.logger.info(f"Running batch detection on {len(transcripts)} transcripts")

        # Validate all transcripts first
        for i, transcript in enumerate(transcripts):
            try:
                self._validate_transcript(transcript)
            except ValueError as e:
                self.logger.error(f"Invalid transcript at index {i}: {e}")
                raise

        # Load model once
        self._load_model()

        try:
            # Batch primary scam detection
            self.logger.debug("Running batched primary scam detection...")
            primary_results = self._pipeline(
                transcripts,
                candidate_labels=self.PRIMARY_LABELS,
                multi_label=False,
            )

            # Process results
            results = []
            scam_indices = []
            scam_transcripts = []

            for i, result in enumerate(primary_results):
                scores = dict(zip(result["labels"], result["scores"]))
                scam_probability = scores.get("scam", 0.0)
                is_scam = scam_probability >= self.SCAM_THRESHOLD

                results.append({
                    "is_scam": is_scam,
                    "scam_probability": float(scam_probability),
                    "scam_type": None,
                    "confidence_scores": {k: float(v) for k, v in scores.items()},
                })

                if is_scam:
                    scam_indices.append(i)
                    scam_transcripts.append(transcripts[i])

            # Batch type classification for scam transcripts only
            if scam_transcripts:
                self.logger.debug(f"Running batched type classification for {len(scam_transcripts)} scams...")
                type_results = self._pipeline(
                    scam_transcripts,
                    candidate_labels=self.SCAM_TYPE_LABELS,
                    multi_label=False,
                )

                for idx, type_result in zip(scam_indices, type_results):
                    all_scores = dict(zip(type_result["labels"], type_result["scores"]))
                    top_type = type_result["labels"][0]
                    top_confidence = type_result["scores"][0]

                    # Only assign type if confidence exceeds threshold
                    scam_type = top_type if top_confidence >= self.TYPE_CONFIDENCE_THRESHOLD else None

                    # Update result with type information
                    results[idx]["scam_type"] = scam_type
                    results[idx]["confidence_scores"].update(
                        {k: float(v) for k, v in all_scores.items()}
                    )

            self.logger.info(f"Batch detection complete: {len(results)} results")
            return results

        except Exception as e:
            self.logger.error(f"Batch detection pipeline failed: {e}", exc_info=True)
            # Return safe defaults for all transcripts on failure
            return [
                {
                    "is_scam": False,
                    "scam_probability": 0.0,
                    "scam_type": None,
                    "confidence_scores": {},
                }
                for _ in transcripts
            ]

    def detect_demo(
        self,
        transcript: str,
        mock_result: bool = False
    ) -> Dict[str, Any]:
        """
        Perform detection with demo mode support.
        
        If settings.DEMO_MODE is True and mock_result is True,
        returns realistic mock results without loading models.
        
        Args:
            transcript: The text to analyze.
            mock_result: If True in demo mode, return mock data.
            
        Returns:
            Detection result (real or mocked based on configuration).
            
        Examples:
            >>> detector = ScamDetector()
            >>> # In demo mode with mock enabled
            >>> result = detector.detect_demo("Test text", mock_result=True)
        """
        if settings.DEMO_MODE and mock_result:
            self.logger.info("Returning mock detection result (demo mode)")

            # Generate realistic mock result based on keywords
            transcript_lower = transcript.lower()
            scam_keywords = [
                "lottery", "prize", "won", "winner", "claim",
                "refund", "tax", "payment", "urgent", "verify",
                "suspend", "account", "password", "click", "link",
            ]

            has_scam_keyword = any(kw in transcript_lower for kw in scam_keywords)

            if has_scam_keyword:
                return {
                    "is_scam": True,
                    "scam_probability": 0.87,
                    "scam_type": "lottery scam",
                    "confidence_scores": {
                        "scam": 0.87,
                        "legitimate": 0.13,
                        "lottery scam": 0.72,
                        "phishing scam": 0.15,
                        "tech support scam": 0.08,
                    },
                }
            else:
                return {
                    "is_scam": False,
                    "scam_probability": 0.23,
                    "scam_type": None,
                    "confidence_scores": {
                        "scam": 0.23,
                        "legitimate": 0.77,
                    },
                }

        # Use real detection
        return self.detect(transcript)


# Module-level singleton
_detector_instance: Optional[ScamDetector] = None


def get_scam_detector() -> ScamDetector:
    """
    Get the global ScamDetector singleton instance.
    
    Returns:
        ScamDetector singleton instance.
        
    Examples:
        >>> detector = get_scam_detector()
        >>> result = detector.detect("Suspicious text")
    """
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = ScamDetector()
    return _detector_instance
