package com.snippycalderone.spankytts.anchor

import android.net.Uri
import android.text.Html
import android.util.Log
import android.util.Xml
import org.xmlpull.v1.XmlPullParser
import java.io.File
import java.nio.charset.StandardCharsets
import java.util.Locale
import java.util.zip.ZipFile

object EpubTextIndexer {
    private const val TAG = "SpankyTTS"
    private const val CONTAINER_XML_PATH = "META-INF/container.xml"

    private val epubTextExtensions = setOf(".html", ".htm", ".xhtml")
    private val readableMediaTypes = setOf("application/xhtml+xml", "text/html")

    fun indexEpub(epubFile: File): BookIndex {
        require(epubFile.exists()) { "EPUB file does not exist: ${epubFile.absolutePath}" }

        ZipFile(epubFile).use { zip ->
            val spineResult = tryIndexFromSpine(zip)
            val sections = if (spineResult.sections.isNotEmpty()) {
                spineResult.sections
            } else {
                Log.w(TAG, "EPUB INDEX: spine unavailable, using fallback full-html scan")
                indexAllReadableEntries(zip)
            }

            val fallbackUsed = spineResult.sections.isEmpty()
            Log.i(TAG, "EPUB INDEX: package=${spineResult.packagePath ?: "<unknown>"}")
            Log.i(TAG, "EPUB INDEX: spine items=${spineResult.spineItemsCount}")
            Log.i(TAG, "EPUB INDEX: indexed spine sections=${spineResult.sections.size}")
            Log.i(TAG, "EPUB INDEX: fallback=$fallbackUsed")

            return BookIndex(
                sourceFilename = epubFile.name,
                sections = sections
            )
        }
    }

    private data class SpineIndexResult(
        val packagePath: String?,
        val spineItemsCount: Int,
        val sections: List<SectionIndex>
    )

    private data class ManifestItem(
        val id: String,
        val href: String,
        val mediaType: String,
        val properties: String
    )

    private data class PackageData(
        val manifest: Map<String, ManifestItem>,
        val spineIdRefs: List<String>
    )

    private fun tryIndexFromSpine(zip: ZipFile): SpineIndexResult {
        return try {
            val packagePath = parseContainerForPackagePath(zip)
            if (packagePath.isNullOrBlank()) {
                return SpineIndexResult(packagePath = null, spineItemsCount = 0, sections = emptyList())
            }

            val packageEntryName = resolveZipEntryName(zip, packagePath)
                ?: return SpineIndexResult(packagePath = packagePath, spineItemsCount = 0, sections = emptyList())

            val packageXml = readZipEntryText(zip, packageEntryName) ?: ""
            val packageData = parsePackageDocument(packageXml)
            if (packageData.spineIdRefs.isEmpty() || packageData.manifest.isEmpty()) {
                return SpineIndexResult(
                    packagePath = packageEntryName,
                    spineItemsCount = packageData.spineIdRefs.size,
                    sections = emptyList()
                )
            }

            val opfBaseDir = parentDir(packageEntryName)
            val sections = mutableListOf<SectionIndex>()
            for (idref in packageData.spineIdRefs) {
                val item = packageData.manifest[idref] ?: continue
                if (!isReadableSpineItem(item)) {
                    continue
                }

                val resolvedRelative = resolveRelativePath(opfBaseDir, item.href)
                val entryName = resolveZipEntryName(zip, resolvedRelative) ?: continue
                val rawText = readZipEntryText(zip, entryName) ?: continue
                val readable = extractReadableText(rawText)
                val normalized = TextNormalizer.normalizeForMatch(readable)
                if (normalized.isNotBlank()) {
                    sections.add(
                        SectionIndex(
                            entryName = entryName,
                            readableText = readable,
                            normalizedText = normalized
                        )
                    )
                }
            }

            SpineIndexResult(
                packagePath = packageEntryName,
                spineItemsCount = packageData.spineIdRefs.size,
                sections = sections
            )
        } catch (e: Exception) {
            Log.w(TAG, "EPUB INDEX: spine parse failed", e)
            SpineIndexResult(packagePath = null, spineItemsCount = 0, sections = emptyList())
        }
    }

