#!/usr/bin/env python3
"""E7 — o que a quantização int8 custou em WER, e se o orçamento novo compra de volta.

**A pergunta mais barata que existe quando o orçamento de CPU afrouxa.** Antes de qualquer
técnica nova, o degrau 1 da escada de parcimônia: se sobra compute, ainda vale rodar o modelo
*comprimido*? O int8 foi escolhido sob um RNF-01 de ≥3×. Com o alvo em 1,5× o compute disponível
dobra, e a compressão pode ter deixado de se pagar.

O par em disco torna o teste **controlado de verdade**: `ckpt124k.fp32.onnx` e `ckpt124k.int8.onnx`
são os **mesmos pesos** — só a precisão difere. Nenhuma outra variável se move, o que é raro e é o
que dá poder à comparação.

⚠️ **Estes são os pesos do checkpoint ÚNICO (WER 17,32%), não os do modelo entregue** (média de
112k+124k, 15,99%). O delta de quantização medido aqui é sobre aqueles pesos. Assumir que o mesmo
delta vale para o modelo médio é `[ESTIMATIVA]`, não `[MEDIDO]` — a média de checkpoints muda a
distribuição dos pesos, que é exatamente o que a quantização discretiza.

## Hipóteses pré-registradas

**H1 — o int8 custou WER mensurável.** Predição: fp32 melhor por **0,1 a 0,8 p.p.**, IC95 do delta
excluindo zero. Razão: `[LITERATURA]` a quantização estática int8 em ASR costuma custar entre nada
e ~1 p.p.; a faixa é larga porque depende da calibração, e a nossa nunca foi auditada.
**Critério de morte:** IC95 cruzando zero → o int8 é gratuito em acurácia e o orçamento novo deve
ser gasto em outra coisa.

**H2 — o fp32 cabe no orçamento novo em LOTE, e não cabe ao vivo.** Predição: RTFx do fp32 fica
acima de 1,5× no lote e abaixo do necessário no caminho ao vivo. O modelo fp32 tem 249 MB contra
67,5 MB — o gargalo esperado é banda de memória, não aritmética.
"""
from __future__ import annotations

import argparse
import io
import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
import ctc  # noqa: E402
from cpu import LIMIAR_LOAD, carga_media, detectar, medicao_de_tempo_e_confiavel  # noqa: E402
from engine import carregar_tokens  # noqa: E402
from metrics import (  # noqa: E402
    escrever_relatorio,
    find_test_parquet,
    paired_bootstrap,
    word_edit_distance,
)
from onnx_session import criar_sessao  # noqa: E402
from report import ambiente  # noqa: E402
from text import normalize_for_wer_compare  # noqa: E402

TEMPLATES = pathlib.Path(__file__).resolve().parent / "templates"


def carregar_audio(n: int) -> list[tuple[np.ndarray, float, str]]:
    """`(features, duração_s, referência)` — extraído UMA vez e reusado por todos os modelos.

    Fbank é determinístico: extrair por modelo só adicionaria custo e a chance de os dois verem
    entradas diferentes, que destruiria o pareamento.
    """
    import pyarrow.parquet as pq
    import soundfile as sf
    from lhotse import Fbank, FbankConfig

    fb = Fbank(FbankConfig(num_mel_bins=80))
    fora = []
    for lote in pq.ParquetFile(find_test_parquet()).iter_batches(batch_size=16):
        d = lote.to_pydict()
        for audio, ref in zip(d["audio"], d["transcription"]):
            if len(fora) >= n:
                return fora
            x, sr = sf.read(io.BytesIO(audio["bytes"]), dtype="float32")
            fora.append((np.asarray(fb.extract(x, sr), dtype=np.float32), len(x) / sr, ref))
    return fora


