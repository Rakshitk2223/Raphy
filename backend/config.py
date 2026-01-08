from pathlib import Path

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
    ollama_model: str = "qwen2.5:7b-instruct-q5_K_M"

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


settings = Settings()
