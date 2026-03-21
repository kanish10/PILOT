package com.pilot.app.agent

import com.pilot.app.model.GlowState
import com.pilot.app.model.TaskState
import com.pilot.app.model.TaskStatus
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

object TaskStateManager {

    private val _taskState = MutableStateFlow(TaskState())
    val taskState: StateFlow<TaskState> = _taskState.asStateFlow()

    private val _glowState = MutableStateFlow(GlowState.IDLE)
    val glowState: StateFlow<GlowState> = _glowState.asStateFlow()

    private val _statusText = MutableStateFlow("")
    val statusText: StateFlow<String> = _statusText.asStateFlow()

    private val _isServiceRunning = MutableStateFlow(false)
    val isServiceRunning: StateFlow<Boolean> = _isServiceRunning.asStateFlow()

    fun updateTask(state: TaskState) {
        _taskState.value = state
    }

    fun updateGlow(state: GlowState) {
        _glowState.value = state
    }

    fun updateStatus(text: String) {
        _statusText.value = text
    }

    fun setServiceRunning(running: Boolean) {
        _isServiceRunning.value = running
    }

    fun isIdle(): Boolean = _taskState.value.status == TaskStatus.IDLE
}
