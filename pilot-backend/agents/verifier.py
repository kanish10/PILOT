"""
Agent 4 — The Verifier.
Deterministic comparator first, LLM fallback second.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from core.formatting import format_ui_tree
from core.groq_client import GroqLLMClient
from core.json_utils import extract_json
from core.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are PILOT's Verifier. Return JSON only.
Choose exactly one:
{"result":"success","reason":"..."}
{"result":"failed","reason":"..."}
{"result":"unexpected","reason":"...","suggestion":"..."}
{"result":"blocked","reason":"...","suggestion":"..."}\
"""
_BLOCKED_PATTERNS = ("sign in", "log in", "permission", "allow", "grant", "verify it's you")
_DIALOG_PATTERNS = ("cancel", "dismiss", "not now", "close", "ok", "allow", "deny")


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
        deterministic = self._deterministic_verify(action, old_screen, new_screen, objective)
        if deterministic is not None:
            logger.info(
                "Verifier(det) -> %s | %s",
                deterministic.get("result"),
                deterministic.get("reason", ""),
            )
            return deterministic

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
            logger.info("Verifier(llm) -> %s | %s", result.get("result"), result.get("reason", ""))
            return result
        except Exception as exc:
            logger.warning("Groq verifier failed (%s), trying Ollama fallback", exc)
            if self.ollama and await self.ollama.is_available():
                raw = await self.ollama.chat(messages, max_tokens=256)
                return extract_json(raw)
        return {"result": "failed", "reason": "No reliable state change detected"}

    def _deterministic_verify(
        self,
        action: Dict[str, Any],
        old_screen: Dict[str, Any],
        new_screen: Dict[str, Any],
        objective: str,
    ) -> Optional[Dict[str, Any]]:
        old_sig = _screen_signature(old_screen)
        new_sig = _screen_signature(new_screen)
        old_tokens = _screen_tokens(old_screen)
        new_tokens = _screen_tokens(new_screen)
        objective_tokens = _meaningful_tokens(objective)

        if _contains_pattern(new_tokens, _BLOCKED_PATTERNS):
            return {
                "result": "blocked",
                "reason": "A login or permission wall appeared",
                "suggestion": "Ask the user to resolve the blocker on device",
            }

        if _looks_like_dialog(old_screen, new_screen):
            return {
                "result": "unexpected",
                "reason": "A dialog interrupted the expected flow",
                "suggestion": "Dismiss the dialog or choose the safe default",
            }

        action_type = action.get("action")
        if action_type == "wait":
            if old_sig != new_sig:
                return {"result": "success", "reason": "The screen changed while waiting"}
            return {"result": "failed", "reason": "Waiting did not change the screen"}

        if action_type == "open_app":
            if (new_screen.get("package") or "") != (old_screen.get("package") or ""):
                return {"result": "success", "reason": "The active app changed"}

        if action_type == "back":
            if old_sig != new_sig:
                return {"result": "success", "reason": "Back navigation changed the screen"}

        if action_type in {"scroll_down", "scroll_up"}:
            old_visible = _visible_element_ids(old_screen)
            new_visible = _visible_element_ids(new_screen)
            if old_visible != new_visible or old_sig != new_sig:
                return {"result": "success", "reason": "The viewport changed after scrolling"}

        if action_type == "tap":
            if old_sig != new_sig:
                return {"result": "success", "reason": "Tapping changed the UI state"}

        if action_type == "type":
            typed_value = _normalize_text(str(action.get("value") or ""))
            if typed_value and typed_value in new_tokens and typed_value not in old_tokens:
                return {"result": "success", "reason": "The requested text is now visible"}
            target_id = action.get("element_id")
            if target_id is not None:
                old_text = _element_text_for_id(old_screen, target_id)
                new_text = _element_text_for_id(new_screen, target_id)
                if new_text and new_text != old_text:
                    return {"result": "success", "reason": "The target field value changed"}

        if action_type == "step_done":
            if objective_tokens and any(token in new_tokens for token in objective_tokens):
                return {"result": "success", "reason": "The completion target is visible"}

        old_hits = sum(token in old_tokens for token in objective_tokens)
        new_hits = sum(token in new_tokens for token in objective_tokens)
        if objective_tokens and new_hits > old_hits:
            return {"result": "success", "reason": "The screen moved closer to the objective"}

        if old_sig == new_sig:
            return {"result": "failed", "reason": "No visible screen change detected"}

        return None


def _describe_action(action: Dict[str, Any]) -> str:
    t = action.get("action", "unknown")
    if t == "tap":
        return f"Tapped element #{action.get('element_id')}"
    if t == "type":
        return f"Typed into element #{action.get('element_id')}"
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


def _screen_signature(screen: Dict[str, Any]) -> Tuple[str, str, Tuple[Tuple[Any, str], ...]]:
    elements = tuple(
        (
            element.get("id"),
            _normalize_text(
                " ".join(
                    [
                        str(element.get("text") or ""),
                        str(element.get("hint") or ""),
                        str(element.get("content_desc") or ""),
                        str(element.get("resource_id") or ""),
                    ]
                )
            ),
        )
        for element in screen.get("elements", [])[:40]
    )
    return (
        str(screen.get("package") or ""),
        str(screen.get("activity") or ""),
        elements,
    )


def _visible_element_ids(screen: Dict[str, Any]) -> Tuple[Any, ...]:
    return tuple(element.get("id") for element in screen.get("elements", [])[:40])


def _screen_tokens(screen: Dict[str, Any]) -> str:
    bits: List[str] = [
        str(screen.get("package") or ""),
        str(screen.get("activity") or ""),
        str(screen.get("screen_title") or ""),
    ]
    for element in screen.get("elements", [])[:100]:
        bits.extend(
            [
                str(element.get("text") or ""),
                str(element.get("hint") or ""),
                str(element.get("content_desc") or ""),
                str(element.get("resource_id") or "").split("/")[-1],
            ]
        )
    return _normalize_text(" ".join(bits))


def _contains_pattern(text: str, patterns: Tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _looks_like_dialog(old_screen: Dict[str, Any], new_screen: Dict[str, Any]) -> bool:
    old_count = len(old_screen.get("elements", []))
    new_count = len(new_screen.get("elements", []))
    if new_count > old_count + 1 and _contains_pattern(_screen_tokens(new_screen), _DIALOG_PATTERNS):
        return True
    return False


def _element_text_for_id(screen: Dict[str, Any], element_id: Any) -> str:
    for element in screen.get("elements", []):
        if element.get("id") == element_id:
            return _normalize_text(
                " ".join(
                    [
                        str(element.get("text") or ""),
                        str(element.get("hint") or ""),
                        str(element.get("content_desc") or ""),
                    ]
                )
            )
    return ""


def _meaningful_tokens(value: str) -> List[str]:
    tokens = _normalize_text(value).split()
    return [token for token in tokens if len(token) > 2]


def _normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s']", " ", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()
