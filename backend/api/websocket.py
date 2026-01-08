from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio

from backend.core.llm import ollama_client

CHUNK_BUFFER_SIZE = 10
CHUNK_FLUSH_INTERVAL = 0.05


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.conversation_history: dict[str, list[dict]] = {}
        self.stop_flags: dict[str, bool] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections.append(websocket)
        if client_id not in self.conversation_history:
            self.conversation_history[client_id] = []
        self.stop_flags[client_id] = False

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


manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, client_id: str = "default"):
    await manager.connect(websocket, client_id)

    async def handle_generation(user_content: str):
        manager.add_message(client_id, "user", user_content)
        manager.reset_stop(client_id)

        await websocket.send_text(
            json.dumps(
                {
                    "type": "start",
                    "role": "assistant",
                }
            )
        )

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
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "chunk",
                                "content": chunk_buffer,
                            }
                        )
                    )
                    chunk_buffer = ""
                    last_flush_time = current_time

            if chunk_buffer:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "chunk",
                            "content": chunk_buffer,
                        }
                    )
                )

            if full_response:
                manager.add_message(client_id, "assistant", full_response)

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "end",
                        "stopped": was_stopped,
                    }
                )
            )
        except asyncio.CancelledError:
            if full_response:
                manager.add_message(client_id, "assistant", full_response)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "end",
                        "stopped": True,
                    }
                )
            )

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "stop":
                manager.request_stop(client_id)
                continue

            if message.get("type") == "clear":
                manager.request_stop(client_id)
                manager.clear_history(client_id)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "system",
                            "content": "Conversation cleared.",
                        }
                    )
                )
                continue

            if message.get("type") == "chat":
                user_content = message.get("content", "")
                asyncio.create_task(handle_generation(user_content))

    except WebSocketDisconnect:
        manager.disconnect(websocket, client_id)
    except Exception as e:
        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "content": str(e),
                    }
                )
            )
        except Exception:
            pass
        manager.disconnect(websocket, client_id)
