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

SR = 16000
CHUNK = 512          # ~32ms @ 16kHz
BLANK = 0
WORD_START = "▁"  # ▁ (marca início de palavra no BPE)
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
        self.fbank = Fbank(FbankConfig(num_mel_bins=80))
        self.hop_s, self.window_s, self.left_ctx_s = hop_s, window_s, left_ctx_s
        self.buf = np.zeros(0, dtype=np.float32)
        self.t0 = 0.0            # tempo abs (s) do buf[0]
        self.committed = []      # [(palavra, tempo_abs)] final/travado
        self.prev_unc = []       # tail não-confirmado (texto) da atualização anterior

    def _decode(self):
        feats = self.fbank.extract(self.buf, SR)
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
        if len(self.buf) < int(0.3 * SR):   # < 300ms: sem contexto p/ decodar
            return [], list(self.prev_unc)
        words, times = self._decode()
        newly, self.prev_unc = commit_localagreement(
            words, times, self.committed, self.prev_unc)
        self.committed.extend(newly)
        self._trim()
        return [w for w, _ in newly], list(self.prev_unc)

    def _trim(self):
        """Descarta o áudio antes da última palavra confirmada (menos left-context)."""
        if len(self.buf) / SR <= self.window_s or not self.committed:
            return
        cut_t = self.committed[-1][1] - self.left_ctx_s
        drop = int((cut_t - self.t0) * SR)
        if drop > 0:
            self.buf = self.buf[drop:]
            self.t0 = cut_t
