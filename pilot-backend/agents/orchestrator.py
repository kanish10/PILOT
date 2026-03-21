"""
Agent 0 — The Orchestrator.
Central coordinator: owns the task state machine, routes between agents,
enforces the typing rule, handles retries, and manages error recovery.

State machine:
  PLANNING → EXECUTING ⇄ VERIFYING → CONFIRMING → EXECUTING → DONE
                  ↑                                    |
                  └──────────────── retry ─────────────┘
"""
import logging
from typing import Any, Dict, List, Optional

from agents.actor import ActorAgent, _APP_ALIASES
from agents.planner import PlannerAgent
from agents.verifier import VerifierAgent
from config import settings
from core.state_store import state_store
from models.task import GlowState, PlanStep, TaskState, TaskStatus

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
        self,
        planner: PlannerAgent,
        actor: ActorAgent,
        verifier: VerifierAgent,
    ) -> None:
        self.planner = planner
        self.actor = actor
        self.verifier = verifier

    # ── Task lifecycle ────────────────────────────────────────────────────────

    async def start_task(self, user_intent: str) -> TaskState:
        """
        Create a task, plan it, and store it.
        Returns the TaskState (already saved in state_store).
        """
        task = TaskState(user_intent=user_intent, status=TaskStatus.PLANNING)
        task.status_text = "Planning your task..."
        await state_store.create(task)

        try:
            plan_result = await self.planner.plan(user_intent)
            raw_steps = self._validate_plan_result(plan_result)
        except ValueError as exc:
            logger.warning("Planner returned invalid plan for task %s: %s", task.task_id, exc)
            try:
                plan_result = await self.planner.plan(user_intent, repair_hint=str(exc))
                raw_steps = self._validate_plan_result(plan_result)
            except Exception as repair_exc:
                logger.error("Planner repair failed for task %s: %s", task.task_id, repair_exc)
                task.status = TaskStatus.ERROR
                task.glow_state = GlowState.ERROR
                task.status_text = "Failed to create a valid plan. Please try again."
                task.errors.append(str(repair_exc))
                return task
        except Exception as exc:
            logger.error("Planning failed for task %s: %s", task.task_id, exc)
            task.status = TaskStatus.ERROR
            task.glow_state = GlowState.ERROR
            task.status_text = "Failed to create a plan. Please try again."
            task.errors.append(str(exc))
            return task

        task.plan = [
            PlanStep(
                step=s.get("step", i + 1),
                app=s.get("app", ""),
                objective=s.get("objective", f"Step {i + 1}"),
                needs=s.get("needs"),
                status="pending",
            )
            for i, s in enumerate(raw_steps)
        ]
        task.info = plan_result.get("info_extracted", {})

        if task.plan:
            task.plan[0].status = "in_progress"

        task.status = TaskStatus.EXECUTING
        task.glow_state = GlowState.WORKING
        task.confirmation_message = plan_result.get(
            "confirmation_message",
            f"Got it, I'll handle: {user_intent}",
        )
        logger.info("Task %s started: %d steps planned", task.task_id, len(task.plan))
        return task

    # ── Screen processing (stateful) ──────────────────────────────────────────

    async def process_screen(
        self,
        task: TaskState,
        ui_tree: Dict[str, Any],
        screenshot_b64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Receive current screen, decide the next action.
        Handles: pending_type_action, step_done, need_help, need_vision,
        two-step typing rule, and back-press counting.
        """
        if task.is_complete:
            return {
                "action": "step_done",
                "status": "Task already complete",
                "task_complete": True,
            }

        # If we previously intercepted a type and need to deliver it now
        if task.pending_type_action:
            action = task.pending_type_action
            task.pending_type_action = None
            task.record_action(action)
            if action.get("status"):
                task.status_text = action["status"]
            return action

        current_step = task.current_step
        if not current_step:
            task.status = TaskStatus.DONE
            task.glow_state = GlowState.DONE
            task.status_text = "All steps complete!"
            return {"action": "step_done", "status": "All steps complete!", "task_complete": True}

        task.last_ui_tree = ui_tree

        # Detect if we need vision mode
        use_vision = (
            screenshot_b64 is not None
            and bool(task.action_history)
            and task.action_history[-1].action == "need_vision"
        )

        try:
            action = await self.actor.decide(
                objective=current_step.objective,
                ui_tree=ui_tree,
                action_history=task.recent_actions_as_dicts(10),
                user_intent=task.user_intent,
                use_vision=use_vision,
                screenshot_b64=screenshot_b64,
                step_context=current_step.model_dump(),
            )
        except Exception as exc:
            logger.error("Actor failed for task %s: %s", task.task_id, exc)
            task.errors.append(str(exc))
            action = {"action": "wait", "seconds": 2, "status": "Retrying..."}

        action_type = action.get("action", "")

        # ── Enforce two-step typing rule ──────────────────────────────────────
        if action_type == "type":
            last = task.action_history[-1] if task.action_history else None
            tap_preceded = (
                last is not None
                and last.action == "tap"
                and last.element_id == action.get("element_id")
            )
            if not tap_preceded:
                logger.info(
                    "Inserting tap before type (element #%s)", action.get("element_id")
                )
                task.pending_type_action = action
                tap_action = {
                    "action": "tap",
                    "element_id": action.get("element_id"),
                    "status": action.get("status", "Focusing text field..."),
                }
                task.record_action(tap_action)
                task.status_text = tap_action["status"]
                return tap_action

        # ── Update status text ────────────────────────────────────────────────
        if action.get("status"):
            task.status_text = action["status"]

        # ── Handle special action types ───────────────────────────────────────
        if action_type == "step_done":
            has_more = task.advance_step()
            if has_more:
                task.status_text = f"Moving to: {task.current_step.objective[:50]}"
            else:
                task.status = TaskStatus.DONE
                task.glow_state = GlowState.DONE
                task.status_text = "Task complete!"
            action["task_complete"] = not has_more
            action["step_complete"] = True

        elif action_type in {"need_help", "need_user"}:
            task.record_action(action)
            task.pending_confirmation = True
            task.confirmation_message = action.get("question", "I need your help to continue.")
            task.glow_state = GlowState.LISTENING
            task.status = TaskStatus.CONFIRMING

        elif action_type == "need_vision":
            task.status_text = "Looking more carefully at the screen..."
            task.record_action(action)

        elif action_type == "back":
            task.record_action(action)
            task.back_press_count += 1
            if task.back_press_count >= settings.max_back_presses:
                task.errors.append("Max back-presses reached, restarting step")
                task.back_press_count = 0

        else:
            task.record_action(action)

        return action

    # ── Verification (stateful) ───────────────────────────────────────────────

    async def process_verify(
        self,
        task: TaskState,
        old_screen: Dict[str, Any],
        new_screen: Dict[str, Any],
        action_performed: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Verify the outcome of an action.
        Returns result dict with optional next_action.
        """
        current_step = task.current_step
        if not current_step:
            return {
                "result": "success",
                "reason": "No more steps",
                "status_text": task.status_text,
                "glow_state": task.glow_state.value,
                "next_action": None,
            }

        try:
            verification = await self.verifier.verify(
                action=action_performed,
                old_screen=old_screen,
                new_screen=new_screen,
                objective=current_step.objective,
            )
        except Exception as exc:
            logger.error("Verifier failed for task %s: %s", task.task_id, exc)
            verification = {"result": "failed", "reason": f"Verification error: {exc}"}

        v_result = verification.get("result", "failed")
        v_reason = verification.get("reason", "")
        v_suggestion = verification.get("suggestion", "")

        # Update last action result in history
        if task.action_history:
            task.action_history[-1].result = v_result

        # ── Success ───────────────────────────────────────────────────────────
        if v_result == "success":
            task.retry_count = 0
            task.back_press_count = 0
            task.last_ui_tree = new_screen
            return _build_verify_response(v_result, v_reason, task, next_action=None)

        # ── Blocked (login / permission wall) ────────────────────────────────
        if v_result == "blocked":
            task.pending_confirmation = True
            task.confirmation_message = (
                v_suggestion or "I need your help to continue past this screen."
            )
            task.glow_state = GlowState.LISTENING
            task.status = TaskStatus.CONFIRMING
            return _build_verify_response(
                v_result,
                v_reason,
                task,
                next_action=None,
                pending_confirmation=True,
                confirmation_message=task.confirmation_message,
            )

        # ── Unexpected (dialog / popup / wrong screen) ────────────────────────
        if v_result == "unexpected" and v_suggestion:
            # Ask Actor to handle the suggestion inline
            try:
                next_action = await self.actor.decide(
                    objective=v_suggestion,
                    ui_tree=new_screen,
                    action_history=task.recent_actions_as_dicts(5),
                    user_intent=task.user_intent,
                    step_context=current_step.model_dump(),
                )
                task.record_action(next_action)
                task.status_text = next_action.get("status", "Handling unexpected state...")
                task.last_ui_tree = new_screen
                return _build_verify_response(v_result, v_reason, task, next_action=next_action)
            except Exception as exc:
                logger.warning("Could not get next action for unexpected state: %s", exc)

        # ── Failed — retry logic ──────────────────────────────────────────────
        task.retry_count += 1
        if task.retry_count >= settings.max_retries:
            task.retry_count = 0
            task.pending_confirmation = True
            task.confirmation_message = (
                f"I'm having trouble with step: \"{current_step.objective}\". "
                "Can you help me past this?"
            )
            task.glow_state = GlowState.LISTENING
            task.status = TaskStatus.CONFIRMING
            return _build_verify_response(
                "blocked",
                f"Failed after {settings.max_retries} attempts",
                task,
                next_action=None,
                pending_confirmation=True,
                confirmation_message=task.confirmation_message,
            )

        task.status_text = (
            f"Retrying ({task.retry_count}/{settings.max_retries})..."
        )
        return _build_verify_response(v_result, v_reason, task, next_action=None)

    # ── User response (yes/no/free text) ─────────────────────────────────────

    async def handle_user_response(
        self,
        task: TaskState,
        response: str,
    ) -> Dict[str, Any]:
        task.pending_confirmation = False
        r = _normalize_confirmation(response)

        if r == "repeat":
            task.pending_confirmation = True
            task.status = TaskStatus.CONFIRMING
            task.glow_state = GlowState.LISTENING
            task.status_text = task.confirmation_message or "Please say yes or no."
            return {
                "action": "repeat",
                "status_text": task.status_text,
                "glow_state": GlowState.LISTENING.value,
                "task_complete": False,
            }

        if r in ("no", "cancel", "stop"):
            task.status = TaskStatus.CANCELLED
            task.glow_state = GlowState.OFF
            task.status_text = "Stopped. The app is as you left it."
            return {
                "action": "cancelled",
                "status_text": task.status_text,
                "glow_state": GlowState.OFF.value,
                "task_complete": True,
            }

        # Any affirmative → continue
        task.glow_state = GlowState.WORKING
        task.status = TaskStatus.EXECUTING
        task.status_text = "Continuing..."
        return {
            "action": "continue",
            "status_text": task.status_text,
            "glow_state": GlowState.WORKING.value,
            "task_complete": False,
        }

    # ── Stateless single-shot endpoint ────────────────────────────────────────

    async def agent_step(
        self,
        user_intent: str,
        current_step: str,
        ui_tree: Dict[str, Any],
        action_history: list,
        screenshot_b64: Optional[str] = None,
        step_needs: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Simplified stateless endpoint: runs Actor only and returns the next action.
        Does not require a task to exist in state_store.
        """
        current_package = (ui_tree.get("package") or "").lower()
        expected_package = _resolve_expected_package(current_step, user_intent)

        # ── STUCK DETECTION: if agent is looping, force recovery ───────────
        stuck_recovery = self._detect_stuck_and_recover(
            action_history, current_step, expected_package
        )
        if stuck_recovery is not None:
            return stuck_recovery

        # Detect loops in action history
        consecutive_vision = 0
        recent_scrolls = 0
        consecutive_open_app = 0
        consecutive_waits = 0
        for a in reversed(action_history[-6:]):
            if a.get("action") == "need_vision":
                consecutive_vision += 1
            else:
                break
        for a in reversed(action_history[-4:]):
            if a.get("action") == "open_app":
                consecutive_open_app += 1
            else:
                break
        for a in reversed(action_history[-6:]):
            if a.get("action") == "wait":
                consecutive_waits += 1
            else:
                break
        for a in action_history[-6:]:
            if a.get("action") in ("scroll_down", "scroll_up"):
                recent_scrolls += 1

        # Wrong-app detection: if we're in the wrong app, go back to the right one
        if (
            expected_package
            and current_package
            and current_package != expected_package
            and "launcher" not in current_package
            and "android" != current_package
        ):
            logger.warning(
                "[ORCH] Wrong app detected: in %s, need %s. Switching back.",
                current_package, expected_package,
            )
            return {
                "action": {"action": "open_app", "package": expected_package, "status": "Switching to correct app"},
                "status_text": "Switching to correct app",
                "glow_state": GlowState.WORKING.value,
                "step_complete": False,
                "task_complete": False,
            }

        use_vision = screenshot_b64 is not None and bool(action_history) and \
            action_history[-1].get("action") == "need_vision"

        # If vision has failed 2+ times, stop trying
        if consecutive_vision >= 2:
            use_vision = False
            logger.warning("[ORCH] need_vision loop detected (%d), forcing text-only", consecutive_vision)

        action = await self.actor.decide(
            objective=current_step,
            ui_tree=ui_tree,
            action_history=action_history[-8:],
            user_intent=user_intent,
            use_vision=use_vision,
            screenshot_b64=screenshot_b64,
            step_context={"objective": current_step, "needs": step_needs or ""},
        )

        action_type = action.get("action", "")

        # Break need_vision loop
        if action_type == "need_vision" and consecutive_vision >= 2:
            logger.warning("[ORCH] Overriding need_vision loop → need_help")
            action = {
                "action": "need_help",
                "question": f"I'm having trouble with: {current_step}. Can you help?",
                "status": "Need your guidance now",
            }
            action_type = "need_help"

        # Break scroll oscillation loop (4+ scrolls in last 6 actions)
        if action_type in ("scroll_down", "scroll_up") and recent_scrolls >= 4:
            logger.warning("[ORCH] Scroll oscillation detected (%d in last 6), escalating", recent_scrolls)
            action = {
                "action": "need_help",
                "question": f"I can't find what I need for: {current_step}. Can you help?",
                "status": "Need your guidance now",
            }
            action_type = "need_help"

        # Break open_app loop (2+ consecutive open_app for same package)
        if action_type == "open_app" and consecutive_open_app >= 2:
            logger.warning("[ORCH] open_app loop detected (%d consecutive), marking step_done", consecutive_open_app)
            action = {"action": "step_done", "status": "App appears to be open"}
            action_type = "step_done"

        # Break wait loop (3+ consecutive waits = screen isn't changing, skip LLM)
        if action_type == "wait" and consecutive_waits >= 3:
            logger.warning("[ORCH] Wait loop detected (%d consecutive), forcing LLM decision", consecutive_waits)
            # Force LLM to decide instead of waiting again
            action = {"action": "step_done", "status": "Moving on from stuck screen"}
            action_type = "step_done"

        step_complete = action_type == "step_done"
        task_complete = False  # stateless: caller must track this

        return {
            "action": action,
            "status_text": action.get("status", "Working..."),
            "glow_state": GlowState.WORKING.value,
            "step_complete": step_complete,
            "task_complete": task_complete,
        }

    def _detect_stuck_and_recover(
        self,
        action_history: list,
        current_step: str,
        expected_package: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Detect if the agent is stuck in a loop and return a recovery action.
        Returns None if not stuck, or a response dict if recovery is needed.

        Recovery escalation:
          1. press back (clear modals/popups)
          2. go home (escape the app entirely)
          3. open_app (fresh start in the right app)
          4. step_done (skip the step and move on)
        """
        if len(action_history) < 8:
            return None

        recent = action_history[-8:]
        recent_types = [a.get("action") for a in recent]

        # Only trigger stuck detection if recent actions are all "work" actions
        # (no recovery actions like back/home/step_done already in progress)
        work_actions = {"tap", "type", "scroll_down", "scroll_up", "need_vision"}
        all_work = all(a.get("action") in work_actions for a in recent)

        if not all_work:
            return None

        # Pattern 1: tap/type loop on same element
        tap_type_loop = False
        if len(recent) >= 4:
            last4 = recent[-4:]
            types4 = [a.get("action") for a in last4]
            elems4 = [a.get("element_id") for a in last4]
            if types4 == ["tap", "type", "tap", "type"]:
                unique_elems = set(e for e in elems4 if e is not None)
                if len(unique_elems) <= 1:
                    tap_type_loop = True

        # Pattern 2: same element tapped 3+ times in recent history
        element_ids = [a.get("element_id") for a in recent if a.get("element_id") is not None]
        same_element_spam = False
        if element_ids:
            from collections import Counter
            counts = Counter(element_ids)
            _, top_count = counts.most_common(1)[0]
            if top_count >= 3:
                same_element_spam = True

        # Pattern 3: 8+ work actions without step_done = aimless
        aimless = len(recent) >= 8

        is_stuck = tap_type_loop or same_element_spam or aimless

        if not is_stuck:
            return None

        # Determine recovery action based on what's already in FULL history
        all_types = [a.get("action") for a in action_history]
        back_count = all_types.count("back")
        home_count = all_types.count("home")
        open_app_count = all_types.count("open_app")

        if back_count == 0:
            logger.warning("[ORCH] STUCK on '%s' (pattern: %s), pressing BACK",
                           current_step[:40],
                           "tap/type loop" if tap_type_loop else "same element" if same_element_spam else "aimless")
            return {
                "action": {"action": "back", "status": "Resetting — seemed stuck"},
                "status_text": "Resetting — seemed stuck",
                "glow_state": GlowState.WORKING.value,
                "step_complete": False,
                "task_complete": False,
            }
        elif home_count == 0:
            logger.warning("[ORCH] STUCK after back, going HOME")
            return {
                "action": {"action": "home", "status": "Going home to restart"},
                "status_text": "Going home to restart",
                "glow_state": GlowState.WORKING.value,
                "step_complete": False,
                "task_complete": False,
            }
        elif expected_package and open_app_count <= 1:
            logger.warning("[ORCH] STUCK after home, reopening %s", expected_package)
            return {
                "action": {"action": "open_app", "package": expected_package, "status": "Restarting from app home"},
                "status_text": "Restarting from app home",
                "glow_state": GlowState.WORKING.value,
                "step_complete": False,
                "task_complete": False,
            }
        else:
            logger.warning("[ORCH] STUCK — recovery exhausted, SKIPPING step '%s'", current_step[:40])
            return {
                "action": {"action": "step_done", "status": "Skipping stuck step"},
                "status_text": "Skipping stuck step",
                "glow_state": GlowState.WORKING.value,
                "step_complete": True,
                "task_complete": False,
            }

    def _validate_plan_result(self, plan_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_steps = plan_result.get("plan")
        if not isinstance(raw_steps, list):
            raise ValueError("Planner response must include a list under 'plan'")
        if not 3 <= len(raw_steps) <= 8:
            raise ValueError("Planner must return between 3 and 8 steps")

        steps: List[Dict[str, Any]] = []
        for index, step in enumerate(raw_steps, start=1):
            if not isinstance(step, dict):
                raise ValueError("Each plan step must be a JSON object")
            objective = str(step.get("objective", "")).strip()
            app = str(step.get("app", "")).strip()
            if not objective or not app:
                raise ValueError("Each plan step must include non-empty 'app' and 'objective'")
            steps.append(step)

        final_objective = steps[-1]["objective"].lower()
        if not any(keyword in final_objective for keyword in ("verify", "confirm", "review", "check")):
            raise ValueError("The last plan step must be a verification or confirmation step")
        return steps


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_verify_response(
    result: str,
    reason: str,
    task: TaskState,
    next_action: Optional[Dict[str, Any]],
    pending_confirmation: bool = False,
    confirmation_message: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "result": result,
        "reason": reason,
        "status_text": task.status_text,
        "glow_state": task.glow_state.value,
        "next_action": next_action,
        "pending_confirmation": pending_confirmation or task.pending_confirmation,
        "confirmation_message": confirmation_message or task.confirmation_message,
    }


def _normalize_confirmation(response: str) -> str:
    normalized = "".join(ch for ch in response.lower().strip() if ch.isalpha() or ch.isspace())
    token = " ".join(normalized.split())
    if not token:
        return "yes"  # empty response = continue, don't cancel
    if token in {"no", "stop", "cancel"}:
        return "no"
    if token in {"yes", "yeah", "yep", "sure", "ok", "okay", "continue", "go"}:
        return "yes"
    if token == "repeat":
        return "repeat"
    return "yes"  # unknown text = continue


# Build a reverse lookup: package → app label
_PACKAGE_TO_LABEL = {}
for _label, _pkg in _APP_ALIASES.items():
    if _pkg not in _PACKAGE_TO_LABEL:
        _PACKAGE_TO_LABEL[_pkg] = _label


_KEYWORD_TO_PACKAGE = {
    "photo": "com.sec.android.app.camera",
    "picture": "com.sec.android.app.camera",
    "selfie": "com.sec.android.app.camera",
    "shutter": "com.sec.android.app.camera",
}


def _resolve_expected_package(current_step: str, user_intent: str) -> Optional[str]:
    """Try to figure out which app package the current step should be in."""
    step_lower = current_step.lower()
    intent_lower = user_intent.lower()
    # Explicit app name matches first
    for label, package in _APP_ALIASES.items():
        if label in step_lower or label in intent_lower:
            return package
    # Keyword-based inference
    for keyword, package in _KEYWORD_TO_PACKAGE.items():
        if keyword in step_lower or keyword in intent_lower:
            return package
    return None
