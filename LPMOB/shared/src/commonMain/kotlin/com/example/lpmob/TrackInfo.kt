package com.example.lpmob

import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.ImageBitmap

/** Informações lidas de dentro do arquivo de música (qualquer campo pode ser nulo). */
class TrackInfo(
    val title: String?,
    val artist: String?,
    val cover: ImageBitmap?
)

/**
 * Devolve uma função que lê título, artista e capa embutida de uma música.
 * Roda em segundo plano, então pode ser chamada de dentro de uma coroutine.
 */
@Composable
expect fun rememberTrackInfoReader(): suspend (uri: String) -> TrackInfo
