"""
Lena's Player Beta V5.5 Mobile (retrato + toque, com Lyrics+ Integrado)

Requisitos:
  1) VLC instalado (mesma arquitetura do Python: 64 ou 32 bits)
  2) pip install python-vlc
  3) (opcional) pip install pillow   -> mostra capas em JPG (PNG funciona sem)
  4) pip install numpy soundcard     -> analisador de graves por loopback (visualizações/LPLA)

Estrutura de Pastas:
  Files/Animations -> Animações de letras (.lpla) e visualizações
  Files/Lyrics     -> Letras (.lrc / .txt) carregadas automaticamente pelo nome da música
  Files/Playlists  -> Playlists salvas (.m3u)
  Files/Themes     -> Temas visuais (.json)
  Plugins          -> Plugins em Python (.lpp)
"""
import ast
import base64
import bisect
import difflib
import hashlib
import io
import json
import math
import os
import queue
import random
import re
import sys
import tempfile
import time
import traceback
import types
import unicodedata
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog
from tkinter import font as tkfont

try:
    import vlc
except Exception as e:
    detalhe = traceback.format_exc()
    caminho_log = None
    try:
        _base = os.path.dirname(os.path.abspath(__file__))
        _files = os.path.join(_base, "Files")
        os.makedirs(_files, exist_ok=True)
        caminho_log = os.path.join(_files, "startup.log")
        with open(caminho_log, "a", encoding="utf-8") as _f:
            _f.write("\n" + "=" * 72 + "\nFalha ao importar python-vlc\n" + detalhe + "\n")
    except Exception:
        pass
    try:
        _r = tk.Tk()
        _r.withdraw()
        extra = f"\n\nDetalhes salvos em: {caminho_log}" if caminho_log else ""
        messagebox.showerror(
            "Lena's Player - erro",
            "Não consegui carregar o VLC.\n\n"
            "1) Instale o VLC (mesma arquitetura 32/64 bits do Python)\n"
            "2) No terminal, rode: py -m pip install python-vlc\n\n"
            f"Detalhe: {e}{extra}", parent=_r)
        _r.destroy()
    except Exception:
        pass
    sys.exit(1)

try:
    from PIL import Image, ImageTk, ImageFilter, ImageEnhance
except Exception:
    Image = ImageTk = ImageFilter = ImageEnhance = None

# Analisador de graves: captura loopback da saída do sistema (sem substituir o áudio do VLC).
try:
    import numpy as np
    import soundcard as sc
except Exception:
    np = sc = None

try:
    from tkinterdnd2 import TkinterDnD
    _RootBase = TkinterDnD.Tk
    DND_AVAILABLE = True
except Exception:
    _RootBase = tk.Tk
    DND_AVAILABLE = False

EXTS = (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma",
        ".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv")
VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv")

BG, BG2, FG, ACC = "#121212", "#1e1e1e", "#eaeaea", "#1db954"
CBG, WHITE, DIM = "#0b0b0b", "#ffffff", "#6b6b6b"


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def files_dir(*sub):
    p = os.path.join(app_dir(), "Files", *sub)
    os.makedirs(p, exist_ok=True)
    return p


APP_NOME = "Lena's Player"
APP_VERSAO = "Beta V5.5 Mobile"
ASSINATURA_TEXTO = "Lena"
ICONE_ARQUIVOS = ("Lena.icon", "Lena.ico", "Lena.png", "Lena.jpg", "Lena.jpeg")
ASSINATURA_ARQUIVOS = (
    "Assinatura.png", "Assinatura.jpg", "Assinatura.jpeg",
    "Lena.ass.png", "Lena.ass.jpg", "Ass.png", "Ass.jpg"
)


def _pasta_files_arquivo(nomes):
    d = files_dir()
    for n in nomes:
        p = os.path.join(d, n)
        if os.path.isfile(p):
            return p
    return None


def find_app_icon():
    return _pasta_files_arquivo(ICONE_ARQUIVOS)


def load_image_pil(path):
    if not path or Image is None:
        return None
    try:
        im = Image.open(path)
        if getattr(im, "format", "") == "ICO" and hasattr(im, "ico"):
            try:
                im.size = max(im.ico.sizes())
            except Exception:
                pass
        im.load()
        return im.convert("RGBA")
    except Exception:
        return None


