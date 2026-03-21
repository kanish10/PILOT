package com.pilot.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.IBinder
import android.util.Log
import android.view.Gravity
import android.view.WindowManager
import com.pilot.app.MainActivity
import com.pilot.app.agent.AgentLoopController
import com.pilot.app.agent.TaskStateManager
import com.pilot.app.model.GlowState
import com.pilot.app.overlay.FloatingButtonView
import com.pilot.app.overlay.GlowBorderView
import com.pilot.app.overlay.StatusBarView
import com.pilot.app.util.Constants
import com.pilot.app.voice.SpeechRecognizerHelper
import com.pilot.app.voice.TextToSpeechHelper

class OverlayService : Service() {

    companion object {
        private const val TAG = "OverlayService"
        var instance: OverlayService? = null
            private set

        fun start(context: Context) {
            val intent = Intent(context, OverlayService::class.java)
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            val intent = Intent(context, OverlayService::class.java)
            context.stopService(intent)
        }
    }

    private lateinit var windowManager: WindowManager
    private var glowBorder: GlowBorderView? = null
    private var fab: FloatingButtonView? = null
    private var statusBar: StatusBarView? = null

    lateinit var speechHelper: SpeechRecognizerHelper
        private set
    lateinit var ttsHelper: TextToSpeechHelper
        private set
    lateinit var agentLoop: AgentLoopController
        private set

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        TaskStateManager.setServiceRunning(true)
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager

        createNotificationChannel()
        startForeground(Constants.OVERLAY_NOTIFICATION_ID, buildNotification())

        speechHelper = SpeechRecognizerHelper(this)
        speechHelper.initialize()

        ttsHelper = TextToSpeechHelper(this)

        agentLoop = AgentLoopController(this)

        setupOverlays()
        setupVoiceCallbacks()

        Log.i(TAG, "Overlay service started")
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            Constants.NOTIFICATION_CHANNEL_ID,
            getString(com.pilot.app.R.string.notification_channel_name),
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = getString(com.pilot.app.R.string.notification_channel_description)
        }
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )
        return Notification.Builder(this, Constants.NOTIFICATION_CHANNEL_ID)
            .setContentTitle("PILOT Active")
            .setContentText("Tap to open settings")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun setupOverlays() {
        addGlowBorder()
        addStatusBar()
        addFab()
    }

    private fun addGlowBorder() {
        glowBorder = GlowBorderView(this)
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        )
        windowManager.addView(glowBorder, params)
    }

    private fun addStatusBar() {
        statusBar = StatusBarView(this)
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = statusBar!!.getMarginBottom()
        }
        windowManager.addView(statusBar, params)
    }

    private fun addFab() {
        fab = FloatingButtonView(this)
        val size = fab!!.getButtonSize()
        val params = WindowManager.LayoutParams(
            size, size,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = resources.displayMetrics.widthPixels - size - (16 * resources.displayMetrics.density).toInt()
            y = resources.displayMetrics.heightPixels / 2
        }
        fab!!.setWindowParams(params, windowManager)
        fab!!.onTapListener = { onFabTapped() }
        windowManager.addView(fab, params)
    }

    private fun setupVoiceCallbacks() {
        speechHelper.onResult = { transcription ->
            Log.d(TAG, "Voice result: $transcription")
            fab?.setListeningState(false)
            agentLoop.onVoiceResult(transcription)
        }

        speechHelper.onError = { errorCode ->
            Log.w(TAG, "Voice error: $errorCode")
            fab?.setListeningState(false)
            setGlowState(GlowState.ERROR)
            updateStatusText("Voice recognition failed. Tap to try again.")
        }

        speechHelper.onKeywordDetected = { keyword ->
            Log.d(TAG, "Keyword detected: $keyword")
            agentLoop.onKeyword(keyword)
        }
    }

    private fun onFabTapped() {
        if (speechHelper.isCurrentlyListening()) {
            speechHelper.stopListening()
            fab?.setListeningState(false)
            setGlowState(GlowState.IDLE)
        } else {
            fab?.setListeningState(true)
            setGlowState(GlowState.LISTENING)
            updateStatusText("Listening...")
            speechHelper.startListening(forKeywords = agentLoop.isTaskActive())
        }
    }

    // ── Public API for AgentLoopController ──────────────────────────

    fun setGlowState(state: GlowState) {
        glowBorder?.post { glowBorder?.setState(state) }
        TaskStateManager.updateGlow(state)
    }

    fun updateStatusText(text: String) {
        statusBar?.post { statusBar?.updateStatus(text) }
        TaskStateManager.updateStatus(text)
    }

    fun speak(text: String) {
        ttsHelper.speak(text)
    }

    fun startKeywordListening() {
        fab?.post {
            fab?.setListeningState(true)
            speechHelper.startListening(forKeywords = true)
        }
    }

    fun stopKeywordListening() {
        fab?.post {
            fab?.setListeningState(false)
            speechHelper.stopListening()
        }
    }

    override fun onDestroy() {
        agentLoop.cancel()
        speechHelper.destroy()
        ttsHelper.destroy()

        glowBorder?.let {
            it.cleanup()
            windowManager.removeView(it)
        }
        fab?.let {
            it.cleanup()
            windowManager.removeView(it)
        }
        statusBar?.let {
            windowManager.removeView(it)
        }

        instance = null
        TaskStateManager.setServiceRunning(false)
        super.onDestroy()
    }
}
