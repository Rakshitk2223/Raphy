import httpx
from collections.abc import AsyncIterator

from backend.config import settings
from backend.personality.prompts import get_system_prompt


class OllamaClient:
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model
        self.client = httpx.AsyncClient(timeout=120.0)

    async def check_health(self) -> bool:
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [model["name"] for model in data.get("models", [])]
            return []
        except Exception:
            return []

    async def generate_stream(
        self,
        messages: list[dict],
        model: str | None = None,
    ) -> AsyncIterator[str]:
        model = model or self.model

        system_message = {"role": "system", "content": get_system_prompt()}
        full_messages = [system_message] + messages

        payload = {
            "model": model,
            "messages": full_messages,
            "stream": True,
        }

        async with self.client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
        ) as response:
            async for line in response.aiter_lines():
                if line:
                    import json

                    try:
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

    async def generate(
        self,
        messages: list[dict],
        model: str | None = None,
    ) -> str:
        chunks = []
        async for chunk in self.generate_stream(messages, model):
            chunks.append(chunk)
        return "".join(chunks)

    async def close(self):
        await self.client.aclose()


ollama_client = OllamaClient()
