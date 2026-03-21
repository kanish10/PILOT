package com.pilot.app.agent

import android.util.Log
import com.pilot.app.model.ActionPayload
import com.pilot.app.model.ActionRecord
import com.pilot.app.model.GlowState
import com.pilot.app.model.TaskState
import com.pilot.app.model.TaskStatus
import com.pilot.app.network.PilotApiClient
import com.pilot.app.service.OverlayService
import com.pilot.app.service.PilotAccessibilityService
import com.pilot.app.util.Constants
import com.pilot.app.voice.SpeechRecognizerHelper
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class AgentLoopController(private val service: OverlayService) {

    companion object {
        private const val TAG = "AgentLoop"
    }

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var loopJob: Job? = null

    private val _taskStatus = MutableStateFlow(TaskStatus.IDLE)
    val taskStatus: StateFlow<TaskStatus> = _taskStatus.asStateFlow()

    private val _statusText = MutableStateFlow("")
    val statusText: StateFlow<String> = _statusText.asStateFlow()

    private var _taskStateField = TaskState()
    private var taskState: TaskState
        get() = _taskStateField
        set(value) {
            _taskStateField = value
            _taskStatus.value = value.status
        }

    private val apiClient = PilotApiClient(
        com.pilot.app.BuildConfig.SERVER_URL
    )

    fun isTaskActive(): Boolean =
        taskState.status == TaskStatus.EXECUTING || taskState.status == TaskStatus.CONFIRMING

    fun updateServerUrl(url: String) {
        apiClient.updateBaseUrl(url)
    }

    private fun setStatusText(text: String) {
        _statusText.value = text
        service.updateStatusText(text)
    }

    fun onVoiceResult(transcription: String) {
        if (taskState.status == TaskStatus.CONFIRMING) {
            handleConfirmation(transcription)
        } else {
            startTask(transcription)
        }
    }

    fun onKeyword(keyword: SpeechRecognizerHelper.KeywordType) {
        when (keyword) {
            SpeechRecognizerHelper.KeywordType.STOP -> cancelCurrentTask()
            SpeechRecognizerHelper.KeywordType.YES -> {
                if (taskState.status == TaskStatus.CONFIRMING) {
                    handleConfirmation("yes")
                }
            }
            SpeechRecognizerHelper.KeywordType.NO -> {
                if (taskState.status == TaskStatus.CONFIRMING) {
                    handleConfirmation("no")
                }
            }
        }
    }

    private fun startTask(transcription: String) {
        loopJob?.cancel()
        loopJob = scope.launch {
            try {
                taskState = TaskState(
                    userIntent = transcription,
                    status = TaskStatus.PLANNING,
                    startTime = System.currentTimeMillis()
                )

                service.setGlowState(GlowState.WORKING)
                setStatusText("Planning your task...")
                service.speak("Got it, working on that for you.")

                val startResult = apiClient.startTask(transcription)
                startResult.onFailure { e ->
                    handleError("Failed to connect to server: ${e.message}")
                    return@launch
                }

                val response = startResult.getOrThrow()
                taskState = taskState.copy(
                    taskId = response.taskId,
                    plan = response.plan,
                    status = TaskStatus.EXECUTING,
                    currentStepIndex = 0
                )

                if (response.confirmationMessage.isNotBlank()) {
                    service.speak(response.confirmationMessage)
                }

                executeAgentLoop()

            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                handleError("Task failed: ${e.message}")
            }
        }
    }

    private suspend fun executeAgentLoop() {
        val plan = taskState.plan ?: return

        while (taskState.currentStepIndex < plan.plan.size) {
            val currentStep = plan.plan[taskState.currentStepIndex]
            Log.i(TAG, "Step ${currentStep.step}: ${currentStep.objective}")
            setStatusText(currentStep.objective + "...")

            var retries = 0
            var stepDone = false

            while (!stepDone && retries < Constants.MAX_RETRIES) {
                val a11y = PilotAccessibilityService.instance
                if (a11y == null) {
                    handleError("Accessibility service not running")
                    return
                }

                val screenState = a11y.readScreen()
                val needsVision = taskState.actionHistory.lastOrNull()?.action == "need_vision"
                val screenshotB64 = if (needsVision) a11y.captureScreenshotBase64() else null
                Log.d(
                    TAG,
                    "Sending screen package=${screenState.packageName} elements=${screenState.elements.size} screenshot=${screenshotB64 != null}"
                )

                val recentHistory = taskState.actionHistory.takeLast(10)
                val stepResult = apiClient.agentStep(
                    taskId = taskState.taskId,
                    userIntent = taskState.userIntent,
                    currentStep = currentStep.objective,
                    stepNeeds = currentStep.needs,
                    uiTree = screenState,
                    screenshotB64 = screenshotB64,
                    actionHistory = recentHistory
                )

                if (stepResult.isFailure) {
                    Log.e(TAG, "Agent step failed", stepResult.exceptionOrNull())
                    retries++
                    if (retries >= Constants.MAX_RETRIES) {
                        handleError("Lost connection to server")
                        return
                    }
                    delay(1000)
                    continue
                }

                val agentResponse = stepResult.getOrThrow()

                if (agentResponse.statusText.isNotBlank()) {
                    setStatusText(agentResponse.statusText)
                }

                val action = agentResponse.action
                val actionResult = executeAction(action, a11y)

                taskState.actionHistory.add(
                    ActionRecord(
                        action = actionName(action),
                        elementId = actionElementId(action),
                        value = actionValue(action),
                        packageName = actionPackage(action),
                        result = if (actionResult) "success" else "failed"
                    )
                )

                when (action) {
                    is ActionPayload.StepDone -> {
                        stepDone = true
                    }
                    is ActionPayload.NeedHelp -> {
                        taskState = taskState.copy(status = TaskStatus.CONFIRMING)
                        service.setGlowState(GlowState.LISTENING)
                        service.speak(action.question)
                        service.startKeywordListening()
                        return
                    }
                    is ActionPayload.NeedVision -> {
                        Log.d(TAG, "Vision fallback requested, retrying with screenshot")
                        retries++
                    }
                    else -> {
                        if (!actionResult) {
                            retries++
                            Log.w(TAG, "Action failed, retry $retries/${Constants.MAX_RETRIES}")
                        } else {
                            retries = 0
                        }
                        delay(Constants.ACTION_SETTLE_DELAY_MS)
                    }
                }

                if (agentResponse.stepComplete) {
                    stepDone = true
                }
                if (agentResponse.taskComplete) {
                    completeTask()
                    return
                }
            }

            if (!stepDone) {
                handleError("Step '${currentStep.objective}' failed after $retries retries")
                return
            }

            taskState = taskState.copy(currentStepIndex = taskState.currentStepIndex + 1)
        }

        completeTask()
    }

    private suspend fun executeAction(action: ActionPayload, a11y: PilotAccessibilityService): Boolean {
        return when (action) {
            is ActionPayload.Tap -> a11y.executeTap(action.elementId)
            is ActionPayload.Type -> a11y.executeType(action.elementId, action.value)
            is ActionPayload.ScrollDown -> a11y.executeScrollDown()
            is ActionPayload.ScrollUp -> a11y.executeScrollUp()
            is ActionPayload.ScrollLeft -> a11y.executeScrollLeft()
            is ActionPayload.ScrollRight -> a11y.executeScrollRight()
            is ActionPayload.Back -> a11y.executeBack()
            is ActionPayload.Home -> a11y.executeHome()
            is ActionPayload.OpenApp -> a11y.executeOpenApp(action.packageName)
            is ActionPayload.Wait -> {
                delay(action.seconds * 1000L)
                true
            }
            is ActionPayload.StepDone -> true
            is ActionPayload.NeedHelp -> true
            is ActionPayload.NeedVision -> true
        }
    }

    private fun handleConfirmation(response: String) {
        service.stopKeywordListening()
        taskState = taskState.copy(status = TaskStatus.EXECUTING)
        service.setGlowState(GlowState.WORKING)

        loopJob = scope.launch {
            val result = apiClient.sendUserResponse(taskState.taskId, response)
            result.onFailure {
                handleError("Failed to send response to server")
                return@launch
            }
            executeAgentLoop()
        }
    }

    private fun completeTask() {
        taskState = taskState.copy(status = TaskStatus.DONE)
        service.setGlowState(GlowState.DONE)
        service.speak("All done!")
        setStatusText("Task complete")

        scope.launch {
            delay(3000)
            resetState()
        }
    }

    private fun handleError(message: String) {
        Log.e(TAG, message)
        taskState = taskState.copy(status = TaskStatus.ERROR)
        service.setGlowState(GlowState.ERROR)
        setStatusText(message)
        service.speak("Something went wrong. $message")

        scope.launch {
            delay(5000)
            resetState()
        }
    }

    private fun resetState() {
        taskState = TaskState()
        service.setGlowState(GlowState.IDLE)
        setStatusText("")
    }

    fun cancelCurrentTask() {
        loopJob?.cancel()
        if (taskState.taskId.isNotBlank()) {
            scope.launch {
                apiClient.cancelTask(taskState.taskId)
            }
        }
        service.speak("Stopped.")
        resetState()
    }

    fun cancel() {
        loopJob?.cancel()
        apiClient.close()
    }

    private fun actionName(action: ActionPayload): String = when (action) {
        is ActionPayload.Tap -> "tap"
        is ActionPayload.Type -> "type"
        is ActionPayload.ScrollDown -> "scroll_down"
        is ActionPayload.ScrollUp -> "scroll_up"
        is ActionPayload.ScrollLeft -> "scroll_left"
        is ActionPayload.ScrollRight -> "scroll_right"
        is ActionPayload.Back -> "back"
        is ActionPayload.Home -> "home"
        is ActionPayload.OpenApp -> "open_app"
        is ActionPayload.Wait -> "wait"
        is ActionPayload.StepDone -> "step_done"
        is ActionPayload.NeedHelp -> "need_help"
        is ActionPayload.NeedVision -> "need_vision"
    }

    private fun actionElementId(action: ActionPayload): Int? = when (action) {
        is ActionPayload.Tap -> action.elementId
        is ActionPayload.Type -> action.elementId
        else -> null
    }

    private fun actionValue(action: ActionPayload): String? = when (action) {
        is ActionPayload.Type -> action.value
        else -> null
    }

    private fun actionPackage(action: ActionPayload): String? = when (action) {
        is ActionPayload.OpenApp -> action.packageName
        else -> null
    }
}
