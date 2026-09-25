package com.snippycalderone.spankytts

import android.content.Intent
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.util.Log
import android.widget.Button
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.snippycalderone.spankytts.anchor.AnchorStorage
import com.snippycalderone.spankytts.anchor.EpubTextIndexer
import kotlin.concurrent.thread

private const val TAG = "SpankyTTS"
private const val ENGINE_PACKAGE = "com.snippycalderone.spankytts"
private const val TEST_UTTERANCE_ID = "SPANKY_LONG_TEST_001"
private const val TEST_PARAGRAPH = "The old house stood at the edge of the field, quiet beneath a sky heavy with rain. For years, travelers had passed it without stopping, assuming it was abandoned. But every evening, just after sunset, a warm light appeared in the upstairs window. No one in the nearby village knew who lit it, and no one could remember seeing anyone enter or leave the house. Still, the light returned each night, steady and patient, as though someone inside were waiting for a visitor who had not yet arrived."

class MainActivity : AppCompatActivity() {
    private var tts: TextToSpeech? = null
    private lateinit var sendTestButton: Button
    private lateinit var stopTestButton: Button
    private lateinit var importEpubButton: Button
    private lateinit var clearAnchorButton: Button
    private lateinit var activeEpubValue: TextView
    private lateinit var indexStatusValue: TextView

    private val openDocumentLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode != RESULT_OK) {
            return@registerForActivityResult
        }

        val data = result.data ?: return@registerForActivityResult
        val uri = data.data ?: return@registerForActivityResult

        val flags = data.flags and
            (Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        try {
            contentResolver.takePersistableUriPermission(uri, flags)
            Log.i(TAG, "EPUB import: persisted URI permission")
        } catch (e: SecurityException) {
            Log.w(TAG, "EPUB import: persistable permission not granted", e)
        }

        indexStatusValue.text = "Indexing..."
        thread {
            try {
                val copiedEpub = AnchorStorage.importEpubToPrivateStorage(this, uri)
                val bookIndex = EpubTextIndexer.indexEpub(copiedEpub)
                val indexFile = AnchorStorage.saveIndex(this, copiedEpub.nameWithoutExtension, bookIndex)
                AnchorStorage.setActiveBook(
                    context = this,
                    epubName = copiedEpub.name,
                    epubPath = copiedEpub.absolutePath,
                    indexPath = indexFile.absolutePath
                )

                runOnUiThread {
                    activeEpubValue.text = copiedEpub.name
                    indexStatusValue.text = "Ready"
                }
                Log.i(
                    TAG,
                    "EPUB import complete: file=${copiedEpub.absolutePath}, sections=${bookIndex.sections.size}, index=${indexFile.absolutePath}"
                )
            } catch (e: Exception) {
                Log.e(TAG, "EPUB import failed", e)
                runOnUiThread {
                    indexStatusValue.text = "Import failed"
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        sendTestButton = findViewById(R.id.sendTestButton)
        stopTestButton = findViewById(R.id.stopTestButton)
        importEpubButton = findViewById(R.id.importEpubButton)
        clearAnchorButton = findViewById(R.id.clearAnchorButton)
        activeEpubValue = findViewById(R.id.activeEpubValue)
        indexStatusValue = findViewById(R.id.indexStatusValue)

        sendTestButton.isEnabled = false
        stopTestButton.isEnabled = false

        refreshAnchorStatus()

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

        importEpubButton.setOnClickListener {
            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "application/epub+zip"
                putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("application/epub+zip"))
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
            }
            openDocumentLauncher.launch(intent)
        }

        clearAnchorButton.setOnClickListener {
            AnchorStorage.clearAnchorStateOnly(this)
            refreshAnchorStatus()
            Log.i(TAG, "ANCHOR UI: reset requested")
        }
    }

    private fun refreshAnchorStatus() {
        val activeEpubName = AnchorStorage.getActiveEpubName(this)
        val indexPath = AnchorStorage.getActiveIndexPath(this)
        activeEpubValue.text = activeEpubName ?: "None"
        indexStatusValue.text = if (!indexPath.isNullOrBlank()) "Ready" else "Not ready"
    }

    override fun onDestroy() {
        super.onDestroy()
        tts?.shutdown()
        Log.i(TAG, "CLIENT TEST: TTS shutdown")
    }
}