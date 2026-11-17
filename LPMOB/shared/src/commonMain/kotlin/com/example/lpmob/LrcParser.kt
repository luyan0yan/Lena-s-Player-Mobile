package com.example.lpmob

data class LrcLyricLine(
    val timeMs: Long?,
    val text: String
)

data class LyricsResult(
    val lines: List<LrcLyricLine>,
    val synchronized: Boolean
)

object LrcParser {
    private val timestampRegex = Regex("""\[(\d{1,3}):(\d{2})(?::(\d{2}))?(?:[.,:](\d{1,4}))?]""")
    private val bareTimestampRegex = Regex("""^\s*(\d{1,3}):(\d{2})(?::(\d{2}))?(?:[.,:](\d{1,4}))?(?=\s|[-–]|$)\s*[-–]?\s*""")
    private val offsetRegex = Regex("""\[offset:\s*([+-]?\d+)]""", RegexOption.IGNORE_CASE)
    private val atrasoRegex = Regex("""^\s*(?:\[offset_lplus:\s*([+-]?\d+)]|atraso:\s*["']?([+-]?\d+)\s*ms["']?)\s*$""", RegexOption.IGNORE_CASE)

    fun parse(text: String): LyricsResult {
        var offset = 0L
        val items = mutableListOf<Pair<Long, String>>()
        val plain = mutableListOf<String>()

        val lines = text.replace("\r", "").split("\n")
        for (raw in lines) {
            val line = raw.trim('\uFEFF', ' ', '\t')
            if (line.isEmpty()) continue

            // Check [offset:...]
            val offsetMatch = offsetRegex.find(line)
            if (offsetMatch != null) {
                offset = offsetMatch.groupValues[1].toLongOrNull() ?: 0L
                continue
            }

            // Skip metadata tags like [ar:...], [ti:...], etc.
            if (Regex("""^\[[A-Za-z#][^\]]*:[^\]]*]\s*$""").matches(line)) continue
            if (Regex("""^(?:language|idioma|atraso)\s*:""", RegexOption.IGNORE_CASE).matches(line)) continue

            var pos = 0
            val times = mutableListOf<Long>()
            while (true) {
                val match = timestampRegex.find(line, pos)
                if (match == null || match.range.first != pos) break
                val ms = convertToMs(match)
                times.add(ms)
                pos = match.range.last + 1
            }

            if (times.isEmpty()) {
                val bareMatch = bareTimestampRegex.find(line)
                if (bareMatch != null) {
                    val ms = convertToMs(bareMatch)
                    times.add(ms)
                    pos = bareMatch.range.last + 1
                }
            }

            val txt = line.substring(pos).replace(Regex("<[^>]*>"), "").trim()
            if (times.isNotEmpty()) {
                for (t in times) {
                    items.add(Pair(maxOf(0L, t + offset), txt))
                }
            } else {
                plain.add(txt)
            }
        }

        if (items.isNotEmpty()) {
            items.sortBy { it.first }
            return LyricsResult(
                lines = items.map { LrcLyricLine(it.first, it.second) },
                synchronized = true
            )
        }

        return LyricsResult(
            lines = plain.map { LrcLyricLine(null, it) },
            synchronized = false
        )
    }

    private fun convertToMs(match: MatchResult): Long {
        val groups = match.groupValues
        val a = groups[1].toLongOrNull() ?: 0L
        val b = groups[2].toLongOrNull() ?: 0L
        val c = groups[3].ifEmpty { null }?.toLongOrNull()
        val d = groups[4].ifEmpty { null }

        val ms = if (c == null) {
            (a * 60 + b) * 1000
        } else {
            (a * 3600 + b * 60 + c) * 1000
        }

        return if (d != null) {
            val paddedD = d.padEnd(3, '0').take(3).toLongOrNull() ?: 0L
            ms + paddedD
        } else {
            ms
        }
    }

    fun readAtraso(text: String): Long {
        var ultimoVal = 0L
        for (linha in text.split("\n")) {
            val m = atrasoRegex.find(linha)
            if (m != null) {
                ultimoVal = (m.groups[1]?.value ?: m.groups[2]?.value)?.toLongOrNull() ?: 0L
            }
        }
        return ultimoVal
    }
}
