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
        from backend.memory.profile import user_profile

        notes = user_profile.list_notes()
        return {"notes": notes}
    except ImportError:
        return {"error": "Memory module not available"}


@router.get("/memory/reminders")
async def list_reminders():
    try:
        from backend.memory.profile import user_profile

        all_notes = user_profile.get_notes()
        reminders = [n for n in all_notes if n.get("category") == "reminder"]
        return {"reminders": reminders}
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


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    about: str | None = None


@router.get("/profile")
async def get_profile():
    try:
        from backend.memory.profile import user_profile

        user_profile.reload()
        return {
            "profile": {
                "name": user_profile.get_name(),
                "about": user_profile.get_about(),
                "preferences": user_profile.get_all_preferences(),
            },
            "notes": user_profile.get_notes(),
        }
    except ImportError:
        return {"error": "Profile module not available"}


@router.post("/profile")
async def update_profile(request: ProfileUpdateRequest):
    try:
        from backend.memory.profile import user_profile

        if request.name is not None:
            user_profile.set_name(request.name)
        if request.about is not None:
            user_profile.set_about(request.about)

        return {"success": True}
    except ImportError:
        return {"error": "Profile module not available"}


@router.get("/knowledge")
async def get_knowledge():
    try:
        from backend.memory.vector import memory_store

        count = memory_store.collection.count()

        results = memory_store.search_knowledge("", top_k=100)

        sources = set()
        categories = {}
        for r in results:
            source = r.get("source", "unknown")
            cat = r.get("category", "unknown")
            sources.add(source)
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_chunks": count,
            "files": list(sources),
            "categories": categories,
        }
    except ImportError:
        return {"error": "Memory module not available"}


@router.post("/knowledge/reindex")
async def reindex_knowledge():
    try:
        import subprocess
        from pathlib import Path

        script_path = Path("scripts/index_knowledge.py")
        if not script_path.exists():
            return {"error": "Index script not found", "success": False}

        result = subprocess.run(
            ["python", str(script_path), "--clear"],
            capture_output=True,
            text=True,
            cwd=Path(".").resolve(),
        )

        output = result.stdout + result.stderr

        import re

        chunks_match = re.search(r"Indexed (\d+) chunks", output)
        files_match = re.search(r"from (\d+) files", output)

        chunks = int(chunks_match.group(1)) if chunks_match else 0
        files = int(files_match.group(1)) if files_match else 0

        return {
            "success": True,
            "chunks": chunks,
            "files": files,
        }
    except Exception as e:
        return {"error": str(e), "success": False}


@router.get("/settings/voices")
async def get_voices():
    return {
        "voices": [
            {"id": "af_sarah", "name": "Sarah", "gender": "Female"},
            {"id": "af_amy", "name": "Amy", "gender": "Female"},
            {"id": "af_nova", "name": "Nova", "gender": "Female"},
            {"id": "af_alloy", "name": "Alloy", "gender": "Neutral"},
            {"id": "am_eric", "name": "Eric", "gender": "Male"},
            {"id": "am_michael", "name": "Michael", "gender": "Male"},
        ],
        "current": "af_sarah",
    }


class VoiceUpdateRequest(BaseModel):
    voice: str


@router.post("/settings/voice")
async def update_voice(request: VoiceUpdateRequest):
    from backend.config import settings

    settings.tts_voice = request.voice
    return {"success": True, "voice": request.voice}


@router.get("/brain")
async def get_brain():
    try:
        from backend.memory.brain import brain

        brain.reload()
        return {
            "summary": brain.get_summary(),
            "data": brain.data,
        }
    except ImportError:
        return {"error": "Brain module not available"}


@router.get("/brain/export")
async def export_brain():
    try:
        from backend.memory.brain import brain

        brain.reload()
        print(f"[API] Exporting brain data: {brain.data}")
        return brain.data
    except ImportError:
        return {"error": "Brain module not available"}
    except Exception as e:
        print(f"[API] Brain export error: {e}")
        return {"error": str(e)}


class BrainUpdateRequest(BaseModel):
    key: str
    value: str
    action: str = "update"


@router.post("/brain")
async def update_brain(request: BrainUpdateRequest):
    try:
        from backend.memory.brain import brain

        brain.reload()

        if request.action == "update":
            brain.update_info(request.key, request.value)
            return {"success": True}
        elif request.action == "delete":
            success = brain.delete_info(request.key)
            return {"success": success}
        else:
            return {"error": "Unknown action"}
    except Exception as e:
        return {"error": str(e)}