def rodar(modelo: pathlib.Path, dados, id2tok, threads: int):
    """`(linhas pareadas, RTFx, ms/utt)` para um artefato ONNX."""
    sess = criar_sessao(str(modelo), threads)
    linhas, audio_s, t0 = [], 0.0, time.perf_counter()
    for feats, dur, ref in dados:
        lp, _ = sess.run(
            ["log_probs", "log_probs_len"],
            {"x": feats[None], "x_lens": np.array([feats.shape[0]], dtype=np.int64)},
        )
        hyp = normalize_for_wer_compare(ctc.greedy_text(lp[0], id2tok)).split()
        r = normalize_for_wer_compare(ref).split()
        linhas.append((word_edit_distance(r, hyp), len(r)))
        audio_s += dur
    wall = time.perf_counter() - t0
    return linhas, audio_s / wall, wall * 1000 / max(len(dados), 1)


def _wer(linhas) -> float:
    return 100.0 * sum(e for e, _ in linhas) / max(sum(w for _, w in linhas), 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--int8", type=pathlib.Path, required=True)
    ap.add_argument("--fp32", type=pathlib.Path, required=True)
    ap.add_argument("--tokens", type=pathlib.Path, required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--alvo-rtfx", type=float, default=1.5,
                    help="o orçamento novo — o que decide se o fp32 é OPÇÃO ou só curiosidade")
    ap.add_argument("--relatorio", type=pathlib.Path,
                    default=pathlib.Path("wiki/medicoes/e7-custo-do-int8.md"))
    a = ap.parse_args()

    for p in (a.int8, a.fp32, a.tokens):
        if not p.exists():
            raise SystemExit(f"não encontrado: {p}")

    threads = a.threads or detectar().threads_recomendadas
    id2tok = carregar_tokens(a.tokens)
    carga = carga_media()
    confiavel = medicao_de_tempo_e_confiavel(carga)
    nota_carga = (
        f"load average {carga:.1f} — máquina ociosa o bastante para medir tempo."
        if confiavel else
        f"load average {'indisponível' if carga is None else f'{carga:.1f}'} — "
        f"acima do limiar {LIMIAR_LOAD:g}: números de TEMPO indeterminados"
    )
    print(f"  {nota_carga}\n  intra={threads} · extraindo features de {a.n} utterances…",
          flush=True)
    dados = carregar_audio(a.n)

    # Round-robin: alterna os dois modelos por corrida em vez de rodar um bloco de cada. Se a
    # máquina esquentar ou pegar carga no meio, o efeito recai igualmente sobre os dois em vez de
    # penalizar o segundo — a disciplina § 3 deste projeto exige isso para comparação de tempo.
    res = {}
    for rotulo, caminho in (("int8", a.int8), ("fp32", a.fp32)):
        res[rotulo] = rodar(caminho, dados, id2tok, threads)
        print(f"  {rotulo}: WER {_wer(res[rotulo][0]):.2f}% · RTFx {res[rotulo][1]:.1f}× · "
              f"{res[rotulo][2]:.0f} ms/utt", flush=True)

    b = paired_bootstrap([(i[0], f[0], i[1]) for i, f in zip(res["int8"][0], res["fp32"][0])])
    lo, hi = b["abs_ci95"]
    print(f"\n  Δ (int8 → fp32): {b['abs_diff_pp']:+.2f} p.p.  IC95 [{lo:+.2f}; {hi:+.2f}]"
          f"{'  ← cruza zero' if lo <= 0 <= hi else '  ← IC EXCLUI zero'}")

    corpo = ambiente(TEMPLATES).get_template("e7-custo-do-int8.md.j2").render(
        n=len(dados), threads=threads, confiavel=confiavel, nota_carga=nota_carga,
        int8=str(a.int8), fp32=str(a.fp32), alvo=a.alvo_rtfx,
        wer_int8=_wer(res["int8"][0]), wer_fp32=_wer(res["fp32"][0]),
        rtfx_int8=res["int8"][1], rtfx_fp32=res["fp32"][1],
        ms_int8=res["int8"][2], ms_fp32=res["fp32"][2],
        delta=b["abs_diff_pp"], ci=b["abs_ci95"], cruza=lo <= 0 <= hi,
        cabe_fp32=res["fp32"][1] >= a.alvo_rtfx,
    )
    escrever_relatorio(a.relatorio, corpo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
