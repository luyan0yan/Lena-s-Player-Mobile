package com.example.lpmob

import androidx.compose.runtime.Composable

/**
 * Devolve uma função que abre o seletor de arquivos de texto (.lrc / .txt).
 * Quando o usuário escolhe um arquivo, chama onPicked(nome, conteúdo).
 */
@Composable
expect fun rememberTextFilePicker(onPicked: (name: String, text: String) -> Unit): () -> Unit
