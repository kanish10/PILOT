"""
All FastAPI routes for the PILOT backend.
"""
import logging
import time
import traceback
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

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
    t0 = time.perf_counter()
    logger.info("=" * 70)
    logger.info("POST /task/start  intent='%s'", req.transcription)
    logger.info("=" * 70)

    if not req.transcription or not req.transcription.strip():
        raise HTTPException(status_code=400, detail="Empty transcription")

    transcription = req.transcription.strip()
    # Reject garbage transcriptions (voice noise like "23", "the", single chars)
    if len(transcription) < 3:
        raise HTTPException(status_code=400, detail="Transcription too short")
    if transcription.isdigit():
        raise HTTPException(status_code=400, detail="Transcription appears to be noise")

    orch = container.orchestrator
    try:
        task = await orch.start_task(req.transcription.strip())
    except Exception as exc:
        logger.error("TASK START FAILED: %s", exc)
        logger.error(traceback.format_exc())
        raise

    elapsed = time.perf_counter() - t0
    resp = TaskStartResponse(
        task_id=task.task_id,
        plan={
            "plan": [s.model_dump() for s in task.plan],
            "info_extracted": task.info,
        },
        confirmation_message=task.confirmation_message or f"On it: {req.transcription}",
        glow_state=task.glow_state.value,
        status_text=task.status_text,
    )

    logger.info("RESPONSE /task/start (%.2fs):", elapsed)
    logger.info("  task_id=%s  status=%s  glow=%s", task.task_id, task.status.value, task.glow_state.value)
    logger.info("  confirmation='%s'", resp.confirmation_message)
    logger.info("  plan steps=%d:", len(task.plan))
    for s in task.plan:
        logger.info("    step %d: [%s] %s (needs=%s, status=%s)", s.step, s.app, s.objective, s.needs, s.status)
    if task.errors:
        logger.error("  errors: %s", task.errors)
    logger.info("-" * 70)

    return resp


# ── Task: screen → action ────────────────────────────────────────────────────

@router.post("/task/screen", response_model=TaskActionResponse)
async def task_screen(req: TaskScreenRequest) -> TaskActionResponse:
    """
    Phone sends current UI tree (and optionally a screenshot).
    Server returns the next action to execute.
    """
    t0 = time.perf_counter()
    logger.info("POST /task/screen  task=%s  has_screenshot=%s", req.task_id, req.screenshot_b64 is not None)
    logger.debug("  ui_tree package=%s  elements=%d",
                 req.ui_tree.get("package", "?"), len(req.ui_tree.get("elements", [])))
    task = await _get_task(req.task_id)
    logger.debug("  task status=%s  step_idx=%d/%d", task.status.value, task.current_step_index, len(task.plan))

    lock = await state_store.lock(req.task_id)
    async with lock:
        action = await container.orchestrator.process_screen(
            task=task,
            ui_tree=req.ui_tree,
            screenshot_b64=req.screenshot_b64,
        )

    elapsed = time.perf_counter() - t0
    resp = TaskActionResponse(
        action=action,
        status_text=task.status_text,
        glow_state=task.glow_state.value,
        step_complete=action.get("step_complete", False),
        task_complete=task.is_complete,
        pending_confirmation=task.pending_confirmation,
        confirmation_message=task.confirmation_message,
    )
    logger.info("RESPONSE /task/screen (%.2fs): action=%s  step_complete=%s  task_complete=%s  glow=%s",
                elapsed, action.get("action"), resp.step_complete, resp.task_complete, resp.glow_state)
    logger.debug("  full action: %s", action)
    return resp


# ── Task: verify ──────────────────────────────────────────────────────────────

