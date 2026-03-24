import asyncio
from enum import Enum
from typing import Any, Callable, Optional
import numpy as np

from backend.core.audio import audio_recorder, continuous_stream, vad
from backend.core.stt import transcribe_audio
from backend.core.tts import speak, stop_playback, reset_stop_flag


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
            self.cancel_listening()
            self.set_state(VoiceState.MUTED)
        else:
            self.set_state(VoiceState.IDLE)
        return self.is_muted

    def set_muted(self, muted: bool):
        self.is_muted = muted
        if muted:
            self.cancel_listening()
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
            print("[Voice] stop_listening called but not in LISTENING state")
            return None

        self.set_state(VoiceState.PROCESSING)

        audio = audio_recorder.stop_recording()
        print(f"[Voice] Recorded audio: {len(audio)} samples, duration: {len(audio) / 16000:.2f}s")

        if len(audio) < 1600:
            print("[Voice] Audio too short, discarding")
            self.set_state(VoiceState.IDLE)
            return None

        import numpy as np

        rms = np.sqrt(np.mean(audio**2))
        print(f"[Voice] Audio RMS energy: {rms:.6f}")

        if rms < 0.001:
            print("[Voice] Audio too quiet, might be silence")

        try:
            print("[Voice] Starting transcription...")
            text = await transcribe_audio(audio)
            print(f"[Voice] Transcription result: '{text}'")
            self.set_state(VoiceState.IDLE)

            if text and text.strip():
                if self.on_transcription:
                    self.on_transcription(text.strip())
                return text.strip()

            return None
        except Exception as e:
            print(f"[Voice] Transcription error: {e}")
            import traceback

            traceback.print_exc()
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


class ConversationalVoiceService:
    def __init__(self):
        self.state = VoiceState.IDLE
        self.is_running = False
        self.is_muted = False
        self._conversation_task: Optional[asyncio.Task] = None
        self._audio_buffer: list[np.ndarray] = []
        self._silence_frames = 0
        self._speech_frames = 0
        self._barge_in_requested = False

        self.on_state_change: Optional[Callable[[VoiceState], None]] = None
        self.on_transcription: Optional[Callable[[str], Any]] = None
        self.on_error: Optional[Callable[[str], None]] = None

        self.silence_threshold_frames = 30
        self.speech_threshold_frames = 3
        self.sample_rate = 16000
        self.frame_duration_ms = 30
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)

    def set_state(self, state: VoiceState):
        if self.state != state:
            print(f"[ConvVoice] State: {self.state.value} -> {state.value}")
            self.state = state
            if self.on_state_change:
                try:
                    self.on_state_change(state)
                except Exception as e:
                    print(f"[ConvVoice] Error in state change callback: {e}")

    async def start(self):
        if self.is_running:
            return

        self.is_running = True
        self.is_muted = False
        self._barge_in_requested = False
        continuous_stream.start()
        self._conversation_task = asyncio.create_task(self._conversation_loop())
        print("[ConvVoice] Conversational mode started")

    async def stop(self):
        self.is_running = False
        if self._conversation_task:
            self._conversation_task.cancel()
            try:
                await self._conversation_task
            except asyncio.CancelledError:
                pass
            self._conversation_task = None
        continuous_stream.stop()
        self.set_state(VoiceState.IDLE)
        print("[ConvVoice] Conversational mode stopped")

    def set_muted(self, muted: bool):
        self.is_muted = muted
        if muted:
            self.set_state(VoiceState.MUTED)
            stop_playback()
        else:
            self.set_state(VoiceState.IDLE)

    def request_barge_in(self):
        if self.state == VoiceState.SPEAKING:
            self._barge_in_requested = True
            stop_playback()
            print("[ConvVoice] Barge-in requested")

    async def _conversation_loop(self):
        print("[ConvVoice] Conversation loop started")

        while self.is_running:
            try:
                if self.is_muted:
                    await asyncio.sleep(0.1)
                    continue

                if self.state == VoiceState.IDLE:
                    self.set_state(VoiceState.LISTENING)
                    self._audio_buffer = []
                    self._silence_frames = 0
                    self._speech_frames = 0

                if self.state == VoiceState.LISTENING:
                    await self._listen_for_speech()

                elif self.state == VoiceState.PROCESSING:
                    await asyncio.sleep(0.05)

                elif self.state == VoiceState.SPEAKING:
                    await self._monitor_for_barge_in()

                else:
                    await asyncio.sleep(0.05)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[ConvVoice] Error in conversation loop: {e}")
                import traceback

                traceback.print_exc()
                await asyncio.sleep(0.1)

        print("[ConvVoice] Conversation loop ended")

    async def _listen_for_speech(self):
        frame = await asyncio.get_event_loop().run_in_executor(
            None, lambda: continuous_stream.get_frame(timeout=0.1)
        )

        if frame is None:
            return

        is_speech = vad.is_speech_frame(frame, self.frame_duration_ms)

        if is_speech:
            self._speech_frames += 1
            self._silence_frames = 0
            self._audio_buffer.append(frame)
        else:
            if self._speech_frames > 0:
                self._audio_buffer.append(frame)
                self._silence_frames += 1

        if (
            self._speech_frames >= self.speech_threshold_frames
            and self._silence_frames >= self.silence_threshold_frames
        ):
            await self._process_speech()

    async def _process_speech(self):
        if len(self._audio_buffer) == 0:
            self.set_state(VoiceState.IDLE)
            return

        self.set_state(VoiceState.PROCESSING)

        audio = np.concatenate(self._audio_buffer)
        self._audio_buffer = []
        self._speech_frames = 0
        self._silence_frames = 0

        duration = len(audio) / self.sample_rate
        print(f"[ConvVoice] Processing {duration:.2f}s of audio")

        if duration < 0.3:
            print("[ConvVoice] Audio too short, ignoring")
            self.set_state(VoiceState.LISTENING)
            return

        try:
            text = await transcribe_audio(audio)
            print(f"[ConvVoice] Transcribed: '{text}'")

            if text and text.strip() and self.on_transcription:
                self.set_state(VoiceState.SPEAKING)
                continuous_stream.clear_queue()

                try:
                    await self.on_transcription(text.strip())
                except Exception as e:
                    print(f"[ConvVoice] Error in transcription callback: {e}")

                if not self._barge_in_requested:
                    self.set_state(VoiceState.IDLE)
                self._barge_in_requested = False
            else:
                self.set_state(VoiceState.LISTENING)

        except Exception as e:
            print(f"[ConvVoice] Transcription error: {e}")
            self.set_state(VoiceState.LISTENING)

    async def _monitor_for_barge_in(self):
        frame = await asyncio.get_event_loop().run_in_executor(
            None, lambda: continuous_stream.get_frame(timeout=0.05)
        )

        if frame is None:
            return

        is_speech = vad.is_speech_frame(frame, self.frame_duration_ms)

        if is_speech:
            self._speech_frames += 1
            self._audio_buffer.append(frame)

            if self._speech_frames >= self.speech_threshold_frames:
                print("[ConvVoice] Barge-in detected!")
                self.request_barge_in()
                self.set_state(VoiceState.LISTENING)
                self._silence_frames = 0
        else:
            self._speech_frames = 0
            self._audio_buffer = []


voice_service = VoiceService()
conversational_service = ConversationalVoiceService()
