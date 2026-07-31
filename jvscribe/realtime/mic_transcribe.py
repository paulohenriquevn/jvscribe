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
import sounddevice as sd

import pathlib

# `common/` é o shared kernel. Um humano rodando este script direto só tem o diretório dele
# no path — sem o insert explícito o script quebra standalone e a suíte inteira passa.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
from artifact import default_model_path as _default_model_path  # noqa: E402
from artifact import default_sibling as _default_sibling  # noqa: E402
from onnx_session import criar_sessao  # noqa: E402

# Motor de streaming: `streaming.py` (um por canal em live_transcribe.py). Re-exportado
# aqui porque este script e seus testes já o consomem por este nome.
from streaming import (  # noqa: E402,F401
    SR, CHUNK, BLANK, WORD_START,
    load_tokens, longest_common_prefix, ctc_words, commit_localagreement, StreamingCTC,
)

DIM, RESET, CLR = "\033[2m", "\033[0m", "\033[K"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=_default_model_path())
    ap.add_argument("--tokens", default=_default_sibling("tokens.txt"))
    ap.add_argument("--hop", type=float, default=0.5, help="intervalo de re-decode (s) — menor = menos latência, mais flicker")
    ap.add_argument("--window", type=float, default=12.0, help="janela máx (s) antes do trim")
    ap.add_argument("--nl-sil", type=float, default=1.2, help="silêncio (s) sem texto novo p/ quebrar linha")
    ap.add_argument("--max-line-words", type=int, default=16, help="quebra a linha ao atingir N palavras finais")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--device", default=None, help="índice do device de input")
    a = ap.parse_args()

    print("[init] carregando modelo ONNX...", flush=True)
    # Fábrica do shared kernel — uma configuração medida para todos os entrypoints.
    sess = criar_sessao(a.model, a.threads)
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
