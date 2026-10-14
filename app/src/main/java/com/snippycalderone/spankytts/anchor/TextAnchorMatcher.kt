package com.snippycalderone.spankytts.anchor

import kotlin.math.min

class TextAnchorMatcher(private val bookIndex: BookIndex) {
    private var anchored = false
    private var activeSectionIndex = -1
    private var lastMatchStart = -1
    private var lastMatchEnd = -1
    private var reliableCurrentMatch: TextMatch? = null

    private val rollingHistory = ArrayDeque<String>()
    private val maxHistorySize = 4
    private val localSearchWindow = 6000
    private val shortLocalSearchWindow = 400
    private val reanchorConfirmWindow = 400

    private data class PendingReanchor(
        val sectionIndex: Int,
        val sectionName: String,
        val start: Int,
        val end: Int
    )

    private data class PendingOutcome(
        val confirmed: Boolean,
        val rejected: Boolean,
        val logs: List<String>
    )

    private var pendingReanchor: PendingReanchor? = null

    fun clearAnchor() {
        anchored = false
        activeSectionIndex = -1
        lastMatchStart = -1
        lastMatchEnd = -1
        reliableCurrentMatch = null
        pendingReanchor = null
        rollingHistory.clear()
    }

    fun processIncomingText(rawInput: String): AnchorProcessResult {
        reliableCurrentMatch = null
        val normalizedInput = TextNormalizer.normalizeForMatch(rawInput)
        if (normalizedInput.isBlank()) {
            return AnchorProcessResult(
                logs = listOf(
                    "ANCHOR: ${if (anchored) "ANCHORED" else "UNANCHORED"}",
                    "ANCHOR INPUT: <empty after normalization>",
                    "ANCHOR STATUS: NOOP"
                ),
                reliableCurrentMatch = null
            )
        }

        addToHistory(normalizedInput)

        val logs = if (!anchored) {
            handleUnanchored(normalizedInput)
        } else {
            val pendingOutcome = tryConfirmPendingReanchor(normalizedInput)
            if (pendingOutcome.confirmed) {
                pendingOutcome.logs
            } else {
                val logs = mutableListOf<String>()
                logs.addAll(pendingOutcome.logs)
                logs.addAll(handleAnchored(normalizedInput))
                logs
            }
        }
        return AnchorProcessResult(logs, reliableCurrentMatch)
    }

    private fun handleUnanchored(normalizedInput: String): List<String> {
        val logs = mutableListOf<String>()
        logs.add("ANCHOR: UNANCHORED")
        logs.add("ANCHOR INPUT: \"${preview(normalizedInput)}\"")

        val candidates = buildCandidates()
        for (candidate in candidates) {
            if (candidate.length < minimumReliableLength(fromHistory = candidate != normalizedInput)) {
                continue
            }

            val matches = findAllMatches(candidate)
            if (matches.size == 1) {
                val match = matches[0]
                anchored = true
                activeSectionIndex = match.sectionIndex
                lastMatchStart = match.start
                lastMatchEnd = match.end
                // A history candidate can include earlier requests. Only the suffix
                // corresponding to this request is eligible for narration context.
                if (candidate.endsWith(normalizedInput)) {
                    markCurrentMatch(match.sectionIndex, match.end - normalizedInput.length, match.end)
                }
                logs.add("ANCHOR MATCH: section=${match.sectionName} start=${match.start} end=${match.end}")
                logs.add("ANCHOR STATUS: ESTABLISHED")
                return logs
            }

            if (matches.size > 1) {
                logs.add("ANCHOR AMBIGUOUS: matches=${matches.size}, retaining previous state")
                logs.add("ANCHOR STATUS: UNANCHORED")
                return logs
            }
        }

        logs.add("ANCHOR MISS: no reliable global match")
        logs.add("ANCHOR STATUS: UNANCHORED")
        return logs
    }

