package com.snippycalderone.spankytts.anchor

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

object AnchorStorage {
    private const val PREFS_NAME = "spanky_anchor"
    private const val KEY_ACTIVE_EPUB_NAME = "active_epub_name"
    private const val KEY_ACTIVE_EPUB_PATH = "active_epub_path"
    private const val KEY_ACTIVE_INDEX_PATH = "active_index_path"
    private const val KEY_ANCHOR_RESET_VERSION = "anchor_reset_version"

    private const val ANCHOR_DIR = "anchor"
    private const val EPUB_DIR = "epubs"
    private const val INDEX_DIR = "indexes"

    fun getActiveEpubName(context: Context): String? {
        return prefs(context).getString(KEY_ACTIVE_EPUB_NAME, null)
    }

    fun getActiveIndexPath(context: Context): String? {
        return prefs(context).getString(KEY_ACTIVE_INDEX_PATH, null)
    }

    fun getAnchorResetVersion(context: Context): Int {
        return prefs(context).getInt(KEY_ANCHOR_RESET_VERSION, 0)
    }

    fun setActiveBook(context: Context, epubName: String, epubPath: String, indexPath: String) {
        prefs(context)
            .edit()
            .putString(KEY_ACTIVE_EPUB_NAME, epubName)
            .putString(KEY_ACTIVE_EPUB_PATH, epubPath)
            .putString(KEY_ACTIVE_INDEX_PATH, indexPath)
            .apply()
    }

    fun saveIndex(context: Context, baseName: String, bookIndex: BookIndex): File {
        val indexDir = File(anchorRootDir(context), INDEX_DIR)
        if (!indexDir.exists()) {
            indexDir.mkdirs()
        }
        val safeName = sanitizeFilename(baseName)
        val indexFile = File(indexDir, "$safeName.index.json")
        val root = JSONObject()
        root.put("sourceFilename", bookIndex.sourceFilename)

        val sections = JSONArray()
        for (section in bookIndex.sections) {
            val sectionJson = JSONObject()
            sectionJson.put("entryName", section.entryName)
            sectionJson.put("readableText", section.readableText)
            sectionJson.put("normalizedText", section.normalizedText)
            sections.put(sectionJson)
        }
        root.put("sections", sections)

        indexFile.writeText(root.toString())
        return indexFile
    }

    fun loadIndex(indexPath: String): BookIndex? {
        val file = File(indexPath)
        if (!file.exists() || !file.isFile) {
            return null
        }

        return try {
            val root = JSONObject(file.readText())
            val sourceFilename = root.optString("sourceFilename", file.name)
            val sectionsArray = root.optJSONArray("sections") ?: JSONArray()
            val sections = mutableListOf<SectionIndex>()
            for (i in 0 until sectionsArray.length()) {
                val item = sectionsArray.optJSONObject(i) ?: continue
                sections.add(
                    SectionIndex(
                        entryName = item.optString("entryName"),
                        readableText = item.optString("readableText"),
                        normalizedText = item.optString("normalizedText")
                    )
                )
            }
            BookIndex(sourceFilename = sourceFilename, sections = sections)
        } catch (_: Exception) {
            null
        }
    }

    fun importEpubToPrivateStorage(context: Context, uri: Uri): File {
        val displayName = resolveDisplayName(context, uri) ?: "imported_book.epub"
        val safeName = sanitizeFilename(displayName)
        val targetDir = File(anchorRootDir(context), EPUB_DIR)
        if (!targetDir.exists()) {
            targetDir.mkdirs()
        }

        val targetFile = uniqueTargetFile(targetDir, safeName)
        val tempFile = File(targetDir, ".${targetFile.name}.${UUID.randomUUID()}.part")
        context.contentResolver.openInputStream(uri).use { input ->
            requireNotNull(input) { "Unable to open EPUB input stream" }
            tempFile.outputStream().use { output ->
                input.copyTo(output)
            }
        }

        if (!tempFile.renameTo(targetFile)) {
            tempFile.delete()
            throw IllegalStateException("Unable to finalize EPUB import to ${targetFile.absolutePath}")
        }

        return targetFile
    }

    fun clearAnchorStateOnly(context: Context) {
        val current = getAnchorResetVersion(context)
        prefs(context)
            .edit()
            .putInt(KEY_ANCHOR_RESET_VERSION, current + 1)
            .apply()
    }

    fun anchorRootDir(context: Context): File {
        val root = File(context.filesDir, ANCHOR_DIR)
        if (!root.exists()) {
            root.mkdirs()
        }
        return root
    }

    private fun resolveDisplayName(context: Context, uri: Uri): String? {
        context.contentResolver.query(uri, null, null, null, null).use { cursor ->
            if (cursor == null || !cursor.moveToFirst()) {
                return null
            }
            val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            return if (index >= 0) cursor.getString(index) else null
        }
    }

    private fun sanitizeFilename(input: String): String {
        val candidate = input
            .replace(Regex("[^a-zA-Z0-9._ -]"), "_")
            .trim()
            .ifBlank { "imported_book.epub" }
        return if (candidate.endsWith(".epub", ignoreCase = true)) candidate else "$candidate.epub"
    }

    private fun uniqueTargetFile(targetDir: File, safeName: String): File {
        val direct = File(targetDir, safeName)
        if (!direct.exists()) {
            return direct
        }

        val dot = safeName.lastIndexOf('.')
        val base = if (dot > 0) safeName.substring(0, dot) else safeName
        val ext = if (dot > 0) safeName.substring(dot) else ""
        var i = 2
        while (true) {
            val candidate = File(targetDir, "$base ($i)$ext")
            if (!candidate.exists()) {
                return candidate
            }
            i++
        }
    }

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
}
