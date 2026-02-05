"""Safe model download script - downloads one at a time to avoid OOM."""

from __future__ import annotations

import subprocess
import sys
import time
import gc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("scripts.download_models_safe")


def download_whisper_model() -> bool:
    """Download Whisper ASR model."""
    try:
        logger.info(f"Downloading Whisper model: {settings.WHISPER_MODEL_NAME}")
        import whisper
        
        whisper_dir = settings.MODELS_DIR / "whisper"
        whisper_dir.mkdir(parents=True, exist_ok=True)
        
        start_time = time.time()
        model = whisper.load_model(
            settings.WHISPER_MODEL_NAME,
            download_root=str(whisper_dir)
        )
        elapsed = time.time() - start_time
        
        if model is not None:
            logger.info(f"✓ Whisper model downloaded successfully in {elapsed:.2f}s")
            # Force garbage collection to free memory
            del model
            gc.collect()
            return True
        else:
            logger.error("✗ Whisper model download returned None")
            return False
            
    except Exception as e:
        logger.error(f"✗ Failed to download Whisper model: {e}")
        return False


def download_distilbert_model() -> bool:
    """Download NLI-compatible model for zero-shot classification."""
    try:
        logger.info(f"Downloading NLI model: {settings.DISTILBERT_MODEL_NAME}")
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        
        distilbert_dir = settings.distilbert_model_path
        distilbert_dir.mkdir(parents=True, exist_ok=True)
        
        start_time = time.time()
        model = AutoModelForSequenceClassification.from_pretrained(
            settings.DISTILBERT_MODEL_NAME
        )
        tokenizer = AutoTokenizer.from_pretrained(settings.DISTILBERT_MODEL_NAME)
        
        model.save_pretrained(str(distilbert_dir))
        tokenizer.save_pretrained(str(distilbert_dir))
        elapsed = time.time() - start_time
        
        logger.info(f"✓ NLI model downloaded in {elapsed:.2f}s")
        del model, tokenizer
        gc.collect()
        return True
        
    except (OSError, Exception) as e:
        logger.error(f"✗ Failed to download DistilBERT/BART models: {e}")
        return False


