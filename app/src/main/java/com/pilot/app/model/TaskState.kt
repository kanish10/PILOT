package com.pilot.app.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
enum class TaskStatus {
    @SerialName("idle") IDLE,
    @SerialName("planning") PLANNING,
    @SerialName("executing") EXECUTING,
    @SerialName("confirming") CONFIRMING,
    @SerialName("done") DONE,
    @SerialName("error") ERROR
}

@Serializable
data class PlanStep(
    val step: Int,
    val app: String? = null,
    val objective: String,
    val needs: String? = null,
    var status: String = "pending"
)

@Serializable
data class TaskPlan(
    val plan: List<PlanStep>,
    @SerialName("info_extracted") val infoExtracted: Map<String, String> = emptyMap()
)

@Serializable
data class ActionRecord(
    val action: String,
    @SerialName("element_id") val elementId: Int? = null,
    val value: String? = null,
    @SerialName("package") val packageName: String? = null,
    val result: String? = null
)

data class TaskState(
    val taskId: String = "",
    val userIntent: String = "",
    val status: TaskStatus = TaskStatus.IDLE,
    val plan: TaskPlan? = null,
    val currentStepIndex: Int = 0,
    val actionHistory: MutableList<ActionRecord> = mutableListOf(),
    val errors: MutableList<String> = mutableListOf(),
    val totalActions: Int = 0,
    val startTime: Long = 0L,
    val glowState: GlowState = GlowState.IDLE,
    val statusText: String = ""
)