def foto_do_arquivo(path, tamanho):
    if not path:
        return None
    try:
        if Image is not None and ImageTk is not None:
            im = load_image_pil(path)
            if im is None:
                return None
            im.thumbnail((tamanho, tamanho), getattr(Image, "Resampling", Image).LANCZOS)
            return ImageTk.PhotoImage(im)
        p = tk.PhotoImage(file=path)
        k = max(1, -(-max(p.width(), p.height()) // tamanho))
        return p.subsample(k) if k > 1 else p
    except Exception:
        return None


def tail_log(path, max_bytes=120_000):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            tam = f.tell()
            f.seek(max(0, tam - max_bytes))
            bruto = f.read()
        texto = bruto.decode("utf-8", "replace")
        if tam > max_bytes and "\n" in texto:
            texto = texto.split("\n", 1)[1]
        return texto
    except OSError:
        return None


# =====================================================================
#  Capa do álbum
# =====================================================================
_PNG = b"\x89PNG\r\n\x1a\n"
_JPG = b"\xff\xd8\xff"


def _find_magic(blob):
    best = -1
    for sig in (_PNG, _JPG):
        k = blob.find(sig)
        if k >= 0 and (best < 0 or k < best):
            best = k
    return blob[best:] if best >= 0 else None


def _syncsafe(b):
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def cover_from_id3(f):
    h = f.read(10)
    if len(h) < 10 or h[:3] != b"ID3":
        return None
    ver, flags, size = h[3], h[5], _syncsafe(h[6:10])
    data = f.read(size)
    pos = 0
    if ver >= 3 and flags & 0x40 and len(data) >= 4:
        pos = _syncsafe(data[:4]) if ver == 4 else int.from_bytes(data[:4], "big") + 4
    idlen, hlen = (3, 6) if ver == 2 else (4, 10)
    while pos + hlen <= len(data):
        fid = data[pos:pos + idlen]
        if fid[0] == 0:
            break
        if ver == 2:
            fsize = int.from_bytes(data[pos + 3:pos + 6], "big")
        elif ver == 4:
            fsize = _syncsafe(data[pos + 4:pos + 8])
        else:
            fsize = int.from_bytes(data[pos + 4:pos + 8], "big")
        body = data[pos + hlen:pos + hlen + fsize]
        pos += hlen + fsize
        if fid in (b"APIC", b"PIC"):
            img = _find_magic(body)
            if img:
                return img
    return None


def cover_from_flac(f):
    if f.read(4) != b"fLaC":
        return None
    while True:
        h = f.read(4)
        if len(h) < 4:
            return None
        last, typ, ln = h[0] & 0x80, h[0] & 0x7F, int.from_bytes(h[1:4], "big")
        blk = f.read(ln)
        if typ == 6:
            return _find_magic(blk)
        if last:
            return None


def cover_from_mp4(f):
    data = f.read(12 * 1024 * 1024)
    i = data.find(b"covr")
    return _find_magic(data[i:i + 8 * 1024 * 1024]) if i >= 0 else None


def find_cover(path):
    ext = os.path.splitext(path)[1].lower()
    img = None
    try:
        with open(path, "rb") as f:
            if ext == ".mp3":
                img = cover_from_id3(f)
            elif ext == ".flac":
                img = cover_from_flac(f)
            elif ext in (".m4a", ".mp4", ".aac"):
                img = cover_from_mp4(f)
    except Exception:
        img = None
    if img:
        return img
    d = os.path.dirname(path)
    base = os.path.splitext(os.path.basename(path))[0]
    for n in (base, "cover", "folder", "front", "album", "capa"):
        for e in (".jpg", ".jpeg", ".png"):
            p = os.path.join(d, n + e)
            if os.path.isfile(p):
                try:
                    with open(p, "rb") as f:
                        return f.read()
                except Exception:
                    pass
    return None


# =====================================================================
#  Lyrics+ (.lrc / .txt + Auto-Busca em Files/Lyrics + Editor Rápido)
# =====================================================================
TS = r"(\d{1,3}):(\d{2})(?::(\d{2}))?(?:[.,:](\d{1,4}))?"
_TAG = re.compile(r"\s*\[" + TS + r"\]")
_BARE = re.compile(r"\s*" + TS + r"(?=\s|[-–]|$)\s*[-–]?\s*")


def _to_ms(m):
    a, b, c, d = m.groups()
    if c is None:
        ms = (int(a) * 60 + int(b)) * 1000
    else:
        ms = (int(a) * 3600 + int(b) * 60 + int(c)) * 1000
    if d:
        ms += int(d.ljust(3, "0")[:3])
    return ms


def parse_lyrics(text):
    """Retorna (linhas, sincronizada). linhas = [(ms|None, texto)]."""
    offset, items, plain = 0, [], []
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip("\ufeff \t")
        if not line:
            continue
        mo = re.match(r"\[offset:\s*([+-]?\d+)\]", line, re.I)
        if mo:
            offset = int(mo.group(1))
            continue
        if re.match(r"^\[[A-Za-z#][^\]]*:[^\]]*\]\s*$", line):
            continue
        if re.match(r"^(?:language|idioma|atraso)\s*:", line, re.I):
            continue
        pos, times = 0, []
        while True:
            m = _TAG.match(line, pos)
            if not m:
                break
            times.append(_to_ms(m))
            pos = m.end()
        if not times:
            m = _BARE.match(line)
            if m:
                times, pos = [_to_ms(m)], m.end()
        txt = re.sub(r"<[^>]*>", "", line[pos:]).strip()
        if times:
            for t in times:
                items.append((max(0, t + offset), txt))
        else:
            plain.append(txt)
    if items:
        items.sort(key=lambda x: x[0])
        return items, True
    return [(None, t) for t in plain], False


def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", "ignore")


# ---------------------------------------------------------------------
#  Busca de letras: nome igual OU parecido
# ---------------------------------------------------------------------
_RUIDO = frozenset((
    "mp3", "wav", "flac", "m4a", "ogg", "aac", "wma", "160k", "128k", "192k", "256k", "320k",
    "private", "official", "audio", "video", "lyrics", "lyric", "letra", "letras", "hd", "hq",
    "feat", "ft", "explicit", "translation", "translated", "traducao", "tradução",
    "pt", "br", "ptbr", "portuguese", "portugues", "português", "english", "original",
    "lyrics", "letra", "versao", "versão"))
_EXT_LETRA = (".lrc", ".lcr", ".txt")


def _tokens_nome(nome):
    base = os.path.splitext(os.path.basename(nome))[0].replace("_", " ")
    base = "".join(ch for ch in unicodedata.normalize("NFKD", base) if not unicodedata.combining(ch))
    toks = re.findall(r"\w+", base.casefold())
    return [t for t in toks if t not in _RUIDO] or toks


def _sim_token(a, b):
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 4:
        if a.startswith(b) or b.startswith(a):
            return 0.9
        r = difflib.SequenceMatcher(None, a, b).ratio()
        if r >= 0.84:
            return r
    return 0.0


def pontuar_letra(tokens_musica, tokens_letra):
    if not tokens_musica or not tokens_letra:
        return 0.0, 0.0, 0.0
    livres, soma = list(range(len(tokens_letra))), 0.0
    for tm in tokens_musica:
        melhor, idx = 0.0, None
        for j in livres:
            sim = _sim_token(tm, tokens_letra[j])
            if sim > melhor:
                melhor, idx = sim, j
        if idx is not None:
            livres.remove(idx)
            soma += melhor
    cm, cl = soma / len(tokens_musica), soma / len(tokens_letra)
    return 0.65 * cm + 0.35 * cl, cm, cl


def achar_letra_parecida(caminho_musica, pastas):
    tm = _tokens_nome(caminho_musica)
    if sum(len(t) for t in tm) < 3:
        return None
    melhor, melhor_chave = None, None
    for pasta in pastas:
        try:
            nomes = os.listdir(pasta)
        except OSError:
            continue
        for nome in nomes:
            ext = os.path.splitext(nome)[1].lower()
            if ext not in _EXT_LETRA:
                continue
            score, cm, cl = pontuar_letra(tm, _tokens_nome(nome))
            if cm >= 0.99 or score >= 0.75:
                chave = (score, cl, -_EXT_LETRA.index(ext), -len(nome))
                caminho = os.path.join(pasta, nome)
                if (melhor_chave is None or chave > melhor_chave) and os.path.isfile(caminho):
                    melhor, melhor_chave = caminho, chave
    return melhor


def find_lyrics_file(path):
    """Busca somente em Files/Lyrics: nome exato primeiro, depois nome parecido."""
    if not path:
        return None
    pasta = files_dir("Lyrics")
    base_name = os.path.splitext(os.path.basename(path))[0]

    # Correspondência exata, sem diferenciar maiúsculas/minúsculas.
    try:
        nomes = os.listdir(pasta)
    except OSError:
        return None
    por_nome = {nome.casefold(): nome for nome in nomes}
    for ext in _EXT_LETRA:
        nome = por_nome.get((base_name + ext).casefold())
        if nome:
            candidato = os.path.join(pasta, nome)
            if os.path.isfile(candidato):
                return candidato

    return achar_letra_parecida(path, [pasta])


# ---------------------------------------------------------------------
#  Lyrics+ Duo: classificação de idioma e associação Original/Tradução
# ---------------------------------------------------------------------
_RE_TRADUCAO_NOME = re.compile(
    r"(?:^|[ _().\-])(traducao|tradução|translation|translated|pt[ _-]?br|portugues|portuguese)(?:$|[ _().\-])",
    re.IGNORECASE)
_RE_LANGUAGE = re.compile(r"^\s*\[?\s*(?:language|idioma)\s*:\s*[\"']?([^\"'\]]+)", re.IGNORECASE | re.MULTILINE)


def classificar_letra(path):
    """Retorna 'translation' ou 'original'; prioriza nome/metadados explícitos."""
    nome = os.path.splitext(os.path.basename(path))[0]
    if _RE_TRADUCAO_NOME.search(nome):
        return "translation"
    try:
        texto = read_text(path)
        m = _RE_LANGUAGE.search(texto)
        if m:
            idioma = m.group(1).strip().casefold()
            if any(x in idioma for x in ("portugu", "pt-br", "pt_br", "brazil", "brasil")):
                return "translation"
            if any(x in idioma for x in ("english", "inglês", "ingles", "original")):
                return "original"
        # Heurística conservadora: só classifica como português com vários indícios.
        corpo = " ".join(re.sub(r"^\[[^]]*\]", "", x) for x in texto.splitlines()).casefold()
        palavras = re.findall(r"[a-zá-ú]+", corpo)
        comuns = {"que", "não", "uma", "você", "voce", "para", "com", "meu", "minha",
                  "seu", "sua", "está", "esta", "mais", "por", "porque", "como", "amor",
                  "coração", "coracao", "então", "quando", "também", "tambem"}
        if sum(1 for w in palavras if w in comuns) >= 3:
            return "translation"
    except Exception:
        pass
    return "original"


def find_lyrics_files(path):
    """Encontra até duas letras em Files/Lyrics, separando original e tradução."""
    if not path:
        return None, None
    pasta = files_dir("Lyrics")
    music_tokens = _tokens_nome(path)
    base_musica = os.path.splitext(os.path.basename(path))[0].casefold()
    ranked = []
    try:
        names = os.listdir(pasta)
    except OSError:
        names = []

    for name in names:
        full = os.path.join(pasta, name)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in _EXT_LETRA:
            continue

        nome_base = os.path.splitext(name)[0].casefold()
        exato = nome_base == base_musica
        score, cm, cl = pontuar_letra(music_tokens, _tokens_nome(name))
        # Correspondência exata sempre vence a aproximada. Marcadores como
        # "tradução" continuam sendo tratados pela classificação Lyrics Duo.
        if exato or cm >= 0.99 or score >= 0.75:
            ranked.append((1 if exato else 0, score, cl,
                           -_EXT_LETRA.index(ext), -len(name), full))

    ranked.sort(reverse=True)
    escolhidas = {"original": None, "translation": None}
    for _, _, _, _, _, full in ranked:
        papel = classificar_letra(full)
        if escolhidas[papel] is None:
            escolhidas[papel] = full

    # Se só foi encontrada uma tradução, aproveita o próximo candidato como original.
    if escolhidas["original"] is None and ranked:
        for _, _, _, _, _, full in ranked:
            if full != escolhidas["translation"]:
                escolhidas["original"] = full
                break
    return escolhidas["original"], escolhidas["translation"]


# ---------------------------------------------------------------------
#  Atraso independente salvo no próprio arquivo: atraso: "500ms" (compatível com tag antiga)
# ---------------------------------------------------------------------
TAG_ATRASO = re.compile(
    r"^\s*(?:\[offset_lplus:\s*([+-]?\d+)\]|atraso:\s*[\"']?([+-]?\d+)\s*ms[\"']?)\s*$",
    re.IGNORECASE)


def _ler_letra(caminho):
    with open(caminho, "rb") as f:
        bruto = f.read()
    crlf = b"\r\n" in bruto
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = bruto.decode(enc)
        except UnicodeDecodeError:
            continue
        if enc == "utf-8-sig" and not bruto.startswith(b"\xef\xbb\xbf"):
            enc = "utf-8"
        return texto, enc, crlf
    return bruto.decode("utf-8", "replace"), "utf-8", crlf


def ler_atraso_arquivo(caminho):
    """Lê o atraso (ms) da última ocorrência de [offset_lplus: X] no arquivo."""
    try:
        texto, _, _ = _ler_letra(caminho)
        ultimo_val = 0
        for linha in texto.splitlines():
            m = TAG_ATRASO.match(linha)
            if m:
                ultimo_val = int(m.group(1) or m.group(2))
        return ultimo_val
    except Exception:
        return 0


def salvar_atraso_arquivo(caminho, ms):
    """Grava/atualiza a tag no fim do .lrc sem mexer no resto."""
    try:
        texto, enc, crlf = _ler_letra(caminho)
        linhas_orig = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        tem_tag = any(TAG_ATRASO.match(l) for l in linhas_orig)

        if ms == 0 and not tem_tag:
            return True

        linhas = [l for l in linhas_orig if not TAG_ATRASO.match(l)]
        while linhas and not linhas[-1].strip():
            linhas.pop()

        linhas.append(f'atraso: "{int(ms)}ms"')
        eol = "\r\n" if crlf else "\n"
        tmp = caminho + ".lplus.tmp"
        with open(tmp, "wb") as f:
            f.write((eol.join(linhas) + eol).encode(enc))
        os.replace(tmp, caminho)
        return True
    except Exception:
        return False


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def fmt(ms, force_hours=False):
    s = max(0, int(ms // 1000))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    if h or force_hours:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# =====================================================================
#  Analisador de graves em tempo real (captura loopback do áudio do sistema)
# =====================================================================
class BassAnalyzer:
    """Analisa 35-180 Hz da saída de áudio do sistema sem alterar o VLC."""
    def __init__(self, is_playing, samplerate=22050, blocksize=2048):
        self.is_playing = is_playing
        self.samplerate = int(samplerate)
        self.blocksize = int(blocksize)
        self.level = 0.0
        self.raw_db = -90.0
        self.available = bool(np is not None and sc is not None)
        self.error = ""
        self._stop = __import__("threading").Event()
        self._lock = __import__("threading").Lock()
        self._thread = None
        self._window = np.hanning(self.blocksize).astype(np.float32) if self.available else None
        if self.available:
            self._thread = __import__("threading").Thread(
                target=self._run, name="LenaBassAnalyzer", daemon=True)
            self._thread.start()

    def snapshot(self):
        with self._lock:
            return float(self.level), float(self.raw_db)

    def _run(self):
        try:
            speaker = sc.default_speaker()
            # Speaker recorder usa loopback: o VLC continua usando sua saída normal.
            with speaker.recorder(samplerate=self.samplerate, channels=2,
                                  blocksize=self.blocksize) as recorder:
                freqs = np.fft.rfftfreq(self.blocksize, 1.0 / self.samplerate)
                band = (freqs >= 35.0) & (freqs <= 180.0)
                while not self._stop.is_set():
                    audio = recorder.record(numframes=self.blocksize)
                    if audio is None or len(audio) == 0:
                        continue
                    if not self.is_playing():
                        with self._lock:
                            self.level *= 0.72
                            if self.level < 0.004:
                                self.level = 0.0
                            self.raw_db = -90.0
                        continue
                    data = np.asarray(audio, dtype=np.float32)
                    if data.ndim == 2:
                        data = data.mean(axis=1)
                    if len(data) != self.blocksize:
                        if len(data) < self.blocksize:
                            data = np.pad(data, (0, self.blocksize-len(data)))
                        else:
                            data = data[:self.blocksize]
                    spectrum = np.abs(np.fft.rfft(data * self._window))
                    # RMS espectral aproximado da faixa grave, normalizado pela janela.
                    amp = float(np.sqrt(np.mean((spectrum[band] * (2.0 / self._window.sum())) ** 2))) if np.any(band) else 0.0
                    db = 20.0 * np.log10(max(amp, 1e-7))
                    # Faixa ajustada para conteúdo musical comum; clamp evita saltos extremos.
                    target = max(0.0, min(1.0, (db + 48.0) / 34.0))
                    with self._lock:
                        # Ataque rápido e queda gradual para preservar a sensação de chama.
                        k = 0.58 if target > self.level else 0.16
                        self.level += (target - self.level) * k
                        self.raw_db = db
        except Exception as exc:
            self.error = str(exc)
            self.available = False
            with self._lock:
                self.level, self.raw_db = 0.0, -90.0

    def close(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.8)


# =====================================================================
#  Sistema de Plugins (.LPP) e Animações (.LPLA)
# =====================================================================
PLUGIN_API_VERSION = 2
EVENTOS = ("ao_iniciar_faixa", "ao_fim_da_faixa", "ao_parar", "ao_fechar", "ao_modo_repeticao")


class LPLAWrapper:
    def __init__(self, aid, meta, mod):
        self.id = aid
        self.nome = meta.get("nome", aid)
        self.opcoes = meta.get("opcoes", [])
        self._mod = mod
        self.controla_vizinhas = bool(getattr(mod, "CONTROLA_VIZINHAS", False))

    def animando(self, ctx):
        fn = getattr(self._mod, "animando", None)
        return bool(fn(ctx)) if callable(fn) else True

    def desenhar(self, ctx):
        fn = getattr(self._mod, "desenhar", None)
        if callable(fn):
            fn(ctx)


class PluginAPI:
    versao = PLUGIN_API_VERSION

    def __init__(self, mgr, pid, nome):
        self._mgr = mgr
        self.id = pid
        self.nome = nome
        self.vlc = vlc
        self.handlers = {}
        self.menu_items = []
        self.animacoes = []
        self.config = mgr.config_for(pid)

    @property
    def player(self):
        return self._mgr.host.mp

    @property
    def instance(self):
        return self._mgr.host.instance

    @property
    def pasta_plugins(self):
        return self._mgr.dir

    @property
    def pasta_temp(self):
        p = os.path.join(tempfile.gettempdir(), "LenasPlayer", self.id)
        os.makedirs(p, exist_ok=True)
        return p

    def faixa_atual(self):
        return self._mgr.host.current_path()

    def tocar_arquivo(self, caminho, titulo=None):
        self._mgr.host.play_path(caminho, titulo)

    def mensagem(self, texto):
        self._mgr.host.say(str(texto))

    def na_interface(self, fn):
        self._mgr.host.run_in_ui(fn)

    def on(self, evento, fn):
        if evento not in EVENTOS:
            raise ValueError(f"Evento desconhecido: {evento}. Use: {', '.join(EVENTOS)}")
        self.handlers.setdefault(evento, []).append(fn)

    def add_menu_item(self, rotulo, callback):
        self.menu_items.append({"tipo": "cmd", "rotulo": rotulo, "cb": callback})

    def add_toggle(self, rotulo, callback, inicial=False):
        self.menu_items.append({"tipo": "chk", "rotulo": rotulo, "cb": callback,
                                "estado": bool(inicial), "var": None})

    def registrar_animacao(self, anim):
        if not callable(getattr(anim, "desenhar", None)):
            raise TypeError("a animação precisa ter o método desenhar(ctx)")
        nome = str(getattr(anim, "nome", "") or type(anim).__name__)
        lid = re.sub(r"\W", "_", str(getattr(anim, "id", "") or nome)).lower()
        if any(a == lid for a, _ in self.animacoes):
            raise ValueError(f"já existe uma animação com id '{lid}' neste plugin")
        self.animacoes.append((lid, anim))
        return f"{self.id}:{lid}"

    def salvar_config(self):
        self._mgr.save_state()

    def log(self, *partes):
        self._mgr.log(self.id, " ".join(str(p) for p in partes))


class PluginManager:
    # Plugins substituídos pela integração nativa Lyrics+ (evita duplicidade)
    OBSOLETOS = frozenset(("lyrics_auto_loader", "lyrics_plus"))

    def __init__(self, host, directory, anim_directory):
        self.host = host
        self.dir = directory
        self.anim_dir = anim_directory
        self.plugins = {}
        self.lpla_anims = {}
        self.state = {"ativos": {}, "confiaveis": {}, "config": {}}
        os.makedirs(directory, exist_ok=True)
        os.makedirs(anim_directory, exist_ok=True)
        self.state_path = os.path.join(directory, "plugins.json")
        self.log_path = os.path.join(directory, "plugins.log")
        try:
            if os.path.getsize(self.log_path) > 200_000:
                os.remove(self.log_path)
        except OSError:
            pass
        # Cria o arquivo desde o início para que "Ver log" sempre tenha um destino.
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                if os.path.getsize(self.log_path) == 0:
                    f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Lena's Player: log iniciado\n")
        except OSError:
            pass
        self._load_state()

    def _load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                data = json.load(f)
            for k in self.state:
                if isinstance(data.get(k), dict):
                    self.state[k] = data[k]
        except Exception:
            pass

    def save_state(self):
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def log(self, who, text):
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {who}: {text}\n")
        except Exception:
            pass

    def config_for(self, pid):
        return self.state["config"].setdefault(pid, {})

    @staticmethod
    def _hash(path):
        try:
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except OSError:
            return ""

    @staticmethod
    def _read_meta(path, pid, var_name="PLUGIN"):
        meta = {"nome": pid, "versao": "?", "autor": "?", "descricao": "", "api": 1}
        try:
            with open(path, "rb") as f:
                tree = ast.parse(f.read())
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == var_name for t in node.targets):
                    d = ast.literal_eval(node.value)
                    if isinstance(d, dict):
                        meta.update(d)
        except Exception:
            pass
        return meta

    def scan_lpla(self):
        self.lpla_anims.clear()
        try:
            names = sorted(os.listdir(self.anim_dir))
        except OSError:
            names = []
        for n in names:
            if n.lower().endswith(".lpla"):
                path = os.path.join(self.anim_dir, n)
                aid = os.path.splitext(n)[0].lower()
                meta = self._read_meta(path, aid, "ANIMACAO")
                try:
                    with open(path, "rb") as f:
                        code = compile(f.read(), path, "exec")
                    mod = types.ModuleType("lpla_" + re.sub(r"\W", "_", aid))
                    exec(code, mod.__dict__)
                    if callable(getattr(mod, "desenhar", None)):
                        self.lpla_anims[f"lpla:{aid}"] = LPLAWrapper(aid, meta, mod)
                except Exception:
                    self.log("lpla", f"Erro ao carregar {n}:\n" + traceback.format_exc())

    def scan(self):
        self.scan_lpla()
        found = {}
        try:
            names = sorted(os.listdir(self.dir))
        except OSError:
            names = []
        for n in names:
            if n.lower().endswith(".lpp"):
                pid = os.path.splitext(n)[0].lower()
                if pid in self.OBSOLETOS:
                    continue
                found[pid] = os.path.join(self.dir, n)
        for pid in list(self.plugins):
            if pid not in found:
                self.disable(pid, remember=False)
                del self.plugins[pid]
        for pid, path in found.items():
            info = self.plugins.setdefault(pid, {
                "id": pid, "path": path, "status": "desativado", "erro": "",
                "meta": {}, "module": None, "api": None, "hash": ""})
            info["path"] = path
            info["hash"] = self._hash(path)
            info["meta"] = self._read_meta(path, pid, "PLUGIN")

    def load_all(self):
        self.scan()
        for pid in list(self.plugins):
            if self.state["ativos"].get(pid) is False:
                self.plugins[pid]["status"] = "desativado"
                continue
            self.enable(pid)

    def enable(self, pid):
        info = self.plugins.get(pid)
        if not info:
            return False
        if info["status"] == "ativo":
            return True
        m = info["meta"]
        if self.state["confiaveis"].get(pid) != info["hash"]:
            novo = pid not in self.state["confiaveis"]
            texto = (
                f"{'Plugin novo' if novo else 'Plugin MODIFICADO desde a última vez'}: "
                f"{m.get('nome', pid)} (v{m.get('versao', '?')}) de {m.get('autor', '?')}\n\n"
                f"{m.get('descricao', '')}\n\nArquivo: {os.path.basename(info['path'])}\n\n"
                "Plugins .LPP executam código no seu PC. Ativar este plugin?")
            if not self.host.confirmar("Lena's Player - plugin", texto):
                info.update(status="desativado", erro="Recusado pelo usuário.")
                self.state["ativos"][pid] = False
                self.save_state()
                return False
            self.state["confiaveis"][pid] = info["hash"]
        ok = self._exec(info)
        if ok:
            self.state["ativos"][pid] = True
        self.save_state()
        return ok

    def _exec(self, info):
        pid, meta = info["id"], info["meta"]
        info["erro"] = ""
        try:
            req = int(meta.get("api", 1))
        except Exception:
            req = 1
        if req > PLUGIN_API_VERSION:
            info.update(status="erro", erro=f"Requer API {req}; este player tem a {PLUGIN_API_VERSION}.")
            self.log(pid, info["erro"])
            self.host.say(f"Plugin '{pid}' não carregou: {info['erro']}")
            return False
        name = "lpp_" + re.sub(r"\W", "_", pid)
        api = PluginAPI(self, pid, str(meta.get("nome", pid)))
        try:
            with open(info["path"], "rb") as f:
                code = compile(f.read(), info["path"], "exec")
            mod = types.ModuleType(name)
            mod.__file__ = info["path"]
            sys.modules[name] = mod
            exec(code, mod.__dict__)
            reg = getattr(mod, "register", None)
            if not callable(reg):
                raise RuntimeError("o plugin não tem a função register(api)")
            reg(api)
        except Exception as e:
            sys.modules.pop(name, None)
            info.update(status="erro", erro=f"{type(e).__name__}: {e}", module=None, api=None)
            self.log(pid, "erro ao carregar:\n" + traceback.format_exc())
            self.host.say(f"Plugin '{pid}' deu erro ao carregar. Veja Plugins > Ver log de plugins.")
            return False
        info.update(status="ativo", module=mod, api=api)
        self.log(pid, "carregado")
        return True

    def disable(self, pid, remember=True):
        info = self.plugins.get(pid)
        if not info:
            return
        if info["status"] == "ativo":
            try:
                fn = getattr(info["module"], "unregister", None)
                if callable(fn):
                    fn(info["api"])
            except Exception:
                self.log(pid, "erro em unregister:\n" + traceback.format_exc())
            sys.modules.pop("lpp_" + re.sub(r"\W", "_", pid), None)
            self.log(pid, "descarregado")
        info.update(status="desativado", erro="", module=None, api=None)
        if remember:
            self.state["ativos"][pid] = False
            self.save_state()

    def reload(self, pid):
        info = self.plugins.get(pid)
        if not info:
            return False
        self.disable(pid, remember=False)
        info["hash"] = self._hash(info["path"])
        info["meta"] = self._read_meta(info["path"], pid, "PLUGIN")
        return self.enable(pid)

    def unload_all(self):
        for pid in list(self.plugins):
            self.disable(pid, remember=False)

    def emit(self, evento, *args):
        handled = False
        for info in list(self.plugins.values()):
            api = info.get("api")
            if info["status"] != "ativo" or not api:
                continue
            for fn in list(api.handlers.get(evento, [])):
                try:
                    if fn(*args) is True:
                        handled = True
                except Exception:
                    self.log(info["id"], f"erro em {evento}:\n" + traceback.format_exc())
        return handled

    def animacao(self, aid):
        if aid in self.lpla_anims:
            return self.lpla_anims[aid]
        pid, _, local = aid.partition(":")
        info = self.plugins.get(pid)
        if not info or info["status"] != "ativo" or not info["api"]:
            return None
        for lid, anim in info["api"].animacoes:
            if lid == local:
                return anim
        return None

    def animacoes(self):
        out = []
        for aid, anim in sorted(self.lpla_anims.items()):
            out.append((aid, anim, None))
        for pid in sorted(self.plugins):
            info = self.plugins[pid]
            if info["status"] == "ativo" and info["api"]:
                for lid, anim in info["api"].animacoes:
                    out.append((f"{pid}:{lid}", anim, info))
        return out

    def menu_groups(self):
        out = []
        for pid in sorted(self.plugins):
            info = self.plugins[pid]
            if info["status"] == "ativo" and info["api"] and info["api"].menu_items:
                out.append((info["api"].nome, info["api"].menu_items))
        return out


# =====================================================================
#  Contexto de Animações de Letras
# =====================================================================
class AnimCtx:
    def __init__(self, host, anim, aid, W, H, px, texto, norm, indice, total,
                 decorrido, duracao, pos_ms, sincronizada):
        self._host, self._anim = host, anim
        # Intensidade dos graves em tempo real (0.0 a 1.0), disponível às animações .LPLA.
        self.graves, self.grave_db = host.bass_analyzer.snapshot()
        self.bass, self.bass_db = self.graves, self.grave_db  # aliases em inglês
        self._cfg = host.anim_cfg(aid)
        self.canvas = host.canvas
        self.largura, self.altura, self.px = W, H, px
        self.max_largura = W * 0.86
        self.texto, self.norm = texto, norm
        self.indice, self.total_linhas = indice, total
        self.decorrido_ms, self.duracao_ms = decorrido, duracao
        self.posicao_ms, self.sincronizada = pos_ms, sincronizada
        self.cor_texto, self.cor_fundo = WHITE, CBG
        self.cor_vizinha, self.cor_destaque = DIM, ACC
        self.cx, self.cy = W / 2, H / 2
        self._rows, self._lh, self._cur_h = [], 0, 0

    @property
    def restante_ms(self):
        return max(0, self.duracao_ms - self.decorrido_ms)

    @property
    def progresso(self):
        return min(1.0, max(0.0, self.decorrido_ms / max(1, self.duracao_ms)))

    def opcao(self, chave):
        for o in getattr(self._anim, "opcoes", None) or []:
            if o.get("chave") == chave:
                return self._cfg.get(chave, o.get("padrao"))
        return self._cfg.get(chave)

    def fonte(self, px=None, negrito=True):
        return self._host.font(max(8, int(px or self.px)), negrito)

    @staticmethod
    def _clamp(t):
        return 0.0 if t < 0 else 1.0 if t > 1 else t

    def misturar(self, c1, c2, t):
        return mix(c1, c2, self._clamp(t))

    def cor_com_opacidade(self, cor, opacidade):
        return mix(self.cor_fundo, cor, self._clamp(opacidade))

    def quebrar(self, texto=None, fonte=None):
        return self._host.layout(self.norm if texto is None else texto,
                                 fonte or self.fonte(), self.max_largura)

    def pintar(self, rows, lh, fonte, cor, dy=0, revelar=None, destaque=None,
               cor_destaque=None, cx=None, cy=None):
        self._host.paint(rows, lh, self.cx if cx is None else cx,
                         self.cy if cy is None else cy, fonte, cor, revelar,
                         destaque, cor_destaque or self.cor_destaque, dy)

    def pintar_texto(self, opacidade=1.0, dy=0, cor=None, revelar=None,
                     destaque=None, cor_destaque=None):
        self.pintar(self._rows, self._lh, self.fonte(),
                    self.cor_com_opacidade(cor or self.cor_texto, opacidade),
                    dy, revelar, destaque, cor_destaque)

    def pintar_vizinhas(self, op_anterior=1.0, op_proxima=1.0):
        self._host.desenhar_vizinhas(self, op_anterior, op_proxima)

    def preparar(self, cx, cy):
        self.cx, self.cy = cx, cy
        self._rows, self._lh, self._cur_h = self._host.layout(
            self.norm, self.fonte(), self.max_largura)


# =====================================================================
#  Player Principal
# =====================================================================
RETRATO_MAX = 0.85          # largura/altura máxima da janela (só retrato)
FONTE_MENU = ("Segoe UI", 12)


class ToplevelMovel(tk.Toplevel):
    """Toplevel que nunca passa do tamanho da tela (janelas de diálogo em celular/tablet)."""

    def geometry(self, spec=None):
        if isinstance(spec, str):
            m = re.match(r"^(\d+)x(\d+)(.*)$", spec)
            if m:
                sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
                w = min(int(m.group(1)), max(240, sw - 16))
                h = min(int(m.group(2)), max(240, sh - 70))
                spec = f"{w}x{h}{m.group(3)}"
        return super().geometry(spec)


class SliderToque(tk.Canvas):
    """Controle deslizante grande, feito para o dedo (toque ou mouse).
    Mesma interface básica do ttk.Scale: get(), set(v) e command(v)."""
    PAD = 16

    def __init__(self, parent, from_=0, to=100, command=None, height=40, bg=BG, **kw):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0,
                         cursor="hand2", **kw)
        self._min, self._max = float(from_), float(to)
        self._cmd = command
        self._val = self._min
        self.bind("<Configure>", lambda e: self._desenhar())
        self.bind("<Button-1>", self._tocar)
        self.bind("<B1-Motion>", self._tocar)
        self.bind("<MouseWheel>",
                  lambda e: self.set(self._val + (5 if e.delta > 0 else -5)))

    def get(self):
        return self._val

    def set(self, v):
        self._val = max(self._min, min(self._max, float(v)))
        self._desenhar()
        if self._cmd:
            self._cmd(self._val)

    def _tocar(self, e):
        w = max(1, self.winfo_width() - 2 * self.PAD)
        frac = max(0.0, min(1.0, (e.x - self.PAD) / w))
        self.set(self._min + frac * (self._max - self._min))
        return "break"

    def _desenhar(self):
        self.delete("all")
        W, H = self.winfo_width(), self.winfo_height()
        if W < 40:
            return
        span = (self._max - self._min) or 1.0
        frac = (self._val - self._min) / span
        x = self.PAD + frac * (W - 2 * self.PAD)
        cy = H / 2
        self.create_rectangle(self.PAD, cy - 3, W - self.PAD, cy + 3, fill="#2e2e2e", outline="")
        self.create_rectangle(self.PAD, cy - 3, x, cy + 3, fill=ACC, outline="")
        self.create_oval(x - 12, cy - 12, x + 12, cy + 12, fill=WHITE, outline=ACC, width=2)



class Player(_RootBase):
    def __init__(self):
        super().__init__()
        self.title("Lena's Player Beta V5.5 Mobile")
        self._configurar_janela_retrato()
        self.configure(bg=BG)
        self.aplicar_icone()

        self.instance = vlc.Instance()
        self.mp = self.instance.media_player_new()
        self.bass_analyzer = BassAnalyzer(lambda: bool(self.mp.is_playing()))
        self.playlist = []
        self.index = -1
        self.playlist_groups = {}
        self.display_rows = []
        self.playlists_dir = files_dir("Playlists")
        self.lyrics_dir = files_dir("Lyrics")
        self.animations_dir = files_dir("Animations")
        self.themes_dir = files_dir("Themes")

        self.seeking = False
        self.shuffle = tk.BooleanVar(value=False)
        self.repeat = tk.StringVar(value="off")
        self._ui_q = queue.Queue()
        self._ended_seen = False
        self.current_file = None
        self._say_job = None

        # Capa / Lyrics+
        self.cover_src = None
        self.cover_img = None
        self.cover_built = -100
        self.cover_hint = False
        self.lyr, self.lyr_synced, self.lyr_times = [], False, []
        self.lyr_offset_ms = 0
        self.lyr_file, self.lyr_delay_ms, self.lyr_status_base = None, 0, ""
        # Segunda coluna independente (tradução), com atraso próprio por arquivo.
        self.lyr_translation, self.lyr_translation_synced = [], False
        self.lyr_translation_times, self.lyr_translation_file = [], None
        self.lyr_translation_delay_ms, self.lyr_translation_offset_ms = 0, 0
        self.lyrics_view = tk.StringVar(value="both")
        self.lyrics_delay_target = tk.StringVar(value="original")
        self.canvas_visible = False

        # Tela cheia imersiva
        self.immersive = False
        self.bg_img, self.bg_key, self.bg_avg = None, None, CBG
        self._fs_job, self._fs_ui, self._fs_hover = None, True, False
        self.last_sig = None
        self._fonts = {}

        # Gerenciador de Plugins & Animações
        self.lpp = PluginManager(self, os.path.join(app_dir(), "Plugins"), self.animations_dir)
        self.p_cfg = self.lpp.state["config"].setdefault("_player", {})
        self.p_cfg.setdefault("habilitar_vis", False)
        self.p_cfg.setdefault("vis_modo", "Ondas")
        self.p_cfg.setdefault("vis_barras_max", 12)
        self.p_cfg.setdefault("vis_fade_sens", 75)
        self.p_cfg.setdefault("wave_bar_beta", False)
        self.p_cfg.setdefault("animacao", "lpla:karaoke_suave")

        self.var_vis_beta = tk.BooleanVar(value=bool(self.p_cfg["habilitar_vis"]))
        self.var_vis_modo = tk.StringVar(value=str(self.p_cfg["vis_modo"]))
        self.var_wave_beta = tk.BooleanVar(value=bool(self.p_cfg["wave_bar_beta"]))

        self.anim_rev = 0
        self.anim_sel = tk.StringVar(value=str(self.p_cfg.get("animacao", "")))

        self.build_ui()
        self.mp.set_hwnd(self.video.winfo_id())
        try:
            self.mp.video_set_mouse_input(False)
            self.mp.video_set_key_input(False)
        except Exception:
            pass
        self.mp.audio_set_volume(80)
        self.set_canvas_visible(True)
        self.after(300, self.tick)
        self.after(60, self.render)
        self.after(80, self.pump)
        self.after(200, self.lpp.load_all)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- Interface ----------
    def _configurar_janela_retrato(self):
        """Janela só em modo retrato (proporção de celular)."""
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        h = max(480, min(840, sh - 90))
        w = max(300, min(int(h * 0.56), sw - 10))
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2 - 20)}")
        self.minsize(300, 480)
        try:
            self.wm_aspect(1, 3, 17, 20)   # largura/altura entre 1/3 e 0,85
        except Exception:
            pass
        self._retrato_job = None
        self._ult_larg = 0
        self.bind("<Configure>", self._on_configure_janela, add="+")

    def _on_configure_janela(self, e):
        if e.widget is not self:
            return
        if e.width != self._ult_larg:
            self._ult_larg = e.width
            wl = max(160, e.width - 28)
            for nome in ("label", "status", "lyr_status"):
                wdg = getattr(self, nome, None)
                if wdg is not None:
                    try:
                        wdg.config(wraplength=wl)
                    except Exception:
                        pass
        if getattr(self, "immersive", False):
            return
        if self._retrato_job is not None:
            self.after_cancel(self._retrato_job)
        self._retrato_job = self.after(180, self._forcar_retrato)

    def _forcar_retrato(self):
        self._retrato_job = None
        if getattr(self, "immersive", False):
            return
        try:
            if self.state() == "zoomed":
                self.state("normal")
        except Exception:
            pass
        w, h = self.winfo_width(), self.winfo_height()
        if w > h * RETRATO_MAX:
            self.geometry(f"{max(300, int(h * RETRATO_MAX))}x{h}")

    def build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Horizontal.TScale", background=BG, troughcolor=BG2)
        self.build_menus()
        self._menubar_visivel = False
        self._lista_visivel = False
        fonte_grande = ("Segoe UI Symbol", 18)

        # ---- Barra superior: botão ☰ (canto superior esquerdo) ----
        top = tk.Frame(self, bg=BG2)
        top.pack(side="top", fill="x")
        self._topbar = top
        self.btn_menu = tk.Button(top, text="☰", command=self.toggle_menubar, bg=BG2, fg=FG,
                                  activebackground=ACC, activeforeground="black", bd=0,
                                  font=("Segoe UI Symbol", 18), width=3, pady=4,
                                  cursor="hand2")
        self.btn_menu.pack(side="left")
        self.btn_lista = tk.Button(top, text="🎵 Lista", command=self.toggle_lista, bg=BG2,
                                   fg=FG, activebackground=ACC, activeforeground="black",
                                   bd=0, font=("Segoe UI", 11), padx=10, pady=10,
                                   cursor="hand2")
        self.btn_lista.pack(side="right")
        tk.Label(top, text="Lena's Player", fg=ACC, bg=BG2,
                 font=("Segoe UI", 12, "bold")).pack(side="left", expand=True)

        # ---- Barra de menus (aparece ao tocar no ☰) ----
        self._menubar_frame = tk.Frame(self, bg=BG)
        self._montar_barra_menus()

        # ---- Área inferior: letras/status, linha do tempo e botões ----
        bottom = tk.Frame(self, bg=BG)
        bottom.pack(side="bottom", fill="x")
        self._bottom = bottom

        # ---- Área central: capa + letras (player) ou lista de músicas ----
        content = tk.Frame(self, bg=BG)
        content.pack(side="top", fill="both", expand=True)
        self._content = content
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        side = tk.Frame(content, bg=BG2)
        side.grid(row=0, column=0, sticky="nsew")
        self._side = side

        self.video = tk.Frame(content, bg="black")
        self.video.grid(row=0, column=0, sticky="nsew")
        self.canvas = tk.Canvas(self.video, bg=CBG, highlightthickness=0)
        self._criar_botao_fs()

        self.prog_tooltip = tk.Label(self, text="00:00:00", bg="#222222", fg=ACC,
                                     font=("Segoe UI", 10, "bold"), padx=8, pady=3,
                                     bd=1, relief="solid")

        # Página da lista de músicas
        hdr = tk.Frame(side, bg=BG2)
        hdr.pack(fill="x", padx=4, pady=(6, 0))
        self.btn(hdr, "➕ Músicas", self.add_files).pack(side="left", expand=True, fill="x", padx=2)
        self.btn(hdr, "📁 Pasta", self.add_folder).pack(side="left", expand=True, fill="x", padx=2)
        self.btn(hdr, "🗑 Limpar", self.clear).pack(side="left", expand=True, fill="x", padx=2)
        self.listbox = tk.Listbox(side, bg=BG2, fg=FG, selectbackground=ACC,
                                  selectforeground="black", bd=0, font=("Segoe UI", 13),
                                  highlightthickness=0, activestyle="none")
        self.listbox.pack(fill="both", expand=True, padx=4, pady=4)
        self.listbox.bind("<Delete>", self.remove_selected)
        self._lst = {"y0": 0, "acum": 0, "arrastou": False, "long": False, "job": None}

        # Informações (status das letras / mensagens)
        info = tk.Frame(bottom, bg=BG)
        info.pack(fill="x", padx=10, pady=(4, 0))
        self.lyr_status = tk.Label(info, text="Lyrics+: nenhuma", fg=DIM, bg=BG, anchor="w",
                                   justify="left", font=("Segoe UI", 8), wraplength=360)
        self.lyr_status.pack(fill="x")
        self.status = tk.Label(info, text="", fg=ACC, bg=BG, anchor="w", justify="left",
                               font=("Segoe UI", 9), wraplength=360)
        self.status.pack(fill="x")

        # Linha do tempo (alta, para o dedo)
        prog = tk.Frame(bottom, bg=BG)
        prog.pack(fill="x", padx=10, pady=(4, 0))
        self.t_cur = tk.Label(prog, text="00:00", fg=FG, bg=BG, width=7, font=("Segoe UI", 10))
        self.t_cur.pack(side="left")
        self.t_tot = tk.Label(prog, text="00:00", fg=FG, bg=BG, width=7, font=("Segoe UI", 10))
        self.t_tot.pack(side="right")
        self.prog_canvas = tk.Canvas(prog, bg=BG, height=44, highlightthickness=0, cursor="hand2")
        self.prog_canvas.pack(fill="x", expand=True, side="left", padx=4)
        self.prog_canvas.bind("<Button-1>", self.on_prog_click)
        self.prog_canvas.bind("<B1-Motion>", self.on_prog_drag)
        self.prog_canvas.bind("<ButtonRelease-1>", self.on_prog_leave)
        self.prog_canvas.bind("<Motion>", self.on_prog_motion)
        self.prog_canvas.bind("<Leave>", self.on_prog_leave)

        # Nome da faixa
        self.label = tk.Label(bottom, text="Nada tocando", fg=FG, bg=BG, height=2,
                              font=("Segoe UI", 12, "bold"), wraplength=360, justify="center")
        self.label.pack(fill="x", padx=10)

        # Botões de reprodução (abaixo da capa/letras)
        ctrl = tk.Frame(bottom, bg=BG)
        ctrl.pack(fill="x", padx=8, pady=(2, 2))
        for col in range(4):
            ctrl.grid_columnconfigure(col, weight=1, uniform="bt")
        self.btn(ctrl, "⏮", self.prev, font=fonte_grande, pady=8).grid(row=0, column=0, sticky="ew", padx=3)
        self.btn_play = self.btn(ctrl, "▶", self.toggle, font=fonte_grande, pady=8)
        self.btn_play.grid(row=0, column=1, sticky="ew", padx=3)
        self.btn(ctrl, "⏹", self.stop, font=fonte_grande, pady=8).grid(row=0, column=2, sticky="ew", padx=3)
        self.btn(ctrl, "⏭", self.next, font=fonte_grande, pady=8).grid(row=0, column=3, sticky="ew", padx=3)

        ctrl2 = tk.Frame(bottom, bg=BG)
        ctrl2.pack(fill="x", padx=8, pady=(4, 10))
        self.btn_shuf = self.btn(ctrl2, "🔀", self.toggle_shuffle, font=("Segoe UI Symbol", 14))
        self.btn_shuf.pack(side="left", padx=3)
        self.btn_rep = self.btn(ctrl2, "🔁 off", self.cycle_repeat, 9)
        self.btn_rep.pack(side="left", padx=3)
        self.vol = SliderToque(ctrl2, from_=0, to=100, command=self.on_volume, height=40, bg=BG)
        self.vol.pack(side="right", fill="x", expand=True, padx=(8, 2))
        self.vol.set(80)
        tk.Label(ctrl2, text="🔊", fg=FG, bg=BG, font=("Segoe UI Symbol", 14)).pack(side="right")

        self.video.tkraise()

        # ---- Teclado (continua funcionando no PC) ----
        self.bind("<space>", lambda e: self.toggle())
        self.bind("<Left>", lambda e: self.jump(-5000))
        self.bind("<Right>", lambda e: self.jump(5000))
        self.bind("<Up>", lambda e: self.vol.set(min(100, self.vol.get() + 5)))
        self.bind("<Down>", lambda e: self.vol.set(max(0, self.vol.get() - 5)))
        self.bind("n", lambda e: self.next())
        self.bind("p", lambda e: self.prev())
        self.bind("f", lambda e: self.toggle_fullscreen())
        self.bind("<Escape>", lambda e: self.exit_immersive())

        # ---- Toque: duplo toque = modo imersivo; toque longo = menu de contexto ----
        for wdg in (self.video, self.canvas):
            wdg.bind("<Double-Button-1>", lambda e: self.toggle_fullscreen())
            wdg.bind("<Motion>", self._fs_motion, add="+")
            wdg.bind("<Button-1>", self._fs_motion, add="+")
            wdg.bind("<Button-3>", self.show_ctx)
            self._bind_long_press(wdg, self.show_ctx)

        # ---- Lista: toque toca, arrastar rola, toque longo abre o menu ----
        self.listbox.bind("<ButtonPress-1>", self._lista_press)
        self.listbox.bind("<B1-Motion>", self._lista_move)
        self.listbox.bind("<ButtonRelease-1>", self._lista_release)
        self.listbox.bind("<Button-3>", self.ctx_list)

        if DND_AVAILABLE:
            for widget in (self, self.video, self.canvas, self.listbox):
                try:
                    widget.drop_target_register("DND_Files")
                    widget.dnd_bind("<<Drop>>", self.on_drop)
                except Exception:
                    pass

    def btn(self, parent, text, cmd, width=None, font=None, pady=8):
        return tk.Button(parent, text=text, command=cmd, bg=BG2, fg=FG,
                         activebackground=ACC, activeforeground="black",
                         bd=0, padx=10, pady=pady, width=width or 0,
                         font=font or ("Segoe UI", 11), cursor="hand2")

    # ---------- Barra de menus (botão ☰) e páginas ----------
    def _montar_barra_menus(self):
        itens = [("Arquivo", self.menu_arquivo), ("Playlists", self.menu_playlists),
                 ("Reproduzir", self.menu_reproduzir), ("Letras", self.menu_letras),
                 ("Capas", self.menu_capas), ("Plugins", self.menu_plugins),
                 ("Configurações", self.menu_config)]
        pos = [(0, 0, 1), (0, 1, 1), (0, 2, 1), (0, 3, 1),
               (1, 0, 1), (1, 1, 1), (1, 2, 2)]
        for col in range(4):
            self._menubar_frame.grid_columnconfigure(col, weight=1, uniform="mb")
        for (rot, fn), (r, c, span) in zip(itens, pos):
            mb = tk.Menubutton(self._menubar_frame, text=rot, bg=BG2, fg=FG,
                               activebackground=ACC, activeforeground="black", bd=0,
                               relief="flat", font=("Segoe UI", 11), pady=12,
                               cursor="hand2")
            mb.menu = fn(mb)
            mb.config(menu=mb.menu)
            mb.grid(row=r, column=c, columnspan=span, sticky="ew", padx=1, pady=1)

    def toggle_menubar(self):
        if self._menubar_visivel:
            self._menubar_frame.pack_forget()
        else:
            self._menubar_frame.pack(side="top", fill="x", after=self._topbar)
        self._menubar_visivel = not self._menubar_visivel
        self.btn_menu.config(fg=ACC if self._menubar_visivel else FG)
        self.last_sig = None

    def mostrar_lista(self):
        self._lista_visivel = True
        self._side.tkraise()
        self.btn_lista.config(text="⬅ Player", fg=ACC)

    def mostrar_player(self):
        self._lista_visivel = False
        self.video.tkraise()
        self.btn_lista.config(text="🎵 Lista", fg=FG)
        self.last_sig = None

    def toggle_lista(self):
        if self._lista_visivel:
            self.mostrar_player()
        else:
            self.mostrar_lista()

    # ---------- Toque: toque longo e lista com arrastar ----------
    def _bind_long_press(self, wdg, cb, delay=550, slop=12):
        st = {"job": None, "x": 0, "y": 0}

        def cancelar(_e=None):
            if st["job"] is not None:
                try:
                    wdg.after_cancel(st["job"])
                except Exception:
                    pass
                st["job"] = None

        def disparar(e):
            st["job"] = None
            cb(e)

        def press(e):
            cancelar()
            st["x"], st["y"] = e.x, e.y
            st["job"] = wdg.after(delay, lambda: disparar(e))

        def move(e):
            if st["job"] is not None and (abs(e.x - st["x"]) > slop or abs(e.y - st["y"]) > slop):
                cancelar()

        wdg.bind("<ButtonPress-1>", press, add="+")
        wdg.bind("<B1-Motion>", move, add="+")
        wdg.bind("<ButtonRelease-1>", cancelar, add="+")

    def _lista_cancelar_long(self):
        job = self._lst.get("job")
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._lst["job"] = None

    def _lista_altura_linha(self):
        try:
            bb = self.listbox.bbox(self.listbox.nearest(0))
            if bb:
                return max(16, bb[3])
        except Exception:
            pass
        return 28

    def _lista_press(self, e):
        st = self._lst
        st.update(y0=e.y, acum=0, arrastou=False, long=False)
        self._lista_cancelar_long()
        st["job"] = self.after(550, lambda: self._lista_long(e))
        return "break"

    def _lista_long(self, e):
        self._lst["job"] = None
        self._lst["long"] = True
        self.ctx_list(e)

    def _lista_move(self, e):
        st = self._lst
        dy = e.y - st["y0"]
        if not st["arrastou"]:
            if abs(dy) < 8:
                return "break"
            st["arrastou"] = True
            self._lista_cancelar_long()
        st["acum"] += dy
        st["y0"] = e.y
        linha = self._lista_altura_linha()
        passos = int(st["acum"] / linha)
        if passos:
            self.listbox.yview_scroll(-passos, "units")
            st["acum"] -= passos * linha
        return "break"

    def _lista_release(self, e):
        st = self._lst
        self._lista_cancelar_long()
        if st["arrastou"] or st["long"] or self.listbox.size() == 0:
            return "break"
        row = self.listbox.nearest(e.y)
        bb = self.listbox.bbox(row)
        if row < 0 or row >= len(self.display_rows) or not bb or not (bb[1] <= e.y <= bb[1] + bb[3]):
            return "break"
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(row)
        kind, value = self.display_rows[row]
        if kind == "group":
            self.playlist_groups[value]["expanded"] = not self.playlist_groups[value].get("expanded", True)
            self.refresh_list()
        elif value in self.playlist:
            self.play(self.playlist.index(value))
            self.mostrar_player()
        return "break"

    # ---------- Linha do Tempo ----------
    def on_prog_click(self, event):
        length = self.mp.get_length()
        w = max(1, self.prog_canvas.winfo_width())
        frac = max(0.0, min(1.0, event.x / w))
        if length > 0:
            target_ms = int(frac * length)
            self.mp.set_time(target_ms)
            self.t_cur.config(text=fmt(target_ms))
            self.render_prog_bar(override_frac=frac)

    def on_prog_drag(self, event):
        self.on_prog_click(event)
        self.on_prog_motion(event)

    def on_prog_motion(self, event):
        length = self.mp.get_length()
        w = max(1, self.prog_canvas.winfo_width())
        frac = max(0.0, min(1.0, event.x / w))
        target_ms = int(frac * length) if length > 0 else 0
        self.prog_tooltip.config(text=fmt(target_ms, force_hours=True))
        rx = self.prog_canvas.winfo_rootx() - self.winfo_rootx() + event.x - 28
        ry = self.prog_canvas.winfo_rooty() - self.winfo_rooty() - 26
        self.prog_tooltip.place(x=max(4, rx), y=max(4, ry))

    def on_prog_leave(self, _):
        self.prog_tooltip.place_forget()

    def render_prog_bar(self, override_frac=None):
        c = self.prog_canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10:
            return
        length = self.mp.get_length()
        pos = max(0, self.mp.get_time())
        frac = override_frac if override_frac is not None else ((pos / length) if length > 0 else 0.0)
        frac = max(0.0, min(1.0, frac))

        base_y = h - 14
        # SPRITE: TRILHO DA LINHA DO TEMPO — faixa escura na parte inferior da janela.
        # SPRITE: TRILHO DA LINHA DO TEMPO — faixa escura na parte inferior da janela.
        c.create_rectangle(0, base_y - 3, w, base_y + 3, fill="#2e2e2e", outline="")
        # SPRITE: PROGRESSO DA LINHA DO TEMPO — preenchimento verde proporcional à posição.
        c.create_rectangle(0, base_y - 3, int(w * frac), base_y + 3, fill=ACC, outline="")

        if self.var_wave_beta.get() and length > 0:
            step = 4
            num_bars = w // step
            max_bar_h = base_y - 4
            seed_base = hash(self.current_file or "") & 0xFFFF
            for i in range(num_bars):
                bx = i * step + 1
                env = abs(math.sin((i + seed_base) * 0.23) * math.cos((i * 0.11) + seed_base))
                if abs((i / max(1, num_bars)) - frac) < 0.02 and self.mp.is_playing():
                    env = min(1.0, env + 0.25)
                bar_h = max(2, int(env * max_bar_h))
                ratio = bar_h / max(1, max_bar_h)
                if ratio >= 0.68:
                    color = "#ff3b30"
                elif ratio >= 0.36:
                    color = "#ffcc00"
                else:
                    color = "#33b5e5"
                # SPRITE: MINI BARRAS DE ÁUDIO — barras pequenas sobre a linha do tempo.
                c.create_rectangle(bx, base_y - 3 - bar_h, bx + 2, base_y - 3, fill=color, outline="")

        nx = int(w * frac)
        # SPRITE: INDICADOR DA LINHA DO TEMPO — círculo que mostra a posição atual da música.
        c.create_oval(nx - 9, base_y - 9, nx + 9, base_y + 9, fill=WHITE, outline=ACC, width=2)

    # ---------- Playlists e Arquivos ----------
    def refresh_list(self):
        self.listbox.delete(0, "end")
        self.display_rows = []
        grouped = set()
        for group_id, group in self.playlist_groups.items():
            title = group["name"]
            grouped.update(group["paths"])
            self.listbox.insert("end", ("▾ " if group.get("expanded", True) else "▸ ") + title)
            self.display_rows.append(("group", group_id))
            if group.get("expanded", True):
                for path in group["paths"]:
                    self.listbox.insert("end", "    └ " + os.path.basename(path))
                    self.display_rows.append(("track", path))
        for path in self.playlist:
            if path not in grouped:
                self.listbox.insert("end", os.path.basename(path))
                self.display_rows.append(("track", path))
        if self.current_file:
            for row, item in enumerate(self.display_rows):
                if item == ("track", self.current_file):
                    self.listbox.selection_set(row)
                    break

    def add_paths(self, paths, play_first=True):
        clean = [os.path.abspath(x) for x in paths if os.path.isfile(x) and x.lower().endswith(EXTS)]
        was_empty = not self.playlist
        for path in clean:
            if path not in self.playlist:
                self.playlist.append(path)
        self.refresh_list()
        if clean and (was_empty or play_first):
            self.play(self.playlist.index(clean[0]))

    def read_m3u(self, f):
        base = os.path.dirname(f)
        paths = []
        with open(f, encoding="utf-8-sig", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                path = line if os.path.isabs(line) else os.path.join(base, line)
                if os.path.isfile(path) and path.lower().endswith(EXTS):
                    paths.append(os.path.abspath(path))
        return paths

    def import_playlist(self, f):
        paths = self.read_m3u(f)
        if not paths:
            messagebox.showwarning("Playlist", "Nenhum arquivo de mídia válido foi encontrado.", parent=self)
            return
        gid = os.path.abspath(f)
        self.playlist_groups[gid] = {"name": os.path.basename(f), "paths": paths, "expanded": True, "source": f}
        for path in paths:
            if path not in self.playlist:
                self.playlist.append(path)
        self.refresh_list()
        if self.index < 0:
            self.play(self.playlist.index(paths[0]))

    def add_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Mídia", " ".join("*" + e for e in EXTS)), ("Todos", "*.*")])
        if files:
            self.add_paths(files)

    def add_folder(self):
        d = filedialog.askdirectory()
        if not d:
            return
        found = []
        for root, _, files in os.walk(d):
            for name in sorted(files):
                if name.lower().endswith(EXTS):
                    found.append(os.path.join(root, name))
        self.add_paths(found)

    def clear(self):
        self.stop()
        self.playlist.clear()
        self.playlist_groups.clear()
        self.refresh_list()
        self.index = -1
        self.label.config(text="Nada tocando")
        self.cover_src = None
        self.set_lyrics([], False, "Lyrics+: nenhuma")

    def remove_selected(self, _=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        row = sel[0]
        if row >= len(self.display_rows):
            return
        kind, value = self.display_rows[row]
        if kind == "group":
            group = self.playlist_groups.pop(value, None)
            if group:
                for path in group["paths"]:
                    if path in self.playlist:
                        self.playlist.remove(path)
            if self.current_file not in self.playlist:
                self.stop()
                self.current_file = None
                self.index = -1
        else:
            path = value
            if path in self.playlist:
                i = self.playlist.index(path)
                self.playlist.remove(path)
                if i < self.index:
                    self.index -= 1
                elif i == self.index:
                    self.index = -1
                    self.stop()
            for group in self.playlist_groups.values():
                if path in group["paths"]:
                    group["paths"].remove(path)
        self.refresh_list()

    def save_playlist(self):
        if not self.playlist:
            return
        f = filedialog.asksaveasfilename(initialdir=self.playlists_dir, defaultextension=".m3u",
                                         filetypes=[("Playlist", "*.m3u")])
        if f:
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("#EXTM3U\n" + "\n".join(self.playlist) + "\n")

    def load_playlist(self):
        f = filedialog.askopenfilename(initialdir=self.playlists_dir, filetypes=[("Playlist", "*.m3u *.m3u8")])
        if f:
            self.import_playlist(f)

    def add_saved_playlist(self):
        files = [os.path.join(self.playlists_dir, n) for n in os.listdir(self.playlists_dir)
                 if n.lower().endswith((".m3u", ".m3u8"))]
        if not files:
            messagebox.showinfo("Playlists", "Coloque arquivos .m3u na pasta Files/Playlists.", parent=self)
            return
        w = ToplevelMovel(self)
        w.title("Adicionar playlist da lista")
        w.configure(bg=BG)
        w.geometry("380x300")
        lb = tk.Listbox(w, bg=BG2, fg=FG, selectbackground=ACC, bd=0)
        lb.pack(fill="both", expand=True, padx=8, pady=8)
        for f in files:
            lb.insert("end", os.path.splitext(os.path.basename(f))[0])

        def add(_=None):
            sel = lb.curselection()
            if sel:
                self.import_playlist(files[sel[0]])
                w.destroy()

        lb.bind("<Double-Button-1>", add)
        self.btn(w, "Adicionar", add).pack(pady=(0, 8))

    def on_list_click(self, event):
        row = self.listbox.nearest(event.y)
        if row < len(self.display_rows) and self.display_rows[row][0] == "group":
            gid = self.display_rows[row][1]
            self.playlist_groups[gid]["expanded"] = not self.playlist_groups[gid].get("expanded", True)
            self.refresh_list()
            return "break"

    def on_drop(self, event):
        try:
            paths = list(self.tk.splitlist(event.data))
        except Exception:
            paths = [event.data.strip("{}")]
        media, lyrics, playlists = [], [], []
        for path in paths:
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext in (".txt", ".lrc", ".lcr"):
                lyrics.append(path)
            elif ext in (".m3u", ".m3u8"):
                playlists.append(path)
            elif ext in EXTS:
                media.append(path)
        if media:
            self.add_paths(media, play_first=True)
        for path in playlists:
            self.import_playlist(path)
        for path in lyrics:
            escolha = messagebox.askyesnocancel(
                "Importar letra", f"O arquivo {os.path.basename(path)} é a TRADUÇÃO?\n\n"
                "Sim = Tradução\nNão = Letra original\nCancelar = ignorar este arquivo", parent=self)
            if escolha is not None:
                self.load_lyrics(path, role="translation" if escolha else "original")

    def rename_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        row = sel[0]
        if row >= len(self.display_rows):
            return
        kind, value = self.display_rows[row]
        if kind == "group":
            group = self.playlist_groups[value]
            name = simpledialog.askstring("Renomear playlist", "Novo nome:", initialvalue=group["name"], parent=self)
            if name:
                group["name"] = name
                self.refresh_list()
        else:
            old = os.path.basename(value)
            name = simpledialog.askstring("Renomear item", "Novo nome (extensão preservada):",
                                          initialvalue=os.path.splitext(old)[0], parent=self)
            if name:
                new = os.path.join(os.path.dirname(value), name + os.path.splitext(old)[1])
                try:
                    os.rename(value, new)
                    self.playlist[self.playlist.index(value)] = new
                    if self.current_file == value:
                        self.current_file = new
                    for g in self.playlist_groups.values():
                        g["paths"] = [new if x == value else x for x in g["paths"]]
                    self.refresh_list()
                except Exception as e:
                    messagebox.showerror("Renomear", str(e), parent=self)

    # ---------- Capa do álbum (separada do núcleo Lyrics+) ----------
    def pick_cover(self):
        f = filedialog.askopenfilename(filetypes=[("Imagem", "*.jpg *.jpeg *.png"), ("Todos", "*.*")])
        if f:
            try:
                with open(f, "rb") as fh:
                    self.set_cover(fh.read())
            except Exception as e:
                messagebox.showerror("Capa", str(e))

    def set_cover(self, data):
        self.cover_src = data
        self.cover_img = None
        self.cover_built = -100
        self.cover_hint = False
        self.last_sig = None

    def build_cover(self, s):
        self.cover_img = None
        self.cover_built = s
        data = self.cover_src
        if not data:
            return
        try:
            if Image is not None:
                im = Image.open(io.BytesIO(data)).convert("RGB")
                im.thumbnail((s, s))
                self.cover_img = ImageTk.PhotoImage(im)
            elif data[:8] == _PNG:
                p = tk.PhotoImage(data=base64.b64encode(data))
                k = max(1, -(-max(p.width(), p.height()) // s))
                self.cover_img = p.subsample(k) if k > 1 else p
            else:
                self.cover_hint = True
        except Exception:
            self.cover_img = None


    # =================================================================
    # LYRICS+ — núcleo do player: carregamento, associação, atraso e editor
    # (a renderização visual permanece na seção de Canvas/Animações abaixo)
    # =================================================================
    def set_canvas_visible(self, visible):
        if visible and not self.canvas_visible:
            self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        elif not visible and self.canvas_visible:
            self.canvas.place_forget()
        self.canvas_visible = visible
        self.last_sig = None
        self._atualizar_botao_fs()

    def set_lyrics(self, lines, synced, status, path=None):
        self.lyr, self.lyr_synced = lines, synced
        self.lyr_times = [t for t, _ in lines] if synced else []
        self.lyr_file = path
        self.lyr_delay_ms = ler_atraso_arquivo(path) if path else 0
        self.lyr_offset_ms = -self.lyr_delay_ms
        self.lyr_status_base = status
        self._mostrar_status_letra()
        self.last_sig = None

    def _mostrar_status_letra(self):
        extra = f" | original {self.lyr_delay_ms:+d} ms" if self.lyr_delay_ms else ""
        if self.lyr_translation_file and self.lyr_translation_delay_ms:
            extra += f" | tradução {self.lyr_translation_delay_ms:+d} ms"
        self.lyr_status.config(text=self.lyr_status_base + extra)

    def _set_translation(self, path=None, quiet=True):
        self.lyr_translation, self.lyr_translation_synced = [], False
        self.lyr_translation_times, self.lyr_translation_file = [], None
        self.lyr_translation_delay_ms = self.lyr_translation_offset_ms = 0
        if path:
            try:
                lines, synced = parse_lyrics(read_text(path))
                if lines:
                    self.lyr_translation = lines
                    self.lyr_translation_synced = synced
                    self.lyr_translation_times = [t for t, _ in lines] if synced else []
                    self.lyr_translation_file = path
                    self.lyr_translation_delay_ms = ler_atraso_arquivo(path)
                    self.lyr_translation_offset_ms = -self.lyr_translation_delay_ms
                elif not quiet:
                    messagebox.showwarning("Lyrics+", "O arquivo de tradução está vazio.")
            except Exception as e:
                if not quiet:
                    messagebox.showerror(f"Não foi possivel ler a tradução de \n{e}")
        self._mostrar_status_letra()
        self.last_sig = None

    def load_lyrics(self, path, quiet=False, role=None):
        try:
            lines, synced = parse_lyrics(read_text(path))
        except Exception as e:
            if not quiet:
                messagebox.showerror(f"Não foi possivel ler o arquivo:\n{e}")
            return
        if not lines:
            if not quiet:
                messagebox.showwarning("devia ter algo aqui? O arquivo está vazio.")
            return
        role = role or classificar_letra(path)
        modo = "sincronizadas" if synced else "sem tempo"
        if role == "translation":
            self._set_translation(path, quiet=True)
            self.lyrics_delay_target.set("translation")
            self.lyr_status_base = f"Achei a tradução ({len(lines)} linhas, {modo})"
        else:
            self.set_lyrics(lines, synced, f"{len(lines)} linhas ({modo})", path)
            self.lyrics_delay_target.set("letra original")
        self._mostrar_status_letra()
        self.last_sig = None

    def pick_lyrics(self):
        f = filedialog.askopenfilename(initialdir=self.lyrics_dir,
                                       filetypes=[("Letras", "*.txt *.lcr *.lrc"), ("Todos", "*.*")])
        if not f:
            return
        escolha = messagebox.askyesnocancel(
            "Importar letra", "Este arquivo é a TRADUÇÃO?\n\nSim = Tradução\nNão = Letra original\nCancelar = não importar",
            parent=self)
        if escolha is None:
            return
        self.load_lyrics(f, role="translation" if escolha else "original")

    def load_lyrics_with_offset(self, path, ms, quiet=False):
        self.load_lyrics(path, quiet)
        role = "translation" if self.lyr_translation_file == path else "original"
        self.set_lyrics_delay(ms, save=False, target=role)

    # ---------- Atraso independente: original ou tradução ----------
    def selecionar_alvo_atraso(self, target):
        if target == "translation" and not self.lyr_translation_file:
            self.lyrics_delay_target.set("original")
            self.say("ainda não há uma tradução carregada.")
            return
        self.lyrics_delay_target.set(target)

    def _delay_target(self, target=None):
        target = target or self.lyrics_delay_target.get()
        if target == "translation" and self.lyr_translation_file:
            return "translation", self.lyr_translation_file, self.lyr_translation_delay_ms
        return "original", self.lyr_file, self.lyr_delay_ms

    def set_lyrics_delay(self, ms, save=True, target=None):
        ms = int(ms)
        role, path, _ = self._delay_target(target)
        if role == "translation":
            self.lyr_translation_delay_ms = ms
            self.lyr_translation_offset_ms = -ms
        else:
            self.lyr_delay_ms = ms
            self.lyr_offset_ms = -ms
        self.last_sig = None
        self._mostrar_status_letra()
        if save and path and not salvar_atraso_arquivo(path, ms):
            self.lpp.log(f"foi mal, não consegui gravar o atraso em {path}")
            self.say("não deu pra gravar o atraso no arquivo da letra.")

    def nudge_lyrics_delay(self, delta_ms):
        _, _, atual = self._delay_target()
        self.set_lyrics_delay(atual + int(delta_ms))
        self.say(f"Lyrics+: atraso {self.lyrics_delay_target.get()} {atual + int(delta_ms):+d} ms")

    def adjust_lyrics_offset(self, delta_ms):
        _, _, atual = self._delay_target()
        self.set_lyrics_delay(atual - int(delta_ms))

    def open_lyrics_delay_window(self):
        if not self.lyr and not self.lyr_translation:
            self.say("nenhuma letra carregada no momento.")
            return
        w0 = getattr(self, "_lyr_win", None)
        if w0 is not None and w0.winfo_exists():
            w0.lift(); w0.focus_force(); return
        win = self._lyr_win = ToplevelMovel(self)
        win.title("Atraso independente")
        win.geometry("470x190")
        win.resizable(False, False)
        win.configure(bg="#141414")
        win.transient(self)
        win.attributes("-topmost", True)
        tk.Label(win, text="Qual arquivo deseja sincronizar?", bg="#141414", fg=ACC,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
        alvo = tk.StringVar(value=self.lyrics_delay_target.get())
        escolha = tk.Frame(win, bg="#141414"); escolha.pack(fill="x", padx=14)
        tk.Radiobutton(escolha, text="Original", variable=alvo, value="original", bg="#141414",
                       fg="#eeeeee", selectcolor="#252525", activebackground="#141414",
                       command=lambda: atualizar()).pack(side="left")
        tk.Radiobutton(escolha, text="Tradução", variable=alvo, value="translation", bg="#141414",
                       fg="#eeeeee", selectcolor="#252525", activebackground="#141414",
                       state=("normal" if self.lyr_translation_file else "disabled"),
                       command=lambda: atualizar()).pack(side="left", padx=12)
        nome_var = tk.StringVar()
        tk.Label(win, textvariable=nome_var, bg="#141414", fg="#aaaaaa",
                 anchor="w").pack(fill="x", padx=14, pady=(2, 0))
        fr = tk.Frame(win, bg="#141414"); fr.pack(fill="x", padx=14, pady=6)
        var_texto = tk.StringVar(); trava = {"ativo": False, "job": None}
        slider = tk.Scale(fr, from_=-5000, to=5000, resolution=1, orient="horizontal",
                          showvalue=False, bg="#141414", fg="#eeeeee", troughcolor="#2a2a2a",
                          activebackground=ACC, highlightthickness=0, bd=0, sliderrelief="flat")
        slider.pack(side="left", fill="x", expand=True, padx=(0, 10))
        def valor_atual():
            return self.lyr_translation_delay_ms if alvo.get() == "translation" else self.lyr_delay_ms
        def atualizar(*_):
            self.lyrics_delay_target.set(alvo.get())
            _, path, val = self._delay_target(alvo.get())
            nome_var.set(os.path.basename(path) if path else "(arquivo não carregado)")
            var_texto.set(str(val)); trava["ativo"] = True
            try:
                if val < -5000: slider.config(from_=val)
                if val > 5000: slider.config(to=val)
                slider.set(val)
            finally: trava["ativo"] = False
        def gravar_depois(v):
            if trava["job"] is not None:
                try: win.after_cancel(trava["job"])
                except Exception: pass
            trava["job"] = win.after(180, lambda: self.set_lyrics_delay(v, save=True, target=alvo.get()))
        def deslizar(v):
            if trava["ativo"]: return
            val = int(float(v)); var_texto.set(str(val))
            self.set_lyrics_delay(val, save=False, target=alvo.get()); gravar_depois(val)
        slider.configure(command=deslizar)
        def confirmar(event=None):
            try: val = int(var_texto.get().strip())
            except ValueError: var_texto.set(str(valor_atual())); return
            trava["ativo"] = True
            try: slider.set(val)
            finally: trava["ativo"] = False
            self.set_lyrics_delay(val, save=True, target=alvo.get())
        entry = tk.Entry(fr, textvariable=var_texto, width=7, justify="right", bg="#252525",
                         fg="#ffffff", insertbackground="#ffffff", relief="flat")
        entry.pack(side="left", ipady=3); entry.bind("<Return>", confirmar); entry.bind("<FocusOut>", confirmar)
        tk.Label(fr, text="ms", bg="#141414", fg="#aaaaaa").pack(side="left", padx=(4, 0))
        tk.Label(win, text="Positivo (+) atrasa a letra; negativo (-) adianta.", bg="#141414",
                 fg="#888888").pack(anchor="w", padx=14)
        atualizar()
        def fechar():
            if trava["job"] is not None:
                try: win.after_cancel(trava["job"])
                except Exception: pass
            self.set_lyrics_delay(valor_atual(), save=True, target=alvo.get())
            self._lyr_win = None; win.destroy()
        win.protocol("WM_DELETE_WINDOW", fechar)

    def open_lyrics_plus_editor(self):
        w = ToplevelMovel(self)
        w.title("Editar letras atual (Lyrics reader)")
        w.geometry("520x760")
        w.configure(bg=BG)
        w.transient(self)

        txt = tk.Text(w, bg=BG2, fg=FG, insertbackground=WHITE, font=("Consolas", 11), bd=0, padx=8, pady=8)
        txt.pack(fill="both", expand=True, padx=10, pady=10)

        if self.lyr:
            for t, line in self.lyr:
                if t is not None:
                    mm, ss = divmod(int(t // 1000), 60)
                    cs = int((t % 1000) // 10)
                    txt.insert("end", f"[{mm:02d}:{ss:02d}.{cs:02d}] {line}\n")
                else:
                    txt.insert("end", f"{line}\n")

        def stamp_time():
            pos = max(0, self.mp.get_time())
            mm, ss = divmod(int(pos // 1000), 60)
            cs = int((pos % 1000) // 10)
            line_idx = txt.index("insert").split(".")[0]
            txt.insert(f"{line_idx}.0", f"[{mm:02d}:{ss:02d}.{cs:02d}] ")
            txt.mark_set("insert", f"{int(line_idx)+1}.0")

        def save_lrc():
            default_name = "letra.lrc"
            if self.current_file:
                default_name = os.path.splitext(os.path.basename(self.current_file))[0] + ".lrc"
            out_path = os.path.join(self.lyrics_dir, default_name)
            content = txt.get("1.0", "end").strip()
            atraso_antes = self.lyr_delay_ms
            if content:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(content + "\n")
                self.load_lyrics(out_path, quiet=True)
                if atraso_antes:
                    self.set_lyrics_delay(atraso_antes)
                self.say(f"Lyrics+ salvo em Files/Lyrics/{default_name}")
                w.destroy()

        bar = tk.Frame(w, bg=BG)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        self.btn(bar, "⏱ Marcar Tempo Atual", stamp_time).pack(side="left", padx=4)
        self.btn(bar, "💾 Salvar em Files/Lyrics", save_lrc).pack(side="right", padx=4)

    def load_extras(self, path):
        self.set_cover(find_cover(path))
        original, traducao = find_lyrics_files(path)
        if original:
            self.load_lyrics(original, quiet=True, role="original")
        elif traducao:
            self.set_lyrics([], False, "Letra original não encontrada")
        else:
            self.set_lyrics([], False, "nao tem nada aquinenhuma (Files/Lyrics)")
        self._set_translation(traducao, quiet=True)
        self.lyrics_delay_target.set("original")
        ext = os.path.splitext(path)[1].lower()
        self.set_canvas_visible(ext not in VIDEO_EXTS)


    # =================================================================
    # LYRICS+ / CANVAS — sprites, animações e desenho das letras
    # =================================================================
    def font(self, px, bold=True):
        key = (px, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(family="Segoe UI", size=-px,
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    @staticmethod
    def layout(text, f, maxw):
        words = text.split()
        sp = f.measure(" ")
        rows, cur, curw, idx = [], [], 0, 0
        for w in words:
            ww = f.measure(w)
            if cur and curw + sp + ww > maxw:
                rows.append((cur, curw))
                cur, curw = [], 0
            x = curw + (sp if cur else 0)
            cur.append((w, x, idx))
            curw = x + ww
            idx += len(w) + 1
        if cur:
            rows.append((cur, curw))
        lh = f.metrics("linespace")
        return rows, lh, len(rows) * lh

    def paint(self, rows, lh, cx, cy, f, color, reveal=None, hl=None, hcolor=None, dy=0):
        # SPRITE: TEXTO PRINCIPAL / LETRAS — exibido no centro do canvas de Lyrics+.
        y = cy - len(rows) * lh / 2 + lh / 2 + dy
        for row, rw in rows:
            x0 = cx - rw / 2
            for w, x, i in row:
                vis = len(w) if reveal is None else max(0, min(len(w), reveal - i))
                if vis > 0:
                    self.canvas.create_text(x0 + x, y, text=w[:vis], anchor="w", font=f, fill=color)
                if hl is not None:
                    h = max(0, min(len(w), hl - i))
                    if h > 0:
                        self.canvas.create_text(x0 + x, y, text=w[:h], anchor="w", font=f, fill=hcolor)
            y += lh

    def draw_background_visualization(self, c, W, H, pos_ms):
        # Visualizações agora reagem ao grave real capturado no loopback do sistema.
        if not self.var_vis_beta.get():
            return
        modo = self.var_vis_modo.get()
        base = self.bg_avg if (self.immersive and self.bg_img is not None) else CBG
        playing = self.mp.is_playing()
        bass, _bass_db = self.bass_analyzer.snapshot()
        t = pos_ms * 0.005 if playing else 0.0
        vol_factor = max(0.2, self.vol.get() / 100.0)
        intensity = max(0.0, min(1.0, bass * (self.p_cfg.get("vis_fade_sens", 75) / 75.0)))

        if modo == "Ondas":
            for wave_idx, (amp, freq, speed, col) in enumerate((
                (38 * vol_factor * (0.25 + intensity), 0.012, 1.0, mix(base, ACC, 0.35)),
                (26 * vol_factor * (0.20 + intensity), 0.018, -1.4, mix(base, "#00d4ff", 0.25))
            )):
                pts = []
                for x in range(0, W + 20, 16):
                    y = (H * 0.52) + math.sin(x * freq + t * speed + wave_idx) * amp
                    pts.extend((x, y))
                if len(pts) >= 4:
                    c.create_line(*pts, fill=col, width=3, smooth=True)

        elif modo == "Fade de grave":
            steps = 6
            max_reach = (W * 0.42) * intensity
            for step in range(steps, 0, -1):
                frac = step / steps
                alpha = (1.0 - frac) * 0.45 * intensity
                col = mix(base, ACC, alpha)
                band_w = max_reach * frac
                if band_w > 2:
                    c.create_rectangle(0, 0, band_w, H, fill=col, outline="")
                    c.create_rectangle(W - band_w, 0, W, H, fill=col, outline="")

        elif modo == "Barras":
            n_bars = max(1, min(15, int(self.p_cfg.get("vis_barras_max", 12))))
            margin = W * 0.12
            usable_w = W - 2 * margin
            slot_w = usable_w / n_bars
            bar_w = slot_w * 0.65
            for i in range(n_bars):
                # Pequena variação espacial, mas a energia vem do grave capturado.
                variation = 0.72 + 0.28 * abs(math.sin(i * 0.75 + t * 0.25))
                pulse = intensity * variation
                bar_h = max(3, pulse * (H * 0.55) * vol_factor)
                x0 = margin + i * slot_w + (slot_w - bar_w) / 2
                x1 = x0 + bar_w
                y1 = H - 12
                y0 = y1 - bar_h
                col = mix(base, ACC, 0.25 + 0.65 * pulse)
                c.create_rectangle(x0, y0, x1, y1, fill=col, outline="")

    def render(self):
        try:
            self._render()
        except Exception:
            traceback.print_exc()
        self.after(35 if self.mp.is_playing() else 120, self.render)

    # ---------- Animações de Letras ----------
    def anim_atual(self):
        aid = self.anim_sel.get()
        if aid:
            anim = self.lpp.animacao(aid)
            if anim is not None:
                return anim, aid
        return None, ""

    def anim_cfg(self, aid):
        if not aid:
            return {}
        return self.lpp.state["config"].setdefault("_anim:" + aid, {})

    def salvar_anim_escolha(self):
        self.p_cfg["animacao"] = self.anim_sel.get()
        self.lpp.save_state()

    def set_anim(self):
        self.anim_rev += 1
        self.last_sig = None
        self.salvar_anim_escolha()
        anim, aid = self.anim_atual()
        self.say("Animação das letras: " + (str(getattr(anim, "nome", aid)) if anim else "nenhuma"))

    def anim_falhou(self, aid, onde):
        self.lpp.log("animação", f"{aid} falhou em {onde}:\n" + traceback.format_exc())
        self.anim_sel.set("")
        self.anim_rev += 1
        self.salvar_anim_escolha()

    def fill_anim_menu(self, m):
        m.delete(0, "end")
        m.add_radiobutton(label="Nenhuma (letra simples)", variable=self.anim_sel,
                          value="", command=self.set_anim)
        lista = self.lpp.animacoes()
        for aid, anim, _ in lista:
            m.add_radiobutton(label=str(getattr(anim, "nome", aid)), variable=self.anim_sel,
                              value=aid, command=self.set_anim)

    def open_anim_options(self):
        anim, aid = self.anim_atual()
        if anim is None:
            self.say("Escolha uma animação em Letras > Animação das letras.")
            return
        opcoes = list(getattr(anim, "opcoes", None) or [])
        if not opcoes:
            self.say("Esta animação não tem opções.")
            return
        w = ToplevelMovel(self)
        w.title("Opções - " + str(getattr(anim, "nome", aid)))
        w.configure(bg=BG)
        w.transient(self)
        w.resizable(False, False)
        cfg = self.anim_cfg(aid)
        for lin, o in enumerate(opcoes):
            chave, tipo = o["chave"], o.get("tipo", "int")
            atual = cfg.get(chave, o.get("padrao"))
            tk.Label(w, text=o.get("rotulo", chave), fg=FG, bg=BG).grid(row=lin, column=0, sticky="w", padx=10, pady=5)
            if tipo == "bool":
                var = tk.BooleanVar(value=bool(atual))
                wd = tk.Checkbutton(w, variable=var, bg=BG, fg=FG, activebackground=BG, selectcolor=BG2)
            else:
                var = tk.StringVar(value=str(atual))
                wd = tk.Spinbox(w, from_=o.get("min", 0), to=o.get("max", 99999),
                                textvariable=var, width=8, bg=BG2, fg=FG, bd=0)
            wd.grid(row=lin, column=1, padx=10, pady=5)

            def bind_var(k=chave, t=tipo, v=var):
                def _cb(*_):
                    try:
                        cfg[k] = bool(v.get()) if t == "bool" else int(float(v.get()))
                        self.anim_rev += 1
                        self.last_sig = None
                        self.lpp.save_state()
                    except Exception:
                        pass
                v.trace_add("write", _cb)

            bind_var()

    def desenhar_vizinhas(self, ctx, op_prev, op_next):
        # SPRITE: LETRAS VIZINHAS — linha anterior e próxima, acima/abaixo da letra atual.
        lines, n, idx = self.lyr, len(self.lyr), ctx.indice
        f_sm = self.font(max(12, int(ctx.px * 0.6)), False)
        gap = int(ctx.px * 0.7)
        for i, acima, op in ((idx - 1, True, op_prev), (idx + 1, False, op_next)):
            if 0 <= i < n and op > 0.01:
                t = " ".join(lines[i][1].split()) or "♪"
                rows, lh, h = self.layout(t, f_sm, ctx.max_largura)
                y = (ctx.cy - ctx._cur_h / 2 - gap - h / 2) if acima else \
                    (ctx.cy + ctx._cur_h / 2 + gap + h / 2)
                self.paint(rows, lh, ctx.cx, y, f_sm,
                           mix(ctx.cor_fundo, ctx.cor_vizinha, ctx._clamp(op)))

    def _lyrics_index(self, lines, synced, times, pos, length):
        if not lines:
            return -1
        if synced:
            return bisect.bisect_right(times, max(0, pos)) - 1
        if length > 0:
            return min(len(lines) - 1, int(max(0, pos) / length * len(lines)))
        return 0

    def _render_dual_columns(self, c, W, H, top, pos, length):
        """Mobile (retrato): original em cima e tradução embaixo, cada uma com seu sincronismo."""
        area_top = top if top else 0
        sec_h = (H - area_top) / 2
        px = int(max(18, min(40 if self.immersive else 30, W / 17, sec_h / 4.2)))
        f = self.font(px, True)
        fsmall = self.font(max(11, int(px * .62)), False)
        entries = [
            ("ORIGINAL", self.lyr, self.lyr_synced, self.lyr_times,
             pos - self.lyr_delay_ms),
            ("TRADUÇÃO", self.lyr_translation, self.lyr_translation_synced,
             self.lyr_translation_times, pos - self.lyr_translation_delay_ms),
        ]
        cx = W / 2
        c.create_line(14, area_top + sec_h, W - 14, area_top + sec_h, fill="#343434", width=1)
        for sec, (label, lines, synced, times, local_pos) in enumerate(entries):
            y0 = area_top + sec * sec_h
            cy = y0 + sec_h / 2 + 8
            c.create_text(cx, y0 + 6, text=label, fill=ACC, font=self.font(10, True), anchor="n")
            if not lines:
                c.create_text(cx, cy, text=("Tradução não carregada" if sec else "Letra original não carregada"),
                              fill=DIM, font=self.font(15, False), width=W * .9, justify="center")
                continue
            idx = self._lyrics_index(lines, synced, times, local_pos, length)
            if idx < 0:
                c.create_text(cx, cy, text="♪", fill=DIM, font=f)
                continue
            if sec_h >= 140:
                for neighbor, y in ((idx - 1, cy - px * 1.9), (idx + 1, cy + px * 1.9)):
                    if 0 <= neighbor < len(lines):
                        txt = " ".join(lines[neighbor][1].split())
                        c.create_text(cx, y, text=txt, fill="#777777", font=fsmall,
                                      width=W * .9, justify="center")
            current = " ".join(lines[idx][1].split()) or "♪"
            c.create_text(cx, cy, text=current, fill=WHITE, font=f,
                          width=W * .9, justify="center")

    def _render(self):
        if not self.canvas_visible or getattr(self, "_lista_visivel", False):
            return
        c = self.canvas
        W, H = c.winfo_width(), c.winfo_height()
        if W < 60 or H < 60:
            return
        pos = max(0, self.mp.get_time() + self.lyr_offset_ms)
        length = self.mp.get_length()
        lines, n = self.lyr, len(self.lyr)

        idx, elapsed, dur = -1, 0, 6000
        if lines:
            if self.lyr_synced:
                idx = bisect.bisect_right(self.lyr_times, pos) - 1
                if idx >= 0:
                    start = self.lyr_times[idx]
                    elapsed = pos - start
                    if idx + 1 < n:
                        dur = self.lyr_times[idx + 1] - start
                    elif length > start:
                        dur = length - start
            elif length > 0:
                idx = min(n - 1, int(pos / length * n))
                dur = length / n
                elapsed = pos - idx * dur
        dur = max(200, dur)

        text = lines[idx][1] if (lines and idx >= 0) else ""
        norm = " ".join(text.split()) or "♪"
        px = int(max(22, min(64 if self.immersive else 46, W / 15)))
        anim, aid = self.anim_atual() if (lines and idx >= 0) else (None, "")
        ctx = AnimCtx(self, anim, aid, W, H, px, text, norm, idx, n, elapsed, dur,
                      pos, self.lyr_synced)
        bg = self.build_bg(W, H) if self.immersive else None
        if bg is not None:
            ctx.cor_fundo = self.bg_avg

        vis_active = self.var_vis_beta.get() and self.mp.is_playing()
        ativa = vis_active or (self.lyrics_view.get() == "both" and bool(self.lyr_translation)) \
                or self.lyrics_view.get() == "translation"
        if anim is not None:
            try:
                fn = getattr(anim, "animando", None)
                ativa = ativa or (bool(fn(ctx)) if callable(fn) else elapsed < 1000)
            except Exception:
                self.anim_falhou(aid, "animando")
                anim, aid = None, ""

        bass_now, _bass_db = self.bass_analyzer.snapshot()
        sig = (W, H, idx, id(self.cover_src), aid, self.anim_rev,
               self.var_vis_beta.get(), self.var_vis_modo.get(), self.immersive,
               round(bass_now, 2) if (ativa or anim is not None) else None,
               pos if ativa else None)
        if sig == self.last_sig:
            return
        self.last_sig = sig

        c.delete("all")

        # SPRITE: FUNDO DESFOCADO — imagem da capa usada no modo de tela cheia imersiva.
        if bg is not None:
            c.create_image(0, 0, image=bg, anchor="nw")

        self.draw_background_visualization(c, W, H, pos)

        # SPRITE: CAPA DO ÁLBUM — aparece no topo do canvas quando há capa disponível.
        top = 0
        if self.cover_src:
            s = int(max(60, min(W * 0.70, H * 0.36)))
            if abs(s - self.cover_built) >= 6:
                self.build_cover(s)
            if self.cover_img:
                c.create_image(W / 2, 14 + self.cover_img.height() / 2, image=self.cover_img)
                top = self.cover_img.height() + 28
            elif self.cover_hint:
                # SPRITE: AVISO DE CAPA — dica de instalação do Pillow quando a capa não pode ser exibida.
                c.create_text(W / 2, 12, anchor="n", fill=DIM, font=self.font(12, False),
                              text="Capa em JPG: instale com  pip install pillow")

        cy = (top + H) / 2 if top else H / 2
        cx = W / 2

        if self.lyrics_view.get() == "both" and self.lyr_translation:
            self._render_dual_columns(c, W, H, top, self.mp.get_time(), length)
            return

        if self.lyrics_view.get() == "translation":
            lines, n = self.lyr_translation, len(self.lyr_translation)
            pos = max(0, self.mp.get_time() - self.lyr_translation_delay_ms)
            synced = self.lyr_translation_synced
            times = self.lyr_translation_times
            idx = self._lyrics_index(lines, synced, times, pos, length)
            if not lines:
                c.create_text(cx, cy, text="Tradução não carregada", fill=DIM, font=self.font(18))
                return
            text = lines[idx][1] if idx >= 0 else "♪"
            c.create_text(cx, cy, text=text, fill=WHITE, font=self.font(int(max(22, min(46, W / 15)))),
                          width=W * .86, justify="center")
            return

        # SPRITE: ESTADO SEM LETRAS — mostra o nome da faixa quando Lyrics+ está vazio.
        if not lines:
            name = "♪"
            if 0 <= self.index < len(self.playlist):
                name = os.path.splitext(os.path.basename(self.playlist[self.index]))[0]
            # SPRITE: NOME DA FAIXA — texto central exibido quando nenhuma letra está carregada.
            c.create_text(cx, cy, text=name, fill=WHITE, font=self.font(24),
                          width=W * 0.86, justify="center")
            return

        ctx.preparar(cx, cy)
        if anim is None:
            ctx.pintar_vizinhas()
            if idx >= 0:
                ctx.pintar_texto()
            return
        try:
            if not getattr(anim, "controla_vizinhas", False):
                ctx.pintar_vizinhas()
            anim.desenhar(ctx)
        except Exception:
            self.anim_falhou(aid, "desenhar")

    # ---------- Reprodução ----------
    def play(self, i):
        if not (0 <= i < len(self.playlist)):
            return
        self.index = i
        path = self.playlist[i]
        self.mp.set_media(self.instance.media_new(path))
        self.mp.play()
        self.btn_play.config(text="⏸")
        self.label.config(text=os.path.basename(path))
        self.current_file = path
        self.refresh_list()
        self.load_extras(path)
        self._ended_seen = False
        self.lpp.emit("ao_iniciar_faixa", path)

    def on_dbl(self, _):
        sel = self.listbox.curselection()
        if sel and sel[0] < len(self.display_rows):
            kind, value = self.display_rows[sel[0]]
            if kind == "track" and value in self.playlist:
                self.play(self.playlist.index(value))

    def toggle(self):
        if self.mp.get_state() in (vlc.State.NothingSpecial, vlc.State.Stopped,
                                   vlc.State.Ended) and self.playlist:
            self.play(max(self.index, 0))
            return
        self.mp.pause()
        self.btn_play.config(text="▶" if self.mp.is_playing() else "⏸")

    def stop(self):
        self.mp.stop()
        self.btn_play.config(text="▶")
        self.t_cur.config(text="00:00")
        self.last_sig = None
        self._ended_seen = False
        self.render_prog_bar(override_frac=0.0)
        self.lpp.emit("ao_parar")

    def next(self, auto=False):
        if not self.playlist:
            return
        if auto and self.repeat.get() == "one":
            self.play(self.index)
        elif self.shuffle.get() and len(self.playlist) > 1:
            n = self.index
            while n == self.index:
                n = random.randrange(len(self.playlist))
            self.play(n)
        elif self.index + 1 < len(self.playlist):
            self.play(self.index + 1)
        elif self.repeat.get() == "all" or not auto:
            self.play(0)
        else:
            self.stop()

    def prev(self):
        if self.mp.get_time() > 3000:
            self.mp.set_time(0)
        elif self.index > 0:
            self.play(self.index - 1)

    def jump(self, ms):
        self.mp.set_time(max(0, self.mp.get_time() + ms))

    def toggle_shuffle(self):
        self.shuffle.set(not self.shuffle.get())
        self.btn_shuf.config(fg=ACC if self.shuffle.get() else FG)

    def cycle_repeat(self):
        order = ["off", "all", "one", "instant"]
        nxt = order[(order.index(self.repeat.get()) + 1) % len(order)]
        self.repeat.set(nxt)
        self.sync_buttons()

    # ---------- Tela cheia imersiva ----------
    def toggle_fullscreen(self):
        self.toggle_immersive()

    def toggle_immersive(self):
        if self.immersive:
            self.exit_immersive()
        else:
            self.enter_immersive()

    def enter_immersive(self):
        if self.immersive:
            return
        self.immersive = True
        self._topbar.pack_forget()
        if self._menubar_visivel:
            self._menubar_frame.pack_forget()
        self._bottom.pack_forget()
        self.mostrar_player()
        # Só usa tela cheia de verdade se a própria tela já for em pé (mantém o retrato).
        if self.winfo_screenheight() > self.winfo_screenwidth():
            self.attributes("-fullscreen", True)
        self.last_sig = None
        self._fs_ui = True
        self._atualizar_botao_fs()
        self._fs_motion()

    def exit_immersive(self):
        if not self.immersive:
            return
        self.immersive = False
        if self._fs_job is not None:
            self.after_cancel(self._fs_job)
            self._fs_job = None
        try:
            self.attributes("-fullscreen", False)
        except Exception:
            pass
        self._topbar.pack(side="top", fill="x", before=self._content)
        if self._menubar_visivel:
            self._menubar_frame.pack(side="top", fill="x", after=self._topbar)
        self._bottom.pack(side="bottom", fill="x", before=self._content)
        self.canvas.config(cursor="")
        self._fs_ui = True
        self.last_sig = None
        self._atualizar_botao_fs()

    def _criar_botao_fs(self):
        b = self.fs_btn = tk.Canvas(self.video, width=44, height=44, bg="#1b1b1b",
                                    highlightthickness=1, highlightbackground="#333333",
                                    cursor="hand2")
        b.bind("<Button-1>", lambda e: self.toggle_immersive())
        b.bind("<Enter>", lambda e: self._icone_fs(True))
        b.bind("<Leave>", lambda e: self._icone_fs(False))
        b.bind("<Motion>", self._fs_motion)
        self._icone_fs()

    def _icone_fs(self, hover=None):
        if hover is not None:
            self._fs_hover = hover
        b = self.fs_btn
        col = ACC if self._fs_hover else "#d0d0d0"
        b.delete("all")
        b.config(bg="#262626" if self._fs_hover else "#1b1b1b")
        if not self.immersive:
            for x, y, dx, dy in ((9, 9, 1, 1), (27, 9, -1, 1), (9, 27, 1, -1), (27, 27, -1, -1)):
                # SPRITE: CONTROLE DE CANTO — marca visual do botão de tela cheia.
                b.create_line(x, y + dy * 7, x, y, x + dx * 7, y, fill=col, width=2)
        else:
            for x, y, dx, dy in ((14, 14, -1, -1), (22, 14, 1, -1), (14, 22, -1, 1), (22, 22, 1, 1)):
                # SPRITE: SEGUNDO TRAÇO DO CONTROLE DE CANTO — completa o símbolo de tela cheia.
                b.create_line(x + dx * 7, y, x, y, x, y + dy * 7, fill=col, width=2)
        b.move("all", 4, 4)

    def _atualizar_botao_fs(self):
        if not hasattr(self, "fs_btn"):
            return
        self._icone_fs()
        if self.canvas_visible and (not self.immersive or self._fs_ui):
            self.fs_btn.place(relx=1.0, x=-10, y=10, anchor="ne")
            # Canvas.lift() e interpretado como Canvas.tag_raise(); para elevar a janela,
            # use o comando Tcl de empilhamento de janelas, passando o widget.
            self.fs_btn.tk.call('raise', self.fs_btn._w)
        else:
            self.fs_btn.place_forget()

    def _fs_motion(self, _event=None):
        if not self.immersive:
            return
        if not self._fs_ui:
            self._fs_ui = True
            self.canvas.config(cursor="")
            self._atualizar_botao_fs()
        if self._fs_job is not None:
            self.after_cancel(self._fs_job)
        self._fs_job = self.after(2500, self._fs_hide)

    def _fs_hide(self):
        self._fs_job = None
        if self.immersive:
            self._fs_ui = False
            self.canvas.config(cursor="none")
            self._atualizar_botao_fs()

    def build_bg(self, W, H):
        key = (id(self.cover_src), len(self.cover_src or b""), W, H)
        if key == self.bg_key:
            return self.bg_img
        self.bg_key, self.bg_img, self.bg_avg = key, None, CBG
        if not self.cover_src or Image is None or ImageFilter is None:
            return None
        try:
            res = getattr(Image, "Resampling", Image)
            im = Image.open(io.BytesIO(self.cover_src)).convert("RGB")
            w0, h0 = im.size
            ar = W / H
            if w0 / h0 > ar:
                nw = int(h0 * ar)
                x0 = (w0 - nw) // 2
                im = im.crop((x0, 0, x0 + nw, h0))
            else:
                nh = int(w0 / ar)
                y0 = (h0 - nh) // 2
                im = im.crop((0, y0, w0, y0 + nh))
            small = im.resize((192, max(8, int(192 / ar))), res.BILINEAR)
            small = small.filter(ImageFilter.GaussianBlur(9))
            small = ImageEnhance.Brightness(small).enhance(0.40)
            r, g, b = small.resize((1, 1), res.BILINEAR).getpixel((0, 0))
            self.bg_avg = "#%02x%02x%02x" % (r, g, b)
            self.bg_img = ImageTk.PhotoImage(small.resize((W, H), res.BICUBIC))
        except Exception:
            self.bg_img, self.bg_avg = None, CBG
        return self.bg_img

    def on_volume(self, v):
        self.mp.audio_set_volume(int(float(v)))

    def tick(self):
        state = self.mp.get_state()
        if state == vlc.State.Ended:
            if not self._ended_seen:
                self._ended_seen = True
                if not self.lpp.emit("ao_fim_da_faixa", self.current_file):
                    self.next(auto=True)
        else:
            if state == vlc.State.Playing:
                self._ended_seen = False
            if state in (vlc.State.Playing, vlc.State.Paused):
                self.t_cur.config(text=fmt(self.mp.get_time()))
                self.t_tot.config(text=fmt(self.mp.get_length()))
            self.render_prog_bar()
        self.after(200, self.tick)

    # ---------- Host para Plugins ----------
    def confirmar(self, titulo, texto):
        return messagebox.askyesno(titulo, texto, icon="warning", parent=self)

    def say(self, texto):
        self.status.config(text=texto)
        if self._say_job:
            self.after_cancel(self._say_job)
        self._say_job = self.after(6000, lambda: self.status.config(text=""))

    def current_path(self):
        return self.current_file

    def play_path(self, path, titulo=None):
        self.mp.set_media(self.instance.media_new(path))
        self.mp.play()
        self._ended_seen = False
        self.btn_play.config(text="⏸")
        if titulo:
            self.label.config(text=titulo)

    def run_in_ui(self, fn):
        self._ui_q.put(fn)

    def pump(self):
        try:
            while True:
                self.plugin_call(self._ui_q.get_nowait())
        except queue.Empty:
            pass
        self.after(80, self.pump)

    def plugin_call(self, fn, *args):
        try:
            fn(*args)
        except Exception:
            self.lpp.log("menu", traceback.format_exc())

    def plugin_toggle(self, item):
        item["estado"] = bool(item["var"].get())
        self.plugin_call(item["cb"], item["estado"])

    def on_close(self):
        try:
            self.lpp.emit("ao_fechar")
        except Exception:
            pass
        self.lpp.unload_all()
        try:
            self.bass_analyzer.close()
        except Exception:
            pass
        try:
            self.mp.stop()
        except Exception:
            pass
        self.destroy()

    # ---------- Menus ----------  identificador: barra 
    def mk(self, parent):
        return tk.Menu(parent, tearoff=0, font=FONTE_MENU)

    def build_menus(self):
        # Sem barra de menus nativa: a barra aparece ao tocar no botão ☰ (ver _montar_barra_menus).
        self.menubar = None
        self.ctx = self.mk(self)
        self.ctx.add_cascade(label="Visualizações", menu=self.menu_visualizacoes(self.ctx))
        self.ctx.add_cascade(label="Letras", menu=self.menu_letras(self.ctx))
        self.ctx.add_separator()
        self.ctx.add_command(label="Adicionar Musicas...", command=self.add_files)
        self.ctx.add_command(label="Adicionar pasta de musicas...", command=self.add_folder)
        self.ctx.add_separator()
        self.ctx.add_cascade(label="Reproduzir", menu=self.menu_reproduzir(self.ctx))
        self.ctx.add_cascade(label="Capas", menu=self.menu_capas(self.ctx))
        self.ctx.add_cascade(label="Plugins", menu=self.menu_plugins(self.ctx))

    def menu_visualizacoes(self, parent):
        m = self.mk(parent)
        for modo in ("Ondas", "Fade de grave", "Barras"):
            m.add_radiobutton(
                label=modo,
                variable=self.var_vis_modo,
                value=modo,
                command=lambda md=modo: self.select_vis_mode(md)
            )
        m.add_separator()
        m.add_command(label="Configurar Visualizações...", command=self.open_settings_window)
        return m

    def select_vis_mode(self, modo):
        self.p_cfg["vis_modo"] = modo
        if not self.var_vis_beta.get():
            self.var_vis_beta.set(True)
            self.p_cfg["habilitar_vis"] = True
        self.lpp.save_state()
        self.last_sig = None
        self.say(f"Visualização: {modo}")

    def toggle_vis_beta(self):
        self.p_cfg["habilitar_vis"] = bool(self.var_vis_beta.get())
        self.lpp.save_state()
        self.last_sig = None
        self.say("Visualizações (BETA): " + ("Habilitada" if self.p_cfg["habilitar_vis"] else "Desabilitada"))

    def toggle_wave_beta(self):
        self.p_cfg["wave_bar_beta"] = bool(self.var_wave_beta.get())
        self.lpp.save_state()
        self.render_prog_bar()
        self.say("Barra de ondas na linha do tempo (BETA): " + ("Habilitada" if self.p_cfg["wave_bar_beta"] else "Desabilitada"))

    def menu_config(self, parent):
        m = self.mk(parent)
        settings_sub = self.mk(m)
        settings_sub.add_checkbutton(
            label="Habilitar visualizações (BETA)",
            variable=self.var_vis_beta,
            command=self.toggle_vis_beta
        )
        settings_sub.add_checkbutton(
            label="Barra de ondas na linha do tempo (BETA)",
            variable=self.var_wave_beta,
            command=self.toggle_wave_beta
        )
        settings_sub.add_separator()
        settings_sub.add_command(label="Visualizações...", command=self.open_settings_window)

        m.add_cascade(label="Settings", menu=settings_sub)
        m.add_command(label="Abrir Janela de Configurações...", command=self.open_settings_window)
        m.add_separator()
        m.add_command(label="Sobre o Lena's Player...", command=self.about)
        return m

    def open_settings_window(self):
        old = getattr(self, "_cfg_win", None)
        if old is not None and old.winfo_exists():
            old.lift()
            return
        w = self._cfg_win = ToplevelMovel(self)
        w.title("Configurações - Lena's Player Beta V5.5")
        w.geometry("460x410")
        w.configure(bg=BG)
        w.transient(self)
        w.resizable(False, False)

        frm_vis = tk.LabelFrame(w, text=" Visualizações ", bg=BG, fg=ACC, font=("Segoe UI", 10, "bold"), padx=12, pady=10)
        frm_vis.pack(fill="x", padx=14, pady=(12, 8))

        tk.Checkbutton(
            frm_vis, text="Habilitar visualizações (BETA)",
            variable=self.var_vis_beta, command=self.toggle_vis_beta,
            bg=BG, fg=FG, activebackground=BG, activeforeground=WHITE, selectcolor=BG2
        ).pack(anchor="w")

        row_modo = tk.Frame(frm_vis, bg=BG)
        row_modo.pack(fill="x", pady=(8, 4))
        tk.Label(row_modo, text="Estilo ativo (Files/Animations):", bg=BG, fg=FG).pack(side="left")
        cb_modo = ttk.Combobox(row_modo, textvariable=self.var_vis_modo,
                               values=["Ondas", "Fade de grave", "Barras"], state="readonly", width=18)
        cb_modo.pack(side="right")
        cb_modo.bind("<<ComboboxSelected>>", lambda e: self.select_vis_mode(self.var_vis_modo.get()))

        row_bars = tk.Frame(frm_vis, bg=BG)
        row_bars.pack(fill="x", pady=4)
        tk.Label(row_bars, text="Barras - Quantidade (máx 15):", bg=BG, fg=FG).pack(side="left")
        var_bars = tk.IntVar(value=int(self.p_cfg.get("vis_barras_max", 12)))
        sp_bars = tk.Spinbox(row_bars, from_=1, to=15, textvariable=var_bars, width=6, bg=BG2, fg=FG, bd=0)
        sp_bars.pack(side="right")

        def save_bars(*_):
            try:
                v = max(1, min(15, int(var_bars.get())))
                self.p_cfg["vis_barras_max"] = v
                self.lpp.save_state()
                self.last_sig = None
            except Exception:
                pass
        var_bars.trace_add("write", save_bars)

        row_bass = tk.Frame(frm_vis, bg=BG)
        row_bass.pack(fill="x", pady=4)
        tk.Label(row_bass, text="Fade de grave - Intensidade (%):", bg=BG, fg=FG).pack(side="left")
        var_bass = tk.IntVar(value=int(self.p_cfg.get("vis_fade_sens", 75)))
        sp_bass = tk.Spinbox(row_bass, from_=10, to=150, textvariable=var_bass, width=6, bg=BG2, fg=FG, bd=0)
        sp_bass.pack(side="right")

        def save_bass(*_):
            try:
                v = max(10, min(150, int(var_bass.get())))
                self.p_cfg["vis_fade_sens"] = v
                self.lpp.save_state()
                self.last_sig = None
            except Exception:
                pass
        var_bass.trace_add("write", save_bass)

        frm_tl = tk.LabelFrame(w, text=" Linha do Tempo ", bg=BG, fg=ACC, font=("Segoe UI", 10, "bold"), padx=12, pady=10)
        frm_tl.pack(fill="x", padx=14, pady=8)

        tk.Checkbutton(
            frm_tl, text="Barra de ondas na linha do tempo (BETA)",
            variable=self.var_wave_beta, command=self.toggle_wave_beta,
            bg=BG, fg=FG, activebackground=BG, activeforeground=WHITE, selectcolor=BG2
        ).pack(anchor="w")
        tk.Label(frm_tl, text="Cores dinâmicas: Vermelho (alto), Amarelo (médio), Azul (baixo).",
                 bg=BG, fg=DIM, font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))

        self.btn(w, "Fechar", w.destroy).pack(pady=10)

    def menu_arquivo(self, parent):
        m = self.mk(parent)
        m.add_command(label="Adicionar arquivos...", command=self.add_files)
        m.add_command(label="Adicionar pasta...", command=self.add_folder)
        m.add_separator()
        m.add_command(label="Abrir playlist (.m3u)...", command=self.load_playlist)
        m.add_command(label="Salvar playlist (.m3u)...", command=self.save_playlist)
        m.add_command(label="Limpar playlist", command=self.clear)
        m.add_separator()
        m.add_command(label="Sair", command=self.on_close)
        return m

    def menu_reproduzir(self, parent):
        m = self.mk(parent)
        m.add_command(label="Play / Pause   (Espaço)", command=self.toggle)
        m.add_command(label="Parar", command=self.stop)
        m.add_command(label="Anterior   (P)", command=self.prev)
        m.add_command(label="Próxima   (N)", command=self.next)
        m.add_separator()
        m.add_checkbutton(label="Aleatório", variable=self.shuffle, command=self.sync_buttons)
        rep = self.mk(m)
        for val, lab in (("off", "Desligado"), ("all", "Repetir tudo"),
                         ("one", "Repetir uma faixa"), ("instant", "Instant Loop (plugin)")):
            rep.add_radiobutton(label=lab, variable=self.repeat, value=val, command=self.sync_buttons)
        m.add_cascade(label="Repetir", menu=rep)
        m.add_separator()
        m.add_command(label="Tela cheia   (F)", command=self.toggle_fullscreen)
        return m

    def remove_lyrics_plus(self):
        self.set_lyrics([], False, "Lyrics+: nenhuma")
        self._set_translation(None)
        self.lyrics_view.set("original")

    def menu_letras(self, parent):
        m = self.mk(parent)
        m.add_command(label="Carregar letras (.txt / .lcr / .lrc)...", command=self.pick_lyrics)
        m.add_command(label="Abrir Lyrics+ Studio (Editor)...", command=self.open_lyrics_plus_editor)
        m.add_command(label="Abrir pasta Files/Lyrics", command=lambda: os.startfile(self.lyrics_dir))
        m.add_separator()
        vis = self.mk(m)
        for val, lab in (("original", "Original"), ("translation", "Tradução"), ("both", "Ambas (lado a lado)")):
            vis.add_radiobutton(label=lab, variable=self.lyrics_view, value=val,
                                command=lambda: setattr(self, "last_sig", None))
        m.add_cascade(label="Exibição", menu=vis)
        m.add_separator()
        alvo = self.mk(m)
        alvo.add_radiobutton(label="Ajustar original", variable=self.lyrics_delay_target, value="original",
                             command=lambda: self.selecionar_alvo_atraso("original"))
        alvo.add_radiobutton(label="Ajustar tradução", variable=self.lyrics_delay_target, value="translation",
                             command=lambda: self.selecionar_alvo_atraso("translation"))
        m.add_cascade(label="Arquivo do atraso", menu=alvo)
        m.add_command(label="Atraso das letras (ms)...", command=self.open_lyrics_delay_window)
        m.add_command(label="Atrasar letras (+100 ms)", command=lambda: self.nudge_lyrics_delay(100))
        m.add_command(label="Adiantar letras (-100 ms)", command=lambda: self.nudge_lyrics_delay(-100))
        m.add_command(label="Zerar atraso", command=lambda: self.set_lyrics_delay(0))
        m.add_command(label="Remover letras", command=self.remove_lyrics_plus)
        m.add_separator()
        an = self.mk(m)
        an.config(postcommand=lambda: self.fill_anim_menu(an))
        m.add_cascade(label="Animação das letras (.lpla)", menu=an)
        m.add_command(label="Opções da animação...", command=self.open_anim_options)
        return m

    def menu_capas(self, parent):
        m = self.mk(parent)
        m.add_command(label="Carregar capa...", command=self.pick_cover)
        m.add_command(label="Remover capa", command=lambda: (setattr(self, "cover_src", None), setattr(self, "last_sig", None)))
        return m

    def menu_playlists(self, parent):
        m = self.mk(parent)
        m.add_command(label="Adicionar playlist da lista...", command=self.add_saved_playlist)
        m.add_command(label="Importar arquivo .m3u...", command=self.load_playlist)
        m.add_command(label="Salvar playlist atual...", command=self.save_playlist)
        m.add_command(label="Abrir pasta Files/Playlists", command=lambda: os.startfile(self.playlists_dir))
        return m

    def aplicar_icone(self):
        p = find_app_icon()
        if not p:
            return
        try:
            with open(p, "rb") as f:
                eh_ico = f.read(4) == b"\x00\x00\x01\x00"
        except OSError:
            return
        if eh_ico:
            try:
                self.iconbitmap(p)
                return
            except Exception:
                pass
        foto = foto_do_arquivo(p, 64)
        if foto is not None:
            try:
                self._icone_janela = foto
                self.iconphoto(True, foto)
            except Exception:
                pass

    def _fonte_assinatura(self, tam):
        try:
            fams = set(tkfont.families())
        except Exception:
            fams = set()
        for f in ("Segoe Script", "Lucida Handwriting", "Brush Script MT", "Ink Free", "Lucida Calligraphy"):
            if f in fams:
                return (f, tam)
        return ("Segoe UI", tam, "italic")

    def about(self):
        w0 = getattr(self, "_about_win", None)
        if w0 is not None and w0.winfo_exists():
            w0.lift()
            return
        w = self._about_win = ToplevelMovel(self)
        w.title(f"Sobre o {APP_NOME}")
        w.configure(bg=BG)
        # Ícone da janela Sobre: usa o mesmo arquivo Lena.icon da janela principal.
        try:
            if getattr(self, "_icone_janela", None) is not None:
                w.iconphoto(True, self._icone_janela)
            elif find_app_icon():
                w.iconbitmap(find_app_icon())
        except Exception:
            pass
        w.resizable(False, False)
        w.transient(self)
        logo = foto_do_arquivo(find_app_icon(), 96)
        # SPRITE: LOGO DO PLAYER — ícone no topo da janela "Sobre o Lena's Player".
        if logo is not None:
            w._logo = logo
            tk.Label(w, image=logo, bg=BG).pack(pady=(18, 6))
        else:
            cv = tk.Canvas(w, width=96, height=96, bg=BG, highlightthickness=0)
            # SPRITE: ÍCONE ALTERNATIVO DO SOBRE — círculo e nota musical quando Lena.icon não existe.
            cv.create_oval(6, 6, 90, 90, fill=BG2, outline=ACC, width=2)
            cv.create_text(48, 50, text="\u266a", fill=ACC, font=("Segoe UI", 34, "bold"))
            cv.pack(pady=(18, 6))
        tk.Label(w, text=APP_NOME, bg=BG, fg=WHITE, font=("Segoe UI", 18, "bold")).pack()
        tk.Label(w, text=f"{APP_VERSAO}  (Lyrics+ Edition)", bg=BG, fg=ACC,
                 font=("Segoe UI", 10)).pack(pady=(0, 10))
        tk.Label(w, justify="left", bg=BG, fg=FG, font=("Segoe UI", 9), text=(
            "\u2022 Visualizações de fundo (Ondas, Fade de grave, Barras)\n"
            "\u2022 Linha do tempo com preview HH:MM:SS e Barra de Ondas BETA\n"
            "\u2022 Animações .lpla em Files/Animations\n"
            "\u2022 Lyrics+: letras automáticas (nome igual ou parecido) e atraso em ms por arquivo\n"
            "\u2022 Tela cheia com a capa desfocada ao fundo\n"
            "\u2022 Plugins .lpp em Plugins")).pack(padx=26)
        tk.Frame(w, bg="#333333", height=1).pack(fill="x", padx=26, pady=(14, 8))
        tk.Label(w, text="Criado por", bg=BG, fg=DIM, font=("Segoe UI", 8)).pack()
        # SPRITE: ASSINATURA DO CRIADOR — imagem abaixo de "Criado por" na janela Sobre.
        ass = foto_do_arquivo(_pasta_files_arquivo(ASSINATURA_ARQUIVOS), 220)
        if ass is not None:
            w._ass = ass
            tk.Label(w, image=ass, bg=BG).pack(pady=(0, 4))
        else:
            tk.Label(w, text=ASSINATURA_TEXTO, bg=BG, fg=WHITE,
                     font=self._fonte_assinatura(24)).pack(pady=(0, 4))
        self.btn(w, "Fechar", w.destroy).pack(pady=(8, 16))
        w.update_idletasks()
        try:
            x = self.winfo_rootx() + (self.winfo_width() - w.winfo_width()) // 2
            y = self.winfo_rooty() + (self.winfo_height() - w.winfo_height()) // 3
            w.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def menu_plugins(self, parent):
        m = self.mk(parent)
        m.config(postcommand=lambda: self.fill_plugins_menu(m))
        return m

    def fill_plugins_menu(self, m):
        # Os comandos principais são reconstruídos primeiro e nunca dependem de plugins.
        m.delete(0, "end")
        m.add_command(label="Gerenciar plugins...", command=self.open_plugin_manager)
        m.add_command(label="Recarregar plugins", command=self.reload_plugins)
        m.add_command(label="Abrir pasta Plugins", command=self.open_plugin_folder)
        m.add_separator()
        m.add_command(label="Abrir log de plugins...", command=self.open_plugin_log)
        m.add_separator()
        try:
            groups = self.lpp.menu_groups()
        except Exception:
            self.lpp.log("menu", "não consegui montar o menu de plugins:\n" + traceback.format_exc())
            groups = []
        if not groups:
            m.add_command(label="(nenhum plugin com menu)", state="disabled")
        for nome, items in groups:
            sub = self.mk(m)
            for it in items:
                if it["tipo"] == "chk":
                    if it.get("var") is None:
                        it["var"] = tk.BooleanVar(value=it["estado"])
                    sub.add_checkbutton(label=it["rotulo"], variable=it["var"],
                                        command=lambda it=it: self.plugin_toggle(it))
                else:
                    sub.add_command(label=it["rotulo"],
                                    command=lambda it=it: self.plugin_call(it["cb"]))
            m.add_cascade(label=nome, menu=sub)

    def sync_buttons(self):
        self.btn_shuf.config(fg=ACC if self.shuffle.get() else FG)
        r = self.repeat.get()
        self.btn_rep.config(text=f"🔁 {r}", fg=ACC if r != "off" else FG)
        if hasattr(self, "lpp"):
            self.lpp.emit("ao_modo_repeticao", r)

    def show_ctx(self, e):
        try:
            self.ctx.tk_popup(e.x_root, e.y_root)
        finally:
            self.ctx.grab_release()

    def ctx_list(self, e):
        if self.listbox.size() > 0:
            i = self.listbox.nearest(e.y)
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(i)
        m = self.mk(self)
        m.add_command(label="Remover da lista", command=self.remove_selected)
        m.add_command(label="Renomear...", command=self.rename_selected)
        m.add_separator()
        m.add_command(label="Adicionar arquivos...", command=self.add_files)
        m.add_command(label="Limpar playlist", command=self.clear)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def reload_plugins(self):
        self.lpp.unload_all()
        self.lpp.load_all()
        n = sum(1 for i in self.lpp.plugins.values() if i["status"] == "ativo")
        self.say(f"Plugins recarregados: {n} ativo(s).")

    def open_plugin_folder(self):
        try:
            os.startfile(self.lpp.dir)
        except Exception:
            self.say(f"Pasta de plugins: {self.lpp.dir}")

    @staticmethod
    def estado_txt(info):
        return {"ativo": "ativo", "erro": "ERRO"}.get(info["status"], "desativado")

    def open_plugin_manager(self):
        w = getattr(self, "_pm_win", None)
        if w is not None and w.winfo_exists():
            w.lift()
            self.pm_refresh()
            return
        w = self._pm_win = ToplevelMovel(self)
        w.title("Plugins (.LPP)")
        w.geometry("720x460")
        w.configure(bg=BG)
        w.transient(self)
        st = ttk.Style(self)
        st.configure("Treeview", background=BG2, fieldbackground=BG2, foreground=FG)
        st.map("Treeview", background=[("selected", ACC)], foreground=[("selected", "black")])
        st.configure("Treeview.Heading", background=BG, foreground=FG)
        bar = tk.Frame(w, bg=BG)
        bar.pack(side="bottom", fill="x", padx=8, pady=8)
        txt = self._pm_text = tk.Text(w, height=8, bg=BG2, fg=FG, bd=0, wrap="word", state="disabled")
        txt.pack(side="bottom", fill="x", padx=8)
        tv = self._pm_tree = ttk.Treeview(w, columns=("nome", "versao", "autor", "estado"),
                                          show="headings", height=8, selectmode="browse")
        for c, t, wd in (("nome", "Plugin", 230), ("versao", "Versão", 70),
                         ("autor", "Autor", 170), ("estado", "Estado", 110)):
            tv.heading(c, text=t)
            tv.column(c, width=wd, anchor="w")
        tv.pack(fill="both", expand=True, padx=8, pady=8)
        tv.bind("<<TreeviewSelect>>", lambda e: self.pm_details())
        for t, cmd in (("Ativar / Desativar", self.pm_toggle), ("Recarregar este", self.pm_reload),
                       ("Atualizar lista", self.pm_refresh), ("Ver log", self.open_plugin_log),
                       ("Abrir pasta", self.open_plugin_folder)):
            self.btn(bar, t, cmd).pack(side="left", padx=3)
        self.pm_refresh()

    def pm_selected(self):
        sel = self._pm_tree.selection()
        return sel[0] if sel else None

    def pm_refresh(self):
        self.lpp.scan()
        tv = self._pm_tree
        keep = self.pm_selected()
        tv.delete(*tv.get_children())
        for pid, info in sorted(self.lpp.plugins.items()):
            m = info["meta"]
            tv.insert("", "end", iid=pid, values=(m.get("nome", pid), m.get("versao", "?"),
                                                  m.get("autor", "?"), self.estado_txt(info)))
        if keep and tv.exists(keep):
            tv.selection_set(keep)
        self.pm_details()

    def pm_details(self):
        pid = self.pm_selected()
        t = self._pm_text
        t.config(state="normal")
        t.delete("1.0", "end")
        if not self.lpp.plugins:
            t.insert("end", "Nenhum plugin encontrado.\n\nColoque arquivos .lpp em:\n" + self.lpp.dir)
        elif pid and pid in self.lpp.plugins:
            info = self.lpp.plugins[pid]
            m = info["meta"]
            t.insert("end", f"{m.get('nome', pid)}  v{m.get('versao', '?')}  -  {m.get('autor', '?')}\n\n")
            t.insert("end", f"{m.get('descricao', '')}\n\nArquivo: {info['path']}\n")
            if info["status"] == "ativo" and info["api"]:
                t.insert("end", f"Itens de menu: {len(info['api'].menu_items)}\n")
            if info["erro"]:
                t.insert("end", f"\nProblema: {info['erro']}\n(detalhes completos em Ver log)\n")
        t.config(state="disabled")

    def pm_toggle(self):
        pid = self.pm_selected()
        if not pid:
            return
        if self.lpp.plugins[pid]["status"] == "ativo":
            self.lpp.disable(pid)
        else:
            self.lpp.enable(pid)
        self.pm_refresh()

    def pm_reload(self):
        pid = self.pm_selected()
        if pid:
            self.lpp.reload(pid)
            self.pm_refresh()

    # ---------- log de plugins ----------
    def open_plugin_log(self):
        # Garante que o arquivo exista mesmo quando nenhum plugin gerou mensagens.
        try:
            with open(self.lpp.log_path, "a", encoding="utf-8") as _:
                pass
        except OSError as e:
            messagebox.showerror("Log de plugins", f"Não consegui acessar o log:\n{e}", parent=self)
            return
        w = getattr(self, "_log_win", None)
        if w is not None and w.winfo_exists():
            w.lift()
            self.log_refresh()
            return
        w = self._log_win = ToplevelMovel(self)
        w.title("Log de plugins (plugins.log)")
        w.geometry("780x460")
        w.configure(bg=BG)
        bar = tk.Frame(w, bg=BG)
        bar.pack(side="bottom", fill="x", padx=8, pady=8)
        sb = tk.Scrollbar(w)
        sb.pack(side="right", fill="y")
        txt = self._log_text = tk.Text(w, bg=BG2, fg=FG, wrap="none", bd=0, state="disabled",
                                       font=("Consolas", 9), yscrollcommand=sb.set)
        txt.pack(fill="both", expand=True, padx=(8, 0), pady=(8, 0))
        sb.config(command=txt.yview)
        txt.tag_config("ts", foreground=ACC)
        txt.tag_config("err", foreground="#ff6b6b")
        for t, cmd in (("Atualizar", self.log_refresh), ("Copiar tudo", self.log_copy),
                       ("Limpar log", self.log_clear), ("Abrir arquivo", self.log_open_file)):
            self.btn(bar, t, cmd).pack(side="left", padx=3)
        self.log_refresh()

    def log_refresh(self):
        t = getattr(self, "_log_text", None)
        if t is None or not t.winfo_exists():
            return
        conteudo = tail_log(self.lpp.log_path)
        t.config(state="normal")
        t.delete("1.0", "end")
        if conteudo is None:
            t.insert("end", "Nenhum erro registrado ainda.\n(O arquivo plugins.log é criado no primeiro registro.)")
        else:
            for linha in conteudo.splitlines(True):
                baixo = linha.lower()
                tag = "ts" if re.match(r"\[\d{4}-\d\d-\d\d ", linha) else \
                      "err" if ("error" in baixo or "traceback" in baixo or "erro" in baixo) else None
                t.insert("end", linha, tag) if tag else t.insert("end", linha)
        t.config(state="disabled")
        t.see("end")

    def log_copy(self):
        self.clipboard_clear()
        self.clipboard_append(self._log_text.get("1.0", "end"))
        self.say("Log copiado para a área de transferência.")

    def log_clear(self):
        try:
            open(self.lpp.log_path, "w").close()
        except OSError:
            pass
        self.log_refresh()

    def log_open_file(self):
        try:
            os.startfile(self.lpp.log_path)
        except Exception:
            self.say(f"Log: {self.lpp.log_path}")


def _registrar_erro_inicializacao(exc_text):
    """Grava erros que, em execução .pyw/pythonw, poderiam ficar invisíveis."""
    try:
        pasta = os.path.join(app_dir(), "Files")
        os.makedirs(pasta, exist_ok=True)
        caminho = os.path.join(pasta, "startup.log")
        with open(caminho, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 72 + "\n")
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " — falha ao iniciar Lena's Player\n")
            f.write(exc_text + "\n")
        return caminho
    except Exception:
        return None


if __name__ == "__main__":
    try:
        app = Player()
        files = [f for f in sys.argv[1:] if os.path.isfile(f)]
        if files:
            def open_args():
                media = []
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in (".txt", ".lrc", ".lcr"):
                        app.load_lyrics(f)
                    elif ext in (".m3u", ".m3u8"):
                        app.import_playlist(f)
                    elif ext in EXTS:
                        media.append(f)
                if media:
                    app.add_paths(media, play_first=True)
            app.after(500, open_args)
        app.mainloop()
    except Exception:
        erro = traceback.format_exc()
        log_path = _registrar_erro_inicializacao(erro)
        try:
            _root = tk.Tk()
            _root.withdraw()
            detalhe = f"\n\nO erro completo foi salvo em:\n{log_path}" if log_path else ""
            messagebox.showerror("Lena's Player — falha ao iniciar", erro[-5000:] + detalhe, parent=_root)
            _root.destroy()
        except Exception:
            pass
