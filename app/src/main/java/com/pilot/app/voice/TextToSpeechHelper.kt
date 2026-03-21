package com.pilot.app.voice

import android.content.Context
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import java.util.Locale
import java.util.UUID

class TextToSpeechHelper(context: Context) {

    companion object {
        private const val TAG = "TTSHelper"
    }

    var onSpeakDone: (() -> Unit)? = null
    var enabled: Boolean = true

    private var tts: TextToSpeech? = null
    private var ready = false

    init {
        tts = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val result = tts?.setLanguage(Locale.US)
                ready = result != TextToSpeech.LANG_MISSING_DATA &&
                        result != TextToSpeech.LANG_NOT_SUPPORTED
                if (ready) {
                    tts?.setSpeechRate(1.1f)
                    tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                        override fun onStart(utteranceId: String?) {}
                        override fun onDone(utteranceId: String?) {
                            onSpeakDone?.invoke()
                        }
                        @Deprecated("Deprecated in API")
                        override fun onError(utteranceId: String?) {}
                    })
                }
                Log.d(TAG, "TTS initialized, ready=$ready")
            } else {
                Log.e(TAG, "TTS init failed with status $status")
            }
        }
    }

    fun speak(text: String) {
        if (!enabled || !ready) return
        val utteranceId = UUID.randomUUID().toString()
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, utteranceId)
    }

    fun speakQueued(text: String) {
        if (!enabled || !ready) return
        val utteranceId = UUID.randomUUID().toString()
        tts?.speak(text, TextToSpeech.QUEUE_ADD, null, utteranceId)
    }

    fun stop() {
        tts?.stop()
    }

    fun destroy() {
        tts?.stop()
        tts?.shutdown()
        tts = null
        ready = false
    }
}
