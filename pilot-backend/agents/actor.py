"""
Agent 3 — The Actor.
Given the current screen state and the current step objective,
decides the single next UI action to perform.
"""
import logging
from typing import Any, Dict, List, Optional

from config import settings
from core.formatting import format_action_history, format_ui_tree
from core.groq_client import GroqLLMClient
from core.json_utils import extract_json
from core.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are PILOT's Actor. Look at the current phone screen and decide the SINGLE next UI action.

You receive:
- The overall task and current step objective
- A list of all visible UI elements with their IDs
- Recent actions taken (avoid repeating failed ones)

AVAILABLE ACTIONS:
1.  {"action": "tap",         "element_id": N,                    "status": "short description"}
2.  {"action": "type",        "element_id": N, "value": "text",   "status": "short description"}
3.  {"action": "scroll_down",                                      "status": "short description"}
4.  {"action": "scroll_up",                                        "status": "short description"}
5.  {"action": "back",                                             "status": "short description"}
6.  {"action": "open_app",    "package": "com.example.app",       "status": "short description"}
7.  {"action": "wait",        "seconds": 2,                       "status": "short description"}
8.  {"action": "step_done",                                        "status": "short description"}
9.  {"action": "need_help",   "question": "What should I do?",    "status": "short description"}
10. {"action": "need_vision",                                      "status": "short description"}

RULES:
- Return EXACTLY ONE action as a JSON object. No explanation, no markdown.
- Prefer elements with clear text labels over generic ones.
- If the current step objective is already achieved, return "step_done".
- If the same action has been attempted 3+ times with no result, try something different.
- Typing rule: ALWAYS tap the text field first (separate action), then type in the next call.
- If a loading spinner is visible, return wait (seconds: 2).
- "status" must be 5–8 words — it shows live on the user's screen.
- If you cannot determine the action from text alone, return "need_vision".\
"""


class ActorAgent:
    def __init__(
        self,
        groq: GroqLLMClient,
        ollama: Optional[OllamaClient] = None,
    ) -> None:
        self.groq = groq
        self.ollama = ollama

    async def decide(
        self,
        objective: str,
        ui_tree: Dict[str, Any],
        action_history: List[Dict[str, Any]],
        user_intent: str = "",
        use_vision: bool = False,
        screenshot_b64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return the next action dict."""
        tree_str = format_ui_tree(ui_tree)
        history_str = format_action_history(action_history[-8:])

        prompt = (
            f"Task: {user_intent}\n"
            f"Current objective: {objective}\n\n"
            f"Screen elements:\n{tree_str}\n\n"
            f"Recent actions:\n{history_str}\n\n"
            "What is the single next action?"
        )

        # Vision path
        if use_vision and screenshot_b64:
            try:
                raw = await self.groq.vision_chat(
                    model=settings.vision_model,
                    text_prompt=prompt,
                    screenshot_b64=screenshot_b64,
                    max_tokens=256,
                )
                action = extract_json(raw)
                logger.info("Actor (vision) → %s | %s", action.get("action"), action.get("status", ""))
                return action
            except Exception as exc:
                logger.warning("Vision actor failed (%s), falling back to text", exc)

        # Text path
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = await self.groq.chat(
                model=settings.actor_model,
                messages=messages,
                max_tokens=256,
                temperature=0.1,
            )
            action = extract_json(raw)
            logger.info("Actor → %s | %s", action.get("action"), action.get("status", ""))
            return action

        except Exception as exc:
            logger.warning("Groq actor failed (%s), trying Ollama fallback", exc)
            if self.ollama and await self.ollama.is_available():
                raw = await self.ollama.chat(messages, max_tokens=256)
                return extract_json(raw)
            raise
