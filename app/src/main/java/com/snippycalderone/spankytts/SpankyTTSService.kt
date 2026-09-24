package com.snippycalderone.spankytts

import android.speech.tts.SynthesisCallback
import android.speech.tts.SynthesisRequest
import android.speech.tts.TextToSpeech
import android.speech.tts.TextToSpeechService
import android.util.Log
import android.media.AudioFormat
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicBoolean

class SpankyTTSService : TextToSpeechService() {
    // Log tag
    companion object {
        private const val TAG = "SpankyTTS"
    }
    // New fields for request tracking and cancellation
    private val requestCounter = AtomicInteger(0)
    private val isCancelled = AtomicBoolean(false)

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

    override fun onSynthesizeText(request: SynthesisRequest?, callback: SynthesisCallback?) {
        if (request == null || callback == null) return
        isCancelled.set(false)
        val seq = requestCounter.incrementAndGet()
        val timestamp = System.currentTimeMillis()
        val text = request.text.toString()
        val charCount = text.length
        val language = request.language ?: ""
        val country = request.country ?: ""
        val variant = request.variant ?: ""
        val rate = request.speechRate
        val pitch = request.pitch
        Log.i(TAG, "SynthesisRequest #$seq at $timestamp")
        Log.i(TAG, "Text ($charCount chars): $text")
        Log.i(TAG, "Locale: $language-$country-$variant, rate=$rate, pitch=$pitch")
        Log.i(TAG, "Thread: ${Thread.currentThread().name}")
        try {
            val sampleRate = 16000
            val audioFormat = AudioFormat.ENCODING_PCM_16BIT
            val channelCount = 1
            val startResult = callback.start(sampleRate, audioFormat, channelCount)
            Log.i(TAG, "start returned $startResult")
            if (startResult == TextToSpeech.ERROR || startResult == TextToSpeech.STOPPED) {
                Log.e(TAG, "start failed: $startResult")
                return
            }
            val maxBuffer = callback.maxBufferSize
            val maxSamples = maxBuffer / 2
            val samplesPerChunk = maxSamples
            val totalSamples = sampleRate
            var sampleIndex = 0
            val audioBuffer = ByteArray(maxSamples * 2)
            val byteBuffer = ByteBuffer.wrap(audioBuffer).order(ByteOrder.LITTLE_ENDIAN)
            val freq = 440.0  // test tone frequency
            while (sampleIndex < totalSamples) {
                if (isCancelled.get()) {
                    Log.i(TAG, "Cancellation detected during synthesis request #$seq")
                    return
                }
                val end = minOf(sampleIndex + samplesPerChunk, totalSamples)
                byteBuffer.clear()
                for (i in sampleIndex until end) {
                    val angle = 2.0 * Math.PI * freq * i / sampleRate
                    val sampleValue = (Short.MAX_VALUE * 0.3 * Math.sin(angle)).toInt().toShort()
                    byteBuffer.putShort(sampleValue)
                }
                val length = (end - sampleIndex) * 2
                val audioResult = callback.audioAvailable(audioBuffer, 0, length)
                Log.i(TAG, "audioAvailable returned $audioResult")
                if (audioResult == TextToSpeech.ERROR || audioResult == TextToSpeech.STOPPED) {
                    Log.e(TAG, "audioAvailable failed: $audioResult")
                    return
                }
                sampleIndex = end
            }

            if (isCancelled.get()) {
                Log.i(TAG, "Cancellation detected during synthesis request #$seq")
                return
            }

            callback.done()
            Log.i(TAG, "done() called for request #$seq")
        } catch (e: Exception) {
            Log.e(TAG, "Exception in synthesis", e)
            callback.error(TextToSpeech.ERROR_SYNTHESIS)
        }
    }


    override fun onStop() {
        Log.i(TAG, "onStop() called - cancellation requested on thread ${Thread.currentThread().name}")
        isCancelled.set(true)
    }
}