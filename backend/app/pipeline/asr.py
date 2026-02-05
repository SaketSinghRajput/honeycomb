"""Automatic Speech Recognition (ASR) module using OpenAI Whisper."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import librosa
import numpy as np
import soundfile as sf

from app.core.config import settings
from app.core.logger import get_logger
from app.models.model_loader import get_model_loader

logger = get_logger("pipeline.asr")


class WhisperASR:
    """
    Automatic Speech Recognition using OpenAI Whisper.
    
    Features:
    - Lazy loading of Whisper model via ModelLoader singleton
    - Audio validation and preprocessing with librosa
    - Support for multiple audio formats
    - Batch transcription support
    - Demo mode for testing without models
    
    Examples:
        >>> asr = WhisperASR()
        >>> result = asr.transcribe(Path("audio.wav"))
        >>> print(result["transcript"])
        "Hello, this is a test recording."
    """

    # Supported audio formats
    SUPPORTED_FORMATS = [".wav", ".mp3", ".m4a", ".flac", ".ogg"]
    
    # Whisper configuration
    SAMPLE_RATE = 16000  # Whisper's expected sample rate
    MAX_AUDIO_DURATION_SECONDS = 300  # 5 minutes
    MIN_AUDIO_DURATION_SECONDS = 0.1  # 100ms minimum
    MAX_FILE_SIZE_MB = 50  # Maximum audio file size

    def __init__(self, device: Optional[str] = None) -> None:
        """
        Initialize WhisperASR.
        
        Args:
            device: Optional device override ("cpu" or "cuda").
                   If None, uses device from settings.
        """
        self.device = device or settings.DEVICE
        self.logger = get_logger("pipeline.asr")
        self._whisper_model: Optional[Any] = None
        
        self.logger.info(f"WhisperASR initialized with device: {self.device}")

    def _load_model(self) -> None:
        """
        Load Whisper model (lazy loading).
        
        Raises:
            RuntimeError: If model loading fails.
        """
        if self._whisper_model is not None:
            return

        try:
            self.logger.info("Loading Whisper model...")
            model_loader = get_model_loader()
            self._whisper_model = model_loader.get_whisper_model()
            self.logger.info("Whisper model loaded successfully")

        except FileNotFoundError as e:
            self.logger.error("Whisper model not found. Run: python scripts/download_models.py")
            raise FileNotFoundError(
                "Whisper model not downloaded. Run 'python scripts/download_models.py'"
            ) from e

        except Exception as e:
            self.logger.error(f"Failed to load Whisper model: {e}")
            raise RuntimeError(f"Could not load Whisper model: {e}") from e

    def _validate_audio_file(self, audio_path: Path) -> None:
        """
        Validate audio file path and basic properties.
        
        Args:
            audio_path: Path to audio file.
            
        Raises:
            ValueError: If file is invalid.
            FileNotFoundError: If file doesn't exist.
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if not audio_path.is_file():
            raise ValueError(f"Path is not a file: {audio_path}")

        # Check file extension
        if audio_path.suffix.lower() not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported audio format: {audio_path.suffix}. "
                f"Supported formats: {', '.join(self.SUPPORTED_FORMATS)}"
            )

        # Check file size
        file_size_mb = audio_path.stat().st_size / (1024 * 1024)
        if file_size_mb == 0:
            raise ValueError("Audio file is empty")

        if file_size_mb > self.MAX_FILE_SIZE_MB:
            self.logger.warning(
                f"Large audio file ({file_size_mb:.2f}MB). "
                f"Processing may be slow."
            )

    def _validate_audio_data(
        self,
        audio_array: np.ndarray,
        sample_rate: int
    ) -> None:
        """
        Validate audio data array.
        
        Args:
            audio_array: Audio samples as numpy array.
            sample_rate: Sample rate in Hz.
            
        Raises:
            ValueError: If audio data is invalid.
        """
        if audio_array is None or len(audio_array) == 0:
            raise ValueError("Audio data is empty")

        # Calculate duration
        duration = len(audio_array) / sample_rate

        if duration < self.MIN_AUDIO_DURATION_SECONDS:
            raise ValueError(
                f"Audio too short ({duration:.2f}s). "
                f"Minimum duration: {self.MIN_AUDIO_DURATION_SECONDS}s"
            )

        if duration > self.MAX_AUDIO_DURATION_SECONDS:
            raise ValueError(
                f"Audio too long ({duration:.2f}s). "
                f"Maximum duration: {self.MAX_AUDIO_DURATION_SECONDS}s"
            )

        # Check for silent audio
        max_amplitude = np.abs(audio_array).max()
        if max_amplitude < 1e-6:
            raise ValueError("Audio appears to be silent (no signal detected)")

    def _preprocess_audio(self, audio_path: Path) -> tuple[np.ndarray, int]:
        """
        Load and preprocess audio file.
        
        Performs:
        - Loading with librosa
        - Resampling to SAMPLE_RATE
        - Conversion to mono
        - Amplitude normalization
        
        Args:
            audio_path: Path to audio file.
            
        Returns:
            Tuple of (audio_array, sample_rate).
            
        Raises:
            RuntimeError: If preprocessing fails.
        """
        try:
            self.logger.debug(f"Loading audio: {audio_path}")

            # Load audio with resampling to target sample rate
            audio_array, sample_rate = librosa.load(
                str(audio_path),
                sr=self.SAMPLE_RATE,
                mono=True
            )

            # Normalize amplitude
            if audio_array.max() > 0:
                audio_array = audio_array / np.abs(audio_array).max()

            self.logger.debug(
                f"Audio loaded: duration={len(audio_array)/sample_rate:.2f}s, "
                f"sr={sample_rate}Hz"
            )

            return audio_array, sample_rate

        except Exception as e:
            self.logger.error(f"Audio preprocessing failed: {e}")
            raise RuntimeError(
                f"Failed to preprocess audio: {e}. "
                "File may be corrupted or in unsupported format."
            ) from e

    def _save_uploaded_audio(
        self,
        audio_bytes: bytes,
        filename: str
    ) -> Path:
        """
        Save uploaded audio bytes to temporary file.
        
        Args:
            audio_bytes: Audio data as bytes.
            filename: Original filename (for extension).
            
        Returns:
            Path to temporary audio file.
            
        Raises:
            ValueError: If filename has no extension.
            RuntimeError: If file saving fails.
        """
        try:
            # Extract extension from filename
            file_path = Path(filename)
            extension = file_path.suffix.lower()

            if not extension:
                extension = ".wav"  # Default to WAV

            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=extension,
                dir=tempfile.gettempdir()
            )
            temp_path = Path(temp_file.name)

            # Write bytes to file
            temp_file.write(audio_bytes)
            temp_file.close()

            self.logger.debug(f"Saved uploaded audio to: {temp_path}")
            return temp_path

        except Exception as e:
            self.logger.error(f"Failed to save uploaded audio: {e}")
            raise RuntimeError(f"Could not save audio file: {e}") from e

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcribe audio file to text.
        
        Args:
            audio_path: Path to audio file.
            language: Optional language code (e.g., "en", "hi"). 
                     If None, Whisper auto-detects.
                     
        Returns:
            Dictionary containing:
                - transcript: Transcribed text
                - language: Detected/specified language
                - duration_seconds: Audio duration
                - confidence: Confidence score (if available)
                
        Raises:
            FileNotFoundError: If audio file not found.
            ValueError: If audio is invalid.
            RuntimeError: If transcription fails.
            
        Examples:
            >>> asr = WhisperASR()
            >>> result = asr.transcribe(Path("call.wav"))
            >>> print(result["transcript"])
        """
        start_time = time.time()

        try:
            # Validate input file
            self._validate_audio_file(audio_path)

            # Load model
            self._load_model()

            # Preprocess audio
            audio_array, sample_rate = self._preprocess_audio(audio_path)

            # Validate audio data
            self._validate_audio_data(audio_array, sample_rate)

            # Transcribe with Whisper
            self.logger.info(f"Transcribing audio: {audio_path.name}")
            
            transcribe_options = {
                "fp16": False,  # Disable FP16 for CPU compatibility
            }
            if language:
                transcribe_options["language"] = language

            result = self._whisper_model.transcribe(
                str(audio_path),
                **transcribe_options
            )

            # Extract results
            transcript = result.get("text", "").strip()
            detected_language = result.get("language", language or "unknown")

            duration = len(audio_array) / sample_rate
            elapsed = time.time() - start_time

            self.logger.info(
                f"Transcription complete: {len(transcript)} chars, "
                f"duration={duration:.2f}s, elapsed={elapsed:.2f}s"
            )

            return {
                "transcript": transcript,
                "language": detected_language,
                "duration_seconds": float(duration),
                "confidence": None,  # Whisper doesn't provide confidence scores
            }

        except (FileNotFoundError, ValueError) as e:
            # Re-raise validation errors
            raise

        except Exception as e:
            self.logger.error(f"Transcription failed: {e}", exc_info=True)
            raise RuntimeError(f"Transcription error: {e}") from e

    def transcribe_from_bytes(
        self,
        audio_bytes: bytes,
        filename: str,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcribe audio from bytes (e.g., uploaded file).
        
        Args:
            audio_bytes: Audio data as bytes.
            filename: Original filename (for format detection).
            language: Optional language code.
            
        Returns:
            Transcription result dictionary (same as transcribe).
            
        Raises:
            ValueError: If audio bytes are invalid.
            RuntimeError: If transcription fails.
            
        Examples:
            >>> asr = WhisperASR()
            >>> with open("audio.wav", "rb") as f:
            ...     result = asr.transcribe_from_bytes(f.read(), "audio.wav")
        """
        temp_path: Optional[Path] = None

        try:
            # Save to temporary file
            temp_path = self._save_uploaded_audio(audio_bytes, filename)

            # Transcribe from file
            result = self.transcribe(temp_path, language=language)

            return result

        finally:
            # Clean up temporary file
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                    self.logger.debug(f"Cleaned up temporary file: {temp_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to delete temporary file: {e}")

    def transcribe_stream(
        self,
        audio_chunks: Iterator[bytes],
        filename: str,
        language: Optional[str] = None,
        max_chunk_size: int = 100 * 1024 * 1024  # 100MB max
    ) -> Dict[str, Any]:
        """
        Transcribe audio from streaming chunks.
        
        Note: This implementation buffers all chunks before transcription.
        True real-time streaming requires VAD and incremental processing.
        
        Args:
            audio_chunks: Iterator yielding audio byte chunks.
            filename: Filename for format detection.
            language: Optional language code.
            max_chunk_size: Maximum total size to prevent memory overflow.
            
        Returns:
            Transcription result dictionary.
            
        Raises:
            ValueError: If stream is too large.
            RuntimeError: If transcription fails.
        """
        try:
            self.logger.info("Accumulating audio stream chunks...")

            # Accumulate chunks
            buffer = bytearray()
            total_size = 0

            for chunk in audio_chunks:
                total_size += len(chunk)
                if total_size > max_chunk_size:
                    raise ValueError(
                        f"Audio stream too large (>{max_chunk_size/1024/1024}MB)"
                    )
                buffer.extend(chunk)

            self.logger.info(f"Stream complete: {total_size/1024:.2f}KB")

            # Transcribe accumulated buffer
            return self.transcribe_from_bytes(bytes(buffer), filename, language)

        except Exception as e:
            self.logger.error(f"Stream transcription failed: {e}")
            raise

    def transcribe_demo(
        self,
        audio_path: Optional[Path] = None,
        mock_transcript: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcribe with demo mode support.
        
        If settings.DEMO_MODE is True and mock_transcript is provided,
        returns mock result without loading models.
        
        Args:
            audio_path: Path to audio file (if using real transcription).
            mock_transcript: Mock transcript text (for demo mode).
            
        Returns:
            Transcription result (real or mocked).
            
        Examples:
            >>> asr = WhisperASR()
            >>> # In demo mode
            >>> result = asr.transcribe_demo(mock_transcript="Hello world")
        """
        if settings.DEMO_MODE and mock_transcript:
            self.logger.info("Returning mock transcription (demo mode)")
            return {
                "transcript": mock_transcript,
                "language": "en",
                "duration_seconds": 10.5,
                "confidence": 0.95,
            }

        # Real transcription
        if audio_path is None:
            raise ValueError("audio_path required when not in demo mode")

        return self.transcribe(audio_path)

    def get_audio_info(self, audio_path: Path) -> Dict[str, Any]:
        """
        Get audio file metadata without transcription.
        
        Args:
            audio_path: Path to audio file.
            
        Returns:
            Dictionary with audio metadata:
                - duration: Duration in seconds
                - sample_rate: Sample rate in Hz
                - channels: Number of channels
                - format: File format
                - file_size_mb: File size in MB
                
        Raises:
            FileNotFoundError: If file doesn't exist.
            RuntimeError: If metadata extraction fails.
        """
        try:
            self._validate_audio_file(audio_path)

            # Get duration and sample rate
            duration = librosa.get_duration(path=str(audio_path))

            # Get detailed info from soundfile
            info = sf.info(str(audio_path))

            file_size_mb = audio_path.stat().st_size / (1024 * 1024)

            return {
                "duration": float(duration),
                "sample_rate": info.samplerate,
                "channels": info.channels,
                "format": info.format,
                "file_size_mb": float(file_size_mb),
            }

        except Exception as e:
            self.logger.error(f"Failed to get audio info: {e}")
            raise RuntimeError(f"Could not read audio metadata: {e}") from e

    def transcribe_batch(
        self,
        audio_paths: List[Path],
        language: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Transcribe multiple audio files in batch.
        
        Args:
            audio_paths: List of audio file paths.
            language: Optional language code for all files.
            
        Returns:
            List of transcription results in same order as input.
            Individual failures are logged but don't stop processing.
            
        Examples:
            >>> asr = WhisperASR()
            >>> paths = [Path("audio1.wav"), Path("audio2.wav")]
            >>> results = asr.transcribe_batch(paths)
        """
        if not audio_paths:
            return []

        self.logger.info(f"Starting batch transcription of {len(audio_paths)} files")

        # Load model once
        self._load_model()

        results = []
        for i, audio_path in enumerate(audio_paths):
            try:
                self.logger.info(f"Processing {i+1}/{len(audio_paths)}: {audio_path.name}")
                result = self.transcribe(audio_path, language=language)
                results.append(result)

            except Exception as e:
                self.logger.error(f"Batch transcription failed for {audio_path}: {e}")
                # Append error result
                results.append({
                    "transcript": "",
                    "language": "unknown",
                    "duration_seconds": 0.0,
                    "confidence": None,
                    "error": str(e),
                })

        self.logger.info(f"Batch transcription complete: {len(results)} results")
        return results


# Module-level singleton
_asr_instance: Optional[WhisperASR] = None


def get_whisper_asr() -> WhisperASR:
    """
    Get the global WhisperASR singleton instance.
    
    Returns:
        WhisperASR singleton instance.
        
    Examples:
        >>> asr = get_whisper_asr()
        >>> result = asr.transcribe(Path("audio.wav"))
    """
    global _asr_instance
    if _asr_instance is None:
        _asr_instance = WhisperASR()
    return _asr_instance
