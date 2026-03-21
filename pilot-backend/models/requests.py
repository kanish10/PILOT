"""
Pydantic models for all API request and response bodies.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ── /task/start ───────────────────────────────────────────────────────────────

class TaskStartRequest(BaseModel):
    transcription: str


class TaskStartResponse(BaseModel):
    task_id: str
    # Wrapped as {"plan": [...], "info_extracted": {...}} to match Android TaskPlan model
    plan: Dict[str, Any]
    confirmation_message: str
    glow_state: str = "working"
    status_text: str = "Planning your task..."


# ── /task/screen ──────────────────────────────────────────────────────────────

class TaskScreenRequest(BaseModel):
    task_id: str
    ui_tree: Dict[str, Any]
    screenshot_b64: Optional[str] = None  # send only when server previously returned need_vision


class TaskActionResponse(BaseModel):
    action: Dict[str, Any]
    status_text: str
    glow_state: str
    step_complete: bool = False
    task_complete: bool = False
    pending_confirmation: bool = False
    confirmation_message: Optional[str] = None


# ── /task/verify ──────────────────────────────────────────────────────────────

class TaskVerifyRequest(BaseModel):
    task_id: str
    old_screen: Dict[str, Any]
    new_screen: Dict[str, Any]
    action_performed: Dict[str, Any]


class TaskVerifyResponse(BaseModel):
    result: str          # success | failed | unexpected | blocked
    reason: str
    status_text: str
    glow_state: str
    next_action: Optional[Dict[str, Any]] = None
    pending_confirmation: bool = False
    confirmation_message: Optional[str] = None


# ── /task/user-response ───────────────────────────────────────────────────────

class UserResponseRequest(BaseModel):
    task_id: str
    response: str        # "yes" / "no" / "cancel" / free text


class UserResponseResponse(BaseModel):
    action: str          # "continue" | "cancelled" | "none"
    status_text: str
    glow_state: str
    task_complete: bool = False


# ── /task/cancel ──────────────────────────────────────────────────────────────

class CancelRequest(BaseModel):
    task_id: str


class CancelResponse(BaseModel):
    status: str          # "cancelled"
    status_text: str


# ── /agent/step  (simplified single-shot endpoint) ───────────────────────────

class AgentStepRequest(BaseModel):
    task_id: str
    user_intent: str
    current_step: str
    ui_tree: Dict[str, Any]
    screenshot_b64: Optional[str] = None
    action_history: List[Dict[str, Any]] = []


class AgentStepResponse(BaseModel):
    action: Dict[str, Any]
    status_text: str
    glow_state: str
    step_complete: bool
    task_complete: bool
