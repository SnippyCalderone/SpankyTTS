package com.snippycalderone.spankytts.anchor

data class BookIndex(
    val sourceFilename: String,
    val sections: List<SectionIndex>
)

data class SectionIndex(
    val entryName: String,
    val readableText: String,
    val normalizedText: String
)

data class TextMatch(
    val sectionIndex: Int,
    val sectionName: String,
    val start: Int,
    val end: Int
)

data class AnchorProcessResult(
    val logs: List<String>,
    val reliableCurrentMatch: TextMatch?
)

data class NarrationContext(
    val previous: String,
    val following: String
)
