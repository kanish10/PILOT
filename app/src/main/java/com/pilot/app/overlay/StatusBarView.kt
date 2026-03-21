package com.pilot.app.overlay

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.util.TypedValue
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.TextView

class StatusBarView(context: Context) : LinearLayout(context) {

    companion object {
        private const val BG_COLOR = 0xCC1A1A2E.toInt()
        private const val TEXT_COLOR = 0xFFFFFFFF.toInt()
        private const val PADDING_H_DP = 24
        private const val PADDING_V_DP = 12
        private const val CORNER_RADIUS_DP = 16f
        private const val TEXT_SIZE_SP = 14f
        private const val MARGIN_BOTTOM_DP = 32
    }

    private val density = context.resources.displayMetrics.density

    private val statusText = TextView(context).apply {
        text = ""
        setTextColor(TEXT_COLOR)
        setTextSize(TypedValue.COMPLEX_UNIT_SP, TEXT_SIZE_SP)
        typeface = Typeface.DEFAULT_BOLD
        gravity = Gravity.CENTER
        maxLines = 2
    }

    init {
        orientation = VERTICAL
        gravity = Gravity.CENTER

        val bg = GradientDrawable().apply {
            setColor(BG_COLOR)
            cornerRadius = CORNER_RADIUS_DP * density
        }
        background = bg

        val padH = (PADDING_H_DP * density).toInt()
        val padV = (PADDING_V_DP * density).toInt()
        setPadding(padH, padV, padH, padV)

        addView(statusText, LayoutParams(
            LayoutParams.WRAP_CONTENT,
            LayoutParams.WRAP_CONTENT
        ))

        visibility = GONE
    }

    fun updateStatus(text: String) {
        if (text.isBlank()) {
            visibility = GONE
        } else {
            visibility = VISIBLE
            statusText.text = text
        }
    }

    fun getMarginBottom(): Int = (MARGIN_BOTTOM_DP * density).toInt()
}
