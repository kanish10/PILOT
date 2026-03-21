"""
Agent 0 — The Orchestrator.
Central coordinator: owns the task state machine, routes between agents,
enforces the typing rule, handles retries, and manages error recovery.

State machine:
  PLANNING → EXECUTING ⇄ VERIFYING → CONFIRMING → EXECUTING → DONE
                  ↑                                              |
                  └──────────────── retry ─────────────────────┘
"""
import logging
from typing import Any, Dict, Optional

from agents.actor import ActorAgent
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
        except Exception as exc:
            logger.error("Planning failed for task %s: %s", task.task_id, exc)
            task.status = TaskStatus.ERROR
            task.glow_state = GlowState.ERROR
            task.status_text = "Failed to create a plan. Please try again."
            task.errors.append(str(exc))
            return task

        # Parse plan steps
        raw_steps = plan_result.get("plan", [])
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

        elif action_type == "need_help":
            task.pending_confirmation = True
            task.confirmation_message = action.get("question", "I need your help to continue.")
            task.glow_state = GlowState.LISTENING
            task.status = TaskStatus.CONFIRMING

        elif action_type == "need_vision":
            task.status_text = "Looking more carefully at the screen..."
            # Record so next call knows why there's a screenshot

        elif action_type == "back":
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
        r = response.lower().strip()

        if r in ("no", "cancel", "stop", "abort", "quit"):
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
    ) -> Dict[str, Any]:
        """
        Simplified stateless endpoint: runs Actor only and returns the next action.
        Does not require a task to exist in state_store.
        """
        use_vision = screenshot_b64 is not None and bool(action_history) and \
            action_history[-1].get("action") == "need_vision"

        action = await self.actor.decide(
            objective=current_step,
            ui_tree=ui_tree,
            action_history=action_history[-8:],
            user_intent=user_intent,
            use_vision=use_vision,
            screenshot_b64=screenshot_b64,
        )

        action_type = action.get("action", "")
        step_complete = action_type == "step_done"
        task_complete = False  # stateless: caller must track this

        return {
            "action": action,
            "status_text": action.get("status", "Working..."),
            "glow_state": GlowState.WORKING.value,
            "step_complete": step_complete,
            "task_complete": task_complete,
        }


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
