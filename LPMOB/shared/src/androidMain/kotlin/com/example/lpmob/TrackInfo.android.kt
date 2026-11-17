package com.example.lpmob

import android.content.Context
import android.graphics.BitmapFactory
import android.media.MediaMetadataRetriever
import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
actual fun rememberTrackInfoReader(): suspend (uri: String) -> TrackInfo {
    val context = LocalContext.current.applicationContext
    return remember(context) {
        val reader: suspend (String) -> TrackInfo = { uri -> readTrackInfo(context, uri) }
        reader
    }
}

private suspend fun readTrackInfo(context: Context, uri: String): TrackInfo =
    withContext(Dispatchers.IO) {
        val retriever = MediaMetadataRetriever()
        try {
            retriever.setDataSource(context, Uri.parse(uri))
            val title = retriever
                .extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE)
                ?.takeIf { it.isNotBlank() }
            val artist = retriever
                .extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST)
                ?.takeIf { it.isNotBlank() }
            val cover = retriever.embeddedPicture?.let { decodeCover(it) }
            TrackInfo(title, artist, cover)
        } catch (e: Exception) {
            // Arquivo sem tags ou formato que o Android não consegue ler: segue sem capa
            TrackInfo(null, null, null)
        } finally {
            retriever.release()
        }
    }

/** Decodifica a capa reduzindo imagens gigantes (economiza memória no celular). */
private fun decodeCover(bytes: ByteArray, maxSide: Int = 1024): ImageBitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
    var sample = 1
    while (bounds.outWidth / sample > maxSide || bounds.outHeight / sample > maxSide) {
        sample *= 2
    }
    val options = BitmapFactory.Options().apply { inSampleSize = sample }
    return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)?.asImageBitmap()
}
