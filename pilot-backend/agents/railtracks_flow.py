"""
Optional Railtracks flow adapter for the PILOT agent loop.

This mirrors the Railtracks docs pattern:
- keep flow state in the run context
- compose the system as Python nodes
- treat MCP and other tools as explicit boundaries

The backend does not require Railtracks at runtime yet. If the dependency is
installed later, `build_task_flow()` exposes the same orchestration contract as
the FastAPI endpoints.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from agents.orchestrator import Orchestrator
from models.task import TaskState

try:
    import railtracks as rt  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    rt = None


def railtracks_available() -> bool:
    return rt is not None


def build_task_flow(orchestrator: Orchestrator):
    if rt is None:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Railtracks is not installed. Install it before building the flow adapter."
        )

    @rt.function_node
    async def start_node(user_intent: str) -> Dict[str, Any]:
        task = await orchestrator.start_task(user_intent)
        rt.context["task"] = task
        return _task_payload(task)

    @rt.function_node
    async def screen_node(ui_tree: Dict[str, Any], screenshot_b64: Optional[str] = None) -> Dict[str, Any]:
        task = _require_task()
        return await orchestrator.process_screen(task, ui_tree, screenshot_b64)

    @rt.function_node
    async def verify_node(
        old_screen: Dict[str, Any],
        new_screen: Dict[str, Any],
        action_performed: Dict[str, Any],
    ) -> Dict[str, Any]:
        task = _require_task()
        return await orchestrator.process_verify(task, old_screen, new_screen, action_performed)

    @rt.function_node
    async def user_response_node(response: str) -> Dict[str, Any]:
        task = _require_task()
        return await orchestrator.handle_user_response(task, response)

    @rt.session
    async def task_session(user_intent: str) -> Dict[str, Any]:
        return await rt.call(start_node, user_intent=user_intent)

    return {
        "session": task_session,
        "nodes": {
            "start": start_node,
            "screen": screen_node,
            "verify": verify_node,
            "user_response": user_response_node,
        },
    }


def _require_task() -> TaskState:
    task = rt.context.get("task") if rt is not None else None
    if task is None:
        raise RuntimeError("Railtracks context does not contain an active task")
    return task


def _task_payload(task: TaskState) -> Dict[str, Any]:
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "status_text": task.status_text,
        "glow_state": task.glow_state.value,
        "confirmation_message": task.confirmation_message,
        "plan": [step.model_dump() for step in task.plan],
    }
