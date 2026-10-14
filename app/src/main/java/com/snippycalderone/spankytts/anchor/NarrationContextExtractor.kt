package com.snippycalderone.spankytts.anchor

/** Extracts original EPUB text around a match whose offsets refer to normalized text. */
class NarrationContextExtractor(private val bookIndex: BookIndex) {
    companion object {
        const val MAX_CONTEXT_CHARS = 240
    }

    private data class OffsetMap(val starts: IntArray, val ends: IntArray)

    private val offsetMaps = mutableMapOf<Int, OffsetMap?>()
    private val whitespace = Regex("\\s")

    fun extract(match: TextMatch): NarrationContext? {
        val section = bookIndex.sections.getOrNull(match.sectionIndex) ?: return null
        if (section.entryName != match.sectionName || match.start < 0 ||
            match.end > section.normalizedText.length || match.start >= match.end
        ) return null

        val offsets = if (offsetMaps.containsKey(match.sectionIndex)) {
            offsetMaps[match.sectionIndex]
        } else {
            buildOffsetMap(section).also { offsetMaps[match.sectionIndex] = it }
        } ?: return null

        val rawStart = offsets.starts[match.start]
        val rawEnd = offsets.ends[match.end - 1]
        if (rawStart >= rawEnd) return null

        return NarrationContext(
            previous = previousWords(section.readableText, rawStart),
            following = followingWords(section.readableText, rawEnd)
        )
    }

    private fun buildOffsetMap(section: SectionIndex): OffsetMap? {
        val raw = section.readableText
        val normalized = StringBuilder()
        val starts = ArrayList<Int>(raw.length)
        val ends = ArrayList<Int>(raw.length)

        for (sourceIndex in raw.indices) {
            val replacement = when (raw[sourceIndex]) {
                '\u2018', '\u2019' -> '\''
                '\u201C', '\u201D' -> '"'
                '\u00A0', '\r', '\n', '\t' -> ' '
                else -> raw[sourceIndex]
            }
            for (character in replacement.toString().lowercase()) {
                if (whitespace.matches(character.toString())) {
                    if (normalized.isNotEmpty()) {
                        if (normalized.last() == ' ') {
                            ends[ends.lastIndex] = sourceIndex + 1
                        } else {
                            normalized.append(' ')
                            starts.add(sourceIndex)
                            ends.add(sourceIndex + 1)
                        }
                    }
                } else {
                    normalized.append(character)
                    starts.add(sourceIndex)
                    ends.add(sourceIndex + 1)
                }
            }
        }

        if (normalized.isNotEmpty() && normalized.last() == ' ') {
            normalized.deleteCharAt(normalized.lastIndex)
            starts.removeAt(starts.lastIndex)
            ends.removeAt(ends.lastIndex)
        }

        // Existing indexes were persisted before this map existed. Reject any mapping
        // that does not reproduce their normalized text exactly.
        if (normalized.toString() != section.normalizedText) return null
        return OffsetMap(starts.toIntArray(), ends.toIntArray())
    }

    private fun previousWords(raw: String, boundary: Int): String {
        var start = maxOf(0, boundary - MAX_CONTEXT_CHARS)
        if (start > 0 && start < boundary && !raw[start - 1].isWhitespace() && !raw[start].isWhitespace()) {
            while (start < boundary && !raw[start].isWhitespace()) start++
        }
        return raw.substring(start, boundary).trim()
    }

    private fun followingWords(raw: String, boundary: Int): String {
        var end = minOf(raw.length, boundary + MAX_CONTEXT_CHARS)
        if (end < raw.length && end > boundary && !raw[end - 1].isWhitespace() && !raw[end].isWhitespace()) {
            while (end > boundary && !raw[end - 1].isWhitespace()) end--
        }
        return raw.substring(boundary, end).trim()
    }
}
