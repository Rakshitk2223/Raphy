import asyncio
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional
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


async def play_audio(file_path: Path):
    loop = asyncio.get_event_loop()

    def _play():
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
                sd.wait()
        except Exception as e:
            print(f"Audio playback error: {e}")

    await loop.run_in_executor(None, _play)


def stop_playback():
    sd.stop()
