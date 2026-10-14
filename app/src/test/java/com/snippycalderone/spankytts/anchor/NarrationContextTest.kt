package com.snippycalderone.spankytts.anchor

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NarrationContextTest {
    private fun book(vararg rawSections: String): BookIndex = BookIndex(
        "test.epub",
        rawSections.mapIndexed { index, raw ->
            SectionIndex("section$index", raw, TextNormalizer.normalizeForMatch(raw))
        }
    )

    @Test
    fun extractsOriginalTextWithoutCurrentFragment() {
        val index = book("He said, “And of course,” she continued calmly.")
        val normalized = index.sections[0].normalizedText
        val start = normalized.indexOf("and of course,")
        val context = NarrationContextExtractor(index).extract(
            TextMatch(0, "section0", start, start + "and of course,".length)
        )

        assertNotNull(context)
        assertEquals("He said, “", context!!.previous)
        assertEquals("” she continued calmly.", context.following)
        assertFalse(context.previous.contains("And of course,"))
        assertFalse(context.following.contains("And of course,"))
    }

    @Test
    fun mapsCollapsedWhitespaceAndSmartQuotes() {
        val index = book("Alpha   BETA\u00a0“Gamma”  delta.")
        val normalized = index.sections[0].normalizedText
        val start = normalized.indexOf("beta \"gamma\"")
        val context = NarrationContextExtractor(index).extract(
            TextMatch(0, "section0", start, start + "beta \"gamma\"".length)
        )

        assertNotNull(context)
        assertEquals("Alpha", context!!.previous)
        assertEquals("delta.", context.following)
    }

    @Test
    fun rejectsMismatchedSavedNormalization() {
        val index = BookIndex("test.epub", listOf(SectionIndex("section0", "Original text", "different text")))
        assertNull(NarrationContextExtractor(index).extract(TextMatch(0, "section0", 0, 9)))
    }

    @Test
    fun sectionEdgesHaveOnlyAvailableContext() {
        val index = book("Opening sentence. Closing sentence.")
        val normalized = index.sections[0].normalizedText
        val first = NarrationContextExtractor(index).extract(TextMatch(0, "section0", 0, "opening sentence.".length))!!
        val lastStart = normalized.indexOf("closing sentence.")
        val last = NarrationContextExtractor(index).extract(
            TextMatch(0, "section0", lastStart, normalized.length)
        )!!

        assertEquals("", first.previous)
        assertEquals("Closing sentence.", first.following)
        assertEquals("Opening sentence.", last.previous)
        assertEquals("", last.following)
    }

    @Test
    fun limitsContextAtWordBoundaries() {
        val prefix = "before ".repeat(60)
        val suffix = " after".repeat(60)
        val index = book(prefix + "CURRENT" + suffix)
        val start = index.sections[0].normalizedText.indexOf("current")
        val context = NarrationContextExtractor(index).extract(TextMatch(0, "section0", start, start + 7))!!

        assertTrue(context.previous.length <= NarrationContextExtractor.MAX_CONTEXT_CHARS)
        assertTrue(context.following.length <= NarrationContextExtractor.MAX_CONTEXT_CHARS)
        assertTrue(context.previous.startsWith("before"))
        assertTrue(context.following.endsWith("after"))
    }

    @Test
    fun historyAnchorReportsOnlyCurrentRequest() {
        val index = book("And of course, the old clock chimed.")
        val matcher = TextAnchorMatcher(index)
        assertNull(matcher.processIncomingText("And of course,").reliableCurrentMatch)

        val match = matcher.processIncomingText("the old clock chimed.").reliableCurrentMatch!!
        assertEquals(index.sections[0].normalizedText.indexOf("the old clock chimed."), match.start)
        assertEquals("the old clock chimed.".length, match.end - match.start)
    }

    @Test
    fun ambiguousShortRequestHasNoContextMatch() {
        val index = book("The ancient clock began to strike. yes and yes again.")
        val matcher = TextAnchorMatcher(index)
        assertNotNull(matcher.processIncomingText("The ancient clock began to strike.").reliableCurrentMatch)
        assertNull(matcher.processIncomingText("yes").reliableCurrentMatch)
    }

    @Test
    fun crossSectionCandidateWaitsForConfirmation() {
        val index = book(
            "The ancient clock began to strike. A quiet room followed.",
            "Across the valley a bright lantern appeared. Then the travelers stopped to listen."
        )
        val matcher = TextAnchorMatcher(index)
        assertNotNull(matcher.processIncomingText("The ancient clock began to strike.").reliableCurrentMatch)
        assertNull(matcher.processIncomingText("Across the valley a bright lantern appeared.").reliableCurrentMatch)
        val confirmed = matcher.processIncomingText("Then the travelers stopped to listen.")
        assertEquals(1, confirmed.reliableCurrentMatch?.sectionIndex)
    }
}
