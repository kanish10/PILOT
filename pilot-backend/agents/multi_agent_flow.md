# PILOT Multi-Agent Flow — Deterministic Design

This document summarizes the multi-agent architecture described in `claude.md` and formalizes the contracts, deterministic behaviors, and the full agent loop for the PILOT system. `claude.md` is the single source of truth; this file extracts, condenses, and clarifies the runtime behavior and the deterministic change requested for Agent 5.

## Overview

PILOT is an Android app + Mac server multi-agent system that automates phone tasks via voice. The system uses five specialized agents coordinated by an Orchestrator on the Mac server. Primary goals:

- Deterministic behavior for reproducibility and demos.
- Clear agent contracts and single-shot JSON interfaces between agents.
- Fast, local control flow with LLM fallbacks only when deterministic heuristics fail.

Agents:
- Agent 0 — Orchestrator (Mac server)
- Agent 1 — Eyes (Phone-side Accessibility Service)
- Agent 2 — Planner (LLM on Mac)
- Agent 3 — Actor (Deterministic server-side decision function)
- Agent 4 — Verifier (LLM on Mac)
- Agent 5 — Voice & Glow (Phone-side) — now deterministic

## High-level agent loop (deterministic rail)

1. Phone (Agent 5) records user voice and sends transcription to Orchestrator (`POST /task/start`).
2. Orchestrator calls Planner (Agent 2) once to produce a high-level plan (3–8 steps) and extracted info.
3. For each step in plan:
   a. Orchestrator requests current UI tree from Eyes (Agent 1) — phone posts `/task/screen`.
   b. Orchestrator calls Actor (Agent 3) with `ui_schema`, `objective`, and `action_history` → deterministic action returned.
   c. Phone executes the action (tap/type/scroll/open/back/wait) deterministically via Eyes' executor.
   d. After the action, phone sends new UI tree to Orchestrator.
   e. Orchestrator calls Verifier (Agent 4) to compare before/after and decide `success|failed|unexpected|blocked`.
   f. Based on Verifier and deterministic retry logic, Orchestrator advances, retries, or escalates.
4. Orchestrator updates Agent 5 with status text + deterministic glow state.
5. When plan complete, Agent 5 announces completion and switches glow to DONE.

This loop is engineered to be deterministic in decision-making except where explicitly allowed (LLM fallbacks). The overall system deterministic policy:
- Deterministic components: Orchestrator state machine, Actor heuristics, Eyes normalization & executor, Agent 5 UI/voice policy.
- Probabilistic components (use sparingly): Planner and Verifier LLMs and Vision LLM for screenshots; used only when deterministic heuristics cannot produce a confident action or when verifier cannot determine success.

## Agent contracts (JSON interfaces)

- `POST /task/start`
  - Body: {"transcription": string}
  - Response: {"task_id": string, "plan": [...], "confirmation_message": string}

- `POST /task/screen`
  - Body: {"task_id": string, "ui_tree": {...}, "screenshot_b64": string|null}
  - Response: {"action": {...}, "status_text": string, "glow_state": string}

- `POST /task/verify`
  - Body: {"task_id": string, "old_screen": {...}, "new_screen": {...}, "action_performed": {...}}
  - Response: {"result": "success|failed|unexpected|blocked", "reason": string, "next_action": {...}}

- `POST /task/user-response`
  - Body: {"task_id": string, "response": "yes|no|cancel|..."}
  - Response: {"action": {...}, "status_text": string}

- `POST /task/cancel`
  - Body: {"task_id": string}
  - Response: {"status": "cancelled"}

Simplified single-endpoint option for hackathons: `POST /agent/step` with `ui_tree`, `current_step`, `action_history`, returns `action` + `status_text` + `glow_state`.

## Deterministic details per agent

### Agent 0 — Orchestrator (deterministic)
- Maintains a Task State Object with explicit fields (task_id, user_intent, status, plan, current_step_index, action_history, errors, start_time, glow_state, status_text).
- Implements the state machine: IDLE → LISTENING → PLANNING → EXECUTING → VERIFYING → DONE.
- Decides deterministic retry policy: up to 3 identical attempts → try alternate strategy (scroll/back/wait) → 1 vision fallback → escalate to LLM Actor → ask user.
- Timeouts: per-action timeout (default 8s) and step timeout (default 30s). Deterministic fallback triggers on timeout.