    private fun handleAnchored(normalizedInput: String): List<String> {
        val logs = mutableListOf<String>()
        logs.add("ANCHOR: ANCHORED")
        logs.add("ANCHOR INPUT: \"${preview(normalizedInput)}\"")

        val currentSection = bookIndex.sections.getOrNull(activeSectionIndex)
        if (currentSection != null) {
            val localStart = lastMatchEnd.coerceAtLeast(0)

            if (normalizedInput.length < minimumReliableLength(fromHistory = false)) {
                val shortMatches = findMatchesInRange(
                    haystack = currentSection.normalizedText,
                    needle = normalizedInput,
                    startIndex = localStart,
                    exclusiveLimit = min(localStart + shortLocalSearchWindow, currentSection.normalizedText.length)
                )

                return when {
                    shortMatches.size == 1 -> {
                        val foundStart = shortMatches[0]
                        val foundEnd = foundStart + normalizedInput.length
                        val delta = foundStart - localStart
                        lastMatchStart = foundStart
                        lastMatchEnd = foundEnd
                        markCurrentMatch(activeSectionIndex, foundStart, foundEnd)
                        logs.add(
                            "ANCHOR TRACK: expectedAfter=$localStart foundStart=$foundStart foundEnd=$foundEnd delta=$delta"
                        )
                        logs.add("ANCHOR STATUS: TRACKING")
                        logs
                    }
                    shortMatches.size > 1 -> {
                        logs.add("ANCHOR AMBIGUOUS: local short matches=${shortMatches.size}, retaining previous state")
                        logs.add("ANCHOR STATUS: TRACKING")
                        logs
                    }
                    else -> {
                        logs.add("ANCHOR MISS: short local search failed")
                        logs.add("ANCHOR STATUS: TRACKING")
                        logs
                    }
                }
            }

            val localLimit = min(localStart + localSearchWindow, currentSection.normalizedText.length)
            val localMatch = indexOfBounded(
                currentSection.normalizedText,
                normalizedInput,
                localStart,
                localLimit
            )
            if (localMatch >= 0) {
                val foundEnd = localMatch + normalizedInput.length
                val delta = localMatch - localStart
                lastMatchStart = localMatch
                lastMatchEnd = foundEnd
                if (findMatchesInRange(currentSection.normalizedText, normalizedInput, localStart, localLimit).size == 1) {
                    markCurrentMatch(activeSectionIndex, localMatch, foundEnd)
                }
                logs.add(
                    "ANCHOR TRACK: expectedAfter=$localStart foundStart=$localMatch foundEnd=$foundEnd delta=$delta"
                )
                logs.add("ANCHOR STATUS: TRACKING")
                return logs
            }

            val remainderMatch = currentSection.normalizedText.indexOf(normalizedInput, localStart)
            if (remainderMatch >= 0) {
                val foundEnd = remainderMatch + normalizedInput.length
                val delta = remainderMatch - localStart
                lastMatchStart = remainderMatch
                lastMatchEnd = foundEnd
                if (findMatchesInRange(currentSection.normalizedText, normalizedInput, localStart, currentSection.normalizedText.length).size == 1) {
                    markCurrentMatch(activeSectionIndex, remainderMatch, foundEnd)
                }
                logs.add(
                    "ANCHOR TRACK: expectedAfter=$localStart foundStart=$remainderMatch foundEnd=$foundEnd delta=$delta"
                )
                logs.add("ANCHOR STATUS: TRACKING")
                return logs
            }

            logs.add("ANCHOR MISS: local search failed")
        } else {
            logs.add("ANCHOR MISS: active section unavailable")
        }

        logs.add("ANCHOR RESEARCH: searching active EPUB")
        val globalMatches = findAllMatches(normalizedInput)
        when {
            globalMatches.size == 1 -> {
                val match = globalMatches[0]
                if (match.sectionIndex == activeSectionIndex) {
                    activeSectionIndex = match.sectionIndex
                    lastMatchStart = match.start
                    lastMatchEnd = match.end
                    anchored = true
                    pendingReanchor = null
                    markCurrentMatch(match.sectionIndex, match.start, match.end)
                    logs.add("ANCHOR MATCH: section=${match.sectionName} start=${match.start} end=${match.end}")
                    logs.add("ANCHOR STATUS: RE-ANCHORED")
                } else {
                    pendingReanchor = PendingReanchor(
                        sectionIndex = match.sectionIndex,
                        sectionName = match.sectionName,
                        start = match.start,
                        end = match.end
                    )
                    logs.add("ANCHOR REANCHOR CANDIDATE: section=${match.sectionName} start=${match.start} end=${match.end}")
                    logs.add("ANCHOR STATUS: REANCHOR-PENDING")
                }
            }
            globalMatches.size > 1 -> {
                pendingReanchor = null
                logs.add("ANCHOR AMBIGUOUS: matches=${globalMatches.size}, retaining previous state")
                logs.add("ANCHOR STATUS: TRACKING")
            }
            else -> {
                pendingReanchor = null
                logs.add("ANCHOR STATUS: TRACKING")
            }
        }
        return logs
    }

