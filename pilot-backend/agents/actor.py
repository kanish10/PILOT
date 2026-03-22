"""
Agent 3 — The Actor.
Hybrid: fast deterministic checks for obvious actions (open_app, loading,
typing), LLM reasoning for everything else.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from config import settings
from core.formatting import format_action_history, format_ui_tree
from core.groq_client import GroqLLMClient
from core.json_utils import extract_json
from core.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "a", "an", "and", "app", "button", "field", "for", "from", "in", "into",
    "of", "on", "or", "screen", "select", "step", "tap", "text", "the",
    "then", "to", "verify",
}
_TYPE_VERBS = {"enter", "type", "input", "search", "write", "fill"}
_ACTION_VERBS = {
    "set", "take", "click", "tap", "enter", "type", "choose", "select",
    "book", "confirm", "add", "browse", "search", "send", "order",
    "review", "proceed", "scroll", "swipe",
}
_DONE_HINTS = {"verify", "confirm", "review", "check"}
_BLOCKING_LABELS = {"loading", "spinner", "please wait"}

_APP_ALIASES = {
    "youtube": "com.google.android.youtube",
    "chrome": "com.android.chrome",
    "gmail": "com.google.android.gm",
    "instagram": "com.instagram.android",
    "spotify": "com.spotify.music",
    "twitter": "com.twitter.android",
    "x": "com.twitter.android",
    "tiktok": "com.zhiliaoapp.musically",
    "snapchat": "com.snapchat.android",
    "netflix": "com.netflix.mediaclient",
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
    "settings": "com.android.settings",
    "camera": "com.sec.android.app.camera",
    "calendar": "com.google.android.calendar",
    "phone": "com.google.android.dialer",
    "dialer": "com.google.android.dialer",
    "clock": "com.google.android.deskclock",
    "play store": "com.android.vending",
    "google play": "com.android.vending",
}

_LLM_SYSTEM_PROMPT = """\
You are PILOT's Actor. You control an Android phone by selecting UI actions.
Given the screen elements and step objective, pick the SINGLE best next action.
Return EXACTLY ONE JSON object — no markdown, no explanation.

READING THE SCREEN:
- Each element is: [ID] ClassName: "label" @(x,y) [flags]
- @(x,y) is the center position. Small y = top of screen, large y = bottom.
- Use element_id (the number in [brackets]) when tapping or typing.
- "clickable" means you can tap it. "editable" means you can type in it.

ACTIONS (pick one):
  {"action": "tap",         "element_id": N,                  "status": "brief desc"}
  {"action": "type",        "element_id": N, "value": "text", "status": "brief desc"}
  {"action": "scroll_down",                                    "status": "brief desc"}
  {"action": "scroll_up",                                      "status": "brief desc"}
  {"action": "back",                                           "status": "brief desc"}
  {"action": "home",                                           "status": "brief desc"}
  {"action": "open_app",    "package": "com.x.y",             "status": "brief desc"}
  {"action": "wait",        "seconds": N,                      "status": "brief desc"}
  {"action": "step_done",                                      "status": "brief desc"}
  {"action": "need_help",   "question": "...",                 "status": "brief desc"}

RULES:
- BE DECISIVE. Always tap a relevant element rather than returning need_help.
- need_help is ONLY for login walls, payment confirmation, or truly impossible situations.
- STAY FOCUSED on the CURRENT STEP only. Do NOT perform actions for future steps.
- Tap buttons/fields relevant to the objective. Prefer clearly labeled elements.
- To type: FIRST tap the field, THEN type in the next call. Never type without tapping first.
- If the objective is already achieved on screen, return step_done.
- If a loading spinner or progress bar is visible, return wait (seconds: 2).
- Only scroll if the target is likely off-screen. Never scroll back and forth aimlessly.
- If you already tapped the same element 2+ times in history, try a different element or step_done.
- "status" should be 5-8 words shown to the user.

APP-SPECIFIC KNOWLEDGE:
- YouTube: Search icon is usually desc:"Search" at the top. Tap it, then type in the search field.
  After search results appear, tap the first video result to play it.
- Uber: Pickup is auto-set from GPS. If step says "set pickup", return step_done.
  "Where to?" field is for DESTINATION only. Don't type destination in pickup field.
  When selecting ride type, ALWAYS prefer "UberX" over "Share" or other options.
  After selecting UberX, tap "Choose UberX" / "Confirm" button.