@router.post("/task/verify", response_model=TaskVerifyResponse)
async def task_verify(req: TaskVerifyRequest) -> TaskVerifyResponse:
    """
    Phone sends before/after screens and the action it just executed.
    Server verifies and optionally returns the next action.
    """
    t0 = time.perf_counter()
    logger.info("POST /task/verify  task=%s  action=%s", req.task_id, req.action_performed.get("action", "?"))
    task = await _get_task(req.task_id)

    lock = await state_store.lock(req.task_id)
    async with lock:
        result = await container.orchestrator.process_verify(
            task=task,
            old_screen=req.old_screen,
            new_screen=req.new_screen,
            action_performed=req.action_performed,
        )

    elapsed = time.perf_counter() - t0
    logger.info("RESPONSE /task/verify (%.2fs): result=%s  reason='%s'  pending_confirm=%s",
                elapsed, result["result"], result["reason"], result.get("pending_confirmation", False))
    if result.get("next_action"):
        logger.info("  next_action=%s", result["next_action"].get("action", "?"))

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

@router.post("/task/user-response")
async def task_user_response(req: UserResponseRequest) -> Dict[str, Any]:
    """
    Phone sends user's spoken response (yes/no/cancel/free text).
    Used when the AI is waiting for confirmation (e.g. before payment).
    """
    logger.info("=" * 70)
    logger.info("POST /task/user-response  task=%s  response='%s'", req.task_id, req.response)
    logger.info("=" * 70)
    task = await _get_task(req.task_id)
    logger.debug("  task status=%s  pending_confirmation=%s", task.status.value, task.pending_confirmation)

    lock = await state_store.lock(req.task_id)
    async with lock:
        result = await container.orchestrator.handle_user_response(
            task=task,
            response=req.response,
        )

    # Android deserialises this as AgentStepResponse where `action` must be a valid
    # ActionPayload dict (ActionPayloadSerializer rejects plain strings like "continue").
    is_cancelled = result["action"] == "cancelled"
    resp = {
        "action": {
            "action": "step_done" if is_cancelled else "wait",
            "seconds": 0,
            "status": result["status_text"],
        },
        "status_text": result["status_text"],
        "glow_state": "idle" if is_cancelled else "working",
        "step_complete": is_cancelled,
        "task_complete": is_cancelled,
    }
    logger.info("RESPONSE /task/user-response: cancelled=%s  glow=%s  status='%s'",
                is_cancelled, resp["glow_state"], resp["status_text"])
    return resp


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
    t0 = time.perf_counter()
    logger.info("POST /agent/step  task=%s  step='%s'", req.task_id, req.current_step[:80])
    logger.debug("  user_intent='%s'  history_len=%d  has_screenshot=%s",
                 req.user_intent, len(req.action_history), req.screenshot_b64 is not None)
    logger.debug("  ui_tree package=%s  elements=%d",
                 req.ui_tree.get("package", "?"), len(req.ui_tree.get("elements", [])))
    orch = container.orchestrator

    try:
        result = await orch.agent_step(
            user_intent=req.user_intent,
            current_step=req.current_step,
            step_needs=req.step_needs,
            ui_tree=req.ui_tree,
            action_history=req.action_history,
            screenshot_b64=req.screenshot_b64,
        )
    except Exception as exc:
        logger.error("AGENT STEP FAILED: %s", exc)
        logger.error(traceback.format_exc())
        # Return a graceful wait instead of crashing with 500
        result = {
            "action": {"action": "wait", "seconds": 5, "status": "Retrying shortly..."},
            "status_text": "Retrying shortly...",
            "glow_state": "working",
            "step_complete": False,
            "task_complete": False,
        }

    elapsed = time.perf_counter() - t0
    resp = AgentStepResponse(
        action=result["action"],
        status_text=result["status_text"],
        glow_state=result["glow_state"],
        step_complete=result["step_complete"],
        task_complete=result["task_complete"],
    )
    logger.info("RESPONSE /agent/step (%.2fs): action=%s  step_complete=%s  task_complete=%s  status='%s'",
                elapsed, result["action"].get("action", "?") if isinstance(result["action"], dict) else result["action"],
                resp.step_complete, resp.task_complete, resp.status_text)
    logger.debug("  full action: %s", result["action"])
    return resp


# ── Internal helper ───────────────────────────────────────────────────────────

async def _get_task(task_id: str):
    task = await state_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return task
