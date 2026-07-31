"""Motor de transcrição incremental sobre um modelo CTC offline (janela + LocalAgreement-2).

Extraído de `mic_transcribe.py` quando `live_transcribe.py` passou a precisar do MESMO motor,
um por canal. Manter a cópia em dois scripts seria duplicar conhecimento — e este é o núcleo
que decide o que já pode ser mostrado ao usuário como texto final.

Deliberadamente sem dependência de captura: quem alimenta `StreamingCTC.update()` pode ser
`sounddevice` (mic_transcribe) ou `parec` via `DualCapture` (live_transcribe). O motor só
conhece `np.ndarray` float32 a 16 kHz.
"""
from __future__ import annotations

import numpy as np
from lhotse import Fbank, FbankConfig

from audio import SR  # noqa: E402 — declaração única do domínio de áudio
CHUNK = 512          # ~32ms @ 16kHz
BLANK = 0
WORD_START = "▁"  # ▁ (marca início de palavra no BPE)
SHIFT = 160          # frame shift do fbank: 10 ms @ 16 kHz
CTX_FRAMES = 4       # contexto à esquerda ao estender o cache (ver FeatureCache)
FRAME_LEN = 400      # janela de análise do fbank: 25 ms @ 16 kHz
MAX_COMMITTED = 64   # o motor só consulta committed[-1]; o histórico vive em Transcricao
MARGEM_DIREITA = 2   # frames retidos: o frame i abrange [i·SHIFT−200, i·SHIFT+200], logo um
                     # buffer de tamanho L deixa até 1,75 frames incompletos na cauda



class FeatureCache:
    """Fbank incremental: cada amostra é featurizada UMA vez.

    Antes disto, `StreamingCTC` reextraía o fbank da janela inteira a cada hop — 21,6% do
    custo de decode `[MEDIDO]` gasto refazendo o que já estava feito.

    ⚠️ O offset de extensão tem de ser MÚLTIPLO de `SHIFT`. Com `snip_edges=False` o Kaldi
    centra os frames e preenche as bordas; extrair a partir de um offset desalinhado desloca
    o centro de todos os frames. Medido: offset alinhado converge a 9,5e-07 (ruído de
    float32), desalinhado diverge em 6,57 — e a divergência seria silenciosa, trocando CPU
    por WER sem nenhum erro.
    """

    def __init__(self) -> None:
        self._fbank = Fbank(FbankConfig(num_mel_bins=80))
        self._audio = np.zeros(0, dtype=np.float32)   # cauda ainda não featurizada + contexto
        self._feats = np.zeros((0, 80), dtype=np.float32)
        self._base = 0        # nº de frames já emitidos a partir de `self._audio[0]`

    def append(self, audio: np.ndarray) -> None:
        """Acrescenta áudio e estende o cache só com os frames novos.

        A contagem de frames NÃO é predita: o lhotse usa `round(L/shift)` — 1.680 amostras
        dão 11 frames, não 10 — e errar por um desalinha o cache inteiro em silêncio. Aqui
        o número de frames vem da própria extração.
        """
        if audio.size == 0:
            return
        self._audio = np.concatenate([self._audio, np.asarray(audio, dtype=np.float32)])
        if len(self._audio) < FRAME_LEN:
            return   # menos que uma janela de análise: o lhotse levanta em vez de dar 0 frames
        novo = np.asarray(self._fbank.extract(self._audio, SR), dtype=np.float32)
        # Segura o ÚLTIMO frame: ele é calculado com padding na borda direita e mudaria
        # quando chegasse mais áudio. Medido: sem esta margem divergem exatamente os frames
        # 49, 99, 149… — o último de cada pedaço — em até 6,27. Custo: 10 ms de atraso.
        emitir_ate = len(novo) - MARGEM_DIREITA
        if emitir_ate > self._base:
            self._feats = np.concatenate([self._feats, novo[self._base : emitir_ate]])
            self._base = emitir_ate
        self._compactar()

    def _compactar(self) -> None:
        """Descarta áudio já featurizado, preservando `CTX_FRAMES` de contexto alinhado.

        Mantém `self._base >= CTX_FRAMES ≥ 1` de propósito: o frame 0 de uma re-extração é
        contaminado pelo padding da borda esquerda (`snip_edges=False`) e nunca pode ser
        emitido. Medido: descartar 0 frames diverge 1,42; descartar 1 converge a 9,5e-07.
        """
        if self._base <= CTX_FRAMES:
            return
        descartar_frames = self._base - CTX_FRAMES
        self._audio = self._audio[descartar_frames * SHIFT :]
        self._base = CTX_FRAMES

    def features(self) -> np.ndarray:
        return self._feats

    def descartar(self, n_frames: int) -> None:
        """Remove `n_frames` do INÍCIO — acompanha o trim da janela do decodificador."""
        if n_frames > len(self._feats):
            raise ValueError(
                f"descartar {n_frames} frames de um cache com {len(self._feats)} — "
                "o chamador perdeu o alinhamento entre janela e features"
            )
        if n_frames > 0:
            self._feats = self._feats[n_frames:]
DIM, RESET, CLR = "\033[2m", "\033[0m", "\033[K"


def load_tokens(path):
    id2tok = {}
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) == 2:
                id2tok[int(p[1])] = p[0]
    return id2tok


def longest_common_prefix(a, b):
    """Nº de elementos iguais no início de duas listas — núcleo do LocalAgreement-2."""
    k = 0
    while k < len(a) and k < len(b) and a[k] == b[k]:
        k += 1
    return k


