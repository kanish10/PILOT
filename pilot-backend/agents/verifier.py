"""
Agent 4 — The Verifier.
Compares the before/after screen states to determine whether an action succeeded.
"""
import logging
from typing import Any, Dict, Optional

from config import settings
from core.formatting import format_ui_tree
from core.groq_client import GroqLLMClient
from core.json_utils import extract_json
from core.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are PILOT's Verifier. After an action was performed on the phone,
compare the BEFORE and AFTER screen states to determine the outcome.

You receive:
- The action that was just performed
- The screen BEFORE the action
- The screen AFTER the action
- The current step objective

DECISION GUIDE:
1. Before == After (screens identical) → action likely failed
2. Expected thing happened → success
3. Unexpected popup / dialog appeared → unexpected + suggestion to handle it
4. Login / permission screen appeared → blocked
5. Wrong screen (navigated away unexpectedly) → unexpected
6. Screen moved closer to objective (even if not exactly expected) → success

RESPOND WITH VALID JSON ONLY — choose one:
{"result": "success",    "reason": "brief reason"}
{"result": "failed",     "reason": "brief reason"}
{"result": "unexpected", "reason": "what happened", "suggestion": "what to do next"}
{"result": "blocked",    "reason": "why we cannot proceed", "suggestion": "what user needs to do"}\
"""


class VerifierAgent:
    def __init__(
        self,
        groq: GroqLLMClient,
        ollama: Optional[OllamaClient] = None,
    ) -> None:
        self.groq = groq
        self.ollama = ollama

    async def verify(
        self,
        action: Dict[str, Any],
        old_screen: Dict[str, Any],
        new_screen: Dict[str, Any],
        objective: str,
    ) -> Dict[str, Any]:
        """Return a verification result dict."""
        before_str = format_ui_tree(old_screen)
        after_str = format_ui_tree(new_screen)
        action_desc = _describe_action(action)

        prompt = (
            f"Objective: {objective}\n"
            f"Action performed: {action_desc}\n\n"
            f"BEFORE screen:\n{before_str}\n\n"
            f"AFTER screen:\n{after_str}\n\n"
            "Did the action succeed?"
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = await self.groq.chat(
                model=settings.verifier_model,
                messages=messages,
                max_tokens=256,
                temperature=0.0,
            )
            result = extract_json(raw)
            logger.info("Verifier → %s | %s", result.get("result"), result.get("reason", ""))
            return result

        except Exception as exc:
            logger.warning("Groq verifier failed (%s), trying Ollama fallback", exc)
            if self.ollama and await self.ollama.is_available():
                raw = await self.ollama.chat(messages, max_tokens=256)
                return extract_json(raw)
            raise


def _describe_action(action: Dict[str, Any]) -> str:
    t = action.get("action", "unknown")
    if t == "tap":
        return f"Tapped element #{action.get('element_id')}"
    if t == "type":
        return f"Typed '{action.get('value', '')}' into element #{action.get('element_id')}"
    if t == "scroll_down":
        return "Scrolled down"
    if t == "scroll_up":
        return "Scrolled up"
    if t == "scroll_left":
        return "Scrolled left"
    if t == "scroll_right":
        return "Scrolled right"
    if t == "back":
        return "Pressed back"
    if t == "home":
        return "Pressed home"
    if t == "open_app":
        return f"Opened app: {action.get('package', 'unknown')}"
    if t == "wait":
        return f"Waited {action.get('seconds', 2)}s"
    return f"Action: {t}"
