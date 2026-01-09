import asyncio
import re
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import AsyncGenerator, Optional
import numpy as np
import sounddevice as sd

from backend.config import settings

EDGE_VOICES = {
    "en": "en-US-AriaNeural",
    "hi": "hi-IN-SwaraNeural",
}

PIPER_VOICES = {
    "en": {
        "name": "en_US-lessac-medium",
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "config_url": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
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
_use_edge_tts = True

SPEECH_RATE = 1.0


def clean_text_for_speech(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"\\\[|\\\]|\\\(|\\\)", "", cleaned)
    cleaned = re.sub(r"\\times", " times ", cleaned)
    cleaned = re.sub(r"\\div", " divided by ", cleaned)
    cleaned = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"\1 over \2", cleaned)
    cleaned = re.sub(r"\\sqrt\{([^}]+)\}", r"square root of \1", cleaned)
    cleaned = re.sub(r"\\[a-zA-Z]+", "", cleaned)
    cleaned = re.sub(r"[*_`#~\[\]{}|<>\\]", "", cleaned)
    cleaned = re.sub(r"\s*[:]\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = EMOJI_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def strip_emojis(text: str) -> str:
    return clean_text_for_speech(text)


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


async def synthesize_with_edge(
    text: str,
    language: Optional[str] = None,
    output_path: Optional[Path] = None,
) -> Optional[Path]:
    try:
        import edge_tts

        if language is None:
            language = detect_language(text)

        voice = EDGE_VOICES.get(language, EDGE_VOICES["en"])

        if output_path is None:
            output_path = Path(tempfile.mktemp(suffix=".mp3"))

        communicate = edge_tts.Communicate(text, voice, rate="+10%")
        await communicate.save(str(output_path))

        return output_path
    except Exception as e:
        print(f"Edge TTS error: {e}")
        return None


async def synthesize_with_piper(
    text: str,
    language: Optional[str] = None,
    output_path: Optional[Path] = None,
) -> Optional[Path]:
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

    if _use_edge_tts:
        result = await synthesize_with_edge(text, language, output_path)
        if result:
            return result
        print("Edge TTS failed, falling back to Piper")

    return await synthesize_with_piper(text, language, output_path)


async def speak(text: str, language: Optional[str] = None):
    audio_path = await synthesize_speech(text, language)

    if audio_path and audio_path.exists():
        await play_audio(audio_path)
        audio_path.unlink(missing_ok=True)


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

    tts_start = time.perf_counter()
    audio_path = await synthesize_speech(sentence, language)
    synth_time = time.perf_counter() - tts_start

    if audio_path and audio_path.exists():
        play_start = time.perf_counter()
        await play_audio(audio_path)
        play_time = time.perf_counter() - play_start
        audio_path.unlink(missing_ok=True)
        print(
            f"[TIMING] TTS synth: {synth_time:.2f}s, playback: {play_time:.2f}s for {len(sentence)} chars"
        )
        return True
    return False


async def presynthesize(sentence: str, language: Optional[str] = None) -> Optional[Path]:
    if _stop_requested:
        return None
    return await synthesize_speech(sentence, language)


async def play_presynthesized(audio_path: Optional[Path]) -> bool:
    global _stop_requested
    if _stop_requested or audio_path is None:
        return False

    if audio_path.exists():
        play_start = time.perf_counter()
        await play_audio(audio_path)
        play_time = time.perf_counter() - play_start
        audio_path.unlink(missing_ok=True)
        print(f"[TIMING] TTS playback: {play_time:.2f}s (pre-synthesized)")
        return True
    return False


async def play_audio(file_path: Path, speed: float = SPEECH_RATE):
    global _stop_requested
    loop = asyncio.get_event_loop()

    def _play():
        global _stop_requested
        try:
            actual_path = file_path

            if file_path.suffix == ".mp3":
                wav_path = file_path.with_suffix(".wav")
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(file_path),
                        "-ar",
                        "24000",
                        "-ac",
                        "1",
                        str(wav_path),
                    ],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    print(f"ffmpeg error: {result.stderr.decode()}")
                    return
                actual_path = wav_path

            with wave.open(str(actual_path), "rb") as wf:
                sample_rate = wf.getframerate()
                channels = wf.getnchannels()
                frames = wf.readframes(wf.getnframes())

                audio = np.frombuffer(frames, dtype=np.int16)
                audio = audio.astype(np.float32) / 32768.0

                if channels > 1:
                    audio = audio.reshape(-1, channels)

            if file_path.suffix == ".mp3":
                actual_path.unlink(missing_ok=True)

            adjusted_rate = int(sample_rate * speed)
            sd.play(audio, adjusted_rate)
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


def set_tts_backend(use_edge: bool = True):
    global _use_edge_tts
    _use_edge_tts = use_edge
    print(f"TTS backend: {'Edge TTS' if use_edge else 'Piper'}")
