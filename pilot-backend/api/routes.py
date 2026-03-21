"""
All FastAPI routes for the PILOT backend.
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from core.container import container
from core.state_store import state_store
from models.requests import (
    AgentStepRequest,
    AgentStepResponse,
    CancelRequest,
    CancelResponse,
    TaskActionResponse,
    TaskScreenRequest,
    TaskStartRequest,
    TaskStartResponse,
    TaskVerifyRequest,
    TaskVerifyResponse,
    UserResponseRequest,
    UserResponseResponse,
)
from models.task import GlowState

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "active_tasks": state_store.count(),
    }


# ── Task: start ───────────────────────────────────────────────────────────────

@router.post("/task/start", response_model=TaskStartResponse)
async def task_start(req: TaskStartRequest) -> TaskStartResponse:
    """
    Receive a voice transcription, create a plan, and return the task_id.
    This is the first call the phone makes after speech-to-text.
    """
    logger.info("POST /task/start  intent=%s", req.transcription[:80])
    orch = container.orchestrator
    task = await orch.start_task(req.transcription)

    return TaskStartResponse(
        task_id=task.task_id,
        plan=[s.model_dump() for s in task.plan],
        confirmation_message=task.confirmation_message or f"On it: {req.transcription}",
        glow_state=task.glow_state.value,
        status_text=task.status_text,
    )


# ── Task: screen → action ────────────────────────────────────────────────────

@router.post("/task/screen", response_model=TaskActionResponse)
async def task_screen(req: TaskScreenRequest) -> TaskActionResponse:
    """
    Phone sends current UI tree (and optionally a screenshot).
    Server returns the next action to execute.
    """
    logger.info("POST /task/screen  task=%s", req.task_id)
    task = await _get_task(req.task_id)

    lock = await state_store.lock(req.task_id)
    async with lock:
        action = await container.orchestrator.process_screen(
            task=task,
            ui_tree=req.ui_tree,
            screenshot_b64=req.screenshot_b64,
        )

    return TaskActionResponse(
        action=action,
        status_text=task.status_text,
        glow_state=task.glow_state.value,
        step_complete=action.get("step_complete", False),
        task_complete=task.is_complete,
        pending_confirmation=task.pending_confirmation,
        confirmation_message=task.confirmation_message,
    )


# ── Task: verify ──────────────────────────────────────────────────────────────

@router.post("/task/verify", response_model=TaskVerifyResponse)
async def task_verify(req: TaskVerifyRequest) -> TaskVerifyResponse:
    """
    Phone sends before/after screens and the action it just executed.
    Server verifies and optionally returns the next action.
    """
    logger.info("POST /task/verify  task=%s", req.task_id)
    task = await _get_task(req.task_id)

    lock = await state_store.lock(req.task_id)
    async with lock:
        result = await container.orchestrator.process_verify(
            task=task,
            old_screen=req.old_screen,
            new_screen=req.new_screen,
            action_performed=req.action_performed,
        )

    return TaskVerifyResponse(
        result=result["result"],
        reason=result["reason"],
        status_text=result["status_text"],
        glow_state=result["glow_state"],
        next_action=result.get("next_action"),
        pending_confirmation=result.get("pending_confirmation", False),
        confirmation_message=result.get("confirmation_message"),
    )


# ── Task: user response (yes/no/cancel) ───────────────────────────────────────

@router.post("/task/user-response", response_model=UserResponseResponse)
async def task_user_response(req: UserResponseRequest) -> UserResponseResponse:
    """
    Phone sends user's spoken response (yes/no/cancel/free text).
    Used when the AI is waiting for confirmation (e.g. before payment).
    """
    logger.info("POST /task/user-response  task=%s  response=%s", req.task_id, req.response)
    task = await _get_task(req.task_id)

    lock = await state_store.lock(req.task_id)
    async with lock:
        result = await container.orchestrator.handle_user_response(
            task=task,
            response=req.response,
        )

    return UserResponseResponse(
        action=result["action"],
        status_text=result["status_text"],
        glow_state=result["glow_state"],
        task_complete=result.get("task_complete", False),
    )


# ── Task: cancel ──────────────────────────────────────────────────────────────

@router.post("/task/cancel", response_model=CancelResponse)
async def task_cancel(req: CancelRequest) -> CancelResponse:
    """Immediately cancel a running task."""
    logger.info("POST /task/cancel  task=%s", req.task_id)
    task = await _get_task(req.task_id)

    from models.task import TaskStatus
    task.status = TaskStatus.CANCELLED
    task.glow_state = GlowState.OFF
    task.status_text = "Stopped. The app is as you left it."

    return CancelResponse(status="cancelled", status_text=task.status_text)


# ── Task: state (debug) ───────────────────────────────────────────────────────

@router.get("/task/{task_id}")
async def task_state(task_id: str) -> Dict[str, Any]:
    """Return full task state. Useful for debugging from a browser."""
    task = await _get_task(task_id)
    data = task.model_dump()
    data["glow_state"] = task.glow_state.value
    data["status"] = task.status.value
    return data


# ── Agent/step (simplified stateless endpoint) ────────────────────────────────

@router.post("/agent/step", response_model=AgentStepResponse)
async def agent_step(req: AgentStepRequest) -> AgentStepResponse:
    """
    Simplified, stateless endpoint for hackathon use.
    Phone sends everything the server needs; server runs Actor and returns
    the next action. No state is stored (the phone tracks action_history).
    """
    logger.info("POST /agent/step  task=%s  step=%s", req.task_id, req.current_step[:60])
    orch = container.orchestrator

    result = await orch.agent_step(
        user_intent=req.user_intent,
        current_step=req.current_step,
        ui_tree=req.ui_tree,
        action_history=req.action_history,
        screenshot_b64=req.screenshot_b64,
    )

    return AgentStepResponse(
        action=result["action"],
        status_text=result["status_text"],
        glow_state=result["glow_state"],
        step_complete=result["step_complete"],
        task_complete=result["task_complete"],
    )


# ── Internal helper ───────────────────────────────────────────────────────────

async def _get_task(task_id: str):
    task = await state_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return task
