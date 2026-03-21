package com.pilot.app.voice

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log

class SpeechRecognizerHelper(private val context: Context) {

    companion object {
        private const val TAG = "SpeechHelper"
        private val STOP_KEYWORDS = setOf("stop", "cancel", "abort", "quit")
        private val YES_KEYWORDS = setOf("yes", "yeah", "yep", "sure", "confirm", "okay", "ok", "go ahead")
        private val NO_KEYWORDS = setOf("no", "nah", "nope", "don't", "cancel")
    }

    var onResult: ((String) -> Unit)? = null
    var onPartialResult: ((String) -> Unit)? = null
    var onError: ((Int) -> Unit)? = null
    var onKeywordDetected: ((KeywordType) -> Unit)? = null

    private var recognizer: SpeechRecognizer? = null
    private var isListening = false
    private var keywordMode = false

    enum class KeywordType {
        STOP, YES, NO
    }

    fun initialize() {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            Log.e(TAG, "Speech recognition not available")
            return
        }
        recognizer = SpeechRecognizer.createSpeechRecognizer(context)
        recognizer?.setRecognitionListener(createListener())
    }

    fun startListening(forKeywords: Boolean = false) {
        if (isListening) return
        keywordMode = forKeywords

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }

        try {
            recognizer?.startListening(intent)
            isListening = true
            Log.d(TAG, "Started listening (keyword=$forKeywords)")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start listening", e)
        }
    }

    fun stopListening() {
        if (!isListening) return
        try {
            recognizer?.stopListening()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to stop listening", e)
        }
        isListening = false
    }

    fun isCurrentlyListening(): Boolean = isListening

    private fun createListener() = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            Log.d(TAG, "Ready for speech")
        }

        override fun onBeginningOfSpeech() {}

        override fun onRmsChanged(rmsdB: Float) {}

        override fun onBufferReceived(buffer: ByteArray?) {}

        override fun onEndOfSpeech() {
            isListening = false
        }

        override fun onError(error: Int) {
            isListening = false
            Log.w(TAG, "Recognition error: $error")
            onError?.invoke(error)
        }

        override fun onResults(results: Bundle?) {
            isListening = false
            val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            val text = matches?.firstOrNull() ?: return
            Log.d(TAG, "Result: $text")

            if (keywordMode) {
                detectKeyword(text)
            } else {
                onResult?.invoke(text)
            }
        }

        override fun onPartialResults(partialResults: Bundle?) {
            val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            val text = matches?.firstOrNull() ?: return

            if (keywordMode) {
                detectKeyword(text)
            } else {
                onPartialResult?.invoke(text)
            }
        }

        override fun onEvent(eventType: Int, params: Bundle?) {}
    }

    private fun detectKeyword(text: String) {
        val lower = text.lowercase().trim()
        when {
            STOP_KEYWORDS.any { lower.contains(it) } ->
                onKeywordDetected?.invoke(KeywordType.STOP)
            YES_KEYWORDS.any { lower.contains(it) } ->
                onKeywordDetected?.invoke(KeywordType.YES)
            NO_KEYWORDS.any { lower.contains(it) } ->
                onKeywordDetected?.invoke(KeywordType.NO)
            else -> onResult?.invoke(text)
        }
    }

    fun destroy() {
        stopListening()
        recognizer?.destroy()
        recognizer = null
    }
}
