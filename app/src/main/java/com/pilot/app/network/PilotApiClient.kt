package com.pilot.app.network

import android.util.Log
import com.pilot.app.model.ActionRecord
import com.pilot.app.model.ScreenState
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.logging.LogLevel
import io.ktor.client.plugins.logging.Logging
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

class PilotApiClient(private var baseUrl: String) {

    companion object {
        private const val TAG = "PilotApi"
        private const val TIMEOUT_MS = 30_000L
    }

    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        encodeDefaults = true
    }

    private val client = HttpClient(OkHttp) {
        install(ContentNegotiation) {
            json(this@PilotApiClient.json)
        }
        install(HttpTimeout) {
            requestTimeoutMillis = TIMEOUT_MS
            connectTimeoutMillis = 10_000L
            socketTimeoutMillis = TIMEOUT_MS
        }
        install(Logging) {
            level = LogLevel.BODY
        }
    }

    fun updateBaseUrl(url: String) {
        baseUrl = url.trimEnd('/')
    }

    suspend fun startTask(transcription: String): Result<TaskStartResponse> = runCatching {
        Log.d(TAG, "POST /task/start")
        client.post("$baseUrl/task/start") {
            contentType(ContentType.Application.Json)
            setBody(TaskStartRequest(transcription = transcription))
        }.body<TaskStartResponse>()
    }

    suspend fun agentStep(
        taskId: String,
        userIntent: String,
        currentStep: String,
        uiTree: ScreenState,
        screenshotB64: String? = null,
        actionHistory: List<ActionRecord> = emptyList()
    ): Result<AgentStepResponse> = runCatching {
        Log.d(TAG, "POST /agent/step")
        client.post("$baseUrl/agent/step") {
            contentType(ContentType.Application.Json)
            setBody(
                AgentStepRequest(
                    taskId = taskId,
                    userIntent = userIntent,
                    currentStep = currentStep,
                    uiTree = uiTree,
                    screenshotB64 = screenshotB64,
                    actionHistory = actionHistory
                )
            )
        }.body<AgentStepResponse>()
    }

    suspend fun verify(
        taskId: String,
        oldScreen: ScreenState,
        newScreen: ScreenState,
        actionPerformed: ActionRecord
    ): Result<VerifyResponse> = runCatching {
        Log.d(TAG, "POST /task/verify")
        client.post("$baseUrl/task/verify") {
            contentType(ContentType.Application.Json)
            setBody(
                VerifyRequest(
                    taskId = taskId,
                    oldScreen = oldScreen,
                    newScreen = newScreen,
                    actionPerformed = actionPerformed
                )
            )
        }.body<VerifyResponse>()
    }

    suspend fun sendUserResponse(taskId: String, response: String): Result<AgentStepResponse> = runCatching {
        Log.d(TAG, "POST /task/user-response")
        client.post("$baseUrl/task/user-response") {
            contentType(ContentType.Application.Json)
            setBody(UserResponseRequest(taskId = taskId, response = response))
        }.body<AgentStepResponse>()
    }

    suspend fun cancelTask(taskId: String): Result<StatusResponse> = runCatching {
        Log.d(TAG, "POST /task/cancel")
        client.post("$baseUrl/task/cancel") {
            contentType(ContentType.Application.Json)
            setBody(CancelRequest(taskId = taskId))
        }.body<StatusResponse>()
    }

    fun close() {
        client.close()
    }
}
