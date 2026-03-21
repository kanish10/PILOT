import logging
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Async Ollama API client.
    Works with any Ollama endpoint — local or remote (ngrok, tunnel, etc.).
    The base_url comes from OLLAMA_BASE_URL in .env.
    """

    def __init__(self, base_url: str, model: str, timeout: float = 90.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 1024,
    ) -> str:
        """Send a chat request to Ollama and return the assistant text."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.1,
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]
            logger.debug("Ollama [%s] response: %s", self.model, content[:300])
            return content

    async def is_available(self) -> bool:
        """Ping Ollama to check it's reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False
