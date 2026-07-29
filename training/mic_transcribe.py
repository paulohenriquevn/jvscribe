"""Transcrição em tempo real do microfone com o modelo M5 (ONNX int8, CPU).

Captura o mic (16 kHz mono) → VAD de energia (RMS + histerese, calibra o ruído de fundo)
detecta fala → ao fim de cada frase (pausa) computa fbank → ONNX greedy CTC → mostra a
transcrição ao vivo no terminal.

O M5 é NÃO-streaming (causal=False), então a transcrição sai por FRASE (a cada pausa),
não palavra-a-palavra. Com RTFx ~34× em CPU, a latência após a pausa é ~100ms.
VAD de energia (sem deps de ML) — ajuste --sens se disparar com ruído / não pegar fala.

Uso:  python3 mic_transcribe.py
      python3 mic_transcribe.py --sens 3.5 --min-sil-ms 600
Ctrl+C para sair.
"""
from __future__ import annotations
import argparse, queue, sys, time
import numpy as np
import onnxruntime as ort
import sounddevice as sd
from lhotse import Fbank, FbankConfig

SR = 16000
CHUNK = 512  # ~32ms @ 16kHz


def load_tokens(path):
    id2tok = {}
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) == 2:
                id2tok[int(p[1])] = p[0]
    return id2tok


def ids_to_text(ids, id2tok):
    return "".join(id2tok.get(i, "") for i in ids).replace("▁", " ").strip()


def greedy(log_probs, id2tok):
    ids = log_probs.argmax(-1)[0]
    toks, prev = [], -1
    for t in ids:
        t = int(t)
        if t != prev and t != 0:
            toks.append(t)
        prev = t
    return ids_to_text(toks, id2tok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="m5_avg.int8.onnx")
    ap.add_argument("--tokens", default="tokens.txt")
    ap.add_argument("--min-sil-ms", type=int, default=600, help="silêncio p/ fechar a frase")
    ap.add_argument("--sens", type=float, default=3.0, help="fala = RMS > sens × ruído de fundo")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--device", default=None, help="índice do device de input")
    a = ap.parse_args()

    print("[init] carregando modelo ONNX...", flush=True)
    so = ort.SessionOptions()
    so.intra_op_num_threads = a.threads
    so.enable_cpu_mem_arena = False
    sess = ort.InferenceSession(a.model, so, providers=["CPUExecutionProvider"])
    id2tok = load_tokens(a.tokens)
    fbank = Fbank(FbankConfig(num_mel_bins=80))

    def transcribe(samples: np.ndarray) -> str:
        feats = fbank.extract(samples, SR)
        x = feats[None].astype(np.float32)
        xl = np.array([feats.shape[0]], dtype=np.int64)
        lp, _ = sess.run(["log_probs", "log_probs_len"], {"x": x, "x_lens": xl})
        return greedy(lp, id2tok)

    audio_q: "queue.Queue[np.ndarray]" = queue.Queue()

    def callback(indata, frames, time_info, status):
        if status:
            print(f"[audio] {status}", file=sys.stderr, flush=True)
        audio_q.put(indata[:, 0].copy())

    sil_chunks = max(1, int(a.min_sil_ms / 1000 * SR / CHUNK))
    start_chunks = 3  # ~100ms acima do limiar p/ iniciar

    # calibração do ruído de fundo (~0.5s)
    dev = int(a.device) if a.device is not None else None
    print("[init] calibrando ruído de fundo — fique em silêncio ~1s...", flush=True)
    noise = []
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                        blocksize=CHUNK, callback=callback, device=dev):
        t0 = time.time()
        while time.time() - t0 < 1.0:
            noise.append(np.sqrt(np.mean(audio_q.get() ** 2)))
        noise_floor = max(1e-5, float(np.median(noise)))
        thresh = noise_floor * a.sens
        print("=" * 60)
        print(f"🎤  FALE — transcrição M5 ao vivo (Ctrl+C p/ sair)")
        print(f"    ruído={noise_floor:.4f} · limiar={thresh:.4f} · sens={a.sens} · pausa={a.min_sil_ms}ms")
        print("=" * 60)
        print("🟢 escutando...", flush=True)

        seg, in_speech, sil_run, n = [], False, 0, 0
        while True:
            chunk = audio_q.get()
            rms = np.sqrt(np.mean(chunk ** 2))
            loud = rms > thresh
            if in_speech:
                seg.append(chunk)
                sil_run = 0 if loud else sil_run + 1
                if sil_run >= sil_chunks:  # fim da frase
                    in_speech = False
                    samples = np.concatenate(seg); seg = []
                    if len(samples) < SR // 4:
                        continue
                    t = time.perf_counter()
                    text = transcribe(samples)
                    dt = time.perf_counter() - t
                    dur = len(samples) / SR
                    if text:
                        n += 1
                        print(f"[{n:02d}] {text}   ({dur:.1f}s→{dt*1000:.0f}ms, {dur/dt:.0f}×)", flush=True)
            else:
                if loud:
                    seg.append(chunk)
                    if len(seg) >= start_chunks:
                        in_speech = True
                        sil_run = 0
                else:
                    seg = []


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 encerrado.")