def ctc_words(path, id2tok, stride, t0):
    """Colapsa o caminho greedy do CTC em (palavras, tempos_abs_de_início).

    ⚠️ Reimplementa o colapso de propósito, e não usa o shared kernel (`common/ctc.py`): o
    kernel devolve **texto**, e aqui é preciso o **tempo de início de cada palavra** — é o que
    o LocalAgreement-2 usa para saber o que já foi confirmado. Sem o tempo, não há como
    distinguir palavra nova de palavra re-decodada.

    path: argmax por frame (iterável de ints). stride: segundos por frame de saída.
    t0: tempo absoluto (s) do frame 0. Colapso CTC padrão: remove repetições, depois
    remove blanks; ``▁`` marca início de palavra. Retorna (list[str], list[float]).
    """
    words, times = [], []
    cur, cur_f, prev = "", None, -1
    for i, tt in enumerate(path):
        tt = int(tt)
        if tt == prev:
            continue
        prev = tt
        if tt == BLANK:
            continue
        s = id2tok.get(tt, "")
        if s.startswith(WORD_START):
            if cur:
                words.append(cur)
                times.append(t0 + cur_f * stride)
            cur, cur_f = s[len(WORD_START):], i
        else:
            if cur_f is None:
                cur_f = i
            cur += s
    if cur:
        words.append(cur)
        times.append(t0 + cur_f * stride)
    return words, times


def commit_localagreement(words, times, committed, prev_unc):
    """Núcleo puro do LocalAgreement-2 (testável, sem I/O).

    Dado o resultado do decode atual (words+times), o que já foi confirmado
    (committed=[(palavra, tempo)]) e o tail não-confirmado da rodada anterior
    (prev_unc=list[str]), retorna (newly, new_prev_unc):
      - descarta palavras já confirmadas (tempo <= último confirmado);
      - dedup de costura: a última confirmada reaparece no left-context re-decodado
        pós-trim com tempo ligeiramente > lc → não re-emitir;
      - confirma o maior prefixo comum entre o tail atual e o anterior.
    """
    lc = committed[-1][1] if committed else -1e9
    last_w = committed[-1][0] if committed else None
    unc = [(w, t) for w, t in zip(words, times) if t > lc + 1e-6]
    if unc and last_w is not None and unc[0][0] == last_w and unc[0][1] - lc < 0.5:
        unc = unc[1:]
    unc_w = [w for w, _ in unc]
    k = longest_common_prefix(unc_w, prev_unc)
    return unc[:k], unc_w[k:]


class StreamingCTC:
    """Janela deslizante + LocalAgreement-2 sobre um modelo CTC offline.

    Estado mínimo: buffer de áudio (desde o último trim), tempo abs do buf[0],
    palavras já confirmadas (com tempo) e o tail não-confirmado da rodada anterior.
    """

    def __init__(self, sess, id2tok, hop_s=0.5, window_s=12.0, left_ctx_s=2.0):
        self.sess, self.id2tok = sess, id2tok
        self.cache = FeatureCache()   # fbank incremental: cada amostra featurizada 1× só
        self.hop_s, self.window_s, self.left_ctx_s = hop_s, window_s, left_ctx_s
        self.buf = np.zeros(0, dtype=np.float32)
        self.t0 = 0.0            # tempo abs (s) do buf[0]
        self.committed = []      # [(palavra, tempo_abs)] final/travado
        self.prev_unc = []       # tail não-confirmado (texto) da atualização anterior

    def _decode(self):
        feats = self.cache.features()
        if len(feats) == 0:
            return [], []
        x = feats[None].astype(np.float32)
        xl = np.array([feats.shape[0]], dtype=np.int64)
        lp, _ = self.sess.run(["log_probs", "log_probs_len"], {"x": x, "x_lens": xl})
        path = lp[0].argmax(-1)
        stride = (len(self.buf) / SR) / max(1, len(path))
        return ctc_words(path, self.id2tok, stride, self.t0)

    def update(self, new_audio):
        """Adiciona áudio, re-decodifica a janela e confirma via LocalAgreement-2.

        Retorna (novas_finais: list[str], tentativo_atual: list[str]).
        """
        self.buf = np.concatenate([self.buf, new_audio])
        self.cache.append(new_audio)
        if len(self.buf) < int(0.3 * SR):   # < 300ms: sem contexto p/ decodar
            return [], list(self.prev_unc)
        words, times = self._decode()
        newly, self.prev_unc = commit_localagreement(
            words, times, self.committed, self.prev_unc)
        self.committed.extend(newly)
        # Teto de histórico: `commit_localagreement` e `_trim` consultam apenas o ÚLTIMO
        # confirmado. Sem o corte, uma ligação de 40 min acumula ~28 mil tuplas no caminho
        # quente — medido: 2.128 em 3 min. O diálogo completo é responsabilidade de
        # `Transcricao`, não do motor.
        if len(self.committed) > MAX_COMMITTED:
            self.committed = self.committed[-MAX_COMMITTED:]
        self._trim()
        return [w for w, _ in newly], list(self.prev_unc)

    def _trim(self):
        """Descarta o áudio antes da última palavra confirmada (menos left-context)."""
        if len(self.buf) / SR <= self.window_s or not self.committed:
            return
        cut_t = self.committed[-1][1] - self.left_ctx_s
        drop = int((cut_t - self.t0) * SR)
        if drop > 0:
            drop -= drop % SHIFT          # alinha ao grid de frames; sem isto o cache desloca
            if drop <= 0:
                return
            self.buf = self.buf[drop:]
            self.cache.descartar(min(drop // SHIFT, len(self.cache.features())))
            self.t0 += drop / SR
