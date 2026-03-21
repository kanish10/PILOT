package com.pilot.app.network

import com.pilot.app.model.ActionPayload
import com.pilot.app.model.ActionRecord
import com.pilot.app.model.ScreenState
import com.pilot.app.model.TaskPlan
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// POST /task/start
@Serializable
data class TaskStartRequest(
    val transcription: String
)

@Serializable
data class TaskStartResponse(
    @SerialName("task_id") val taskId: String,
    val plan: TaskPlan,
    @SerialName("confirmation_message") val confirmationMessage: String
)

// POST /agent/step (simplified single endpoint)
@Serializable
data class AgentStepRequest(
    @SerialName("task_id") val taskId: String,
    @SerialName("user_intent") val userIntent: String,
    @SerialName("current_step") val currentStep: String,
    @SerialName("ui_tree") val uiTree: ScreenState,
    @SerialName("screenshot_b64") val screenshotB64: String? = null,
    @SerialName("action_history") val actionHistory: List<ActionRecord> = emptyList()
)

@Serializable
data class AgentStepResponse(
    val action: ActionPayload,
    @SerialName("status_text") val statusText: String = "",
    @SerialName("glow_state") val glowState: String = "working",
    @SerialName("step_complete") val stepComplete: Boolean = false,
    @SerialName("task_complete") val taskComplete: Boolean = false
)

// POST /task/verify
@Serializable
data class VerifyRequest(
    @SerialName("task_id") val taskId: String,
    @SerialName("old_screen") val oldScreen: ScreenState,
    @SerialName("new_screen") val newScreen: ScreenState,
    @SerialName("action_performed") val actionPerformed: ActionRecord
)

@Serializable
data class VerifyResponse(
    val result: String,
    val reason: String,
    val suggestion: String? = null,
    @SerialName("next_action") val nextAction: ActionPayload? = null
)

// POST /task/user-response
@Serializable
data class UserResponseRequest(
    @SerialName("task_id") val taskId: String,
    val response: String
)

// POST /task/cancel
@Serializable
data class CancelRequest(
    @SerialName("task_id") val taskId: String
)

@Serializable
data class StatusResponse(
    val status: String
)
