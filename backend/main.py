import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from backend.config import settings
from backend.api.routes import router as api_router
from backend.api.websocket import websocket_endpoint
from backend.core.llm import ollama_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"\n{'=' * 50}")
    print(f"  Raphael - Your Personal AI Assistant")
    print(f"{'=' * 50}")
    print(f"  Starting up...")

    healthy = await ollama_client.check_health()
    if healthy:
        models = await ollama_client.list_models()
        print(f"  Ollama: Connected")
        print(f"  Available models: {', '.join(models[:5])}")
        if any(settings.ollama_model in m for m in models):
            print(f"  Using model: {settings.ollama_model}")
        else:
            print(f"  WARNING: Model {settings.ollama_model} not found!")
            print(f"  Run: ollama pull {settings.ollama_model}")
    else:
        print(f"  WARNING: Ollama not running!")
        print(f"  Start with: sudo systemctl start ollama")

    print(f"  Loading embedding model in background...")
    asyncio.create_task(load_embedding_model_background())

    print(f"  Loading TTS model in background...")
    asyncio.create_task(load_tts_model_background())

    print(f"\n  Web UI: http://{settings.host}:{settings.port}")
    print(f"  - Chat Mode: http://{settings.host}:{settings.port}/chat")
    print(f"  - Assistant Mode: http://{settings.host}:{settings.port}/assistant")
    print(f"{'=' * 50}\n")

    yield

    await ollama_client.close()
    print("\nRaphael shutting down. See you next time!")


async def load_embedding_model_background():
    from backend.memory.vector import get_embedding_model
    import time

    start = time.perf_counter()
    await asyncio.to_thread(get_embedding_model)
    elapsed = time.perf_counter() - start
    print(f"  Embedding model loaded in {elapsed:.2f}s")


async def load_tts_model_background():
    from backend.core.tts import get_qwen_model
    import time

    start = time.perf_counter()
    try:
        await asyncio.to_thread(get_qwen_model)
        elapsed = time.perf_counter() - start
        print(f"  Qwen TTS model loaded in {elapsed:.2f}s")
    except Exception as e:
        print(f"  Qwen TTS failed to load: {e}")


app = FastAPI(
    title="Raphael",
    description="Personal AI Assistant",
    version="0.2.0",
    lifespan=lifespan,
)

frontend_path = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=frontend_path), name="static")

app.include_router(api_router, prefix="/api")

app.add_api_websocket_route("/ws/{client_id}", websocket_endpoint)


@app.get("/")
async def root():
    return FileResponse(frontend_path / "index.html")


@app.get("/chat")
async def chat_mode():
    return FileResponse(frontend_path / "chat.html")


@app.get("/assistant")
async def assistant_mode():
    return FileResponse(frontend_path / "assistant.html")


def main():
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
