package com.example.lpmob

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalInspectionMode
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer

private class AndroidAudioPlayer(context: Context) : AudioPlayer {
    override var onPlayingChanged: ((Boolean) -> Unit)? = null
    override var onError: ((String) -> Unit)? = null
    override var onEnded: (() -> Unit)? = null

    private val player = ExoPlayer.Builder(context)
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(C.USAGE_MEDIA)
                .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC)
                .build(),
            /* handleAudioFocus = */ true
        )
        .setHandleAudioBecomingNoisy(true) // pausa ao desconectar o fone
        .build()
        .also { exo ->
            exo.addListener(object : Player.Listener {
                override fun onIsPlayingChanged(isPlaying: Boolean) {
                    onPlayingChanged?.invoke(isPlaying)
                }

                override fun onPlayerError(error: PlaybackException) {
                    onError?.invoke(error.message ?: "erro desconhecido")
                }

                override fun onPlaybackStateChanged(playbackState: Int) {
                    if (playbackState == Player.STATE_ENDED) onEnded?.invoke()
                }
            })
        }

    override val positionMs: Long
        get() = player.currentPosition

    override val durationMs: Long
        get() = player.duration.let { if (it == C.TIME_UNSET) 0L else it }

    override fun load(uri: String) {
        player.setMediaItem(MediaItem.fromUri(uri))
        player.prepare()
        player.play()
    }

    override fun resume() {
        // Se a música já terminou, recomeça do início
        if (player.playbackState == Player.STATE_ENDED) player.seekTo(0)
        player.play()
    }

    override fun pause() = player.pause()

    override fun stop() {
        player.pause()
        player.seekTo(0)
    }

    override fun seekTo(ms: Long) = player.seekTo(ms)

    override fun setVolume(volume: Float) {
        player.volume = volume
    }

    override fun unload() {
        player.stop()
        player.clearMediaItems()
    }

    override fun release() = player.release()
}

/** Player "vazio" usado só na pré-visualização do Android Studio. */
private class NoopAudioPlayer : AudioPlayer {
    override var onPlayingChanged: ((Boolean) -> Unit)? = null
    override var onError: ((String) -> Unit)? = null
    override var onEnded: (() -> Unit)? = null
    override val positionMs: Long = 0L
    override val durationMs: Long = 0L
    override fun load(uri: String) {}
    override fun seekTo(ms: Long) {}
    override fun setVolume(volume: Float) {}
    override fun resume() {}
    override fun pause() {}
    override fun stop() {}
    override fun unload() {}
    override fun release() {}
}

@Composable
actual fun rememberAudioPlayer(): AudioPlayer {
    if (LocalInspectionMode.current) return remember { NoopAudioPlayer() }

    val context = LocalContext.current
    val player = remember { AndroidAudioPlayer(context.applicationContext) }
    DisposableEffect(player) {
        onDispose { player.release() }
    }
    return player
}

@Composable
actual fun rememberFilePicker(onPicked: (uri: String, name: String) -> Unit): () -> Unit {
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri: Uri? ->
        if (uri != null) {
            // Guarda a permissão de leitura (vai servir para playlists no futuro)
            try {
                context.contentResolver.takePersistableUriPermission(
                    uri, Intent.FLAG_GRANT_READ_URI_PERMISSION
                )
            } catch (_: Exception) {
            }
            onPicked(uri.toString(), displayName(context, uri))
        }
    }
    return { launcher.launch(arrayOf("audio/*")) }
}

internal fun displayName(context: Context, uri: Uri): String {
    val name = context.contentResolver
        .query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
        ?.use { cursor -> if (cursor.moveToFirst()) cursor.getString(0) else null }
    return name ?: uri.lastPathSegment ?: "Música"
}
