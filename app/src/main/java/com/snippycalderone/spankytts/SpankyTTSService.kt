package com.snippycalderone.spankytts

import com.snippycalderone.spankytts.anchor.AnchorStorage
import com.snippycalderone.spankytts.anchor.NarrationContext
import com.snippycalderone.spankytts.anchor.NarrationContextExtractor
import com.snippycalderone.spankytts.anchor.TextAnchorMatcher
import android.speech.tts.SynthesisCallback
import android.speech.tts.SynthesisRequest
import android.speech.tts.TextToSpeech
import android.speech.tts.TextToSpeechService
import android.util.Log
import android.media.AudioFormat
import okhttp3.Call
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.TimeUnit

class SpankyTTSService : TextToSpeechService() {
    // Log tag
    companion object {
        private const val TAG = "SpankyTTS"
        // TODO(Phase2B): temporary LAN development backend; replace with configurable HTTPS endpoint.
        private const val DEV_BACKEND_TTS_URL = "http://127.0.0.1:8000/tts"
        private const val REQUEST_VOICE = "cedar"
        private const val REQUEST_INSTRUCTIONS = "Read naturally as a professional audiobook narrator. Use natural pacing and expressive but restrained delivery."
        private const val EXPECTED_SAMPLE_RATE = 24000
        private const val EXPECTED_CHANNELS = 1
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
    }
    // New fields for request tracking and cancellation
    private val requestCounter = AtomicInteger(0)
    private val isCancelled = AtomicBoolean(false)
    private val matcherLock = Any()
    private val callLock = Any()