def download_spacy_model() -> bool:
    """Download and install spaCy model."""
    try:
        logger.info(f"Downloading spaCy model: {settings.SPACY_MODEL_NAME}")
        import spacy
        
        start_time = time.time()
        
        try:
            model = spacy.load(settings.SPACY_MODEL_NAME)
            logger.info("✓ spaCy model already installed")
            del model
            gc.collect()
            return True
        except OSError:
            pass
        
        result = subprocess.run(
            [sys.executable, "-m", "spacy", "download", settings.SPACY_MODEL_NAME],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            logger.error(f"✗ spaCy download failed: {result.stderr}")
            return False
        
        model = spacy.load(settings.SPACY_MODEL_NAME)
        elapsed = time.time() - start_time
        
        if model is not None:
            logger.info(f"✓ spaCy model downloaded and verified in {elapsed:.2f}s")
            del model
            gc.collect()
            return True
        else:
            logger.error("✗ spaCy model verification failed")
            return False
            
    except (OSError, SystemExit, Exception) as e:
        logger.error(f"✗ Failed to download spaCy model: {e}")
        return False


def download_tts_model() -> bool:
    """Download TTS model."""
    try:
        import os
        logger.info(f"Downloading TTS model: {settings.TTS_MODEL_NAME}")
        from TTS.api import TTS
        
        tts_dir = settings.MODELS_DIR / "tts"
        tts_dir.mkdir(parents=True, exist_ok=True)
        
        os.environ["TTS_HOME"] = str(tts_dir)
        
        start_time = time.time()
        tts = TTS(model_name=settings.TTS_MODEL_NAME, progress_bar=True)
        elapsed = time.time() - start_time
        
        if tts is not None:
            logger.info(f"✓ TTS model downloaded successfully in {elapsed:.2f}s")
            del tts
            gc.collect()
            return True
        else:
            logger.error("✗ TTS model download returned None")
            return False
            
    except Exception as e:
        logger.error(f"✗ Failed to download TTS model: {e}")
        return False


def download_llm_model() -> bool:
    """Download LLM model for local inference."""
    if settings.LLM_USE_API:
        logger.info("LLM_USE_API enabled; skipping local LLM download")
        return True

    try:
        logger.info(f"Downloading LLM model: {settings.LLM_MODEL_NAME}")
        from transformers import AutoModelForCausalLM, AutoTokenizer

        llm_dir = settings.llm_model_path
        llm_dir.mkdir(parents=True, exist_ok=True)

        start_time = time.time()
        model = AutoModelForCausalLM.from_pretrained(settings.LLM_MODEL_NAME)
        tokenizer = AutoTokenizer.from_pretrained(settings.LLM_MODEL_NAME)

        model.save_pretrained(str(llm_dir))
        tokenizer.save_pretrained(str(llm_dir))
        elapsed = time.time() - start_time

        logger.info(f"✓ LLM model downloaded in {elapsed:.2f}s")
        del model, tokenizer
        gc.collect()
        return True

    except Exception as e:
        logger.error(f"✗ Failed to download LLM model: {e}")
        return False


def download_voice_detector_model() -> bool:
    """Download voice deepfake detection model."""
    try:
        logger.info(f"Downloading voice detector model: {settings.VOICE_DETECTOR_MODEL_NAME}")
        from transformers import AutoModelForAudioClassification, Wav2Vec2Processor

        voice_detector_dir = settings.voice_detector_model_path
        voice_detector_dir.mkdir(parents=True, exist_ok=True)

        start_time = time.time()
        model = AutoModelForAudioClassification.from_pretrained(settings.VOICE_DETECTOR_MODEL_NAME)
        processor = Wav2Vec2Processor.from_pretrained(settings.VOICE_DETECTOR_MODEL_NAME)

        model.save_pretrained(str(voice_detector_dir))
        processor.save_pretrained(str(voice_detector_dir))
        elapsed = time.time() - start_time

        logger.info(f"✓ Voice detector model downloaded in {elapsed:.2f}s")
        del model, processor
        gc.collect()
        return True

    except Exception as e:
        logger.error(f"✗ Failed to download voice detector model: {e}")
        return False


def check_disk_space() -> bool:
    """Check if sufficient disk space is available."""
    try:
        import shutil
        stats = shutil.disk_usage(settings.MODELS_DIR.parent)
        free_gb = stats.free / (1024 ** 3)
        
        if free_gb < 5:
            logger.error(f"✗ Insufficient disk space: {free_gb:.2f}GB free (5GB required)")
            return False
        
        logger.info(f"✓ Disk space check passed: {free_gb:.2f}GB available")
        return True
        
    except Exception as e:
        logger.warning(f"Could not check disk space: {e}")
        return True


def main() -> None:
    """Main execution function - downloads models one at a time."""
    logger.info("=" * 60)
    logger.info("Starting SAFE model download process (one at a time)")
    logger.info("=" * 60)
    
    settings.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Models directory: {settings.MODELS_DIR}")
    
    if not check_disk_space():
        sys.exit(1)
    
    # Download models one by one
    models = [
        ("whisper", download_whisper_model),
        ("distilbert", download_distilbert_model),
        ("spacy", download_spacy_model),
        ("tts", download_tts_model),
        ("llm", download_llm_model),
        ("voice_detector", download_voice_detector_model),
    ]
    
    results = {}
    for model_name, download_func in models:
        logger.info(f"\n{'='*60}")
        logger.info(f"Downloading: {model_name}")
        logger.info(f"{'='*60}")
        
        success = download_func()
        results[model_name] = success
        
        # Wait between downloads to allow memory cleanup
        logger.info(f"Waiting 5 seconds before next model...")
        time.sleep(5)
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Download Summary")
    logger.info("=" * 60)
    
    for model_name, success in results.items():
        status = "✓ SUCCESS" if success else "✗ FAILED"
        logger.info(f"{model_name:15s}: {status}")
    
    logger.info("=" * 60)
    
    failed = [k for k, v in results.items() if not v]
    if failed:
        logger.error(f"Some models failed: {failed}")
        sys.exit(1)
    
    logger.info("All models downloaded successfully!")


if __name__ == "__main__":
    main()