    private fun tryConfirmPendingReanchor(normalizedInput: String): PendingOutcome {
        val pending = pendingReanchor ?: return PendingOutcome(
            confirmed = false,
            rejected = false,
            logs = emptyList()
        )

        val section = bookIndex.sections.getOrNull(pending.sectionIndex)
        if (section == null) {
            pendingReanchor = null
            return PendingOutcome(
                confirmed = false,
                rejected = true,
                logs = listOf(
                    "ANCHOR REANCHOR REJECTED: candidate section unavailable",
                    "ANCHOR REANCHOR: active section unchanged=${activeSectionName()}"
                )
            )
        }

        val expectedAfter = pending.end.coerceAtLeast(0)
        val rangeEnd = min(expectedAfter + reanchorConfirmWindow, section.normalizedText.length)
        val matches = findMatchesInRange(
            haystack = section.normalizedText,
            needle = normalizedInput,
            startIndex = expectedAfter,
            exclusiveLimit = rangeEnd
        )

        return when {
            matches.size == 1 -> {
                val foundStart = matches[0]
                val foundEnd = foundStart + normalizedInput.length
                val delta = foundStart - expectedAfter
                activeSectionIndex = pending.sectionIndex
                lastMatchStart = foundStart
                lastMatchEnd = foundEnd
                anchored = true
                pendingReanchor = null
                markCurrentMatch(pending.sectionIndex, foundStart, foundEnd)
                PendingOutcome(
                    confirmed = true,
                    rejected = false,
                    logs = listOf(
                        "ANCHOR REANCHOR CONFIRMED: section=${pending.sectionName} candidateStart=${pending.start} candidateEnd=${pending.end} confirmedStart=$foundStart confirmedEnd=$foundEnd",
                        "ANCHOR TRACK: expectedAfter=$expectedAfter foundStart=$foundStart foundEnd=$foundEnd delta=$delta",
                        "ANCHOR STATUS: RE-ANCHORED"
                    )
                )
            }
            matches.size > 1 -> {
                pendingReanchor = null
                PendingOutcome(
                    confirmed = false,
                    rejected = true,
                    logs = listOf(
                        "ANCHOR REANCHOR REJECTED: local confirmation ambiguous matches=${matches.size}",
                        "ANCHOR REANCHOR: active section unchanged=${activeSectionName()}"
                    )
                )
            }
            else -> {
                pendingReanchor = null
                PendingOutcome(
                    confirmed = false,
                    rejected = true,
                    logs = listOf(
                        "ANCHOR REANCHOR REJECTED: no local continuation from candidate end=${pending.end}",
                        "ANCHOR REANCHOR: active section unchanged=${activeSectionName()}"
                    )
                )
            }
        }
    }

    private fun activeSectionName(): String {
        return bookIndex.sections.getOrNull(activeSectionIndex)?.entryName ?: "<unknown>"
    }

    private fun markCurrentMatch(sectionIndex: Int, start: Int, end: Int) {
        val section = bookIndex.sections.getOrNull(sectionIndex) ?: return
        reliableCurrentMatch = TextMatch(sectionIndex, section.entryName, start, end)
    }

    private fun addToHistory(normalizedInput: String) {
        rollingHistory.addLast(normalizedInput)
        while (rollingHistory.size > maxHistorySize) {
            rollingHistory.removeFirst()
        }
    }

    private fun buildCandidates(): List<String> {
        val entries = rollingHistory.toList()
        val candidates = mutableListOf<String>()

        for (size in minOf(3, entries.size) downTo 1) {
            val merged = entries.takeLast(size).joinToString(" ")
            candidates.add(merged)
        }

        return candidates.distinct()
    }

    private fun findAllMatches(normalizedNeedle: String): List<TextMatch> {
        val matches = mutableListOf<TextMatch>()
        for ((sectionIndex, section) in bookIndex.sections.withIndex()) {
            var searchStart = 0
            while (searchStart <= section.normalizedText.length - normalizedNeedle.length) {
                val found = section.normalizedText.indexOf(normalizedNeedle, searchStart)
                if (found < 0) {
                    break
                }
                matches.add(
                    TextMatch(
                        sectionIndex = sectionIndex,
                        sectionName = section.entryName,
                        start = found,
                        end = found + normalizedNeedle.length
                    )
                )
                searchStart = found + 1
            }
        }
        return matches
    }

    private fun indexOfBounded(
        haystack: String,
        needle: String,
        startIndex: Int,
        exclusiveLimit: Int
    ): Int {
        var searchFrom = startIndex
        while (searchFrom <= haystack.length - needle.length) {
            val found = haystack.indexOf(needle, searchFrom)
            if (found < 0) {
                return -1
            }
            if (found + needle.length <= exclusiveLimit) {
                return found
            }
            return -1
        }
        return -1
    }

    private fun findMatchesInRange(
        haystack: String,
        needle: String,
        startIndex: Int,
        exclusiveLimit: Int
    ): List<Int> {
        if (needle.isEmpty() || startIndex >= exclusiveLimit) {
            return emptyList()
        }

        val matches = mutableListOf<Int>()
        var searchFrom = startIndex
        while (searchFrom <= haystack.length - needle.length) {
            val found = haystack.indexOf(needle, searchFrom)
            if (found < 0) {
                break
            }
            if (found + needle.length > exclusiveLimit) {
                break
            }
            matches.add(found)
            searchFrom = found + 1
        }
        return matches
    }

    private fun minimumReliableLength(fromHistory: Boolean): Int {
        return if (fromHistory) {
            30
        } else {
            18
        }
    }

    private fun preview(text: String, maxLen: Int = 140): String {
        return if (text.length <= maxLen) text else text.substring(0, maxLen) + "..."
    }
}
