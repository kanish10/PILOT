"""
Agent 2 — The Planner.
Takes a natural-language user request and returns a structured step-by-step plan.
Runs on the Mac server via Groq (with Ollama fallback).
"""
import logging
from typing import Any, Dict, Optional

from config import settings
from core.groq_client import GroqLLMClient
from core.json_utils import extract_json
from core.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are PILOT's Planner. Break down the user's phone task into high-level steps.
Do NOT decide specific UI actions (taps, types) — the Actor handles that.

RULES:
- 3 to 8 steps maximum
- Each step = one clear objective
- Include which app is needed for each step
- Include what info is needed (addresses, names, items, quantities)
- The last step MUST be a verification/confirmation step
- If the task requires user confirmation before payment, include that step

RESPOND WITH VALID JSON ONLY — no prose, no markdown fences:
{
  "plan": [
    {"step": 1, "app": "appname", "objective": "...", "needs": null},
    {"step": 2, "app": "appname", "objective": "...", "needs": "address or info needed"}
  ],
  "info_extracted": {
    "key": "value"
  },
  "confirmation_message": "Got it, I'll [one sentence summary of what I'll do]."
}\
"""


class PlannerAgent:
    def __init__(
        self,
        groq: GroqLLMClient,
        ollama: Optional[OllamaClient] = None,
    ) -> None:
        self.groq = groq
        self.ollama = ollama

    async def plan(self, user_intent: str) -> Dict[str, Any]:
        """Decompose *user_intent* into a structured plan dict."""
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_intent},
        ]

        try:
            raw = await self.groq.chat(
                model=settings.planner_model,
                messages=messages,
                max_tokens=1024,
                temperature=0.1,
            )
            result = extract_json(raw)
            logger.info(
                "Planner created %d-step plan for: %s",
                len(result.get("plan", [])),
                user_intent[:80],
            )
            return result

        except Exception as exc:
            logger.warning("Groq planner failed (%s), trying Ollama fallback", exc)
            if self.ollama and await self.ollama.is_available():
                raw = await self.ollama.chat(messages, max_tokens=1024)
                return extract_json(raw)
            raise
