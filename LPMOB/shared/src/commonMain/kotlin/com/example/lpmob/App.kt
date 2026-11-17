
package com.example.lpmob

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.foundation.Image
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

// Cores originais do Lena's Player
private val BG = Color(0xFF121212)
private val BG2 = Color(0xFF1E1E1E)
private val FG = Color(0xFFEAEAEA)
private val ACC = Color(0xFF1DB954)
private val DIM = Color(0xFF6B6B6B)
private val TRACK = Color(0xFF2E2E2E)

@Composable
@Preview
fun App() {
    MaterialTheme {
        PlayerScreen()
    }
}

@Composable
private fun PlayerScreen() {
    var menuOpen by remember { mutableStateOf(true) }
    var showingList by remember { mutableStateOf(false) }
    var playing by remember { mutableStateOf(false) }
    val playlist = remember { PlaylistState() }
    val shuffle = playlist.shuffle
    val repeatMode = playlist.repeat
    var progress by remember { mutableStateOf(0f) }
    var volume by remember { mutableStateOf(0.8f) }
    var status by remember { mutableStateOf("") }
    var title by remember { mutableStateOf("Nada tocando") }
    var hasTrack by remember { mutableStateOf(false) }
    var positionMs by remember { mutableStateOf(0L) }
    var durationMs by remember { mutableStateOf(0L) }
    var dragging by remember { mutableStateOf(false) }
    var artist by remember { mutableStateOf("") }
    var cover by remember { mutableStateOf<ImageBitmap?>(null) }
    var infoJob by remember { mutableStateOf<Job?>(null) }
    var lyrics by remember { mutableStateOf<Lyrics?>(null) }
    var lyricsName by remember { mutableStateOf("") }
    var showingLyrics by remember { mutableStateOf(false) }

    // Player de áudio (a implementação real fica em androidMain)
    val player = rememberAudioPlayer()
    val scope = rememberCoroutineScope()
    val readTrackInfo = rememberTrackInfoReader()
    DisposableEffect(player) {
        player.onPlayingChanged = { playing = it }
        player.onError = { status = "Erro ao tocar: $it" }
        onDispose {
            player.onPlayingChanged = null
            player.onError = null
        }
    }

    // Volume inicial do player
    LaunchedEffect(player) { player.setVolume(volume) }

    // Atualiza a barra de progresso e os tempos 4x por segundo (exceto enquanto o dedo arrasta)
    LaunchedEffect(player) {
        while (true) {
            if (!dragging) {
                positionMs = player.positionMs
                durationMs = player.durationMs
                progress = if (durationMs > 0) {
                    (positionMs.toFloat() / durationMs).coerceIn(0f, 1f)
                } else 0f
            }
            delay(250)
        }
    }

    // ---------- PLAYLIST ----------

    // Carrega e toca a música de índice [index] da lista (quem chama já escolheu o índice em playlist)
    fun playTrack(index: Int) {
        val track = playlist.tracks.getOrNull(index) ?: return
        player.load(track.uri)
        title = track.name.substringBeforeLast('.')
        hasTrack = true
        status = ""
        artist = ""
        cover = null
        lyrics = null
        lyricsName = ""
        showingLyrics = false

        // Lê título, artista e capa de dentro do arquivo (se trocar de música rápido, cancela a leitura anterior)
        infoJob?.cancel()
        infoJob = scope.launch {
            val info = readTrackInfo(track.uri)
            info.title?.let { title = it }
            artist = info.artist ?: ""
            cover = info.cover
        }
    }

    // Volta o player para "Nada tocando"
    fun resetPlayback() {
        infoJob?.cancel()
        player.unload()
        hasTrack = false
        title = "Nada tocando"
        artist = ""
        cover = null
        lyrics = null
        lyricsName = ""
        showingLyrics = false
    }

    fun removeIndex(index: Int) {
        if (playlist.remove(index)) resetPlayback()
    }

    // Quando a música acaba: repete a mesma, vai para a próxima ou avisa que a lista acabou
    DisposableEffect(player) {
        player.onEnded = {
            if (playlist.repeat == "one") {
                playTrack(playlist.currentIndex)
            } else {
                val next = playlist.next()
                if (next != null) playTrack(next) else status = "Fim da lista."
            }
        }
        onDispose { player.onEnded = null }
    }

    // Lembra a lista entre uma abertura e outra do app
    val store = rememberPlaylistStore()
    var restored by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        playlist.restore(store.load())
        restored = true
    }
    LaunchedEffect(playlist.tracks, restored) {
        if (restored) store.save(playlist.tracks)
    }

    // Arquivo (menu): põe uma música na lista e toca
    val pickFile = rememberFilePicker { uri, name ->
        val index = playlist.add(listOf(Track(uri, name)))
        playlist.select(index)
        playTrack(index)
    }

    // ＋ Músicas: adiciona várias músicas à lista
    val pickMany = rememberMultiFilePicker { picked ->
        if (picked.isNotEmpty()) {
            val before = playlist.tracks.size
            val first = playlist.add(picked)
            status = "${playlist.tracks.size - before} música(s) adicionada(s)."
            if (!hasTrack && first >= 0) {
                playlist.select(first)
                playTrack(first)
            }
        }
    }

    // 📁 Pasta: adiciona todas as músicas de uma pasta
    val pickFolder = rememberFolderPicker { found ->
        if (found.isEmpty()) {
            status = "Não encontrei músicas nessa pasta."
        } else {
            val before = playlist.tracks.size
            val first = playlist.add(found)
            status = "${playlist.tracks.size - before} música(s) adicionada(s)."
            if (!hasTrack && first >= 0) {
                playlist.select(first)
                playTrack(first)
            }
        }
    }

    // Seletor da letra (.lrc com tempos ou .txt simples)
    val pickLyrics = rememberTextFilePicker { name, text ->
        val parsed = parseLyrics(text)
        if (parsed.lines.isEmpty()) {
            status = "Não encontrei letra nesse arquivo."
        } else {
            lyrics = parsed
            lyricsName = name
            showingLyrics = true
            showingList = false
            status = if (parsed.synced) "" else "Letra sem tempos (.txt): não acompanha a música."
        }
    }

    val lyr = lyrics
    // Índice da linha que está tocando agora (-1 = ainda não chegou na primeira)
    val currentLine = if (lyr != null && lyr.synced) {
        lyr.lines.indexOfLast { it.timeMs <= positionMs }
    } else -1

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BG)
            .windowInsetsPadding(WindowInsets.safeDrawing)
    ) {

        // BARRA SUPERIOR
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(48.dp)
                .background(BG2)
                .padding(horizontal = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "☰",
                color = if (menuOpen) ACC else FG,
                fontSize = 25.sp,
                modifier = Modifier
                    .clickable { menuOpen = !menuOpen }
                    .padding(horizontal = 8.dp)
            )

            Text(
                text = "Lena's Player",
                color = ACC,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center,
                modifier = Modifier.weight(1f)
            )

            Text(
                text = if (showingList) "‹ Player" else "🎵 Lista",
                color = if (showingList) ACC else FG,
                fontSize = 12.sp,
                modifier = Modifier
                    .clickable {
                        showingList = !showingList
                        status = ""
                    }
                    .padding(8.dp)
            )
        }

        // MENU EXPANSÍVEL
        if (menuOpen) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(BG)
            ) {
                Row(Modifier.fillMaxWidth()) {
                    MenuButton("Arquivo", Modifier.weight(1f)) {
                        pickFile()
                    }
                    MenuButton("Playlists", Modifier.weight(1f)) {
                        status = "Playlists — em desenvolvimento"
                    }
                    MenuButton("Letras", Modifier.weight(1f)) {
                        pickLyrics()
                    }
                }

                Row(Modifier.fillMaxWidth()) {
                    MenuButton("Plugins", Modifier.weight(1f)) {
                        status = "Plugins — em desenvolvimento"
                    }
                    MenuButton("Configurações", Modifier.weight(2f)) {
                        status = "Configurações — em desenvolvimento"
                    }
                }
            }
        }

        // ÁREA CENTRAL
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .defaultMinSize(minHeight = 120.dp)
                .background(Color(0xFF0B0B0B)),
            contentAlignment = Alignment.Center
        ) {
            if (showingList) {
                Column(
                    modifier = Modifier.fillMaxSize(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Top
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(5.dp),
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        MenuButton("＋ Músicas", Modifier.weight(1f)) {
                            pickMany()
                        }
                        MenuButton("📁 Pasta", Modifier.weight(1f)) {
                            pickFolder()
                        }
                        MenuButton("🗑 Limpar", Modifier.weight(1f)) {
                            playlist.clear()
                            resetPlayback()
                            status = "Lista limpa."
                        }
                    }

                    if (playlist.tracks.isEmpty()) {
                        Spacer(Modifier.height(20.dp))

                        Text(
                            "Nenhuma música na lista",
                            color = DIM,
                            fontSize = 13.sp
                        )
                    } else {
                        TrackList(
                            tracks = playlist.tracks,
                            currentIndex = playlist.currentIndex,
                            onPlay = { index ->
                                playlist.select(index)
                                playTrack(index)
                            },
                            onRemove = { removeIndex(it) },
                            modifier = Modifier
                                .fillMaxWidth()
                                .weight(1f)
                        )
                    }
                }
            } else if (showingLyrics && lyr != null) {
                LyricsView(
                    lyrics = lyr,
                    currentIndex = currentLine,
                    onSeek = { player.seekTo(it) }
                )
            } else {
                val art = cover
                if (art != null) {
                    Image(
                        bitmap = art,
                        contentDescription = "Capa do álbum",
                        contentScale = ContentScale.Fit,
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(8.dp)
                    )
                } else {
                    Text(
                        text = "♫",
                        color = FG,
                        fontSize = 23.sp
                    )
                }
            }
        }

        // PAINEL INFERIOR
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(BG)
                .padding(horizontal = 10.dp)
        ) {

            // Estado do Lyrics+
            Text(
                text = if (lyr == null) {
                    "Lyrics+: nenhuma"
                } else {
                    "Lyrics+: $lyricsName — toque aqui para ver ${if (showingLyrics) "a capa" else "a letra"}"
                },
                color = if (lyr == null) DIM else ACC,
                fontSize = 10.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(enabled = lyr != null) {
                        showingLyrics = !showingLyrics
                        showingList = false
                    }
                    .padding(vertical = 5.dp)
            )

            // Mensagens do player
            Text(
                text = status,
                color = ACC,
                fontSize = 10.sp,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 2.dp)
            )

            // LINHA DO TEMPO
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 5.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    formatTime(positionMs),
                    color = FG,
                    fontSize = 10.sp,
                    modifier = Modifier.width(44.dp)
                )

                Slider(
                    value = progress,
                    onValueChange = {
                        dragging = true
                        progress = it
                        positionMs = (it * durationMs).toLong()
                    },
                    onValueChangeFinished = {
                        if (durationMs > 0) player.seekTo((progress * durationMs).toLong())
                        dragging = false
                    },
                    modifier = Modifier
                        .weight(1f)
                        .height(35.dp),
                    colors = SliderDefaults.colors(
                        thumbColor = ACC,
                        activeTrackColor = ACC,
                        inactiveTrackColor = TRACK
                    )
                )

                Text(
                    formatTime(durationMs),
                    color = FG,
                    fontSize = 10.sp,
                    textAlign = TextAlign.End,
                    modifier = Modifier.width(44.dp)
                )
            }

            // NOME DA MÚSICA
            Text(
                text = if (artist.isNotBlank()) "$artist — $title" else title,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                color = FG,
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 3.dp)
            )

            // CONTROLES PRINCIPAIS
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                ControlButton("⏮", Modifier.weight(1f)) {
                    if (playlist.tracks.isEmpty()) {
                        status = "A lista está vazia."
                    } else if (hasTrack && positionMs > 3000) {
                        player.seekTo(0) // depois de 3 segundos, voltar recomeça a música
                    } else {
                        playlist.previous()?.let { playTrack(it) }
                    }
                }

                ControlButton(
                    if (playing) "Ⅱ" else "▶",
                    Modifier.weight(1f)
                ) {
                    if (!hasTrack) {
                        if (playlist.tracks.isEmpty()) {
                            status = "Escolha uma música em Arquivo."
                        } else {
                            playlist.next()?.let { playTrack(it) }
                        }
                    } else if (playing) {
                        player.pause()
                    } else {
                        player.resume()
                    }
                }

                ControlButton("■", Modifier.weight(1f)) {
                    player.stop()
                    progress = 0f
                    status = "Reprodução parada."
                }

                ControlButton("⏭", Modifier.weight(1f)) {
                    val next = playlist.next()
                    if (next != null) {
                        playTrack(next)
                    } else {
                        status = if (playlist.tracks.isEmpty()) "A lista está vazia." else "Fim da lista."
                    }
                }
            }

            // ALEATÓRIO, REPETIÇÃO E VOLUME
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 5.dp, bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "🔀",
                    fontSize = 16.sp,
                    color = if (shuffle) ACC else FG,
                    modifier = Modifier
                        .clickable { playlist.toggleShuffle() }
                        .padding(horizontal = 5.dp)
                )

                Text(
                    "▣ $repeatMode",
                    color = if (repeatMode != "off") ACC else FG,
                    fontSize = 10.sp,
                    modifier = Modifier
                        .clickable { playlist.cycleRepeat() }
                        .padding(horizontal = 5.dp)
                )

                Spacer(Modifier.weight(1f))

                Text(
                    "🔊",
                    fontSize = 15.sp
                )

                Slider(
                    value = volume,
                    onValueChange = {
                        volume = it
                        player.setVolume(it)
                    },
                    modifier = Modifier
                        .weight(1f)
                        .height(35.dp),
                    colors = SliderDefaults.colors(
                        thumbColor = FG,
                        activeTrackColor = ACC,
                        inactiveTrackColor = TRACK
                    )
                )
            }
        }
    }
}

