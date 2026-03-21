"""
Agent 3 — The Actor.
Deterministic policy engine for selecting the next UI action.
"""
import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from config import settings
from core.formatting import format_action_history, format_ui_tree
from core.groq_client import GroqLLMClient
from core.json_utils import extract_json
from core.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "a",
    "an",
    "and",
    "app",
    "button",
    "field",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "screen",
    "select",
    "step",
    "tap",
    "text",
    "the",
    "then",
    "to",
    "verify",
}
_TYPE_VERBS = {"enter", "type", "input", "search", "write", "fill"}
_DONE_HINTS = {"verify", "confirm", "review", "check"}
_BLOCKING_LABELS = {"loading", "spinner", "progress", "please wait"}
_APP_ALIASES = {
    "uber": "com.ubercab",
    "lyft": "me.lyft.android",
    "whatsapp": "com.whatsapp",
    "messages": "com.google.android.apps.messaging",
    "sms": "com.google.android.apps.messaging",
    "maps": "com.google.android.apps.maps",
    "google maps": "com.google.android.apps.maps",
    "doordash": "com.dd.doordash",
    "dominos": "com.dominospizza.mobile.android",
    "domino's": "com.dominospizza.mobile.android",
}
_VISION_PROMPT = """\
You are PILOT's fallback Actor. Return a single JSON action object only.
Allowed actions: tap, type, scroll_down, scroll_up, back, open_app, wait,
step_done, need_user, need_vision.
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
        step_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Return the next action dict.
        Deterministic heuristics run first; vision is a bounded fallback.
        """
        action = self._decide_deterministic(
            objective=objective,
            ui_tree=ui_tree,
            action_history=action_history,
            user_intent=user_intent,
            step_context=step_context or {},
        )
        if action["action"] != "need_vision" or not (use_vision and screenshot_b64):
            logger.info("Actor(det) -> %s | %s", action["action"], action.get("status", ""))
            return action

        fallback = await self._decide_with_vision(
            objective=objective,
            ui_tree=ui_tree,
            action_history=action_history,
            user_intent=user_intent,
            screenshot_b64=screenshot_b64,
        )
        logger.info("Actor(vision) -> %s | %s", fallback["action"], fallback.get("status", ""))
        return fallback

    def _decide_deterministic(
        self,
        objective: str,
        ui_tree: Dict[str, Any],
        action_history: List[Dict[str, Any]],
        user_intent: str,
        step_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        elements = ui_tree.get("elements", []) or []
        current_package = (ui_tree.get("package") or "").lower()
        objective_norm = _normalize_text(objective)
        needs = _normalize_text(str(step_context.get("needs") or ""))
        objective_tokens = _meaningful_tokens(objective_norm)
        needs_tokens = _meaningful_tokens(needs)
        payload_text = _extract_payload(objective, str(step_context.get("needs") or ""))

        if self._is_loading_screen(elements):
            return {"action": "wait", "seconds": 2, "status": "Waiting for screen update"}

        if self._objective_already_met(objective_norm, objective_tokens, needs_tokens, elements):
            return {"action": "step_done", "status": "Current step already complete"}

        open_app_action = self._maybe_open_app(objective_norm, current_package)
        if open_app_action is not None:
            return open_app_action

        repeated_failures = _count_recent_failed_repeats(action_history)
        if repeated_failures >= settings.max_retries:
            return self._recovery_action(ui_tree, action_history)

        if payload_text:
            text_action = self._maybe_type(payload_text, elements, action_history)
            if text_action is not None:
                return text_action

        best = self._best_element_match(
            objective_tokens=objective_tokens,
            needs_tokens=needs_tokens,
            elements=elements,
            action_history=action_history,
        )
        if best is not None and best["score"] >= 7.5:
            return {
                "action": "tap",
                "element_id": best["element"]["id"],
                "status": _status_for(best["element"], "Opening selected item"),
            }

        if payload_text and any(el.get("editable") for el in elements):
            return self._tap_first_editable(elements)

        if any(el.get("scrollable") for el in elements):
            return self._scroll_action(action_history)

        if best is not None and best["score"] >= 4.0:
            return {
                "action": "tap",
                "element_id": best["element"]["id"],
                "status": _status_for(best["element"], "Trying best screen match"),
            }

        if any(token in objective_tokens for token in _DONE_HINTS):
            return {"action": "step_done", "status": "Verification step looks complete"}

        return {"action": "need_vision", "status": "Need screenshot for disambiguation"}

    def _is_loading_screen(self, elements: List[Dict[str, Any]]) -> bool:
        for element in elements:
            combined = " ".join(
                [
                    str(element.get("class") or ""),
                    str(element.get("text") or ""),
                    str(element.get("content_desc") or ""),
                    str(element.get("resource_id") or ""),
                ]
            ).lower()
            if "progressbar" in combined or any(label in combined for label in _BLOCKING_LABELS):
                return True
        return False

    def _objective_already_met(
        self,
        objective_norm: str,
        objective_tokens: List[str],
        needs_tokens: List[str],
        elements: List[Dict[str, Any]],
    ) -> bool:
        screen_text = " ".join(_element_text_parts(element) for element in elements)
        if needs_tokens and all(token in screen_text for token in needs_tokens[:4]):
            return True
        if any(token in objective_tokens for token in _DONE_HINTS):
            return any(token in screen_text for token in objective_tokens if len(token) > 3)
        if "open " in objective_norm and " app" in objective_norm:
            return False
        if objective_tokens and all(token in screen_text for token in objective_tokens[:3]):
            return True
        return False

    def _maybe_open_app(self, objective_norm: str, current_package: str) -> Optional[Dict[str, Any]]:
        if "open " not in objective_norm or "app" not in objective_norm:
            return None
        for label, package in _APP_ALIASES.items():
            if label in objective_norm:
                if current_package == package:
                    return {"action": "step_done", "status": f"{label.title()} already open"}
                return {
                    "action": "open_app",
                    "package": package,
                    "status": f"Opening {label.title()} app",
                }
        return None

    def _maybe_type(
        self,
        payload_text: str,
        elements: List[Dict[str, Any]],
        action_history: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        editable_elements = [element for element in elements if element.get("editable")]
        if not editable_elements:
            return None

        ranked = sorted(
            editable_elements,
            key=lambda element: (
                -_element_type_score(element),
                int(element.get("id", 10**6)),
            ),
        )
        target = ranked[0]
        last = action_history[-1] if action_history else None
        if (
            last
            and last.get("action") == "tap"
            and last.get("element_id") == target.get("id")
        ):
            return {
                "action": "type",
                "element_id": target["id"],
                "value": payload_text,
                "status": "Typing requested text now",
            }
        return {
            "action": "tap",
            "element_id": target["id"],
            "status": "Focusing text field first",
        }

    def _best_element_match(
        self,
        objective_tokens: List[str],
        needs_tokens: List[str],
        elements: List[Dict[str, Any]],
        action_history: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        combined_tokens = needs_tokens or objective_tokens
        previous_failures = {
            entry.get("element_id")
            for entry in action_history
            if entry.get("action") == "tap" and entry.get("result") == "failed"
        }

        for element in elements:
            score = _score_element(element, objective_tokens, combined_tokens)
            if score <= 0:
                continue
            if element.get("id") in previous_failures:
                score -= 2.0
            candidates.append({"element": element, "score": score})

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                -item["score"],
                0 if item["element"].get("clickable") else 1,
                0 if item["element"].get("editable") else 1,
                int(item["element"].get("id", 10**6)),
            )
        )
        return candidates[0]

    def _tap_first_editable(self, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        ranked = sorted(
            [element for element in elements if element.get("editable")],
            key=lambda element: (
                -_element_type_score(element),
                int(element.get("id", 10**6)),
            ),
        )
        target = ranked[0]
        return {
            "action": "tap",
            "element_id": target["id"],
            "status": "Selecting text field first",
        }

    def _scroll_action(self, action_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        last_scroll = next(
            (
                entry.get("action")
                for entry in reversed(action_history)
                if entry.get("action") in {"scroll_down", "scroll_up"}
            ),
            None,
        )
        action = "scroll_up" if last_scroll == "scroll_down" else "scroll_down"
        return {"action": action, "status": "Scrolling to find target"}

    def _recovery_action(
        self,
        ui_tree: Dict[str, Any],
        action_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        escalations = ["scroll_down", "back", "wait", "need_vision", "need_user"]
        tried = [
            entry.get("action")
            for entry in action_history[-8:]
            if entry.get("action") in escalations
        ]
        for action in escalations:
            if action == "scroll_down" and not any(
                element.get("scrollable") for element in ui_tree.get("elements", [])
            ):
                continue
            if action not in tried:
                if action == "wait":
                    return {"action": "wait", "seconds": 2, "status": "Waiting before next retry"}
                if action == "need_user":
                    return {
                        "action": "need_user",
                        "question": "I am stuck on this step. Can you help me continue?",
                        "status": "Need confirmation to continue",
                    }
                return {
                    "action": action,
                    "status": {
                        "scroll_down": "Trying a recovery scroll",
                        "back": "Backing out to recover",
                        "need_vision": "Need screenshot for recovery",
                    }[action],
                }
        return {"action": "need_user", "question": "I am still blocked. Continue?", "status": "Need user help now"}

    async def _decide_with_vision(
        self,
        objective: str,
        ui_tree: Dict[str, Any],
        action_history: List[Dict[str, Any]],
        user_intent: str,
        screenshot_b64: str,
    ) -> Dict[str, Any]:
        prompt = (
            f"Task: {user_intent}\n"
            f"Objective: {objective}\n\n"
            f"Screen:\n{format_ui_tree(ui_tree)}\n\n"
            f"History:\n{format_action_history(action_history[-8:])}\n"
        )
        try:
            raw = await self.groq.vision_chat(
                model=settings.vision_model,
                text_prompt=f"{_VISION_PROMPT}\n{prompt}",
                screenshot_b64=screenshot_b64,
                max_tokens=256,
            )
            return extract_json(raw)
        except Exception as exc:
            logger.warning("Vision fallback failed (%s)", exc)
            if self.ollama and await self.ollama.is_available():
                raw = await self.ollama.chat(
                    [
                        {"role": "system", "content": _VISION_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=256,
                )
                return extract_json(raw)
        return {"action": "need_user", "question": "I cannot safely identify the next action.", "status": "Need help to continue"}


def _normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s']", " ", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _meaningful_tokens(value: str) -> List[str]:
    return [token for token in value.split() if token and token not in _STOPWORDS]


def _extract_payload(objective: str, needs: str) -> str:
    for source in (needs, objective):
        quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', source)
        if quoted:
            token = next(part for part in quoted[0] if part)
            return token.strip()

    objective_norm = _normalize_text(objective)
    if not any(verb in objective_norm.split() for verb in _TYPE_VERBS):
        return needs.strip()

    for marker in ("saying", "message", "search for", "enter", "type", "input", "for"):
        lower_source = objective.lower()
        idx = lower_source.find(marker)
        if idx >= 0:
            source_slice = objective[idx + len(marker):].strip(" :.-")
            if source_slice:
                return source_slice
    return needs.strip()


def _element_text_parts(element: Dict[str, Any]) -> str:
    parts = [
        str(element.get("text") or ""),
        str(element.get("hint") or ""),
        str(element.get("content_desc") or ""),
        str(element.get("resource_id") or "").split("/")[-1],
        str(element.get("label") or ""),
    ]
    return _normalize_text(" ".join(parts))


def _score_element(
    element: Dict[str, Any],
    objective_tokens: List[str],
    match_tokens: List[str],
) -> float:
    haystack = _element_text_parts(element)
    if not haystack:
        return 0.0

    score = 0.0
    joined = " ".join(match_tokens).strip()
    if joined and joined == haystack:
        score += 10.0
    if joined and joined in haystack:
        score += 7.0

    for token in match_tokens:
        if token == haystack:
            score += 6.0
        elif token in haystack:
            score += 2.5
        else:
            score += SequenceMatcher(None, token, haystack).ratio()

    resource_id = str(element.get("resource_id") or "").split("/")[-1].lower()
    for token in objective_tokens:
        if token and token in resource_id:
            score += 1.5

    if element.get("clickable"):
        score += 1.0
    if element.get("editable"):
        score += 0.5
    return score


def _element_type_score(element: Dict[str, Any]) -> float:
    score = 0.0
    class_name = str(element.get("class") or "").lower()
    if "edit" in class_name:
        score += 3.0
    if element.get("editable"):
        score += 3.0
    if element.get("clickable"):
        score += 1.0
    text = _element_text_parts(element)
    if "search" in text:
        score += 1.0
    return score


def _count_recent_failed_repeats(action_history: List[Dict[str, Any]]) -> int:
    if not action_history:
        return 0
    streak = 0
    last_action = None
    for entry in reversed(action_history):
        action = entry.get("action")
        result = entry.get("result")
        fingerprint = (action, entry.get("element_id"), entry.get("value"), entry.get("package"))
        if result == "success":
            break
        if last_action is None:
            last_action = fingerprint
        if fingerprint != last_action:
            break
        streak += 1
    return streak


def _status_for(element: Dict[str, Any], fallback: str) -> str:
    label = next(
        (
            str(value).strip()
            for value in (
                element.get("text"),
                element.get("content_desc"),
                element.get("hint"),
            )
            if value
        ),
        "",
    )
    if not label:
        return fallback
    trimmed = " ".join(label.split()[:3])
    return f"Selecting {trimmed}".strip()