Success criteria: progress only when Verifier returns `success`; deterministic retries otherwise.

### Agent 1 — Eyes (deterministic)
- Accessibility Service that serializes a canonical UI schema with these fields: package, activity, screen_title, timestamp, elements[], screenshot_b64|null.
- Element canonical fields: id, class, text, hint, content_desc, resource_id, bounds, clickable, scrollable, editable, checked, label (lowercased tokenized label).
- Deterministic filtering: drop invisible/zero-size nodes, remove decorative nodes, limit to top 100 relevant interactable elements.
- Execution functions (deterministic): tap (ACTION_CLICK), type (ACTION_SET_TEXT), scroll (dispatchGesture with deterministic scroll vectors), back (GLOBAL_ACTION_BACK), open_app (Intent with package), wait (sleep). These actions are executed by the same Eyes agent and reported back.
- Deterministic screenshot policy: capture only when `need_vision` or `debug=true`.

### Agent 2 — Planner (LLM; controlled use)
- One-shot planner called at task start. Returns 3–8 step plan, and `info_extracted` object. Uses LLM (Groq) with a strict JSON-only output requirement and a canonical system prompt (as in `claude.md`).
- Planner is allowed to be probabilistic, but Orchestrator may request re-planning deterministically on failures.
- Plan schema validation: Orchestrator validates steps length and required fields; otherwise re-call planner with stricter constraints.

### Agent 3 — Actor (deterministic)
- Signature: decide_action(ui_schema: dict, objective: str, action_history: list) -> action: dict
- Deterministic action types: tap, type, scroll_down, scroll_up, back, open_app, wait, step_done, need_user, need_vision.
- Scoring heuristic (deterministic): exact text match > contains keywords > resource_id similarity > content_desc > clickability. Implementable via deterministic scoring functions (string normalization, edit distances with deterministic tie-breakers like element id).
- Two-step typing rule: only return `type` after a `tap` on same `element_id` in prior action_history.
- Scroll behavior: if candidate element not visible and a scrollable parent exists, return `scroll_down` or `scroll_up` and update deterministic scroll_state to avoid loops.
- Retry policy: if same action tried 3 times → alternate strategies (scroll/back/wait) → if still no progress, return `need_vision`.

### Agent 4 — Verifier (LLM; controlled use)
- Receives action, before_screen, after_screen, current objective and returns `{result, reason, suggestion?}` as JSON.
- LLM may be used here for natural-language understanding, but deterministic comparators are attempted first: exact element presence/absence, text diffs, package/activity changes, and timeouts.
- Deterministic comparator logic: if no screen change → `failed`; if expected element now visible → `success`; if dialog detected (known dialog patterns) → `unexpected` + suggestion to dismiss.

### Agent 5 — Voice & Glow (now deterministic)
This is the main requested change: Agent 5 must be deterministic. The system moves Agent 5 from partially probabilistic (TTS + voice behavior) to a strictly deterministic policy-driven agent with predictable outputs and actions.

Agent 5 responsibilities (deterministic):
- Overlay UI (floating button, glow border, status bar) with deterministic state machine and timing.
- Voice input handling: speech recognition still uses device STT (inherently probabilistic), but Agent 5 exposes deterministic handling rules for transcripts: Jitter-tolerant exact-match rules for short commands (yes/no/stop/cancel) and a normalized transcription pipeline for longer inputs (lowercase, punctuation stripped) sent to the Orchestrator.
- TTS policy: deterministic templates driven by a small finite-state set — no LLM-generated speech. All spoken messages are chosen from a deterministic set of templates that include substitution tokens from the `Task State Object`.

