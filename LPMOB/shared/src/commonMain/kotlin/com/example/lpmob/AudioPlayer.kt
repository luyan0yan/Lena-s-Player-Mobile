package com.example.lpmob

import androidx.compose.runtime.Composable

/**
 * Contrato do player de áudio. A tela (App.kt) só conhece esta interface;
 * a implementação real de cada plataforma fica em androidMain.
 */
interface AudioPlayer {
    /** Chamado quando o player começa ou para de tocar (inclusive ao fim da música). */
    var onPlayingChanged: ((Boolean) -> Unit)?

    /** Chamado quando o arquivo não pôde ser tocado. */
    var onError: ((String) -> Unit)?

    /** Chamado quando a música chega ao fim. */
    var onEnded: (() -> Unit)?

    /** Posição atual e duração da música, em milissegundos (duração 0 = ainda desconhecida). */
    val positionMs: Long
    val durationMs: Long

    /** Carrega a música e já começa a tocar. */
    fun load(uri: String)

    fun resume()
    fun pause()

    /** Pausa e volta para o início (dá para tocar de novo com resume). */
    fun stop()

    fun seekTo(ms: Long)

    /** Volume do player, de 0f a 1f. */
    fun setVolume(volume: Float)

    /** Para e descarrega a música atual (a duração volta a 0). */
    fun unload()

    fun release()
}

@Composable
expect fun rememberAudioPlayer(): AudioPlayer

/**
 * Devolve uma função que abre o seletor de arquivos de áudio.
 * Quando o usuário escolhe um arquivo, chama onPicked(uri, nome).
 */
@Composable
expect fun rememberFilePicker(onPicked: (uri: String, name: String) -> Unit): () -> Unit
