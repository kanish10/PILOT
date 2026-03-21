package com.pilot.app.overlay

import android.animation.ObjectAnimator
import android.animation.PropertyValuesHolder
import android.content.Context
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.MotionEvent
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.TextView

class FloatingButtonView(context: Context) : FrameLayout(context) {

    companion object {
        private const val BUTTON_SIZE_DP = 56
        private const val COLOR_PRIMARY = 0xFF7C5CFC.toInt()
        private const val COLOR_LISTENING = 0xFF00D9FF.toInt()
    }

    var onTapListener: (() -> Unit)? = null

    private val density = context.resources.displayMetrics.density
    private val buttonSizePx = (BUTTON_SIZE_DP * density).toInt()

    private var isListening = false
    private var pulseAnimator: ObjectAnimator? = null

    private var initialX = 0
    private var initialY = 0
    private var initialTouchX = 0f
    private var initialTouchY = 0f
    private var isDragging = false
    private var windowParams: WindowManager.LayoutParams? = null
    private var windowManager: WindowManager? = null

    private val background = GradientDrawable().apply {
        shape = GradientDrawable.OVAL
        setColor(COLOR_PRIMARY)
    }

    private val iconLabel = TextView(context).apply {
        text = "P"
        setTextColor(0xFFFFFFFF.toInt())
        textSize = 20f
        gravity = Gravity.CENTER
        typeface = android.graphics.Typeface.DEFAULT_BOLD
    }

    init {
        setBackground(background)
        elevation = 12f * density

        addView(iconLabel, LayoutParams(
            LayoutParams.MATCH_PARENT,
            LayoutParams.MATCH_PARENT
        ).apply { gravity = Gravity.CENTER })

        startIdlePulse()
    }

    fun setWindowParams(params: WindowManager.LayoutParams, wm: WindowManager) {
        windowParams = params
        windowManager = wm
    }

    fun setListeningState(listening: Boolean) {
        isListening = listening
        background.setColor(if (listening) COLOR_LISTENING else COLOR_PRIMARY)
        iconLabel.text = if (listening) "..." else "P"
        invalidate()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val params = windowParams ?: return super.onTouchEvent(event)
        val wm = windowManager ?: return super.onTouchEvent(event)

        when (event.action) {
            MotionEvent.ACTION_DOWN -> {
                initialX = params.x
                initialY = params.y
                initialTouchX = event.rawX
                initialTouchY = event.rawY
                isDragging = false
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val dx = event.rawX - initialTouchX
                val dy = event.rawY - initialTouchY
                if (dx * dx + dy * dy > 25 * density * density) {
                    isDragging = true
                }
                if (isDragging) {
                    params.x = initialX + dx.toInt()
                    params.y = initialY + dy.toInt()
                    wm.updateViewLayout(this, params)
                }
                return true
            }
            MotionEvent.ACTION_UP -> {
                if (!isDragging) {
                    onTapListener?.invoke()
                }
                return true
            }
        }
        return super.onTouchEvent(event)
    }

    private fun startIdlePulse() {
        val scaleX = PropertyValuesHolder.ofFloat(SCALE_X, 1f, 1.08f)
        val scaleY = PropertyValuesHolder.ofFloat(SCALE_Y, 1f, 1.08f)
        pulseAnimator = ObjectAnimator.ofPropertyValuesHolder(this, scaleX, scaleY).apply {
            duration = 1500
            repeatCount = ObjectAnimator.INFINITE
            repeatMode = ObjectAnimator.REVERSE
            start()
        }
    }

    fun getButtonSize(): Int = buttonSizePx

    fun cleanup() {
        pulseAnimator?.cancel()
        pulseAnimator = null
    }
}