    private fun indexAllReadableEntries(zip: ZipFile): List<SectionIndex> {
        val sections = mutableListOf<SectionIndex>()
        val entries = zip.entries()
        while (entries.hasMoreElements()) {
            val entry = entries.nextElement()
            if (entry.isDirectory) {
                continue
            }

            val lowerName = entry.name.lowercase(Locale.US)
            if (!epubTextExtensions.any { lowerName.endsWith(it) }) {
                continue
            }

            val rawText = readZipEntryText(zip, entry.name) ?: continue
            val readable = extractReadableText(rawText)
            val normalized = TextNormalizer.normalizeForMatch(readable)

            if (normalized.isNotBlank()) {
                sections.add(
                    SectionIndex(
                        entryName = entry.name,
                        readableText = readable,
                        normalizedText = normalized
                    )
                )
            }
        }
        return sections
    }

    private fun parseContainerForPackagePath(zip: ZipFile): String? {
        val containerName = resolveZipEntryName(zip, CONTAINER_XML_PATH) ?: return null
        val xml = readZipEntryText(zip, containerName) ?: return null
        return try {
            val parser = Xml.newPullParser()
            parser.setFeature("http://xmlpull.org/v1/doc/features.html#process-namespaces", true)
            parser.setInput(xml.reader())

            var eventType = parser.eventType
            while (eventType != XmlPullParser.END_DOCUMENT) {
                if (eventType == XmlPullParser.START_TAG && isTag(parser, "rootfile")) {
                    val fullPath = getAttr(parser, "full-path")
                    if (!fullPath.isNullOrBlank()) {
                        return normalizePath(fullPath)
                    }
                }
                eventType = parser.next()
            }
            null
        } catch (_: Exception) {
            null
        }
    }

    private fun parsePackageDocument(xml: String): PackageData {
        val manifest = mutableMapOf<String, ManifestItem>()
        val spineRefs = mutableListOf<String>()

        try {
            val parser = Xml.newPullParser()
            parser.setFeature("http://xmlpull.org/v1/doc/features.html#process-namespaces", true)
            parser.setInput(xml.reader())

            var eventType = parser.eventType
            while (eventType != XmlPullParser.END_DOCUMENT) {
                if (eventType == XmlPullParser.START_TAG) {
                    if (isTag(parser, "item")) {
                        val id = getAttr(parser, "id") ?: ""
                        val href = getAttr(parser, "href") ?: ""
                        val mediaType = getAttr(parser, "media-type") ?: ""
                        val properties = getAttr(parser, "properties") ?: ""
                        if (id.isNotBlank() && href.isNotBlank()) {
                            manifest[id] = ManifestItem(
                                id = id,
                                href = href,
                                mediaType = mediaType,
                                properties = properties
                            )
                        }
                    } else if (isTag(parser, "itemref")) {
                        val idRef = getAttr(parser, "idref")
                        if (!idRef.isNullOrBlank()) {
                            spineRefs.add(idRef)
                        }
                    }
                }
                eventType = parser.next()
            }
        } catch (_: Exception) {
            return PackageData(manifest = emptyMap(), spineIdRefs = emptyList())
        }

        return PackageData(manifest = manifest, spineIdRefs = spineRefs)
    }

    private fun isReadableSpineItem(item: ManifestItem): Boolean {
        val lowerMediaType = item.mediaType.lowercase(Locale.US)
        if (lowerMediaType in readableMediaTypes) {
            return true
        }
        val lowerHref = item.href.lowercase(Locale.US)
        return epubTextExtensions.any { lowerHref.endsWith(it) }
    }

    private fun readZipEntryText(zip: ZipFile, entryName: String): String? {
        val entry = zip.getEntry(entryName) ?: return null
        val bytes = zip.getInputStream(entry).use { it.readBytes() }
        return decodeBytes(bytes)
    }

