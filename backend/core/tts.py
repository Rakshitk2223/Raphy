import asyncio
import re
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import AsyncGenerator, Optional
import numpy as np
import sounddevice as sd

from backend.config import settings

PIPER_VOICES = {
    "en": {
        "name": "en_US-amy-medium",
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx",
        "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx.json",
    },
    "hi": {
        "name": "hi_IN-priyamvada-medium",
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/hi/hi_IN/priyamvada/medium/hi_IN-priyamvada-medium.onnx",
        "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/hi/hi_IN/priyamvada/medium/hi_IN-priyamvada-medium.onnx.json",
    },
}

EMOJI_PATTERN = re.compile(
    "["
    "\U0001f600-\U0001f64f"
    "\U0001f300-\U0001f5ff"
    "\U0001f680-\U0001f6ff"
    "\U0001f1e0-\U0001f1ff"
    "\U00002702-\U000027b0"
    "\U000024c2-\U0001f251"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "\U00002600-\U000026ff"
    "\U00002700-\U000027bf"
    "]+",
    flags=re.UNICODE,
)

SENTENCE_END_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z\u0900-\u097F])|(?<=[.!?])$")

_playback_lock = asyncio.Lock()
_stop_requested = False


def strip_emojis(text: str) -> str:
    cleaned = EMOJI_PATTERN.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def split_into_sentences(text: str) -> list[str]:
    sentences = SENTENCE_END_PATTERN.split(text)
    return [s.strip() for s in sentences if s.strip()]


def detect_language(text: str) -> str:
    hindi_chars = set("अआइईउऊएऐओऔकखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहािीुूेैोौंःँ")
    hindi_count = sum(1 for char in text if char in hindi_chars)
    if hindi_count > len(text) * 0.1:
        return "hi"
    return "en"


def get_voice_path(language: str) -> tuple[Path, Path]:
    voice_info = PIPER_VOICES.get(language, PIPER_VOICES["en"])
    voice_dir = settings.piper_model_dir
    voice_dir.mkdir(parents=True, exist_ok=True)

    model_path = voice_dir / f"{voice_info['name']}.onnx"
    config_path = voice_dir / f"{voice_info['name']}.onnx.json"

    return model_path, config_path


async def download_voice(language: str) -> bool:
    voice_info = PIPER_VOICES.get(language, PIPER_VOICES["en"])
    model_path, config_path = get_voice_path(language)

    if model_path.exists() and config_path.exists():
        return True

    print(f"Downloading Piper voice: {voice_info['name']}...")

    try:
        import httpx

        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
            if not model_path.exists():
                response = await client.get(voice_info["url"])
                response.raise_for_status()
                model_path.write_bytes(response.content)
                print(f"Downloaded: {model_path.name}")

            if not config_path.exists():
                response = await client.get(voice_info["config_url"])
                response.raise_for_status()
                config_path.write_bytes(response.content)
                print(f"Downloaded: {config_path.name}")

        return True
    except Exception as e:
        print(f"Failed to download voice: {e}")
        return False


async def synthesize_speech(
    text: str,
    language: Optional[str] = None,
    output_path: Optional[Path] = None,
) -> Optional[Path]:
    if not text.strip():
        return None

    text = strip_emojis(text)
    if not text.strip():
        return None

    if language is None:
        language = detect_language(text)

    if not await download_voice(language):
        print("Voice not available, falling back to English")
        language = "en"
        if not await download_voice(language):
            return None

    model_path, config_path = get_voice_path(language)

    if output_path is None:
        output_path = Path(tempfile.mktemp(suffix=".wav"))

    loop = asyncio.get_event_loop()

    def _synthesize():
        try:
            cmd = [
                "piper",
                "--model",
                str(model_path),
                "--config",
                str(config_path),
                "--output_file",
                str(output_path),
            ]

            process = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=30,
            )

            if process.returncode != 0:
                print(f"Piper error: {process.stderr.decode()}")
                return None

            return output_path
        except Exception as e:
            print(f"TTS synthesis error: {e}")
            return None

    result = await loop.run_in_executor(None, _synthesize)
    return result


async def speak(text: str, language: Optional[str] = None):
    wav_path = await synthesize_speech(text, language)

    if wav_path and wav_path.exists():
        await play_audio(wav_path)
        wav_path.unlink(missing_ok=True)


async def speak_streaming(text_generator: AsyncGenerator[str, None], on_sentence_start=None):
    global _stop_requested
    _stop_requested = False

    buffer = ""
    language = None

    async for chunk in text_generator:
        if _stop_requested:
            break

        buffer += chunk

        if language is None and len(buffer) > 20:
            language = detect_language(buffer)

        sentences = split_into_sentences(buffer)

        if len(sentences) > 1:
            for sentence in sentences[:-1]:
                if _stop_requested:
                    break

                if on_sentence_start:
                    on_sentence_start(sentence)

                await speak(sentence, language)

            buffer = sentences[-1]

    if buffer.strip() and not _stop_requested:
        if on_sentence_start:
            on_sentence_start(buffer)
        await speak(buffer, language)


async def speak_sentence(sentence: str, language: Optional[str] = None) -> bool:
    global _stop_requested
    if _stop_requested:
        return False

    wav_path = await synthesize_speech(sentence, language)
    if wav_path and wav_path.exists():
        await play_audio(wav_path)
        wav_path.unlink(missing_ok=True)
        return True
    return False


async def play_audio(file_path: Path):
    global _stop_requested
    loop = asyncio.get_event_loop()

    def _play():
        global _stop_requested
        try:
            with wave.open(str(file_path), "rb") as wf:
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()
                frames = wf.readframes(wf.getnframes())

                audio = np.frombuffer(frames, dtype=np.int16)
                audio = audio.astype(np.float32) / 32768.0

                if channels > 1:
                    audio = audio.reshape(-1, channels)

                sd.play(audio, sample_rate)
                while sd.get_stream().active:
                    if _stop_requested:
                        sd.stop()
                        break
                    sd.sleep(50)
        except Exception as e:
            print(f"Audio playback error: {e}")

    async with _playback_lock:
        await loop.run_in_executor(None, _play)


def stop_playback():
    global _stop_requested
    _stop_requested = True
    sd.stop()


def reset_stop_flag():
    global _stop_requested
    _stop_requested = False