- Camera: Shutter button is a large round button at bottom center (@~540,1800+).
  If you see the camera viewfinder, tap the shutter to take the photo.
  To switch to front/selfie camera, tap the "Switch camera" or "flip" button (usually top-right).
  For selfies: switch camera FIRST, then tap shutter.
- DoorDash: Search bar at top. After typing, tap first matching restaurant result.
- Spotify: Search icon at bottom nav. Tap it, then tap search field, type song name.
- Google Maps: Search bar says "Search here" at the top. Tap it, then type the location.
  After typing, tap the first matching search result. To get directions, tap the "Directions" button.
- Most apps: Search/input fields are near the top of the screen (low y values).\
"""

_VISION_PROMPT = """\
You are PILOT's vision Actor. Return a single JSON action object only.
Allowed actions: tap, type, scroll_down, scroll_up, back, open_app, wait,
step_done, need_help.
Return EXACTLY ONE JSON object — no markdown, no explanation.\
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
        Hybrid decision: deterministic fast-path → LLM reasoning → vision → need_help.
        """
        # 1. Fast deterministic checks (instant, no API call)
        action = self._try_fast_checks(
            objective=objective,
            ui_tree=ui_tree,
            action_history=action_history,
            user_intent=user_intent,
            step_context=step_context or {},
        )
        if action is not None:
            logger.info("Actor(det) -> %s | %s", action["action"], action.get("status", ""))
            return action

        # 2. LLM text-based reasoning
        try:
            action = await self._decide_with_llm(
                objective=objective,
                ui_tree=ui_tree,
                action_history=action_history,
                user_intent=user_intent,
            )
            logger.info("Actor(llm) -> %s | %s", action["action"], action.get("status", ""))
            return action
        except Exception as exc:
            logger.warning("LLM actor failed (%s)", exc)

        # 3. Vision fallback
        if use_vision and screenshot_b64:
            try:
                action = await self._decide_with_vision(
                    objective=objective,
                    ui_tree=ui_tree,
                    action_history=action_history,
                    user_intent=user_intent,
                    screenshot_b64=screenshot_b64,
                )
                logger.info("Actor(vision) -> %s | %s", action["action"], action.get("status", ""))
                return action
            except Exception as exc:
                logger.warning("Vision fallback failed (%s)", exc)

        # 4. Last resort
        return {
            "action": "need_help",
            "question": f"I'm stuck on: {objective}. Can you help?",
            "status": "Need your guidance now",
        }

    # ── Fast deterministic checks ─────────────────────────────────────────────

    def _try_fast_checks(
        self,
        objective: str,
        ui_tree: Dict[str, Any],
        action_history: List[Dict[str, Any]],
        user_intent: str,
        step_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Instant checks for obvious actions. Returns None if LLM should decide.
        """
        elements = ui_tree.get("elements", []) or []
        current_package = (ui_tree.get("package") or "").lower()
        objective_norm = _normalize_text(objective)
        needs = _normalize_text(str(step_context.get("needs") or ""))
        objective_tokens = _meaningful_tokens(objective_norm)
        needs_tokens = _meaningful_tokens(needs)
        payload_text = _extract_payload(objective, str(step_context.get("needs") or ""))

        # ── Uber: full deterministic handling ──────────────────────────────
        if current_package == "com.ubercab":
            uber_action = self._uber_fast_path(
                objective_norm, elements, action_history, payload_text
            )
            if uber_action is not None:
                return uber_action

        # ── YouTube: full deterministic handling ─────────────────────────
        if current_package == "com.google.android.youtube":
            yt_action = self._youtube_fast_path(
                objective_norm, elements, action_history, payload_text
            )
            if yt_action is not None:
                return yt_action

        # ── Google Maps: full deterministic handling ──────────────────────
        if current_package == "com.google.android.apps.maps":
            maps_action = self._maps_fast_path(
                objective_norm, elements, action_history, payload_text
            )
            if maps_action is not None:
                return maps_action

        # Loading screen → wait
        if self._is_loading_screen(elements):
            return {"action": "wait", "seconds": 2, "status": "Waiting for screen update"}

        # Objective already met → step_done
        if self._objective_already_met(objective_norm, objective_tokens, needs_tokens, elements):
            return {"action": "step_done", "status": "Current step already complete"}

        # Need to open a specific app → open_app
        open_app_action = self._maybe_open_app(objective_norm, current_package)
        if open_app_action is not None:
            return open_app_action

        # Camera: deterministic handling
        if current_package == "com.sec.android.app.camera":
            # ── Switch to front camera (selfie) ──────────────────────
            if any(k in objective_norm for k in ("front camera", "switch camera", "flip camera", "selfie", "switch to front")):
                # Already tapped the switch button? Step done
                if any(a.get("action") == "tap" for a in action_history[-3:]):
                    return {"action": "step_done", "status": "Camera switched"}
                flip_btn = _find_element_by_text(elements, [
                    "switch camera", "flip camera", "front camera",
                    "camera switch", "toggle camera",
                ])
                if flip_btn:
                    return {"action": "tap", "element_id": flip_btn["id"],
                            "status": "Switching to front camera"}
                # Fallback: look for a camera-switch button by resource_id or position
                for el in elements:
                    if not el.get("clickable"):
                        continue
                    rid = str(el.get("resource_id") or "").lower()
                    desc = str(el.get("content_desc") or "").lower()
                    if any(k in rid for k in ("switch", "flip", "facing", "toggle")) or \
                       any(k in desc for k in ("switch", "flip", "facing", "toggle")):
                        return {"action": "tap", "element_id": el["id"],
                                "status": "Switching to front camera"}
                # If nothing found, mark done (might already be front camera)
                return {"action": "step_done", "status": "Front camera ready"}

            # ── Take photo (shutter button) ──────────────────────────
            if any(k in objective_norm for k in ("shutter", "take photo", "take picture", "capture", "take a photo", "take a picture")):
                # Already tapped the shutter? Photo is taken — move on
                if any(a.get("action") == "tap" for a in action_history[-3:]):
                    return {"action": "step_done", "status": "Photo taken"}
                el = _find_element_by_text(elements, ["shutter", "capture"])
                if el:
                    return {"action": "tap", "element_id": el["id"], "status": "Taking photo"}
                shutter = _find_shutter_button(elements)
                if shutter:
                    return {"action": "tap", "element_id": shutter["id"], "status": "Taking photo"}

        # Know what text to type and there's an editable field → type/tap
        if payload_text:
            text_action = self._maybe_type(payload_text, elements, action_history)
            if text_action is not None:
                return text_action
            # No editable field yet — look for a trigger button (e.g. search icon)
            trigger = self._maybe_tap_search_trigger(elements, current_package, objective_norm)
            if trigger is not None:
                return trigger

        # No confident deterministic answer — let LLM handle it
        return None

    def _is_loading_screen(self, elements: List[Dict[str, Any]]) -> bool:
        # Only detect loading if there's a ProgressBar class AND very few other
        # interactive elements (a real loading screen has almost nothing else).
        has_progress = False
        interactive_count = 0
        for element in elements:
            class_name = str(element.get("class") or "").lower()
            text = str(element.get("text") or "").lower()
            if "progressbar" in class_name:
                has_progress = True
            if element.get("clickable") or element.get("editable"):
                interactive_count += 1
            if any(label in text for label in _BLOCKING_LABELS):
                has_progress = True
        # Only treat as loading if ProgressBar present AND screen is mostly empty
        return has_progress and interactive_count < 5

    def _objective_already_met(
        self,
        objective_norm: str,
        objective_tokens: List[str],
        needs_tokens: List[str],
        elements: List[Dict[str, Any]],
    ) -> bool:
        # If the objective starts with an action verb, the user wants us to DO
        # something — never short-circuit these as "already done".
        if objective_tokens and objective_tokens[0] in _ACTION_VERBS:
            return False
        if "open " in objective_norm or "launch " in objective_norm:
            return False

        screen_text = " ".join(_element_text_parts(element) for element in elements)

        # Only mark done if the objective is purely observational (verify/confirm/check)
        if any(token in objective_tokens for token in _DONE_HINTS):
            content_tokens = [t for t in objective_tokens if t not in _DONE_HINTS and len(t) > 3]
            if content_tokens and all(token in screen_text for token in content_tokens[:3]):
                return True
        return False

    def _maybe_open_app(self, objective_norm: str, current_package: str) -> Optional[Dict[str, Any]]:
        if "open " not in objective_norm and "launch " not in objective_norm:
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
        editable_elements = [el for el in elements if el.get("editable")]
        if not editable_elements:
            return None

        # If we already typed this text recently, don't re-type — let LLM
        # pick from search results or move to the next action
        for a in reversed(action_history[-6:]):
            a_type = a.get("action")
            a_val = a.get("value")
            if a_type == "type":
                logger.debug("_maybe_type history check: action=%s value=%r payload=%r match=%s",
                             a_type, a_val, payload_text, a_val == payload_text)
                if a_val == payload_text:
                    logger.info("_maybe_type: already typed '%s', skipping", payload_text[:40])
                    return None

        ranked = sorted(
            editable_elements,
            key=lambda el: (-_element_type_score(el), int(el.get("id", 10**6))),
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

    def _uber_fast_path(
        self,
        objective_norm: str,
        elements: List[Dict[str, Any]],
        action_history: List[Dict[str, Any]],
        payload_text: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Deterministic handling for ALL common Uber screens.
        Bypasses LLM entirely for reliable Uber flows.
        """
        has_editable = any(el.get("editable") for el in elements)

        # ── Pickup step: just skip it (GPS auto-sets) ──────────────────
        if "pickup" in objective_norm and "destination" not in objective_norm:
            # But if there's a "Confirm pickup" button on screen, tap it first
            confirm = _find_element_by_text(elements, [
                "confirm pickup", "done", "confirm"
            ])
            if confirm:
                return {"action": "tap", "element_id": confirm["id"],
                        "status": "Confirming pickup location"}
            return {"action": "step_done", "status": "Pickup auto-set from GPS"}

        # ── Destination step ───────────────────────────────────────────
        if any(k in objective_norm for k in ("destination", "where to", "enter")):
            # Already typed? Check history
            already_typed = any(
                a.get("action") == "type" and a.get("value") == payload_text
                for a in action_history[-6:]
            ) if payload_text else False

            if already_typed:
                # After typing, look for search result to tap
                # Search results are usually clickable text items below the search field
                results = _find_uber_search_results(elements, payload_text)
                if results:
                    return {"action": "tap", "element_id": results["id"],
                            "status": "Selecting destination from results"}
                # No results yet? Maybe still loading
                return {"action": "wait", "seconds": 2,
                        "status": "Waiting for search results"}

            # Has editable field → type the destination
            if has_editable and payload_text:
                return self._maybe_type(payload_text, elements, action_history)

            # No editable field → find "Where to?" button
            where_to = _find_element_by_text(elements, [
                "where to", "where to?", "search here",
                "search destination", "enter destination",
            ])
            if where_to:
                return {"action": "tap", "element_id": where_to["id"],
                        "status": "Opening destination search"}

            # Look for any search-like element
            search = _find_element_by_text(elements, ["search"])
            if search:
                return {"action": "tap", "element_id": search["id"],
                        "status": "Opening search"}

        # ── Choose ride type step ──────────────────────────────────────
        if any(k in objective_norm for k in ("ride type", "uberx", "choose ride", "select ride")):
            uberx = _find_element_by_text(elements, ["uberx"])
            if uberx:
                return {"action": "tap", "element_id": uberx["id"],
                        "status": "Selecting UberX"}
            # Look for "Choose UberX" / "Confirm UberX" button
            choose = _find_element_by_text(elements, [
                "choose uberx", "confirm uberx", "choose uber"
            ])
            if choose:
                return {"action": "tap", "element_id": choose["id"],
                        "status": "Confirming UberX"}

        # ── Confirm booking step ───────────────────────────────────────
        if any(k in objective_norm for k in ("confirm", "book")):
            confirm = _find_element_by_text(elements, [
                "confirm uberx", "confirm uber", "choose uberx",
                "request uberx", "confirm ride", "request ride",
                "confirm", "request",
            ])
            if confirm:
                return {"action": "tap", "element_id": confirm["id"],
                        "status": "Confirming ride booking"}

        # ── ANY Uber screen: handle "confirm pickup" popup ─────────────
        # This can appear at any step — Uber asks to confirm pickup area
        confirm_pickup = _find_element_by_text(elements, [
            "confirm pickup", "set pickup",
        ])
        if confirm_pickup:
            return {"action": "tap", "element_id": confirm_pickup["id"],
                    "status": "Confirming pickup location"}

        # Didn't match any known Uber pattern — fall through to LLM
        return None

    def _youtube_fast_path(
        self,
        objective_norm: str,
        elements: List[Dict[str, Any]],
        action_history: List[Dict[str, Any]],
        payload_text: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Deterministic handling for YouTube screens.
        Steps: open → tap search icon → type query → tap result → verify playing.
        """
        has_editable = any(el.get("editable") for el in elements)

        # ── Step: "Tap search icon" / "Open search" ───────────────────
        if any(k in objective_norm for k in ("search icon", "open search", "tap the search")):
            # If already on search screen (editable field visible), step is done
            if has_editable:
                return {"action": "step_done", "status": "Search already open"}
            # Find the search icon (usually content_desc="Search" in top bar)
            search_icon = _find_element_by_text(elements, ["search"])
            if search_icon:
                return {"action": "tap", "element_id": search_icon["id"],
                        "status": "Tapping search icon"}

        # ── Step: "Type search query" / "Search for" ──────────────────
        if any(k in objective_norm for k in ("type", "search query", "search for", "enter")):
            # Already typed? We need to submit the search
            already_typed = any(
                a.get("action") == "type" and a.get("value") == payload_text
                for a in action_history[-6:]
            ) if payload_text else False

            if already_typed:
                # Check if we already tapped a suggestion/submitted — if so, step is done
                already_tapped_after_type = False
                found_type = False
                for a in reversed(action_history[-6:]):
                    if a.get("action") == "type":
                        found_type = True
                    elif found_type and a.get("action") == "tap":
                        already_tapped_after_type = True
                        break
                if already_tapped_after_type:
                    return {"action": "step_done", "status": "Search submitted"}

                # Haven't tapped a suggestion yet — find one to submit the search
                suggestion = _find_youtube_search_suggestion(elements, payload_text)
                if suggestion:
                    return {"action": "tap", "element_id": suggestion["id"],
                            "status": "Tapping search suggestion"}
                # No suggestion? Try tapping a non-editable "search" button
                submit = _find_element_by_text(elements, ["search", "submit"])
                if submit and not submit.get("editable"):
                    return {"action": "tap", "element_id": submit["id"],
                            "status": "Submitting search"}
                # Fallback: mark done so we don't loop
                return {"action": "step_done", "status": "Search query entered"}

            # Has editable field → type the query
            if has_editable and payload_text:
                return self._maybe_type(payload_text, elements, action_history)

            # No editable field → need to tap search icon first
            search_icon = _find_element_by_text(elements, ["search"])
            if search_icon:
                return {"action": "tap", "element_id": search_icon["id"],
                        "status": "Opening search first"}

        # ── Step: "Tap first result" / "Play" ─────────────────────────
        if any(k in objective_norm for k in ("first result", "first video", "tap the first", "play")):
            # If screen has very few elements, video might already be playing
            interactive = [el for el in elements if el.get("clickable")]
            if len(elements) <= 10 and not has_editable:
                # Likely video player or minimal screen — check if already played
                already_tapped = any(
                    a.get("action") == "tap" for a in action_history[-3:]
                )
                if already_tapped:
                    return {"action": "step_done",
                            "status": "Video should be playing"}
            # Find video results
            video = _find_youtube_video_result(elements)
            if video:
                return {"action": "tap", "element_id": video["id"],
                        "status": "Playing video"}
            # If no results visible, maybe still loading
            if self._is_loading_screen(elements):
                return {"action": "wait", "seconds": 2, "status": "Waiting for results"}
            # Try scrolling down to find results
            return {"action": "scroll_down", "status": "Looking for video results"}

        # ── Step: "Verify playing" ────────────────────────────────────
        if any(k in objective_norm for k in ("verify", "confirm", "check")):
            # If we see a video player element or "pause" button, it's playing
            player = _find_element_by_text(elements, ["pause", "player"])
            if player:
                return {"action": "step_done", "status": "Video is playing"}
            # Check for any full-screen video indicators
            # (few interactive elements = video playing full screen)
            interactive = [el for el in elements if el.get("clickable")]
            if len(interactive) <= 5:
                return {"action": "step_done", "status": "Video appears to be playing"}
            # Give it a moment
            return {"action": "wait", "seconds": 2, "status": "Waiting for video to start"}

        # Didn't match — fall through to LLM
        return None

    def _maps_fast_path(
        self,
        objective_norm: str,
        elements: List[Dict[str, Any]],
        action_history: List[Dict[str, Any]],
        payload_text: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Deterministic handling for Google Maps screens.
        Steps: open → search location → get directions → verify route.
        """
        has_editable = any(el.get("editable") for el in elements)

        # ── Step: "Search for X" ────────────────────────────────────
        if any(k in objective_norm for k in ("search for", "search", "find", "look up", "type")):
            # Already typed?
            already_typed = any(
                a.get("action") == "type" and a.get("value") == payload_text
                for a in action_history[-6:]
            ) if payload_text else False

            if already_typed:
                # Check if we already tapped a result after typing
                already_tapped_after_type = False
                found_type = False
                for a in reversed(action_history[-6:]):
                    if a.get("action") == "type":
                        found_type = True
                    elif found_type and a.get("action") == "tap":
                        already_tapped_after_type = True
                        break
                if already_tapped_after_type:
                    return {"action": "step_done", "status": "Location selected"}

                # Find a search result to tap (clickable, not editable, has text)
                result = _find_maps_search_result(elements, payload_text)
                if result:
                    return {"action": "tap", "element_id": result["id"],
                            "status": "Selecting search result"}
                # Still loading?
                if self._is_loading_screen(elements):
                    return {"action": "wait", "seconds": 2, "status": "Waiting for results"}
                return {"action": "step_done", "status": "Search submitted"}

            # Has editable field → type the query
            if has_editable and payload_text:
                return self._maybe_type(payload_text, elements, action_history)

            # No editable field → tap the Maps search bar
            search_bar = _find_element_by_text(elements, [
                "search here", "search_omni_box", "search along route",
            ])
            if search_bar:
                return {"action": "tap", "element_id": search_bar["id"],
                        "status": "Opening Maps search"}
            # Fallback: look for any element with "search" that's NOT a bottom nav icon
            for el in elements:
                if not el.get("clickable"):
                    continue
                text = " ".join([
                    str(el.get("text") or ""),
                    str(el.get("hint") or ""),
                    str(el.get("content_desc") or ""),
                    str(el.get("resource_id") or ""),
                ]).lower()
                bounds = el.get("bounds")
                # Maps search bar is at the top of the screen (y < 400)
                if "search" in text and bounds and len(bounds) == 4:
                    cy = (bounds[1] + bounds[3]) // 2
                    if cy < 400:
                        return {"action": "tap", "element_id": el["id"],
                                "status": "Opening Maps search"}

        # ── Step: "Get directions" / "Navigate" ─────────────────────
        if any(k in objective_norm for k in ("direction", "navigate", "route", "start nav")):
            directions_btn = _find_element_by_text(elements, [
                "directions", "navigate", "start",
            ])
            if directions_btn:
                return {"action": "tap", "element_id": directions_btn["id"],
                        "status": "Getting directions"}
            # If we see a route overview, step is done
            route_indicator = _find_element_by_text(elements, [
                "min", "fastest route", "start navigation",
            ])
            if route_indicator:
                return {"action": "step_done", "status": "Directions loaded"}

        # ── Step: "Verify route" ────────────────────────────────────
        if any(k in objective_norm for k in ("verify", "confirm", "check")):
            route = _find_element_by_text(elements, [
                "min", "route", "directions", "start", "navigation",
            ])
            if route:
                return {"action": "step_done", "status": "Route is showing"}
            return {"action": "wait", "seconds": 2, "status": "Waiting for route"}

        return None

    def _maybe_tap_search_trigger(
        self,
        elements: List[Dict[str, Any]],
        current_package: str,
        objective_norm: str,
    ) -> Optional[Dict[str, Any]]:
        """
        When we need to type but there's no editable field, tap a trigger
        button that opens one (e.g. Uber 'Where to?', YouTube search icon).
        """
        # Skip if there are already editable fields — _maybe_type should handle it
        if any(el.get("editable") for el in elements):
            return None

        # Uber: "Where to?" button
        if current_package == "com.ubercab":
            el = _find_element_by_text(elements, ["where to", "search here"])
            if el:
                return {"action": "tap", "element_id": el["id"], "status": "Opening destination input"}

        # YouTube: search icon
        if current_package == "com.google.android.youtube":
            el = _find_element_by_text(elements, ["search"])
            if el:
                return {"action": "tap", "element_id": el["id"], "status": "Opening search"}

        # Google Maps: search bar
        if current_package == "com.google.android.apps.maps":
            el = _find_element_by_text(elements, ["search here", "search_omni_box"])
            if el:
                return {"action": "tap", "element_id": el["id"], "status": "Opening Maps search"}

        # Spotify: search tab
        if current_package == "com.spotify.music":
            el = _find_element_by_text(elements, ["search"])
            if el:
                return {"action": "tap", "element_id": el["id"], "status": "Opening search"}

        # DoorDash: search
        if current_package == "com.dd.doordash":
            el = _find_element_by_text(elements, ["search", "find restaurants"])
            if el:
                return {"action": "tap", "element_id": el["id"], "status": "Opening search"}

        # General: look for any clickable element with "search" in text
        if any(k in objective_norm for k in ("search", "find", "enter", "type")):
            el = _find_element_by_text(elements, ["search"])
            if el:
                return {"action": "tap", "element_id": el["id"], "status": "Opening search field"}

        return None

    # ── LLM-based decision ────────────────────────────────────────────────────

    async def _decide_with_llm(
        self,
        objective: str,
        ui_tree: Dict[str, Any],
        action_history: List[Dict[str, Any]],
        user_intent: str,
    ) -> Dict[str, Any]:
        """Use Groq LLM to reason about the next action."""
        tree_str = format_ui_tree(ui_tree)
        history_str = format_action_history(action_history[-8:])

        prompt = (
            f"Task: {user_intent}\n"
            f"Current step: {objective}\n\n"
            f"Screen elements:\n{tree_str}\n\n"
            f"Recent actions:\n{history_str}\n\n"
            "What is the single next action?"
        )

        messages = [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = await self.groq.chat(
                model=settings.actor_model,
                messages=messages,
                max_tokens=256,
                temperature=0.1,
            )
            return extract_json(raw)
        except Exception as exc:
            logger.warning("Groq LLM failed (%s), trying Ollama", exc)
            if self.ollama and await self.ollama.is_available():
                raw = await self.ollama.chat(messages, max_tokens=256)
                return extract_json(raw)
            raise

    # ── Vision fallback ───────────────────────────────────────────────────────

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
                text_prompt=prompt,
                screenshot_b64=screenshot_b64,
                max_tokens=256,
                system_prompt=_VISION_PROMPT,
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
        return {
            "action": "need_help",
            "question": "I cannot safely identify the next action.",
            "status": "Need help to continue",
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s']", " ", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _meaningful_tokens(value: str) -> List[str]:
    return [token for token in value.split() if token and token not in _STOPWORDS]


def _extract_payload(objective: str, needs: str) -> str:
    # If explicit needs provided (e.g. "Shape of You by Ed Sheeran"), use it directly
    if needs and needs.strip():
        return needs.strip()

    # Check for quoted text in objective
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', objective)
    if quoted:
        token = next(part for part in quoted[0] if part)
        return token.strip()

    # Try to extract payload from objective text after verb markers
    for marker in ("saying", "message", "search for", "enter", "type", "input"):
        lower_source = objective.lower()
        idx = lower_source.find(marker)
        if idx >= 0:
            source_slice = objective[idx + len(marker):].strip(" :.-")
            if source_slice:
                return source_slice
    return ""


def _element_text_parts(element: Dict[str, Any]) -> str:
    parts = [
        str(element.get("text") or ""),
        str(element.get("hint") or ""),
        str(element.get("content_desc") or ""),
        str(element.get("resource_id") or "").split("/")[-1],
        str(element.get("label") or ""),
    ]
    return _normalize_text(" ".join(parts))


def _find_element_by_text(
    elements: List[Dict[str, Any]], keywords: List[str]
) -> Optional[Dict[str, Any]]:
    """Find the first clickable element whose text/hint/desc matches any keyword."""
    for keyword in keywords:
        kw = keyword.lower()
        for el in elements:
            if not el.get("clickable"):
                continue
            text = " ".join([
                str(el.get("text") or ""),
                str(el.get("hint") or ""),
                str(el.get("content_desc") or ""),
            ]).lower()
            if kw in text:
                return el
    return None


def _find_youtube_search_suggestion(
    elements: List[Dict[str, Any]], query: str
) -> Optional[Dict[str, Any]]:
    """Find a YouTube autocomplete suggestion matching the search query."""
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 2]

    candidates = []
    for el in elements:
        if not el.get("clickable"):
            continue
        if el.get("editable"):
            continue
        text = (str(el.get("text") or "") + " " + str(el.get("content_desc") or "")).lower()
        if not text.strip() or len(text.strip()) < 3:
            continue
        # Skip nav elements
        if any(skip in text for skip in ["search", "back", "clear", "voice", "microphone"]):
            continue
        # Score by how many query words match
        match_count = sum(1 for w in query_words if w in text)
        if match_count >= 1:
            candidates.append((el, match_count))

    if candidates:
        candidates.sort(key=lambda x: -x[1])
        return candidates[0][0]
    # No text match — just return the first non-nav clickable element below the search bar
    for el in elements:
        if not el.get("clickable") or el.get("editable"):
            continue
        text = (str(el.get("text") or "") + " " + str(el.get("content_desc") or "")).lower()
        if any(skip in text for skip in ["search", "back", "clear", "voice", "microphone", "home", "shorts", "library"]):
            continue
        bounds = el.get("bounds")
        if bounds and len(bounds) == 4:
            cy = (bounds[1] + bounds[3]) // 2
            if cy > 200:  # below search bar
                return el
    return None


def _find_youtube_video_result(elements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find the first video result on a YouTube search results page."""
    # Video results are typically clickable elements with text (the title),
    # positioned below the search bar (y > 300), and have meaningful text.
    # Skip small nav buttons, icons, and the search field itself.
    candidates = []
    for el in elements:
        if not el.get("clickable"):
            continue
        if el.get("editable"):
            continue
        text = str(el.get("text") or "").strip()
        desc = str(el.get("content_desc") or "").strip()
        label = text or desc
        if not label or len(label) < 5:
            continue
        # Skip known nav/UI elements
        label_lower = label.lower()
        if any(skip in label_lower for skip in [
            "search", "home", "shorts", "subscriptions", "library",
            "notifications", "cast", "account", "explore", "trending",
        ]):
            continue
        # Get vertical position — prefer items further down (actual results)
        bounds = el.get("bounds")
        y = 0
        if bounds and len(bounds) == 4:
            y = (bounds[1] + bounds[3]) // 2
        if y > 200:  # below the top nav bar
            candidates.append((el, y))

    if candidates:
        # Return the first (topmost) video result
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]
    return None


def _find_maps_search_result(
    elements: List[Dict[str, Any]], query: str
) -> Optional[Dict[str, Any]]:
    """Find a search result in Google Maps matching the query."""
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 2]

    candidates = []
    for el in elements:
        if not el.get("clickable"):
            continue
        if el.get("editable"):
            continue
        text = " ".join([
            str(el.get("text") or ""),
            str(el.get("content_desc") or ""),
        ]).lower()
        if not text.strip() or len(text.strip()) < 3:
            continue
        # Skip nav/UI elements
        if any(skip in text for skip in [
            "search", "back", "clear", "voice", "microphone",
            "explore", "go", "transit", "driving", "walking",
        ]):
            continue
        match_count = sum(1 for w in query_words if w in text)
        if match_count >= 1:
            candidates.append((el, match_count))

    if candidates:
        candidates.sort(key=lambda x: -x[1])
        return candidates[0][0]

    # Fallback: first clickable non-nav element below y > 200
    for el in elements:
        if not el.get("clickable") or el.get("editable"):
            continue
        text = " ".join([
            str(el.get("text") or ""),
            str(el.get("content_desc") or ""),
        ]).lower()
        if any(skip in text for skip in ["search", "back", "clear", "voice", "home"]):
            continue
        if text.strip() and len(text.strip()) >= 3:
            bounds = el.get("bounds")
            if bounds and len(bounds) == 4:
                cy = (bounds[1] + bounds[3]) // 2
                if cy > 200:
                    return el
    return None


def _find_uber_search_results(
    elements: List[Dict[str, Any]], query: str
) -> Optional[Dict[str, Any]]:
    """Find a search result in Uber that matches the destination query."""
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 2]

    # Look for clickable elements whose text contains words from the query
    candidates = []
    for el in elements:
        if not el.get("clickable"):
            continue
        if el.get("editable"):
            continue  # skip the search field itself
        text = " ".join([
            str(el.get("text") or ""),
            str(el.get("content_desc") or ""),
        ]).lower()
        if not text.strip():
            continue
        # Count how many query words appear in the element text
        match_count = sum(1 for w in query_words if w in text)
        if match_count >= 1:
            candidates.append((el, match_count))

    if candidates:
        # Return the best match (most query words found)
        candidates.sort(key=lambda x: -x[1])
        return candidates[0][0]
    return None


def _find_shutter_button(elements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find camera shutter button by position/size heuristics."""
    candidates = []
    for el in elements:
        if not el.get("clickable"):
            continue
        bounds = el.get("bounds")
        if not bounds or len(bounds) != 4:
            continue
        left, top, right, bottom = bounds
        cx = (left + right) // 2
        cy = (top + bottom) // 2
        w = right - left
        h = bottom - top
        # Shutter: bottom half, horizontally centered, large-ish button
        if cy > 1500 and 300 < cx < 800 and w > 100 and h > 100:
            candidates.append((el, w * h))
    if candidates:
        candidates.sort(key=lambda x: -x[1])
        return candidates[0][0]
    return None


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
