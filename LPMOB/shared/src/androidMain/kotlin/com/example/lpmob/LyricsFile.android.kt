package com.example.lpmob

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import java.io.ByteArrayOutputStream
import java.io.InputStream

@Composable
actual fun rememberTextFilePicker(onPicked: (name: String, text: String) -> Unit): () -> Unit {
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) {
            val text = try {
                val bytes = context.contentResolver.openInputStream(uri)
                    ?.use { readLimited(it, 1_000_000) }
                if (bytes == null) {
                    ""
                } else {
                    val utf8 = bytes.toString(Charsets.UTF_8)
                    // .lrc antigos costumam estar em ANSI (acentos quebrados em UTF-8)
                    if ('\uFFFD' in utf8) bytes.toString(Charsets.ISO_8859_1) else utf8
                }
            } catch (e: Exception) {
                ""
            }
            onPicked(displayName(context, uri), text)
        }
    }
    // .lrc não tem tipo padrão no Android, por isso aceitamos qualquer arquivo
    return { launcher.launch(arrayOf("*/*")) }
}

/** Lê no máximo `max` bytes (protege contra o usuário escolher um arquivo gigante). */
private fun readLimited(stream: InputStream, max: Int): ByteArray {
    val out = ByteArrayOutputStream()
    val buffer = ByteArray(8192)
    while (out.size() < max) {
        val n = stream.read(buffer)
        if (n < 0) break
        out.write(buffer, 0, n)
    }
    return out.toByteArray()
}
