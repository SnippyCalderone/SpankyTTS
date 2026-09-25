package com.snippycalderone.spankytts.anchor

object TextNormalizer {
    private val multiWhitespace = Regex("\\s+")

    fun normalizeForMatch(input: String): String {
        if (input.isEmpty()) return ""

        return input
            .replace('\u2018', '\'')
            .replace('\u2019', '\'')
            .replace('\u201C', '"')
            .replace('\u201D', '"')
            .replace('\u00A0', ' ')
            .replace('\r', ' ')
            .replace('\n', ' ')
            .replace('\t', ' ')
            .lowercase()
            .replace(multiWhitespace, " ")
            .trim()
    }
}
