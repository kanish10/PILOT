package com.pilot.app.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
enum class GlowState {
    @SerialName("idle") IDLE,
    @SerialName("listening") LISTENING,
    @SerialName("working") WORKING,
    @SerialName("done") DONE,
    @SerialName("error") ERROR
}
