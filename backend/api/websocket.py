from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio

from backend.core.llm import ollama_client

CHUNK_BUFFER_SIZE = 10
CHUNK_FLUSH_INTERVAL = 0.05

voice_enabled = False
speak_func = None
voice_service = None

try:
    from backend.core.voice import voice_service as _voice_service
    from backend.core.tts import speak as _speak

    voice_service = _voice_service
    speak_func = _speak
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


async def websocket_endpoint(websocket: WebSocket, client_id: str = "default"):
    await manager.connect(websocket, client_id)

    async def send_message(msg_type: str, **data):
        await websocket.send_text(json.dumps({"type": msg_type, **data}))

    async def handle_generation(user_content: str):
        manager.add_message(client_id, "user", user_content)
        manager.reset_stop(client_id)

        await send_message("start", role="assistant")

        history = manager.get_history(client_id)
        full_response = ""
        chunk_buffer = ""
        last_flush_time = asyncio.get_event_loop().time()
        was_stopped = False

        try:
            async for chunk in ollama_client.generate_stream(history):
                if manager.should_stop(client_id):
                    was_stopped = True
                    break

                full_response += chunk
                chunk_buffer += chunk

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

            if full_response:
                manager.add_message(client_id, "assistant", full_response)

            await send_message("end", stopped=was_stopped)

            if not was_stopped and full_response and voice_enabled and speak_func:
                if not manager.is_muted(client_id):
                    await send_message("voice_state", state="speaking")
                    try:
                        await speak_func(full_response)
                    except Exception as e:
                        print(f"TTS error: {e}")
                    finally:
                        await send_message("voice_state", state="idle")

        except asyncio.CancelledError:
            if full_response:
                manager.add_message(client_id, "assistant", full_response)
            await send_message("end", stopped=True)

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
