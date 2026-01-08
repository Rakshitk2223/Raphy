import asyncio
import queue
import threading
from pathlib import Path
from typing import Callable
import numpy as np
import sounddevice as sd

from backend.config import settings


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


class VoiceActivityDetector:
    def __init__(
        self,
        energy_threshold: float = 0.01,
        silence_duration: float = 1.0,
        sample_rate: int = 16000,
    ):
        self.energy_threshold = energy_threshold
        self.silence_duration = silence_duration
        self.sample_rate = sample_rate
        self.silence_samples = int(silence_duration * sample_rate)

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        if len(audio_chunk) == 0:
            return False
        energy = np.sqrt(np.mean(audio_chunk**2))
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
vad = VoiceActivityDetector()
