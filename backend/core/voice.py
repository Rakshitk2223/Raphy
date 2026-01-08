import asyncio
from enum import Enum
from typing import Callable, Optional
import numpy as np

from backend.core.audio import audio_recorder, vad
from backend.core.stt import transcribe_audio
from backend.core.tts import speak, stop_playback


class VoiceState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    MUTED = "muted"


class VoiceService:
    def __init__(self):
        self.state = VoiceState.IDLE
        self.is_muted = True
        self.on_state_change: Optional[Callable[[VoiceState], None]] = None
        self.on_transcription: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self._listening_task: Optional[asyncio.Task] = None
        self._speak_queue: asyncio.Queue = asyncio.Queue()
        self._speak_task: Optional[asyncio.Task] = None

    def set_state(self, state: VoiceState):
        self.state = state
        if self.on_state_change:
            self.on_state_change(state)

    def toggle_mute(self) -> bool:
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.stop_listening()
            self.set_state(VoiceState.MUTED)
        else:
            self.set_state(VoiceState.IDLE)
        return self.is_muted

    def set_muted(self, muted: bool):
        self.is_muted = muted
        if muted:
            self.stop_listening()
            self.set_state(VoiceState.MUTED)
        else:
            self.set_state(VoiceState.IDLE)

    async def start_listening(self):
        if self.is_muted:
            return

        if self.state == VoiceState.LISTENING:
            return

        self.set_state(VoiceState.LISTENING)
        audio_recorder.start_recording()

    async def stop_listening(self) -> Optional[str]:
        if self.state != VoiceState.LISTENING:
            return None

        self.set_state(VoiceState.PROCESSING)

        audio = audio_recorder.stop_recording()

        if len(audio) < 1600:
            self.set_state(VoiceState.IDLE)
            return None

        try:
            text = await transcribe_audio(audio)
            self.set_state(VoiceState.IDLE)

            if text and text.strip():
                if self.on_transcription:
                    self.on_transcription(text.strip())
                return text.strip()

            return None
        except Exception as e:
            self.set_state(VoiceState.IDLE)
            if self.on_error:
                self.on_error(str(e))
            return None

    def cancel_listening(self):
        if self.state == VoiceState.LISTENING:
            audio_recorder.stop_recording()
            self.set_state(VoiceState.IDLE)

    async def speak_text(self, text: str):
        if not text.strip():
            return

        self.set_state(VoiceState.SPEAKING)

        try:
            await speak(text)
        except Exception as e:
            if self.on_error:
                self.on_error(str(e))
        finally:
            if self.state == VoiceState.SPEAKING:
                self.set_state(VoiceState.IDLE)

    def stop_speaking(self):
        stop_playback()
        if self.state == VoiceState.SPEAKING:
            self.set_state(VoiceState.IDLE)

    async def toggle_listening(self):
        if self.is_muted:
            return None

        if self.state == VoiceState.LISTENING:
            return await self.stop_listening()
        elif self.state == VoiceState.IDLE:
            await self.start_listening()
            return None
        elif self.state == VoiceState.SPEAKING:
            self.stop_speaking()
            await self.start_listening()
            return None

        return None


voice_service = VoiceService()
