package com.snippycalderone.spankytts

import android.speech.tts.SynthesisCallback
import android.speech.tts.SynthesisRequest
import android.speech.tts.TextToSpeech
import android.speech.tts.TextToSpeechService

class SpankyTTSService : TextToSpeechService() {

    override fun onIsLanguageAvailable(
        lang: String?,
        country: String?,
        variant: String?
    ): Int {
        return TextToSpeech.LANG_AVAILABLE
    }

    override fun onLoadLanguage(
        lang: String?,
        country: String?,
        variant: String?
    ): Int {
        return TextToSpeech.LANG_AVAILABLE
    }

    override fun onGetLanguage(): Array<String> {
        return arrayOf("eng", "USA", "")
    }

    override fun onSynthesizeText(
        request: SynthesisRequest?,
        callback: SynthesisCallback?
    ) {
        // Phase 1 placeholder.
        // OpenAI TTS streaming will be implemented after the app builds cleanly.
    }

    override fun onStop() {
        // Phase 1 placeholder.
        // Cancellation handling will be added later.
    }
}