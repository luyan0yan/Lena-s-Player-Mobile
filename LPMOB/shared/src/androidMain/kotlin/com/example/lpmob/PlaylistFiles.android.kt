package com.example.lpmob

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.platform.LocalContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

// ---------- Guardar a lista (um arquivo de texto na pasta interna do app) ----------

private class FilePlaylistStore(private val file: File) : PlaylistStore {

    // Formato: uma música por linha -> endereço <TAB> nome
    override suspend fun load(): List<Track> = withContext(Dispatchers.IO) {
        try {
            if (!file.exists()) {
                emptyList()
            } else {
                file.readLines().mapNotNull { line ->
                    val tab = line.indexOf('\t')
                    if (tab <= 0) null else Track(line.substring(0, tab), line.substring(tab + 1))
                }
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    override suspend fun save(tracks: List<Track>) {
        withContext(Dispatchers.IO) {
            try {
                val text = tracks.joinToString("\n") {
                    it.uri + "\t" + it.name.replace('\t', ' ').replace('\n', ' ')
                }
                // Escreve num arquivo temporário e troca no fim (não corrompe se o app fechar no meio)
                val temp = File(file.path + ".tmp")
                temp.writeText(text)
                temp.renameTo(file)
            } catch (e: Exception) {
                // Se não deu para salvar, o app continua funcionando; só não lembra da lista
            }
        }
    }
}

@Composable
actual fun rememberPlaylistStore(): PlaylistStore {
    val context = LocalContext.current.applicationContext
    return remember(context) { FilePlaylistStore(File(context.filesDir, "playlist.tsv")) }
}

// ---------- Escolher várias músicas ----------

@Composable
actual fun rememberMultiFilePicker(onPicked: (List<Track>) -> Unit): () -> Unit {
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenMultipleDocuments()
    ) { uris: List<Uri> ->
        val tracks = uris.map { uri ->
            keepAccess(context, uri)
            Track(uri.toString(), displayName(context, uri))
        }
        onPicked(tracks)
    }
    return { launcher.launch(arrayOf("audio/*")) }
}

// ---------- Escolher uma pasta ----------

@Composable
actual fun rememberFolderPicker(onPicked: (List<Track>) -> Unit): () -> Unit {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocumentTree()
    ) { treeUri: Uri? ->
        if (treeUri != null) {
            keepAccess(context, treeUri)
            scope.launch {
                val tracks = withContext(Dispatchers.IO) { scanFolder(context, treeUri) }
                onPicked(tracks)
            }
        }
    }
    return { launcher.launch(null) }
}

/** Pede ao Android para lembrar a permissão de leitura (senão ela some quando o app fecha). */
private fun keepAccess(context: Context, uri: Uri) {
    try {
        context.contentResolver.takePersistableUriPermission(
            uri, Intent.FLAG_GRANT_READ_URI_PERMISSION
        )
    } catch (e: Exception) {
    }
}

private val AUDIO_EXTENSIONS = setOf("mp3", "m4a", "aac", "flac", "ogg", "oga", "opus", "wav", "mka", "amr")

private fun isAudio(name: String, mime: String): Boolean =
    mime.startsWith("audio/") || name.substringAfterLast('.', "").lowercase() in AUDIO_EXTENSIONS

/** Lista as músicas da pasta e das subpastas (até 3 níveis), em ordem alfabética por pasta. */
private fun scanFolder(context: Context, treeUri: Uri): List<Track> {
    val result = mutableListOf<Track>()

    fun walk(folderId: String, depth: Int) {
        val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, folderId)
        val children = mutableListOf<Triple<String, String, String>>() // id, nome, tipo

        context.contentResolver.query(
            childrenUri,
            arrayOf(
                DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                DocumentsContract.Document.COLUMN_MIME_TYPE
            ),
            null, null, null
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                val id = cursor.getString(0) ?: continue
                val name = cursor.getString(1) ?: continue
                val mime = cursor.getString(2) ?: ""
                children += Triple(id, name, mime)
            }
        }

        for ((id, name, mime) in children.sortedBy { it.second.lowercase() }) {
            when {
                mime == DocumentsContract.Document.MIME_TYPE_DIR -> if (depth < 3) walk(id, depth + 1)
                isAudio(name, mime) -> result += Track(
                    DocumentsContract.buildDocumentUriUsingTree(treeUri, id).toString(),
                    name
                )
            }
        }
    }

    walk(DocumentsContract.getTreeDocumentId(treeUri), 0)
    return result
}