// BOTÕES DO MENU
@Composable
private fun MenuButton(
    label: String,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Box(
        modifier = modifier
            .padding(1.dp)
            .height(38.dp)
            .background(BG2)
            .clickable { onClick() },
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = label,
            color = FG,
            fontSize = 10.sp,
            textAlign = TextAlign.Center
        )
    }
}

// BOTÕES DE REPRODUÇÃO
@Composable
private fun ControlButton(
    label: String,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    Box(
        modifier = modifier
            .height(48.dp)
            .background(BG2, RoundedCornerShape(3.dp))
            .clickable { onClick() },
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = label,
            color = FG,
            fontSize = 22.sp
        )
    }
}

// FORMATA MILISSEGUNDOS COMO 03:25 (ou 1:03:25)
private fun formatTime(ms: Long): String {
    val total = (ms / 1000).coerceAtLeast(0)
    val h = total / 3600
    val m = (total % 3600) / 60
    val s = total % 60
    fun two(n: Long) = n.toString().padStart(2, '0')
    return if (h > 0) "$h:${two(m)}:${two(s)}" else "${two(m)}:${two(s)}"
}

// LETRA NA ÁREA CENTRAL
@Composable
private fun LyricsView(
    lyrics: Lyrics,
    currentIndex: Int,
    onSeek: (Long) -> Unit
) {
    val listState = rememberLazyListState()

    BoxWithConstraints(Modifier.fillMaxSize()) {
        // Com metade da altura de folga em cima, a linha atual fica no meio da tela
        val edge = if (lyrics.synced) maxHeight / 2 else 8.dp

        LaunchedEffect(currentIndex, lyrics) {
            if (lyrics.synced && currentIndex >= 0) {
                listState.animateScrollToItem(currentIndex)
            }
        }

        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = edge, bottom = edge),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            itemsIndexed(lyrics.lines) { index, line ->
                val active = index == currentIndex
                Text(
                    text = line.text.ifBlank { "♪" },
                    color = if (active) ACC else FG.copy(alpha = 0.55f),
                    fontSize = if (active) 16.sp else 13.sp,
                    fontWeight = if (active) FontWeight.Bold else FontWeight.Normal,
                    textAlign = TextAlign.Center,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable(enabled = lyrics.synced && line.timeMs >= 0) { onSeek(line.timeMs) }
                        .padding(vertical = 6.dp)
                )
            }
        }
    }
}