Agent 5 deterministic state machine:
- States: IDLE, LISTENING, CONFIRMING, WORKING, ERROR, DONE
- Deterministic transitions:
  - IDLE → LISTENING: user taps floating button or receives wake intent.
  - LISTENING → WORKING: after transcription posted to `/task/start` and Orchestrator responds with `confirmation_message`.
  - WORKING: receives status updates from Orchestrator for each step; deterministic mapping: Orchestrator sends `status_text` and `glow_state` which Agent 5 directly maps to overlay visuals.
  - WORKING → CONFIRMING: when Orchestrator sends action `need_user` or `confirmation_required`.
  - CONFIRMING → WORKING: on deterministic user confirmation (exact-match "yes" per deterministic grammar) or upon explicit `task.user_confirm=false` timeout → escalate to `ERROR` or `cancelled` depending on policy.
  - Any state → ERROR on explicit Orchestrator `error` or `blocked` result.
  - WORKING → DONE when Orchestrator signals task_complete.

Deterministic voice output templates (selected by `status_text` keys):
- start: "Got it. I will {intent_summary}."
- step_update: "{status_text}" (unvarnished, from Orchestrator)
- ask_confirm: "{confirmation_message} Say 'yes' to proceed or 'no' to cancel." (exact phrase)
- done: "Done: {final_status}."
- error: "Error: {reason}. Would you like me to retry? Say 'yes' or 'no'."

Deterministic speech rules:
- Only the exact words in the grammar are accepted for confirmation: yes, no, stop, cancel, repeat. The assistant normalizes transcript to lower-case and trims punctuation.
- If ASR output does not contain an exact grammar token for confirmation within a 4s listening timeout, treat as `no` and follow `no` deterministic path.
- For non-confirmation transcripts (new tasks), Agent 5 forwards the normalized transcription to Orchestrator; Orchestrator controls further flow.

Deterministic glow mapping (visual):
- LISTENING → Blue (#00CEFF), slow pulse
- WORKING → Purple (#6C5CE7), flowing animation
- DONE → Green (#00E676), brief flash then fade
- ERROR → Orange (#FF6D00), fast pulse

All UI animations include deterministic durations and easing curves for demo reproducibility. Agent 5 logs deterministic timestamps for each state transition into `action_history` and includes these in `/task/start` and `/agent/step` messages.

## Error handling and deterministic escalation

- On repeated failures, the Orchestrator triggers deterministic recovery steps in a fixed order: retry action → scroll → back → wait → need_vision → LLM Actor → ask user.
- Agent 5 will deterministically ask the user for help only on reaching the `ask_user` escalation. This will use the `ask_confirm` template and accept only deterministic grammar responses.

## Developer notes — implementation checklist

- Implement `multi_agent_flow.md` (this file).
- Add deterministic templates and grammar list to phone-side Agent 5 TTS/STT module.
- Ensure Eyes executor implements deterministic gesture vectors and scroll_state memory.
- Implement deterministic scoring functions for Actor with unit tests for tie-breaking.
- Add validation and JSON schema checks on Orchestrator for Planner outputs.

## Communication & Endpoint contracts (repeated succinctly)
- `POST /task/start` — transcription → returns task_id, plan, confirmation_message
- `POST /agent/step` — simplified single-call actor+verifier
- `POST /task/screen`, `/task/verify`, `/task/user-response`, `/task/cancel` (see above for schemas)

## Acceptance criteria for deterministic Agent 5

1. Agent 5 state machine implemented exactly as specified with the states and transitions above.
2. All spoken messages come from deterministic templates; no LLM-generated utterances at runtime.
3. Confirmation grammar limited to exact tokens {"yes","no","stop","cancel","repeat"}; unrecognized transcriptions within confirmation windows default to `no`.
4. Visual glow mapping matches the specified colors and deterministic timings.
5. Agent 5 logs deterministic timestamps for all state transitions to the `action_history` returned to Orchestrator.

## Next steps and follow-ups

- Implement deterministic templates and grammar in the phone app (Dev 5 work). Add unit tests for confirmation parsing.
- Implement unit tests for Actor scoring heuristics and Eyes normalization.
- Add JSON schema validation for Planner outputs in Orchestrator.
- Optional: Add pre-recorded vocal TTS assets for selected messages to reduce dependence on device TTS variability.

---

File authored from `claude.md` content. Agent 5 converted to a fully deterministic policy as requested.
