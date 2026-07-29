"""Transcrição em tempo real do microfone com o modelo M5 (ONNX int8, CPU).

Pseudo-streaming de um modelo OFFLINE (o M5 é não-causal) via janela deslizante +
LocalAgreement-2 (Macháček et al., ACL 2023 — o método do `whisper_streaming`):

  - a cada HOP (~0,5s) re-decodifica uma janela CONTÍNUA com sobreposição → NÃO corta
    palavras (o defeito da v1, que cortava nas pausas);
  - o texto TENTATIVO (cinza) aparece na hora (~HOP de latência) = efeito real-time;
  - uma palavra vira FINAL (branca, travada) quando DUAS decodificações consecutivas
    concordam no prefixo (LocalAgreement-2) → ~1–1,5s, estável, sem mudar depois de travar;
  - o áudio já confirmado é descartado por timestamp do CTC → janela pequena, custo baixo.

Real-time em DOIS sentidos, ambos preservados:
  * throughput: RTFx ~34× em CPU → re-decodar 12s a cada 0,5s usa <50% de um core;
  * latência: tentativo ~HOP (quase instantâneo); final ~1–1,5s.
Latência sub-200ms de verdade exige modelo causal (M6). Aqui é o melhor possível com o M5.

Uso:  python3 mic_transcribe.py                 # mic, defaults
      python3 mic_transcribe.py --hop 0.4       # menor latência (mais flicker no tentativo)
      python3 mic_transcribe.py --device N      # escolher input (ver sd.query_devices())
Ctrl+C para sair.
"""
from __future__ import annotations
import argparse, queue, sys, time
import numpy as np
import onnxruntime as ort
import sounddevice as sd
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="m5_avg.int8.onnx")
    ap.add_argument("--tokens", default="tokens.txt")
    ap.add_argument("--hop", type=float, default=0.5, help="intervalo de re-decode (s) — menor = menos latência, mais flicker")
    ap.add_argument("--window", type=float, default=12.0, help="janela máx (s) antes do trim")
    ap.add_argument("--nl-sil", type=float, default=1.2, help="silêncio (s) sem texto novo p/ quebrar linha")
    ap.add_argument("--max-line-words", type=int, default=16, help="quebra a linha ao atingir N palavras finais")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--device", default=None, help="índice do device de input")
    a = ap.parse_args()

    print("[init] carregando modelo ONNX...", flush=True)
    so = ort.SessionOptions()
    so.intra_op_num_threads = a.threads
    so.enable_cpu_mem_arena = False
    sess = ort.InferenceSession(a.model, so, providers=["CPUExecutionProvider"])
    id2tok = load_tokens(a.tokens)
    dec = StreamingCTC(sess, id2tok, hop_s=a.hop, window_s=a.window)

    audio_q: "queue.Queue[np.ndarray]" = queue.Queue()

    def callback(indata, frames, time_info, status):
        if status:
            print(f"[audio] {status}", file=sys.stderr, flush=True)
        audio_q.put(indata[:, 0].copy())

    hop_samples = int(a.hop * SR)
    dev = int(a.device) if a.device is not None else None
    print("=" * 64)
    print("🎤  transcrição M5 ao vivo — streaming (Ctrl+C p/ sair)")
    print(f"    hop={a.hop}s · janela={a.window}s · cinza=tentativo, branco=confirmado")
    print("=" * 64, flush=True)

    with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                        blocksize=CHUNK, callback=callback, device=dev):
        pending, buffered = [], 0
        line_words = []            # palavras finais na linha de exibição atual
        last_change = time.time()
        while True:
            c = audio_q.get()
            pending.append(c)
            buffered += len(c)
            if buffered < hop_samples:
                continue
            chunk = np.concatenate(pending)
            pending, buffered = [], 0

            newly, tentative = dec.update(chunk)
            if newly:
                line_words.extend(newly)
                last_change = time.time()

            committed_str = " ".join(line_words)
            tent_str = " ".join(tentative)
            sep = " " if committed_str and tent_str else ""
            line = committed_str + sep + (DIM + tent_str + RESET if tent_str else "")
            sys.stdout.write("\r" + CLR + line)
            sys.stdout.flush()

            # congela a linha (newline): por tamanho (mesmo com tentativo pendente,
            # senão em fala contínua a linha nunca quebra) ou em pausa sem tentativo.
            quiet = (time.time() - last_change) > a.nl_sil
            if line_words and (len(line_words) >= a.max_line_words or (not tentative and quiet)):
                sys.stdout.write("\n")
                sys.stdout.flush()
                line_words = []
                last_change = time.time()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 encerrado.")