// LISTA DE MÚSICAS
@Composable
private fun TrackList(
    tracks: List<Track>,
    currentIndex: Int,
    onPlay: (Int) -> Unit,
    onRemove: (Int) -> Unit,
    modifier: Modifier = Modifier
) {
    // Abre já mostrando a música que está tocando
    val listState = rememberLazyListState(
        initialFirstVisibleItemIndex = (currentIndex - 2).coerceAtLeast(0)
    )

    LazyColumn(state = listState, modifier = modifier) {
        itemsIndexed(tracks, key = { _, track -> track.uri }) { index, track ->
            val active = index == currentIndex
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onPlay(index) }
                    .padding(horizontal = 10.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = if (active) "▶" else "${index + 1}",
                    color = if (active) ACC else DIM,
                    fontSize = 11.sp,
                    modifier = Modifier.width(30.dp)
                )
                Text(
                    text = track.name.substringBeforeLast('.'),
                    color = if (active) ACC else FG,
                    fontSize = 12.sp,
                    fontWeight = if (active) FontWeight.Bold else FontWeight.Normal,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
                Text(
                    text = "✕",
                    color = DIM,
                    fontSize = 14.sp,
                    modifier = Modifier
                        .clickable { onRemove(index) }
                        .padding(horizontal = 8.dp, vertical = 2.dp)
                )
            }
        }
    }
}
