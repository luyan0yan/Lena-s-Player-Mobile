package com.example.lpmob

/** Uma linha da letra. timeMs = -1 quando a letra não tem tempo (texto simples). */
class LyricLine(val timeMs: Long, val text: String)

class Lyrics(val lines: List<LyricLine>, val synced: Boolean)

// [mm:ss.xx]texto  (aceita vários tempos na mesma linha: [00:12.00][01:30.50]texto)
private val LINE_REGEX = Regex("""^\s*((?:\[\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?\])+)(.*)$""")
private val TIME_REGEX = Regex("""\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]""")
private val OFFSET_REGEX = Regex("""^\s*\[offset:\s*([+-]?\d+)\s*\]""", RegexOption.IGNORE_CASE)
private val METADATA_REGEX = Regex("""^\[[A-Za-z#]+:.*\]$""")        // [ar:...], [ti:...], [by:...]
private val WORD_TAG_REGEX = Regex("""<\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?>""") // <00:12.30> (LRC estendido)

fun parseLyrics(raw: String): Lyrics {
    val timed = mutableListOf<LyricLine>()
    val plain = mutableListOf<LyricLine>()
    var offsetMs = 0L

    for (rawLine in raw.removePrefix("\uFEFF").lines()) {
        val line = rawLine.trim()
        if (line.isEmpty()) continue

        val offsetMatch = OFFSET_REGEX.find(line)
        if (offsetMatch != null) {
            offsetMs = offsetMatch.groupValues[1].toLongOrNull() ?: 0L
            continue
        }

        val match = LINE_REGEX.matchEntire(line)
        if (match != null) {
            val text = match.groupValues[2].replace(WORD_TAG_REGEX, "").trim()
            for (t in TIME_REGEX.findAll(match.groupValues[1])) {
                timed += LyricLine(toMs(t), text)
            }
        } else if (!METADATA_REGEX.matches(line)) {
            plain += LyricLine(-1, line)
        }
    }

    if (timed.isNotEmpty()) {
        val lines = timed
            .map { LyricLine((it.timeMs - offsetMs).coerceAtLeast(0), it.text) }
            .sortedBy { it.timeMs }
        return Lyrics(lines, synced = true)
    }
    return Lyrics(plain, synced = false)
}

private fun toMs(m: MatchResult): Long {
    val min = m.groupValues[1].toLong()
    val sec = m.groupValues[2].toLong()
    val frac = m.groupValues[3]
    val ms = when (frac.length) {
        0 -> 0L
        1 -> frac.toLong() * 100
        2 -> frac.toLong() * 10
        else -> frac.take(3).toLong()
    }
    return min * 60_000 + sec * 1000 + ms
}
