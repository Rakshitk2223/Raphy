from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import json

from backend.core.llm import ollama_client


router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class HealthResponse(BaseModel):
    status: str
    ollama: bool
    model: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    ollama_healthy = await ollama_client.check_health()
    models = await ollama_client.list_models() if ollama_healthy else []
    model_available = any(ollama_client.model in m for m in models)

    return HealthResponse(
        status="ok" if ollama_healthy and model_available else "degraded",
        ollama=ollama_healthy,
        model=ollama_client.model if model_available else "not found",
    )


@router.get("/models")
async def list_models():
    models = await ollama_client.list_models()
    return {"models": models}


@router.post("/chat")
async def chat(request: ChatRequest):
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    response = await ollama_client.generate(messages)
    return {"response": response}


class MemorySearchRequest(BaseModel):
    query: str
    top_k: int = 5


class MemoryNoteRequest(BaseModel):
    key: str
    value: str


class MemoryUpdateRequest(BaseModel):
    id: str
    key: str | None = None
    value: str | None = None


class MemoryDeleteRequest(BaseModel):
    id: str


@router.get("/memory/notes")
async def list_notes():
    try:
        from backend.memory.vector import memory_store

        notes = memory_store.list_notes()
        return {"notes": notes}
    except ImportError:
        return {"error": "Memory module not available"}


@router.post("/memory/notes")
async def add_note(request: MemoryNoteRequest):
    try:
        from backend.memory.vector import memory_store

        note = memory_store.add_note(request.key, request.value)
        return {"note": note}
    except ImportError:
        return {"error": "Memory module not available"}


@router.get("/memory/notes/{note_id}")
async def get_note(note_id: str):
    try:
        from backend.memory.vector import memory_store

        note = memory_store.get_note(note_id)
        if note:
            return {"note": note}
        return {"error": "Note not found"}, 404
    except ImportError:
        return {"error": "Memory module not available"}


@router.patch("/memory/notes/{note_id}")
async def update_note(note_id: str, request: MemoryUpdateRequest):
    try:
        from backend.memory.vector import memory_store

        note = memory_store.update_note(note_id, request.key, request.value)
        if note:
            return {"note": note}
        return {"error": "Note not found"}, 404
    except ImportError:
        return {"error": "Memory module not available"}


@router.delete("/memory/notes/{note_id}")
async def delete_note(note_id: str):
    try:
        from backend.memory.vector import memory_store

        if memory_store.delete_note(note_id):
            return {"deleted": True}
        return {"error": "Note not found"}, 404
    except ImportError:
        return {"error": "Memory module not available"}


@router.post("/memory/search")
async def search_knowledge(request: MemorySearchRequest):
    try:
        from backend.memory.vector import memory_store

        results = memory_store.search_knowledge(request.query, request.top_k)
        return {"results": results}
    except ImportError:
        return {"error": "Memory module not available"}
