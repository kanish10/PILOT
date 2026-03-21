package com.pilot.app.overlay

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Shader
import android.view.View
import android.view.animation.LinearInterpolator
import com.pilot.app.model.GlowState

class GlowBorderView(context: Context) : View(context) {

    companion object {
        private const val BORDER_WIDTH_DP = 10f
        private const val CORNER_RADIUS_DP = 24f

        private const val COLOR_BLUE = 0xFF00D9FF.toInt()
        private const val COLOR_PURPLE = 0xFF7C5CFC.toInt()
        private const val COLOR_GREEN = 0xFF00E5A0.toInt()
        private const val COLOR_ORANGE = 0xFFFF5A5A.toInt()

        private const val COLOR_BLUE_LIGHT = 0xFF6EE7FF.toInt()
        private const val COLOR_PURPLE_LIGHT = 0xFF9B82FF.toInt()
        private const val COLOR_GREEN_LIGHT = 0xFF5CFFC4.toInt()
        private const val COLOR_ORANGE_LIGHT = 0xFFFF8F8F.toInt()
    }

    private val density = context.resources.displayMetrics.density
    private val borderWidth = BORDER_WIDTH_DP * density
    private val cornerRadius = CORNER_RADIUS_DP * density

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = borderWidth
    }

    private val borderRect = RectF()
    private var glowState: GlowState = GlowState.IDLE
    private var animationProgress = 0f
    private var alphaValue = 1f

    private var rotationAnimator: ValueAnimator? = null
    private var pulseAnimator: ValueAnimator? = null
    private var fadeAnimator: ValueAnimator? = null

    fun setState(state: GlowState) {
        if (state == glowState) return
        glowState = state
        stopAllAnimators()

        when (state) {
            GlowState.IDLE -> {
                visibility = GONE
            }
            GlowState.LISTENING -> {
                visibility = VISIBLE
                alphaValue = 1f
                startPulseAnimation(duration = 2000L)
            }
            GlowState.WORKING -> {
                visibility = VISIBLE
                alphaValue = 1f
                startRotationAnimation()
            }
            GlowState.DONE -> {
                visibility = VISIBLE
                alphaValue = 1f
                startFadeAnimation()
            }
            GlowState.ERROR -> {
                visibility = VISIBLE
                alphaValue = 1f
                startPulseAnimation(duration = 600L)
            }
        }
        invalidate()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        val half = borderWidth / 2f
        borderRect.set(half, half, w - half, h - half)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (glowState == GlowState.IDLE) return

        val (primary, secondary) = getColors()
        paint.alpha = (alphaValue * 255).toInt()
        paint.shader = createGradient(primary, secondary)
        canvas.drawRoundRect(borderRect, cornerRadius, cornerRadius, paint)
    }

    private fun getColors(): Pair<Int, Int> = when (glowState) {
        GlowState.LISTENING -> COLOR_BLUE to COLOR_BLUE_LIGHT
        GlowState.WORKING -> COLOR_PURPLE to COLOR_PURPLE_LIGHT
        GlowState.DONE -> COLOR_GREEN to COLOR_GREEN_LIGHT
        GlowState.ERROR -> COLOR_ORANGE to COLOR_ORANGE_LIGHT
        GlowState.IDLE -> Color.TRANSPARENT to Color.TRANSPARENT
    }

    private fun createGradient(primary: Int, secondary: Int): Shader {
        val offset = animationProgress * (width + height) * 2
        return LinearGradient(
            offset, 0f,
            offset + width.toFloat(), height.toFloat(),
            intArrayOf(primary, secondary, primary, secondary),
            floatArrayOf(0f, 0.33f, 0.66f, 1f),
            Shader.TileMode.MIRROR
        )
    }

    private fun startRotationAnimation() {
        rotationAnimator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 3000L
            repeatCount = ValueAnimator.INFINITE
            interpolator = LinearInterpolator()
            addUpdateListener {
                animationProgress = it.animatedValue as Float
                invalidate()
            }
            start()
        }
    }

    private fun startPulseAnimation(duration: Long) {
        pulseAnimator = ValueAnimator.ofFloat(0.4f, 1f).apply {
            this.duration = duration
            repeatCount = ValueAnimator.INFINITE
            repeatMode = ValueAnimator.REVERSE
            addUpdateListener {
                alphaValue = it.animatedValue as Float
                invalidate()
            }
            start()
        }
    }

    private fun startFadeAnimation() {
        fadeAnimator = ValueAnimator.ofFloat(1f, 0f).apply {
            duration = 2000L
            startDelay = 500L
            addUpdateListener {
                alphaValue = it.animatedValue as Float
                invalidate()
            }
            start()
        }
    }

    private fun stopAllAnimators() {
        rotationAnimator?.cancel()
        pulseAnimator?.cancel()
        fadeAnimator?.cancel()
        rotationAnimator = null
        pulseAnimator = null
        fadeAnimator = null
        animationProgress = 0f
        alphaValue = 1f
    }

    fun cleanup() {
        stopAllAnimators()
    }
}