    private val httpClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(45, TimeUnit.SECONDS)
            .writeTimeout(15, TimeUnit.SECONDS)
            .build()
    }

    @Volatile
    private var currentTtsCall: Call? = null

    @Volatile
    private var cachedIndexPath: String? = null

    @Volatile
    private var anchorMatcher: TextAnchorMatcher? = null

    @Volatile
    private var contextExtractor: NarrationContextExtractor? = null

    @Volatile
    private var cachedAnchorResetVersion: Int = -1

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
        cancelCurrentCall()
        val seq = requestCounter.incrementAndGet()
        val timestamp = System.currentTimeMillis()
        val text = request.charSequenceText?.toString().orEmpty()
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

        var narrationContext: NarrationContext? = null
        try {
            synchronized(matcherLock) {
                val matcher = getAnchorMatcherOrNull()
                if (matcher == null) {
                    Log.i(TAG, "ANCHOR: no active EPUB index")
                } else {
                    val anchorResult = matcher.processIncomingText(text)
                    for (line in anchorResult.logs) {
                        Log.i(TAG, line)
                    }
                    narrationContext = anchorResult.reliableCurrentMatch?.let { contextExtractor?.extract(it) }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "ANCHOR: matcher failure", e)
        }
        Log.i(
            TAG,
            "NARRATION CONTEXT: previous=${narrationContext?.previous?.length ?: 0} following=${narrationContext?.following?.length ?: 0}"
        )

        if (isCancelled.get()) {
            Log.i(TAG, "BACKEND TTS: cancelled before request #$seq backend call")
            return
        }

        var activeCall: Call? = null
        try {
            val startMs = System.currentTimeMillis()
            Log.i(TAG, "BACKEND TTS: request chars=$charCount")
            Log.i(TAG, "BACKEND TTS: POST $DEV_BACKEND_TTS_URL")
            val requestJson = JSONObject()
                .put("text", text)
                .put("voice", REQUEST_VOICE)
                .put("instructions", REQUEST_INSTRUCTIONS)
            narrationContext?.let { context ->
                if (context.previous.isNotEmpty()) requestJson.put("previous_context", context.previous)
                if (context.following.isNotEmpty()) requestJson.put("following_context", context.following)
            }

            val httpRequest = Request.Builder()
                .url(DEV_BACKEND_TTS_URL)
                .post(requestJson.toString().toRequestBody(JSON_MEDIA_TYPE))
                .build()

            val call = httpClient.newCall(httpRequest)
            activeCall = call
            setCurrentCall(call)
            if (isCancelled.get()) {
                call.cancel()
                Log.i(TAG, "BACKEND TTS: cancelled before request #$seq backend call")
                return
            }

            val response = call.execute()

            response.use { httpResponse ->
                if (isCancelled.get()) {
                    Log.i(TAG, "BACKEND TTS: cancelled after response for request #$seq")
                    return
                }
                val elapsedMs = System.currentTimeMillis() - startMs
                Log.i(TAG, "BACKEND TTS: response status=${httpResponse.code}")
                Log.i(TAG, "BACKEND TTS: generation/network elapsed=${elapsedMs}ms")

                if (!httpResponse.isSuccessful) {
                    Log.e(TAG, "BACKEND TTS ERROR: non-200 response status=${httpResponse.code}")
                    callback.error(TextToSpeech.ERROR_NETWORK)
                    return
                }

                val contentType = httpResponse.body?.contentType()?.toString().orEmpty()
                if (!contentType.startsWith("application/octet-stream")) {
                    Log.e(TAG, "BACKEND TTS ERROR: unexpected content-type=$contentType")
                    callback.error(TextToSpeech.ERROR_SYNTHESIS)
                    return
                }

                val sampleRateHeader = httpResponse.header("X-Audio-Sample-Rate")?.toIntOrNull()
                val encodingHeader = httpResponse.header("X-Audio-Encoding")?.lowercase()
                val channelsHeader = httpResponse.header("X-Audio-Channels")?.toIntOrNull()
                if (sampleRateHeader != EXPECTED_SAMPLE_RATE || encodingHeader != "pcm_s16le" || channelsHeader != EXPECTED_CHANNELS) {
                    Log.e(
                        TAG,
                        "BACKEND TTS ERROR: unexpected audio headers sampleRate=$sampleRateHeader encoding=$encodingHeader channels=$channelsHeader"
                    )
                    callback.error(TextToSpeech.ERROR_SYNTHESIS)
                    return
                }

                val pcmBytes = httpResponse.body?.bytes()
                if (pcmBytes == null || pcmBytes.isEmpty()) {
                    Log.e(TAG, "BACKEND TTS ERROR: empty PCM response")
                    callback.error(TextToSpeech.ERROR_SYNTHESIS)
                    return
                }

                if (isCancelled.get()) {
                    Log.i(TAG, "BACKEND TTS: cancelled after response for request #$seq")
                    return
                }

                Log.i(TAG, "BACKEND TTS: PCM bytes=${pcmBytes.size}")

                val startResult = callback.start(
                    EXPECTED_SAMPLE_RATE,
                    AudioFormat.ENCODING_PCM_16BIT,
                    EXPECTED_CHANNELS
                )
                Log.i(TAG, "start returned $startResult")
                Log.i(TAG, "BACKEND TTS: callback started 24000Hz PCM16 mono")
                if (startResult == TextToSpeech.ERROR || startResult == TextToSpeech.STOPPED) {
                    Log.e(TAG, "BACKEND TTS ERROR: start failed: $startResult")
                    return
                }

                val maxBuffer = callback.maxBufferSize
                if (maxBuffer <= 0) {
                    Log.e(TAG, "BACKEND TTS ERROR: invalid callback maxBufferSize=$maxBuffer")
                    callback.error(TextToSpeech.ERROR_OUTPUT)
                    return
                }

                var offset = 0
                var chunkCount = 0
                while (offset < pcmBytes.size) {
                    if (isCancelled.get()) {
                        Log.i(TAG, "BACKEND TTS: cancelled during PCM delivery for request #$seq")
                        return
                    }
                    val chunkSize = minOf(maxBuffer, pcmBytes.size - offset)
                    val audioResult = callback.audioAvailable(pcmBytes, offset, chunkSize)
                    Log.i(TAG, "audioAvailable returned $audioResult")
                    if (audioResult == TextToSpeech.ERROR || audioResult == TextToSpeech.STOPPED) {
                        Log.e(TAG, "BACKEND TTS ERROR: audioAvailable failed: $audioResult")
                        return
                    }
                    offset += chunkSize
                    chunkCount += 1
                }

                Log.i(TAG, "BACKEND TTS: delivered PCM chunks=$chunkCount")

                if (isCancelled.get()) {
                    Log.i(TAG, "BACKEND TTS: cancelled after PCM delivery for request #$seq")
                    return
                }

                callback.done()
                Log.i(TAG, "done() called for request #$seq")
                Log.i(TAG, "BACKEND TTS: completed")
            }
        } catch (e: SocketTimeoutException) {
            if (isCancelled.get()) {
                Log.i(TAG, "BACKEND TTS: cancelled")
                return
            }
            Log.e(TAG, "BACKEND TTS ERROR: timeout", e)
            callback.error(TextToSpeech.ERROR_NETWORK_TIMEOUT)
        } catch (e: UnknownHostException) {
            if (isCancelled.get()) {
                Log.i(TAG, "BACKEND TTS: cancelled")
                return
            }
            Log.e(TAG, "BACKEND TTS ERROR: unknown host", e)
            callback.error(TextToSpeech.ERROR_NETWORK)
        } catch (e: ConnectException) {
            if (isCancelled.get()) {
                Log.i(TAG, "BACKEND TTS: cancelled")
                return
            }
            Log.e(TAG, "BACKEND TTS ERROR: connect failure", e)
            callback.error(TextToSpeech.ERROR_NETWORK)
        } catch (e: IOException) {
            if (isCancelled.get()) {
                Log.i(TAG, "BACKEND TTS: cancelled")
                return
            }
            Log.e(TAG, "BACKEND TTS ERROR: network I/O failure", e)
            callback.error(TextToSpeech.ERROR_NETWORK)
        } catch (e: Exception) {
            if (isCancelled.get()) {
                Log.i(TAG, "BACKEND TTS: cancelled")
                return
            }
            Log.e(TAG, "BACKEND TTS ERROR: synthesis failure", e)
            callback.error(TextToSpeech.ERROR_SYNTHESIS)
        } finally {
            activeCall?.let { clearCurrentCallIf(it) }
        }
    }


    override fun onStop() {
        Log.i(TAG, "onStop() called - cancellation requested on thread ${Thread.currentThread().name}")
        isCancelled.set(true)
        cancelCurrentCall()
    }

    private fun setCurrentCall(call: Call) {
        synchronized(callLock) {
            currentTtsCall?.cancel()
            currentTtsCall = call
        }
    }

    private fun clearCurrentCallIf(call: Call) {
        synchronized(callLock) {
            if (currentTtsCall === call) {
                currentTtsCall = null
            }
        }
    }

    private fun cancelCurrentCall() {
        synchronized(callLock) {
            currentTtsCall?.cancel()
            currentTtsCall = null
        }
    }

    private fun getAnchorMatcherOrNull(): TextAnchorMatcher? {
        val configuredPath = AnchorStorage.getActiveIndexPath(this)
        val resetVersion = AnchorStorage.getAnchorResetVersion(this)
        if (configuredPath.isNullOrBlank()) {
            synchronized(matcherLock) {
                cachedIndexPath = null
                anchorMatcher = null
                contextExtractor = null
                cachedAnchorResetVersion = resetVersion
            }
            return null
        }

        synchronized(matcherLock) {
            if (anchorMatcher != null && cachedAnchorResetVersion != resetVersion) {
                anchorMatcher?.clearAnchor()
                cachedAnchorResetVersion = resetVersion
                Log.i(TAG, "ANCHOR: state reset requested")
            }

            if (configuredPath == cachedIndexPath && anchorMatcher != null) {
                return anchorMatcher
            }

            val bookIndex = AnchorStorage.loadIndex(configuredPath)
            if (bookIndex == null) {
                cachedIndexPath = configuredPath
                anchorMatcher = null
                contextExtractor = null
                cachedAnchorResetVersion = resetVersion
                Log.w(TAG, "ANCHOR: failed to load index at $configuredPath")
                return null
            }

            val matcher = TextAnchorMatcher(bookIndex)
            cachedIndexPath = configuredPath
            anchorMatcher = matcher
            contextExtractor = NarrationContextExtractor(bookIndex)
            cachedAnchorResetVersion = resetVersion
            Log.i(TAG, "ANCHOR: loaded index source=${bookIndex.sourceFilename} sections=${bookIndex.sections.size}")
            return matcher
        }
    }
}
