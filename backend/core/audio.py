import asyncio
import queue
import threading
from pathlib import Path
from typing import Callable, Optional
import numpy as np
import sounddevice as sd

from backend.config import settings

try:
    import webrtcvad

    WEBRTC_VAD_AVAILABLE = True
except ImportError:
    webrtcvad = None
    WEBRTC_VAD_AVAILABLE = False
    print("webrtcvad not available, using energy-based VAD")


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        dtype: str = "float32",
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.audio_queue: queue.Queue = queue.Queue()
        self.is_recording = False
        self.stream = None

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"Audio status: {status}")
        if self.is_recording:
            self.audio_queue.put(indata.copy())

    def start_recording(self):
        if self.is_recording:
            return

        self.is_recording = True
        self.audio_queue = queue.Queue()

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._audio_callback,
            blocksize=int(self.sample_rate * 0.1),
        )
        self.stream.start()

    def stop_recording(self) -> np.ndarray:
        if not self.is_recording:
            return np.array([])

        self.is_recording = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        chunks = []
        while not self.audio_queue.empty():
            chunks.append(self.audio_queue.get())

        if chunks:
            return np.concatenate(chunks, axis=0).flatten()
        return np.array([])

    def get_audio_so_far(self) -> np.ndarray:
        chunks = []
        while not self.audio_queue.empty():
            chunks.append(self.audio_queue.get())

        if chunks:
            return np.concatenate(chunks, axis=0).flatten()
        return np.array([])


class ContinuousAudioStream:
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        frame_duration_ms: int = 30,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_duration_ms = frame_duration_ms
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        self.audio_queue: queue.Queue = queue.Queue()
        self.is_running = False
        self.stream = None
        self.on_audio_frame: Optional[Callable[[np.ndarray], None]] = None

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"Audio status: {status}")
        if self.is_running:
            audio_data = indata.copy().flatten()
            self.audio_queue.put(audio_data)
            if self.on_audio_frame:
                self.on_audio_frame(audio_data)

    def start(self):
        if self.is_running:
            return

        self.is_running = True
        self.audio_queue = queue.Queue()

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._audio_callback,
            blocksize=self.frame_size,
        )
        self.stream.start()
        print("[Audio] Continuous stream started")

    def stop(self):
        self.is_running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        print("[Audio] Continuous stream stopped")

    def get_frame(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear_queue(self):
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break


class VoiceActivityDetector:
    def __init__(
        self,
        energy_threshold: float = 0.01,
        silence_duration: float = 1.0,
        sample_rate: int = 16000,
        aggressiveness: int = 2,
    ):
        self.energy_threshold = energy_threshold
        self.silence_duration = silence_duration
        self.sample_rate = sample_rate
        self.silence_samples = int(silence_duration * sample_rate)
        self.aggressiveness = aggressiveness

        if WEBRTC_VAD_AVAILABLE and webrtcvad is not None:
            self.webrtc_vad = webrtcvad.Vad(aggressiveness)  # type: ignore
        else:
            self.webrtc_vad = None

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        if len(audio_chunk) == 0:
            return False

        if self.webrtc_vad and len(audio_chunk) in [160, 320, 480]:
            try:
                audio_int16 = (audio_chunk * 32767).astype(np.int16)
                return self.webrtc_vad.is_speech(audio_int16.tobytes(), self.sample_rate)
            except Exception:
                pass

        energy = np.sqrt(np.mean(audio_chunk**2))
        return energy > self.energy_threshold

    def is_speech_frame(self, audio_frame: np.ndarray, frame_duration_ms: int = 30) -> bool:
        if len(audio_frame) == 0:
            return False

        expected_samples = int(self.sample_rate * frame_duration_ms / 1000)

        if self.webrtc_vad and len(audio_frame) == expected_samples:
            try:
                audio_int16 = (audio_frame * 32767).astype(np.int16)
                return self.webrtc_vad.is_speech(audio_int16.tobytes(), self.sample_rate)
            except Exception as e:
                pass

        energy = np.sqrt(np.mean(audio_frame**2))
        return energy > self.energy_threshold

    def detect_end_of_speech(
        self,
        audio: np.ndarray,
        chunk_size: int = 1600,
    ) -> bool:
        if len(audio) < self.silence_samples:
            return False

        tail = audio[-self.silence_samples :]
        num_chunks = len(tail) // chunk_size

        if num_chunks == 0:
            return False

        speech_chunks = 0
        for i in range(num_chunks):
            chunk = tail[i * chunk_size : (i + 1) * chunk_size]
            if self.is_speech(chunk):
                speech_chunks += 1

        return speech_chunks < num_chunks * 0.1


audio_recorder = AudioRecorder()
continuous_stream = ContinuousAudioStream()
vad = VoiceActivityDetector()
