from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Raphael"
    debug: bool = False

    host: str = "127.0.0.1"
    port: int = 8080

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct-q4_K_M"

    stt_model: Literal["large-v3", "medium", "small", "base", "tiny"] = "large-v3"
    stt_device: Literal["cuda", "cpu", "auto"] = "auto"
    stt_compute_type: Literal["float16", "int8", "int8_float16", "auto"] = "float16"
    stt_language: str | None = None

    tts_streaming: bool = True
    tts_backend: Literal["piper", "edge", "qwen"] = (
        "qwen"  # qwen (best), piper (offline), edge (cloud)
    )

    data_dir: Path = Path("data")
    models_dir: Path = Path("models")

    max_conversation_history: int = 20

    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memory"

    @property
    def conversations_dir(self) -> Path:
        return self.data_dir / "conversations"

    @property
    def whisper_model_dir(self) -> Path:
        return self.models_dir / "whisper"

    @property
    def piper_model_dir(self) -> Path:
        return self.models_dir / "piper"

    knowledge_dir: Path = Path("data/memory/knowledge")
    notes_dir: Path = Path("data/memory/notes")
    chroma_dir: Path = Path("data/memory/chroma")
    embedding_model: str = "all-MiniLM-L6-v2"

    chunk_size: int = 512
    chunk_overlap: int = 50


settings = Settings()
