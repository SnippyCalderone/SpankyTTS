package com.snippycalderone.spankytts

import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.util.Log
import android.widget.Button
import androidx.appcompat.app.AppCompatActivity

private const val TAG = "SpankyTTS"
private const val ENGINE_PACKAGE = "com.snippycalderone.spankytts"
private const val TEST_UTTERANCE_ID = "SPANKY_LONG_TEST_001"
private const val TEST_PARAGRAPH = "The old house stood at the edge of the field, quiet beneath a sky heavy with rain. For years, travelers had passed it without stopping, assuming it was abandoned. But every evening, just after sunset, a warm light appeared in the upstairs window. No one in the nearby village knew who lit it, and no one could remember seeing anyone enter or leave the house. Still, the light returned each night, steady and patient, as though someone inside were waiting for a visitor who had not yet arrived."

class MainActivity : AppCompatActivity() {
    private var tts: TextToSpeech? = null
    private lateinit var sendTestButton: Button
    private lateinit var stopTestButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        sendTestButton = findViewById(R.id.sendTestButton)
        stopTestButton = findViewById(R.id.stopTestButton)
        sendTestButton.isEnabled = false
        stopTestButton.isEnabled = false

        tts = TextToSpeech(this, { status ->
            if (status == TextToSpeech.SUCCESS) {
                Log.i(TAG, "CLIENT TEST INIT SUCCESS with engine $ENGINE_PACKAGE")
                sendTestButton.isEnabled = true
                stopTestButton.isEnabled = true
            } else {
                Log.e(TAG, "CLIENT TEST INIT FAILED: $status")
            }
        }, ENGINE_PACKAGE)

        sendTestButton.setOnClickListener {
            val charCount = TEST_PARAGRAPH.length
            Log.i(TAG, "CLIENT TEST BEGIN")
            Log.i(TAG, "Engine: $ENGINE_PACKAGE")
            Log.i(TAG, "Utterance ID: $TEST_UTTERANCE_ID")
            Log.i(TAG, "Characters sent: $charCount")
            Log.i(TAG, "Speak calls: 1")
            Log.i(TAG, "Text: $TEST_PARAGRAPH")
            val result = tts?.speak(
                TEST_PARAGRAPH,
                TextToSpeech.QUEUE_FLUSH,
                null,
                TEST_UTTERANCE_ID
            )
            Log.i(TAG, "CLIENT speak() returned: $result")
        }

        stopTestButton.setOnClickListener {
            tts?.stop()
            Log.i(TAG, "CLIENT TEST: stop() requested")
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        tts?.shutdown()
        Log.i(TAG, "CLIENT TEST: TTS shutdown")
    }
}