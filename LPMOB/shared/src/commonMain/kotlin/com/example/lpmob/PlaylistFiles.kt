package com.example.lpmob

import androidx.compose.runtime.Composable

/** Guarda e lê a lista de músicas entre uma abertura do app e outra. */
interface PlaylistStore {
    suspend fun load(): List<Track>
    suspend fun save(tracks: List<Track>)
}

@Composable
expect fun rememberPlaylistStore(): PlaylistStore

/** Abre o seletor para escolher várias músicas de uma vez. */
@Composable
expect fun rememberMultiFilePicker(onPicked: (List<Track>) -> Unit): () -> Unit

/** Abre o seletor de pasta e devolve todas as músicas dela (incluindo subpastas). */
@Composable
expect fun rememberFolderPicker(onPicked: (List<Track>) -> Unit): () -> Unit
