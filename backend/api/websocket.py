from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio
import re

from backend.core.llm import ollama_client
from backend.config import settings

CHUNK_BUFFER_SIZE = 10
CHUNK_FLUSH_INTERVAL = 0.05

SENTENCE_END_PATTERN = re.compile(r"(?<=[.!?])\s+")

voice_enabled = False
speak_func = None
speak_sentence_func = None
voice_service = None
reset_stop_func = None
strip_emojis_func = None

try:
    from backend.core.voice import voice_service as _voice_service
    from backend.core.tts import (
        speak as _speak,
        speak_sentence as _speak_sentence,
        reset_stop_flag as _reset_stop,
        strip_emojis as _strip_emojis,
    )

    voice_service = _voice_service
    speak_func = _speak
    speak_sentence_func = _speak_sentence
    reset_stop_func = _reset_stop
    strip_emojis_func = _strip_emojis
    voice_enabled = True
except ImportError as e:
    print(f"Voice modules not available: {e}")


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.conversation_history: dict[str, list[dict]] = {}
        self.stop_flags: dict[str, bool] = {}
        self.muted: dict[str, bool] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections.append(websocket)
        if client_id not in self.conversation_history:
            self.conversation_history[client_id] = []
        self.stop_flags[client_id] = False
        self.muted[client_id] = True

    def disconnect(self, websocket: WebSocket, client_id: str):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    def get_history(self, client_id: str) -> list[dict]:
        return self.conversation_history.get(client_id, [])

    def add_message(self, client_id: str, role: str, content: str):
        if client_id not in self.conversation_history:
            self.conversation_history[client_id] = []
        self.conversation_history[client_id].append({"role": role, "content": content})
        if len(self.conversation_history[client_id]) > 40:
            self.conversation_history[client_id] = self.conversation_history[client_id][-40:]

    def clear_history(self, client_id: str):
        self.conversation_history[client_id] = []

    def request_stop(self, client_id: str):
        self.stop_flags[client_id] = True

    def should_stop(self, client_id: str) -> bool:
        return self.stop_flags.get(client_id, False)

    def reset_stop(self, client_id: str):
        self.stop_flags[client_id] = False

    def set_muted(self, client_id: str, muted: bool):
        self.muted[client_id] = muted

    def is_muted(self, client_id: str) -> bool:
        return self.muted.get(client_id, True)


manager = ConnectionManager()


def extract_complete_sentences(text: str) -> tuple[list[str], str]:
    parts = SENTENCE_END_PATTERN.split(text)
    if len(parts) > 1:
        complete = parts[:-1]
        remainder = parts[-1]
        return complete, remainder
    return [], text


