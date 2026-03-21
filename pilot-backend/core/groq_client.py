import asyncio
import logging
from typing import Any, Dict, List, Optional

from groq import AsyncGroq, APIError, RateLimitError, APIConnectionError

logger = logging.getLogger(__name__)

_RETRY_BASE_DELAY = 1.0  # seconds


class GroqLLMClient:
    """
    Async Groq API client with:
    - Exponential-backoff retry on rate-limit / transient errors
    - Optional JSON mode
    - Vision (image) message support
    """

    def __init__(self, api_key: str, max_retries: int = 3) -> None:
        self._client = AsyncGroq(api_key=api_key)
        self._max_retries = max_retries

    async def chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: int = 1024,
        temperature: float = 0.1,
        json_mode: bool = False,
    ) -> str:
        """
        Send a chat completion request and return the assistant message text.
        Retries on rate-limit and connection errors.
        """
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                response = await self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                logger.debug("Groq [%s] response: %s", model, content[:300])
                return content

            except RateLimitError as exc:
                wait = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "Groq rate limit (attempt %d/%d), waiting %.1fs: %s",
                    attempt + 1,
                    self._max_retries,
                    wait,
                    exc,
                )
                last_exc = exc
                await asyncio.sleep(wait)

            except APIConnectionError as exc:
                wait = _RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "Groq connection error (attempt %d/%d), waiting %.1fs: %s",
                    attempt + 1,
                    self._max_retries,
                    wait,
                    exc,
                )
                last_exc = exc
                await asyncio.sleep(wait)

            except APIError as exc:
                logger.error("Groq API error (non-retryable): %s", exc)
                raise

        raise RuntimeError(
            f"Groq API failed after {self._max_retries} attempts"
        ) from last_exc

    async def vision_chat(
        self,
        model: str,
        text_prompt: str,
        screenshot_b64: str,
        max_tokens: int = 512,
    ) -> str:
        """
        Chat with a vision model by including a base64-encoded JPEG screenshot.
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{screenshot_b64}"
                        },
                    },
                ],
            }
        ]
        return await self.chat(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
        )
