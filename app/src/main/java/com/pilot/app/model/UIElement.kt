package com.pilot.app.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class UIElement(
    val id: Int,
    @SerialName("class") val className: String,
    val text: String? = null,
    val hint: String? = null,
    @SerialName("content_desc") val contentDesc: String? = null,
    @SerialName("resource_id") val resourceId: String? = null,
    val bounds: List<Int>,
    val clickable: Boolean = false,
    val editable: Boolean = false,
    val scrollable: Boolean = false,
    val checkable: Boolean = false,
    val checked: Boolean = false
)
