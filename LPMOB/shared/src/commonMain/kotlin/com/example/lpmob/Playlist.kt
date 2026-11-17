package com.example.lpmob

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** Uma música da lista: endereço do arquivo (uri) e nome para mostrar. */
class Track(val uri: String, val name: String)

/**
 * Lista de reprodução + ordem de tocar (normal ou aleatória) + modo de repetição.
 * Aqui só tem lógica; quem toca de fato é o AudioPlayer.
 */
class PlaylistState {
    var tracks by mutableStateOf<List<Track>>(emptyList())
        private set

    /** Índice da música atual em [tracks]; -1 = nenhuma. */
    var currentIndex by mutableStateOf(-1)
        private set

    var shuffle by mutableStateOf(false)
        private set

    /** "off", "all" (repete a lista) ou "one" (repete a música). */
    var repeat by mutableStateOf("off")
        private set

    // Ordem em que as músicas tocam (índices de [tracks]). Sem aleatório é 0, 1, 2...
    private var order: List<Int> = emptyList()

    /** Carrega a lista salva (sem escolher nenhuma música). */
    fun restore(saved: List<Track>) {
        tracks = saved
        currentIndex = -1
        buildOrder()
    }

    /**
     * Adiciona músicas ao fim da lista, ignorando as que já estão nela.
     * Devolve o índice da primeira música pedida (nova ou já existente), ou -1 se não veio nenhuma.
     */
    fun add(newTracks: List<Track>): Int {
        val indexByUri = mutableMapOf<String, Int>()
        tracks.forEachIndexed { i, t -> indexByUri[t.uri] = i }

        val merged = tracks.toMutableList()
        val addedIndexes = mutableListOf<Int>()
        var first = -1

        for (t in newTracks) {
            val existing = indexByUri[t.uri]
            if (existing != null) {
                if (first < 0) first = existing
            } else {
                merged += t
                val i = merged.size - 1
                indexByUri[t.uri] = i
                addedIndexes += i
                if (first < 0) first = i
            }
        }

        tracks = merged
        // No aleatório, as novas entram no fim da rodada atual (não bagunça o que já tocou)
        order = if (shuffle) order + addedIndexes.shuffled() else tracks.indices.toList()
        return first
    }

    /** Remove uma música. Devolve true se era a que estava tocando. */
    fun remove(index: Int): Boolean {
        if (index !in tracks.indices) return false
        val wasCurrent = index == currentIndex

        tracks = tracks.toMutableList().also { it.removeAt(index) }
        currentIndex = when {
            wasCurrent -> -1
            index < currentIndex -> currentIndex - 1
            else -> currentIndex
        }
        order = order
            .filter { it != index }
            .map { if (it > index) it - 1 else it }
        return wasCurrent
    }

    fun clear() {
        tracks = emptyList()
        currentIndex = -1
        order = emptyList()
    }

    /** O usuário escolheu uma música na mão: no aleatório, começa uma rodada nova a partir dela. */
    fun select(index: Int) {
        if (index !in tracks.indices) return
        currentIndex = index
        if (shuffle) buildOrder()
    }

    /** Vai para a próxima música. Devolve o índice dela, ou null se a lista acabou. */
    fun next(): Int? {
        if (tracks.isEmpty()) return null
        val pos = order.indexOf(currentIndex) // -1 se ainda não tem música atual
        val nextPos = pos + 1
        val target = when {
            nextPos < order.size -> order[nextPos]
            repeat == "all" -> {
                startNewRound()
                order.first()
            }
            else -> return null
        }
        currentIndex = target
        return target
    }

    /** Volta para a música anterior (ou recomeça a atual se não houver anterior). */
    fun previous(): Int? {
        if (tracks.isEmpty()) return null
        val pos = order.indexOf(currentIndex)
        val target = when {
            pos > 0 -> order[pos - 1]
            repeat == "all" && order.size > 1 -> order.last()
            currentIndex >= 0 -> currentIndex
            else -> return null
        }
        currentIndex = target
        return target
    }

    fun toggleShuffle() {
        shuffle = !shuffle
        buildOrder()
    }

    fun cycleRepeat() {
        repeat = when (repeat) {
            "off" -> "all"
            "all" -> "one"
            else -> "off"
        }
    }

    // Monta a ordem de tocar. No aleatório a música atual vem primeiro e as outras são sorteadas.
    private fun buildOrder() {
        val all = tracks.indices.toList()
        order = if (shuffle) {
            val rest = all.filter { it != currentIndex }.shuffled()
            if (currentIndex in all) listOf(currentIndex) + rest else rest
        } else {
            all
        }
    }

    // Ao dar a volta na lista com repetir "all": sorteia de novo, sem começar pela música que acabou
    private fun startNewRound() {
        if (!shuffle) return
        var newOrder = tracks.indices.toList().shuffled()
        if (newOrder.size > 1 && newOrder.first() == currentIndex) {
            newOrder = newOrder.drop(1) + newOrder.first()
        }
        order = newOrder
    }
}
