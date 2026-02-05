"""Text-to-Speech synthesis using Coqui TTS."""

from __future__ import annotations

import io
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import librosa
import numpy as np
import soundfile as sf

from app.core.config import settings
from app.core.logger import get_logger
from app.models.model_loader import get_model_loader

logger = get_logger("pipeline.tts")


class CoquiTTS:
    """
    Text-to-Speech synthesis using Coqui TTS.
    
    Features:
    - Lazy loading of TTS model via ModelLoader singleton
    - Intelligent text chunking for long inputs
    - Configurable audio quality (sample rate, vocoder)
    - Support for WAV output (file and bytes)
    - Demo mode for testing without models
    
    Examples:
        >>> tts = CoquiTTS()
        >>> result = tts.synthesize("Hello, this is a test.")
        >>> print(result["duration_seconds"])
        1.5
    """

    # Audio configuration
    DEFAULT_SAMPLE_RATE = 22050  # Standard TTS output rate
    
    # Text processing limits
    MAX_TEXT_LENGTH = 5000  # Maximum characters per synthesis
    CHUNK_SIZE = 500  # Characters per chunk for long text
    MIN_TEXT_LENGTH = 1  # Minimum valid text length
    
    # Text splitting
    SENTENCE_DELIMITERS = ['.', '!', '?', '\n']
    
    # Language support
    SUPPORTED_LANGUAGES = ['en']

    def __init__(self, device: Optional[str] = None) -> None:
        """
        Initialize CoquiTTS.
        
        Args:
            device: Optional device override ("cpu" or "cuda").
                   If None, uses device from settings.
        """
        self.device = device or settings.DEVICE
        self.logger = get_logger("pipeline.tts")
        self._tts_model: Optional[Any] = None
        self._model_sample_rate: Optional[int] = None
        self._output_sample_rate_override: Optional[int] = None
        self.sample_rate = self.DEFAULT_SAMPLE_RATE
        
        self.logger.info(f"CoquiTTS initialized with device: {self.device}")

    def _load_model(self) -> None:
        """
        Load TTS model (lazy loading).
        
        Raises:
            RuntimeError: If model loading fails.
        """
        if self._tts_model is not None:
            return

        try:
            self.logger.info("Loading TTS model...")
            model_loader = get_model_loader()
            self._tts_model = model_loader.get_tts_model()
            
            if self._tts_model is None:
                raise RuntimeError("TTS model loaded as None")

            # Capture native model sample rate
            try:
                self._model_sample_rate = int(self._tts_model.synthesizer.output_sample_rate)
            except Exception:
                self._model_sample_rate = self.DEFAULT_SAMPLE_RATE

            # Default sample rate to model's native rate
            if self._output_sample_rate_override is None:
                self.sample_rate = self._model_sample_rate
            else:
                self.sample_rate = self._output_sample_rate_override
            
            self.logger.info("TTS model loaded successfully")

        except FileNotFoundError as e:
            self.logger.error("TTS model not found. Run: python scripts/download_models.py")
            raise FileNotFoundError(
                "TTS model not downloaded. Run 'python scripts/download_models.py'"
            ) from e

        except Exception as e:
            self.logger.error(f"Failed to load TTS model: {e}")
            raise RuntimeError(f"Could not load TTS model: {e}") from e

    def _validate_text(self, text: str) -> None:
        """
        Validate input text.
        
        Args:
            text: Text to validate.
            
        Raises:
            ValueError: If text is invalid.
        """
        if text is None or not isinstance(text, str):
            raise ValueError("Text must be a string")

        stripped = text.strip()
        if not stripped:
            raise ValueError("Text cannot be empty")

        if len(text) > self.MAX_TEXT_LENGTH:
            raise ValueError(
                f"Text too long ({len(text)} chars). "
                f"Maximum length: {self.MAX_TEXT_LENGTH} characters"
            )

        if len(stripped) < self.MIN_TEXT_LENGTH:
            raise ValueError(f"Text too short (minimum {self.MIN_TEXT_LENGTH} character)")

        self.logger.debug(f"Text validation passed: {len(text)} characters")

    def _split_by_delimiters(self, text: str, delimiters: List[str]) -> List[str]:
        """
        Split text by delimiters while preserving them.
        
        Args:
            text: Text to split.
            delimiters: List of delimiter characters.
            
        Returns:
            List of text segments with delimiters attached.
        """
        if not delimiters:
            return [text]

        # Create regex pattern that captures delimiters
        pattern = f"([{''.join(re.escape(d) for d in delimiters)}])"
        parts = re.split(pattern, text)
        
        # Reconstruct sentences with delimiters
        sentences = []
        current = ""
        
        for part in parts:
            if not part:
                continue
            current += part
            if part in delimiters:
                sentences.append(current)
                current = ""
        
        if current:
            sentences.append(current)
        
        return sentences

    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into chunks for processing.
        
        Uses intelligent sentence-boundary splitting to maintain
        natural speech flow.
        
        Args:
            text: Text to chunk.
            
        Returns:
            List of text chunks.
        """
        if len(text) <= self.CHUNK_SIZE:
            return [text]

        # Split into sentences
        sentences = self._split_by_delimiters(text, self.SENTENCE_DELIMITERS)
        
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            # If adding this sentence would exceed chunk size
            if len(current_chunk) + len(sentence) > self.CHUNK_SIZE:
                # Save current chunk if not empty
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += sentence

        # Add final chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        self.logger.debug(f"Text chunked into {len(chunks)} segments")
        return chunks

    def _normalize_audio(self, audio_array: np.ndarray) -> np.ndarray:
        """
        Normalize audio amplitude to [-1, 1] range.
        
        Args:
            audio_array: Audio samples.
            
        Returns:
            Normalized audio array.
        """
        max_val = np.abs(audio_array).max()
        
        if max_val > 0:
            return audio_array / max_val
        
        return audio_array

    def _resample_audio(self, audio_array: np.ndarray, target_rate: int) -> np.ndarray:
        """Resample audio to target sample rate if needed."""
        if self._model_sample_rate is None or self._model_sample_rate == target_rate:
            return audio_array
        return librosa.resample(audio_array, orig_sr=self._model_sample_rate, target_sr=target_rate)

    def synthesize(
        self,
        text: str,
        output_path: Optional[Path] = None,
        language: Optional[str] = None,
        speaker: Optional[Union[str, int]] = None,
        speaker_wav: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Synthesize speech from text.
        
        Args:
            text: Text to synthesize.
            output_path: Optional path to save WAV file.
            language: Optional language code (defaults to settings.TTS_LANGUAGE).
            speaker: Optional speaker ID/name (if supported by model).
            speaker_wav: Optional path to a reference speaker WAV (if supported).
            
        Returns:
            Dictionary containing:
                - audio_array: NumPy array of audio samples
                - sample_rate: Sample rate in Hz
                - duration_seconds: Audio duration
                - output_path: File path (if saved)
                - text_length: Input text length
                - num_chunks: Number of chunks processed
                - processing_time_ms: Processing time
                
        Raises:
            ValueError: If text is invalid.
            RuntimeError: If synthesis fails.
            
        Examples:
            >>> tts = CoquiTTS()
            >>> result = tts.synthesize("Hello world", Path("output.wav"))
            >>> print(f"Duration: {result['duration_seconds']:.2f}s")
        """
        start_time = time.time()

        try:
            # Validate input
            self._validate_text(text)

            # Load model
            self._load_model()

            # Chunk text
            chunks = self._chunk_text(text)
            self.logger.info(f"Synthesizing {len(chunks)} text chunks")

            # Resolve audio quality parameters
            lang = language or settings.TTS_LANGUAGE
            if lang and lang not in self.SUPPORTED_LANGUAGES:
                raise ValueError(f"Unsupported language: {lang}")

            resolved_speaker = speaker if speaker is not None else settings.TTS_SPEAKER
            if resolved_speaker is not None and hasattr(self._tts_model, "speakers"):
                if self._tts_model.speakers and resolved_speaker not in self._tts_model.speakers:
                    raise ValueError(f"Unknown speaker: {resolved_speaker}")

            # Synthesize each chunk
            audio_segments = []
            for i, chunk in enumerate(chunks):
                self.logger.debug(f"Synthesizing chunk {i+1}/{len(chunks)}")
                
                # Generate audio for chunk
                tts_kwargs: Dict[str, Any] = {"text": chunk}
                if lang:
                    tts_kwargs["language"] = lang
                if resolved_speaker is not None:
                    tts_kwargs["speaker"] = resolved_speaker
                if speaker_wav is not None:
                    tts_kwargs["speaker_wav"] = str(speaker_wav)

                chunk_audio = self._tts_model.tts(**tts_kwargs)
                
                # Convert to numpy array if needed
                if not isinstance(chunk_audio, np.ndarray):
                    chunk_audio = np.array(chunk_audio)
                
                audio_segments.append(chunk_audio)

            # Concatenate all segments
            if len(audio_segments) > 1:
                audio_array = np.concatenate(audio_segments)
            else:
                audio_array = audio_segments[0]

            # Normalize audio
            audio_array = self._normalize_audio(audio_array)

            # Resample if override is set
            if self._output_sample_rate_override is not None:
                audio_array = self._resample_audio(audio_array, self._output_sample_rate_override)
                self.sample_rate = self._output_sample_rate_override

            # Save to file if requested
            if output_path:
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(output_path), audio_array, self.sample_rate)
                self.logger.info(f"Audio saved to: {output_path}")

            # Calculate metrics
            duration = len(audio_array) / self.sample_rate
            elapsed = time.time() - start_time

            self.logger.info(
                f"Synthesis complete: {duration:.2f}s audio, "
                f"{elapsed:.2f}s processing time"
            )

            return {
                "audio_array": audio_array,
                "sample_rate": self.sample_rate,
                "duration_seconds": float(duration),
                "output_path": str(output_path) if output_path else None,
                "text_length": len(text),
                "num_chunks": len(chunks),
                "processing_time_ms": int(elapsed * 1000),
            }

        except (ValueError, FileNotFoundError) as e:
            # Re-raise validation and model errors
            raise

        except Exception as e:
            self.logger.error(f"Synthesis failed: {e}", exc_info=True)
            raise RuntimeError(f"TTS synthesis error: {e}") from e

    def synthesize_to_file(
        self,
        text: str,
        output_path: Path
    ) -> Dict[str, Any]:
        """
        Synthesize speech and save to file.
        
        Args:
            text: Text to synthesize.
            output_path: Path to save WAV file.
            
        Returns:
            Synthesis result dictionary.
            
        Raises:
            ValueError: If text is invalid.
            IOError: If file write fails.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        return self.synthesize(text, output_path)

    def synthesize_to_bytes(self, text: str) -> bytes:
        """
        Synthesize speech and return as WAV bytes.
        
        Args:
            text: Text to synthesize.
            
        Returns:
            WAV audio as bytes.
            
        Raises:
            ValueError: If text is invalid.
            RuntimeError: If synthesis fails.
            
        Examples:
            >>> tts = CoquiTTS()
            >>> audio_bytes = tts.synthesize_to_bytes("Hello")
            >>> len(audio_bytes)
            44144
        """
        try:
            # Synthesize without saving to file
            result = self.synthesize(text)
            audio_array = result["audio_array"]
            
            # Create in-memory WAV file
            buffer = io.BytesIO()
            sf.write(buffer, audio_array, self.sample_rate, format='WAV')
            
            # Get bytes
            audio_bytes = buffer.getvalue()
            self.logger.debug(f"Generated {len(audio_bytes)} bytes of audio")
            
            return audio_bytes

        except Exception as e:
            self.logger.error(f"Failed to generate audio bytes: {e}")
            raise

    def synthesize_to_temp_file(self, text: str) -> Path:
        """
        Synthesize speech and save to temporary file.
        
        Args:
            text: Text to synthesize.
            
        Returns:
            Path to temporary WAV file.
            
        Note:
            Caller is responsible for cleaning up the temporary file.
            
        Examples:
            >>> tts = CoquiTTS()
            >>> temp_path = tts.synthesize_to_temp_file("Hello")
            >>> # Use the file...
            >>> tts.cleanup_temp_file(temp_path)
        """
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix='.wav',
            dir=tempfile.gettempdir()
        )
        temp_path = Path(temp_file.name)
        temp_file.close()

        # Synthesize to temp file
        self.synthesize_to_file(text, temp_path)
        
        self.logger.info(f"Audio saved to temporary file: {temp_path}")
        return temp_path

    def set_sample_rate(self, sample_rate: int) -> None:
        """
        Set sample rate for future synthesis.
        
        Args:
            sample_rate: Sample rate in Hz (8000-48000).
            
        Raises:
            ValueError: If sample rate is out of valid range.
        """
        if not 8000 <= sample_rate <= 48000:
            raise ValueError(
                f"Sample rate {sample_rate} out of range. "
                "Valid range: 8000-48000 Hz"
            )

        self._output_sample_rate_override = sample_rate
        self.sample_rate = sample_rate

        if self._model_sample_rate and self._model_sample_rate != sample_rate:
            self.logger.warning(
                f"Sample rate override set to {sample_rate} Hz; "
                f"model native rate is {self._model_sample_rate} Hz. Audio will be resampled."
            )
        else:
            self.logger.info(f"Sample rate set to {sample_rate} Hz")

    def get_audio_info(self, audio_array: np.ndarray) -> Dict[str, Any]:
        """
        Get metadata about audio array.
        
        Args:
            audio_array: Audio samples.
            
        Returns:
            Dictionary with audio metadata:
                - duration_seconds: Audio duration
                - sample_rate: Sample rate
                - num_samples: Number of samples
                - max_amplitude: Maximum amplitude
                - rms_level: RMS level
                - is_clipping: Whether audio is clipping
        """
        duration = len(audio_array) / self.sample_rate
        max_amplitude = float(np.abs(audio_array).max())
        rms_level = float(np.sqrt(np.mean(audio_array ** 2)))

        return {
            "duration_seconds": float(duration),
            "sample_rate": self.sample_rate,
            "num_samples": len(audio_array),
            "max_amplitude": max_amplitude,
            "rms_level": rms_level,
            "is_clipping": max_amplitude >= 1.0,
        }

    def synthesize_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Synthesize multiple texts in batch.
        
        Args:
            texts: List of texts to synthesize.
            
        Returns:
            List of synthesis results in same order as input.
            
        Examples:
            >>> tts = CoquiTTS()
            >>> results = tts.synthesize_batch(["Hello", "World"])
            >>> len(results)
            2
        """
        if not texts:
            return []

        self.logger.info(f"Starting batch synthesis of {len(texts)} texts")

        # Load model once
        self._load_model()

        results = []
        success_count = 0
        
        for i, text in enumerate(texts):
            try:
                self.logger.debug(f"Synthesizing batch item {i+1}/{len(texts)}")
                result = self.synthesize(text)
                results.append(result)
                success_count += 1

            except Exception as e:
                self.logger.error(f"Batch synthesis failed for item {i}: {e}")
                # Append error result
                results.append({
                    "audio_array": None,
                    "sample_rate": self.sample_rate,
                    "duration_seconds": 0.0,
                    "output_path": None,
                    "text_length": len(text) if isinstance(text, str) else 0,
                    "num_chunks": 0,
                    "processing_time_ms": 0,
                    "error": str(e),
                })

        self.logger.info(
            f"Batch synthesis complete: {success_count}/{len(texts)} succeeded"
        )
        return results

    def synthesize_demo(
        self,
        text: str,
        mock_audio: bool = False
    ) -> Dict[str, Any]:
        """
        Synthesize with demo mode support.
        
        If settings.DEMO_MODE is True and mock_audio is True,
        returns mock audio without loading models.
        
        Args:
            text: Text to synthesize.
            mock_audio: If True in demo mode, return mock audio.
            
        Returns:
            Synthesis result (real or mocked).
            
        Examples:
            >>> tts = CoquiTTS()
            >>> # In demo mode
            >>> result = tts.synthesize_demo("Test", mock_audio=True)
        """
        if settings.DEMO_MODE and mock_audio:
            self.logger.info("Returning mock audio (demo mode)")
            
            # Generate 2 seconds of silence as mock audio
            mock_audio_array = np.zeros(int(self.sample_rate * 2.0))
            
            return {
                "audio_array": mock_audio_array,
                "sample_rate": self.sample_rate,
                "duration_seconds": 2.0,
                "output_path": None,
                "text_length": len(text),
                "num_chunks": 1,
                "processing_time_ms": 100,
            }

        # Real synthesis
        return self.synthesize(text)

    def cleanup_temp_file(self, file_path: Path) -> None:
        """
        Clean up temporary file.
        
        Args:
            file_path: Path to file to delete.
        """
        try:
            file_path = Path(file_path)
            if file_path.exists():
                file_path.unlink()
                self.logger.debug(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            self.logger.warning(f"Failed to cleanup temporary file: {e}")


# Module-level singleton
_tts_instance: Optional[CoquiTTS] = None


def get_coqui_tts() -> CoquiTTS:
    """
    Get the global CoquiTTS singleton instance.
    
    Returns:
        CoquiTTS singleton instance.
        
    Examples:
        >>> tts = get_coqui_tts()
        >>> result = tts.synthesize("Hello world")
    """
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = CoquiTTS()
    return _tts_instance
