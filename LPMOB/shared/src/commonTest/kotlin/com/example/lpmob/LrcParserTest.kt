package com.example.lpmob

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class LrcParserTest {

    @Test
    fun testParseSynchronizedLyrics() {
        val lrcContent = """
            [ti:Test Song]
            [00:12.34]First line of lyrics
            [01:05.50]Second line of lyrics
        """.trimIndent()

        val result = LrcParser.parse(lrcContent)
        assertTrue(result.synchronized)
        assertEquals(2, result.lines.size)
        assertEquals(12340L, result.lines[0].timeMs)
        assertEquals("First line of lyrics", result.lines[0].text)
        assertEquals(65500L, result.lines[1].timeMs)
        assertEquals("Second line of lyrics", result.lines[1].text)
    }

    @Test
    fun testParsePlainLyrics() {
        val plainContent = """
            Line one without timestamps
            Line two without timestamps
        """.trimIndent()

        val result = LrcParser.parse(plainContent)
        assertTrue(!result.synchronized)
        assertEquals(2, result.lines.size)
        assertEquals(null, result.lines[0].timeMs)
        assertEquals("Line one without timestamps", result.lines[0].text)
    }
}
