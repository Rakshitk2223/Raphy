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
