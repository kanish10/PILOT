import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    CONFIRMING = "confirming"  # waiting for user yes/no
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class GlowState(str, Enum):
    LISTENING = "listening"
    WORKING = "working"
    DONE = "done"
    ERROR = "error"
    OFF = "off"


class PlanStep(BaseModel):
    step: int
    app: str = ""
    objective: str
    needs: Optional[str] = None
    status: str = "pending"  # pending | in_progress | done | failed


class ActionRecord(BaseModel):
    action: str
    element_id: Optional[int] = None
    value: Optional[str] = None
    package: Optional[str] = None
    result: Optional[str] = None
    status_text: Optional[str] = None


class TaskState(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    user_intent: str
    status: TaskStatus = TaskStatus.PLANNING
    plan: List[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    info: Dict[str, Any] = Field(default_factory=dict)
    action_history: List[ActionRecord] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    total_actions: int = 0
    start_time: float = Field(default_factory=time.time)
    glow_state: GlowState = GlowState.WORKING
    status_text: str = "Starting..."
    last_action: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    back_press_count: int = 0
    pending_confirmation: bool = False
    confirmation_message: Optional[str] = None
    # Last screen seen (for verifier comparisons)
    last_ui_tree: Optional[Dict[str, Any]] = None
    # If orchestrator intercepted a type and needs to send it next call
    pending_type_action: Optional[Dict[str, Any]] = None

    @property
    def current_step(self) -> Optional[PlanStep]:
        if 0 <= self.current_step_index < len(self.plan):
            return self.plan[self.current_step_index]
        return None

    @property
    def is_complete(self) -> bool:
        return self.status in (
            TaskStatus.DONE,
            TaskStatus.CANCELLED,
            TaskStatus.ERROR,
        )

    def advance_step(self) -> bool:
        """Mark current step done and move forward. Returns True if more steps remain."""
        if 0 <= self.current_step_index < len(self.plan):
            self.plan[self.current_step_index].status = "done"
        self.current_step_index += 1
        self.retry_count = 0
        self.back_press_count = 0
        if self.current_step_index >= len(self.plan):
            self.status = TaskStatus.DONE
            self.glow_state = GlowState.DONE
            self.status_text = "Task complete!"
            return False
        self.plan[self.current_step_index].status = "in_progress"
        return True

    def record_action(self, action: Dict[str, Any], result: Optional[str] = None) -> None:
        record = ActionRecord(
            action=action.get("action", "unknown"),
            element_id=action.get("element_id"),
            value=action.get("value"),
            package=action.get("package"),
            result=result,
            status_text=action.get("status"),
        )
        self.action_history.append(record)
        self.total_actions += 1
        self.last_action = action

    def recent_actions_as_dicts(self, n: int = 10) -> List[Dict[str, Any]]:
        return [
            {
                "action": r.action,
                "element_id": r.element_id,
                "value": r.value,
                "package": r.package,
                "result": r.result,
                "status_text": r.status_text,
            }
            for r in self.action_history[-n:]
        ]
