package com.pilot.app.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ScreenState(
    @SerialName("package") val packageName: String,
    val activity: String? = null,
    @SerialName("screen_title") val screenTitle: String? = null,
    val timestamp: Long,
    val elements: List<UIElement>,
    @SerialName("screenshot_b64") val screenshotB64: String? = null
)