    private fun resolveZipEntryName(zip: ZipFile, rawPath: String): String? {
        val candidates = linkedSetOf<String>()
        val normalized = normalizePath(stripQueryAndFragment(rawPath))
        if (normalized.isNotBlank()) {
            candidates.add(normalized)
            if (normalized.contains('%')) {
                val decoded = normalizePath(Uri.decode(normalized))
                if (decoded.isNotBlank()) {
                    candidates.add(decoded)
                }
            }
        }

        for (candidate in candidates) {
            val entry = zip.getEntry(candidate)
            if (entry != null) {
                return entry.name
            }
        }
        return null
    }

    private fun resolveRelativePath(baseDir: String, href: String): String {
        if (href.isBlank()) return ""
        val normalizedHref = normalizePath(stripQueryAndFragment(href))
        if (normalizedHref.contains(":/")) {
            return normalizedHref
        }
        val combined = if (baseDir.isBlank()) normalizedHref else "$baseDir/$normalizedHref"
        return normalizePath(combined)
    }

    private fun parentDir(path: String): String {
        val normalized = normalizePath(path)
        val idx = normalized.lastIndexOf('/')
        return if (idx <= 0) "" else normalized.substring(0, idx)
    }

    private fun normalizePath(path: String): String {
        val clean = path.replace('\\', '/').trim().removePrefix("/")
        if (clean.isBlank()) return ""

        val parts = clean.split('/').filter { it.isNotEmpty() }
        val stack = ArrayDeque<String>()
        for (part in parts) {
            when (part) {
                "." -> Unit
                ".." -> if (stack.isNotEmpty()) stack.removeLast()
                else -> stack.addLast(part)
            }
        }
        return stack.joinToString("/")
    }

    private fun stripQueryAndFragment(path: String): String {
        val fragmentStripped = path.substringBefore('#')
        return fragmentStripped.substringBefore('?')
    }

    private fun isTag(parser: XmlPullParser, localName: String): Boolean {
        val name = parser.name ?: return false
        return name == localName || name.endsWith(":$localName")
    }

    private fun getAttr(parser: XmlPullParser, localName: String): String? {
        parser.getAttributeValue(null, localName)?.let { return it }
        for (i in 0 until parser.attributeCount) {
            val attrName = parser.getAttributeName(i) ?: continue
            if (attrName == localName || attrName.endsWith(":$localName")) {
                return parser.getAttributeValue(i)
            }
        }
        return null
    }

    private fun decodeBytes(bytes: ByteArray): String {
        return try {
            String(bytes, StandardCharsets.UTF_8)
        } catch (_: Exception) {
            String(bytes)
        }
    }

    private fun extractReadableText(raw: String): String {
        val parserText = tryExtractWithXmlPullParser(raw)
        val cleaned = if (parserText.isNotBlank()) parserText else stripTags(raw)

        val decoded = Html.fromHtml(cleaned, Html.FROM_HTML_MODE_LEGACY).toString()
        return decoded.replace(Regex("\\s+"), " ").trim()
    }

    private fun tryExtractWithXmlPullParser(raw: String): String {
        return try {
            val parser = Xml.newPullParser()
            parser.setFeature("http://xmlpull.org/v1/doc/features.html#process-namespaces", false)
            parser.setInput(raw.reader())

            val builder = StringBuilder()
            var eventType = parser.eventType
            while (eventType != XmlPullParser.END_DOCUMENT) {
                if (eventType == XmlPullParser.TEXT || eventType == XmlPullParser.CDSECT) {
                    val text = parser.text
                    if (!text.isNullOrBlank()) {
                        builder.append(text).append(' ')
                    }
                }
                eventType = parser.next()
            }

            builder.toString().trim()
        } catch (_: Exception) {
            ""
        }
    }

    private fun stripTags(raw: String): String {
        return raw.replace(Regex("<[^>]+>"), " ")
    }
}
