package com.pilot.app.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonContentPolymorphicSerializer
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

@Serializable(with = ActionPayloadSerializer::class)
sealed class ActionPayload {
    abstract val status: String

    @Serializable @SerialName("tap")
    data class Tap(
        @SerialName("element_id") val elementId: Int,
        override val status: String = ""
    ) : ActionPayload()

    @Serializable @SerialName("type")
    data class Type(
        @SerialName("element_id") val elementId: Int,
        val value: String,
        override val status: String = ""
    ) : ActionPayload()

    @Serializable @SerialName("scroll_down")
    data class ScrollDown(
        override val status: String = ""
    ) : ActionPayload()

    @Serializable @SerialName("scroll_up")
    data class ScrollUp(
        override val status: String = ""
    ) : ActionPayload()

    @Serializable @SerialName("scroll_left")
    data class ScrollLeft(
        override val status: String = ""
    ) : ActionPayload()

    @Serializable @SerialName("scroll_right")
    data class ScrollRight(
        override val status: String = ""
    ) : ActionPayload()

    @Serializable @SerialName("back")
    data class Back(
        override val status: String = ""
    ) : ActionPayload()

    @Serializable @SerialName("home")
    data class Home(
        override val status: String = ""
    ) : ActionPayload()

    @Serializable @SerialName("open_app")
    data class OpenApp(
        @SerialName("package") val packageName: String,
        override val status: String = ""
    ) : ActionPayload()

    @Serializable @SerialName("wait")
    data class Wait(
        val seconds: Int = 2,
        override val status: String = ""
    ) : ActionPayload()

    @Serializable @SerialName("step_done")
    data class StepDone(
        override val status: String = ""
    ) : ActionPayload()

    @Serializable @SerialName("need_help")
    data class NeedHelp(
        val question: String,
        override val status: String = ""
    ) : ActionPayload()

    @Serializable @SerialName("need_vision")
    data class NeedVision(
        override val status: String = ""
    ) : ActionPayload()
}

object ActionPayloadSerializer : JsonContentPolymorphicSerializer<ActionPayload>(ActionPayload::class) {
    override fun selectDeserializer(element: JsonElement) = when (
        element.jsonObject["action"]?.jsonPrimitive?.content
    ) {
        "tap" -> ActionPayload.Tap.serializer()
        "type" -> ActionPayload.Type.serializer()
        "scroll_down" -> ActionPayload.ScrollDown.serializer()
        "scroll_up" -> ActionPayload.ScrollUp.serializer()
        "scroll_left" -> ActionPayload.ScrollLeft.serializer()
        "scroll_right" -> ActionPayload.ScrollRight.serializer()
        "back" -> ActionPayload.Back.serializer()
        "home" -> ActionPayload.Home.serializer()
        "open_app" -> ActionPayload.OpenApp.serializer()
        "wait" -> ActionPayload.Wait.serializer()
        "step_done" -> ActionPayload.StepDone.serializer()
        "need_help" -> ActionPayload.NeedHelp.serializer()
        "need_vision" -> ActionPayload.NeedVision.serializer()
        else -> throw IllegalArgumentException("Unknown action: ${element.jsonObject["action"]}")
    }
}