async def websocket_endpoint(websocket: WebSocket, client_id: str = "default"):
    await manager.connect(websocket, client_id)

    async def send_message(msg_type: str, **data):
        await websocket.send_text(json.dumps({"type": msg_type, **data}))

    async def handle_generation(user_content: str):
        manager.add_message(client_id, "user", user_content)
        manager.reset_stop(client_id)

        if reset_stop_func:
            reset_stop_func()

        await send_message("start", role="assistant")

        history = manager.get_history(client_id)
        full_response = ""
        chunk_buffer = ""
        last_flush_time = asyncio.get_event_loop().time()
        was_stopped = False

        should_speak = voice_enabled and speak_sentence_func and not manager.is_muted(client_id)
        speech_buffer = ""
        sentences_to_speak: asyncio.Queue = asyncio.Queue()
        speech_task = None

        async def speech_worker():
            speaking_started = False
            while True:
                try:
                    sentence = await asyncio.wait_for(sentences_to_speak.get(), timeout=0.1)
                    if sentence is None:
                        break
                    if manager.should_stop(client_id):
                        break

                    if not speaking_started:
                        speaking_started = True
                        await send_message("voice_state", state="speaking")

                    if speak_sentence_func:
                        await speak_sentence_func(sentence)
                    sentences_to_speak.task_done()
                except asyncio.TimeoutError:
                    if manager.should_stop(client_id):
                        break
                    continue
                except Exception as e:
                    print(f"Speech worker error: {e}")
                    break

            if speaking_started:
                await send_message("voice_state", state="idle")

        if should_speak:
            speech_task = asyncio.create_task(speech_worker())

        try:
            async for chunk in ollama_client.generate_stream(history):
                if manager.should_stop(client_id):
                    was_stopped = True
                    break

                full_response += chunk
                chunk_buffer += chunk

                if should_speak:
                    speech_buffer += chunk
                    complete_sentences, speech_buffer = extract_complete_sentences(speech_buffer)
                    for sentence in complete_sentences:
                        cleaned = strip_emojis_func(sentence) if strip_emojis_func else sentence
                        if cleaned.strip():
                            await sentences_to_speak.put(cleaned.strip())

                current_time = asyncio.get_event_loop().time()
                should_flush = (
                    len(chunk_buffer) >= CHUNK_BUFFER_SIZE
                    or (current_time - last_flush_time) >= CHUNK_FLUSH_INTERVAL
                    or chunk.endswith(("\n", ".", "!", "?", ":", ";"))
                )

                if should_flush and chunk_buffer:
                    await send_message("chunk", content=chunk_buffer)
                    chunk_buffer = ""
                    last_flush_time = current_time

            if chunk_buffer:
                await send_message("chunk", content=chunk_buffer)

            if should_speak and speech_buffer.strip() and not was_stopped:
                cleaned = strip_emojis_func(speech_buffer) if strip_emojis_func else speech_buffer
                if cleaned.strip():
                    await sentences_to_speak.put(cleaned.strip())

            if should_speak:
                await sentences_to_speak.put(None)
                if speech_task:
                    await speech_task

            if full_response:
                manager.add_message(client_id, "assistant", full_response)

            await send_message("end", stopped=was_stopped)

        except asyncio.CancelledError:
            if full_response:
                manager.add_message(client_id, "assistant", full_response)
            await send_message("end", stopped=True)
        finally:
            if should_speak and speech_task and not speech_task.done():
                await sentences_to_speak.put(None)
                speech_task.cancel()
                try:
                    await speech_task
                except asyncio.CancelledError:
                    pass

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")

            if msg_type == "stop":
                manager.request_stop(client_id)
                if voice_enabled and voice_service:
                    voice_service.stop_speaking()
                    voice_service.cancel_listening()
                continue

            if msg_type == "clear":
                manager.request_stop(client_id)
                manager.clear_history(client_id)
                await send_message("system", content="Conversation cleared.")
                continue

            if msg_type == "chat":
                user_content = message.get("content", "")
                if user_content.strip():
                    asyncio.create_task(handle_generation(user_content))
                continue

            if msg_type == "mute":
                muted = message.get("muted", True)
                manager.set_muted(client_id, muted)
                if voice_enabled and voice_service:
                    voice_service.set_muted(muted)
                    if muted:
                        voice_service.stop_speaking()
                        voice_service.cancel_listening()
                await send_message("voice_state", state="muted" if muted else "idle")
                continue

            if msg_type == "voice_start":
                if manager.is_muted(client_id):
                    await send_message("voice_state", state="muted")
                    continue
                if voice_enabled and voice_service:
                    await voice_service.start_listening()
                    await send_message("voice_state", state="listening")
                continue

            if msg_type == "voice_stop":
                if voice_enabled and voice_service:
                    text = await voice_service.stop_listening()
                    if text:
                        await send_message("transcription", content=text)
                        asyncio.create_task(handle_generation(text))
                    else:
                        await send_message("voice_state", state="idle")
                continue

            if msg_type == "voice_cancel":
                if voice_enabled and voice_service:
                    voice_service.cancel_listening()
                    voice_service.stop_speaking()
                await send_message("voice_state", state="idle")
                continue

    except WebSocketDisconnect:
        manager.disconnect(websocket, client_id)
    except Exception as e:
        try:
            await send_message("error", content=str(e))
        except Exception:
            pass
        manager.disconnect(websocket, client_id)
