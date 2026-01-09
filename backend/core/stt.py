import asyncio
import time
from pathlib import Path
from typing import Optional
import numpy as np

from backend.config import settings

_whisper_model = None


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        model_size = settings.stt_model
        device = settings.stt_device if settings.stt_device != "auto" else "cuda"
        compute_type = (
            settings.stt_compute_type if settings.stt_compute_type != "auto" else "float16"
        )

        _whisper_model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )
        print(f"Whisper model '{model_size}' loaded on {device}")

    return _whisper_model


async def transcribe_audio(
    audio: np.ndarray,
    sample_rate: int = 16000,
    language: Optional[str] = None,
) -> str:
    model = get_whisper_model()

    if language is None:
        language = settings.stt_language

    loop = asyncio.get_event_loop()

    def _transcribe():
        transcribe_start = time.perf_counter()
        segments, info = model.transcribe(
            audio,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            ),
            language=language,
            initial_prompt="This is a conversation in English or Hindi (Hinglish). The speaker may mix English and Hindi.",
        )

        detected_lang = info.language if hasattr(info, "language") else None
        prob = info.language_probability if hasattr(info, "language_probability") else 0
        print(f"[STT] Detected language: {detected_lang}, probability: {prob:.2f}")

        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        transcribe_time = time.perf_counter() - transcribe_start
        audio_duration = len(audio) / sample_rate
        rtf = transcribe_time / audio_duration if audio_duration > 0 else 0
        print(
            f"[TIMING] STT transcribe: {transcribe_time:.2f}s for {audio_duration:.1f}s audio (RTF: {rtf:.2f}x)"
        )

        return " ".join(text_parts)

    result = await loop.run_in_executor(None, _transcribe)
    return result


async def transcribe_file(
    file_path: Path,
    language: Optional[str] = None,
) -> str:
    model = get_whisper_model()

    loop = asyncio.get_event_loop()

    def _transcribe():
        segments, info = model.transcribe(
            str(file_path),
            beam_size=5,
            vad_filter=True,
            language=language,
        )

        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        return " ".join(text_parts)

    result = await loop.run_in_executor(None, _transcribe)
    return result
