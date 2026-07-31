#!/usr/bin/env python3
"""E6 — beam search e modelo de linguagem: o maior terço do erro.

Pré-registro: `wiki/medicoes/e6-preregistro-beam-lm.md`. **Leia antes de interpretar qualquer
número daqui** — predições e critérios de morte foram escritos antes da primeira corrida.

E4 mediu o **custo** do beam (15,2 ms contra 134 ms de encoder) e matou o argumento de que ele não
cabe. Esta fase mede o **ganho**, que é outra pergunta — em duas etapas de propósito:

1. **beam nu, sem LM** — CONTROLE, não candidato. A expectativa registrada é ganho ~zero: CTC
   assume independência condicional entre frames e as posteriores são *peaky*, então o beam
   reencontra o caminho greedy. Medir isso permite **atribuir** o ganho da etapa 2. Sem o
   controle, um ganho de beam+LM seria creditado à "busca melhor" — conclusão que excede a
   evidência.
2. **beam + LM** — onde a literatura põe 10–20% relativo, e onde mora `real_word_hyp` (36,6% do
   erro, o maior terço, o único que nenhuma outra fase alcança).

## Por que as posteriores são cacheadas

O encoder custa 134 ms e é **idêntico** para todos os decoders. Rodando-o uma vez por utterance e
guardando `log_probs`, todo decoder decide sobre os **mesmos frames**: a comparação fica pareada
por construção. Não é atalho de velocidade — é o que elimina a variância entre corridas que levou
este projeto a declarar vencedor de corrida única três vezes, e errar nas três.

⚠️ **O vazamento pelo LM invalida esta fase inteira.** FLEURS deriva do FLoRes-101, de origem
Wikipédia — um LM treinado em Wikipédia em português pode conter as sentenças do test set. O
relatório publica a contagem de sobreposição, e ela tem de ser zero.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ctc  # noqa: E402
from beam_ctc_probe import beam_prefixo  # noqa: E402 — mesmo pipeline, sem cruzar fronteira
from engine import Motor  # noqa: E402
from metrics import (  # noqa: E402
    escrever_relatorio,
    find_test_parquet,
    paired_bootstrap,
    word_edit_distance,
)
from report import ambiente  # noqa: E402
from text import normalize_for_wer_compare  # noqa: E402

TEMPLATES = pathlib.Path(__file__).resolve().parent / "templates"


def posteriores_do_teste(n: int) -> list[tuple[np.ndarray, str]]:
    """Roda o encoder UMA vez por utterance; devolve `(log_probs, referência)`.

    O custo desta função é o custo inteiro do experimento — tudo depois é aritmética sobre a
    matriz. É também o que torna a comparação pareada: os frames são os mesmos para todo decoder.
    """
    import io

    import pyarrow.parquet as pq
    import soundfile as sf
    from lhotse import Fbank, FbankConfig

    motor = Motor.carregar()
    fb = Fbank(FbankConfig(num_mel_bins=80))
    fora: list[tuple[np.ndarray, str]] = []
    pf = pq.ParquetFile(find_test_parquet())
    for lote in pf.iter_batches(batch_size=16):
        d = lote.to_pydict()
        for audio, ref in zip(d["audio"], d["transcription"]):
            if len(fora) >= n:
                return fora
            x, sr = sf.read(io.BytesIO(audio["bytes"]), dtype="float32")
            feats = np.asarray(fb.extract(x, sr), dtype=np.float32)
            lp, _ = motor.sessao.run(
                ["log_probs", "log_probs_len"],
                {"x": feats[None], "x_lens": np.array([feats.shape[0]], dtype=np.int64)},
            )
            fora.append((lp[0], ref))
    return fora


def avaliar(quadros, decodificar, id2tok) -> tuple[list[tuple[int, int]], float]:
    """`([(erros, palavras_da_ref)], ms por utterance)`.

    A régua é `normalize_for_wer_compare` — a MESMA do baseline publicado. Trocá-la aqui mudaria
    todo delta reportado.
    """
    linhas, t0 = [], time.perf_counter()
    for lp, r in quadros:
        hyp = normalize_for_wer_compare(decodificar(lp, id2tok)).split()
        ref = normalize_for_wer_compare(r).split()
        linhas.append((word_edit_distance(ref, hyp), len(ref)))
    return linhas, (time.perf_counter() - t0) * 1000 / max(len(quadros), 1)


def _wer(linhas) -> float:
    return 100.0 * sum(e for e, _ in linhas) / max(sum(w for _, w in linhas), 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=100, help="utterances de FLEURS test")
    ap.add_argument("--larguras", type=int, nargs="+", default=[2, 4, 8])
    ap.add_argument("--relatorio", type=pathlib.Path,
                    default=pathlib.Path("wiki/medicoes/e6-beam-controle.md"))
    a = ap.parse_args()

    motor = Motor.carregar()
    print(f"  extraindo posteriores de {a.n} utterances (encoder roda UMA vez cada)…", flush=True)
    quadros = posteriores_do_teste(a.n)
    print(f"  {len(quadros)} utterances · vocab {quadros[0][0].shape[1]}\n", flush=True)

    base, ms_greedy = avaliar(quadros, lambda lp, t: ctc.greedy_text(lp, t), motor.id2tok)
    wer_base = _wer(base)
    print(f"  {'decoder':<16} {'WER':>7} {'Δ p.p.':>8} {'IC95 do Δ':>20} {'ms':>8}")
    print("  " + "-" * 66)
    print(f"  {'greedy (base)':<16} {wer_base:6.2f}% {'—':>8} {'—':>20} {ms_greedy:7.1f}")

    resultados = []
    for largura in a.larguras:
        # `beam_prefixo` já devolve o prefixo colapsado (sem blanks); só falta detokenizar —
        # com a MESMA função que o greedy usa, senão a diferença mediria detokenização.
        cand, ms = avaliar(
            quadros,
            lambda lp, t, L=largura: ctc.detok_pieces(beam_prefixo(lp, L), t),
            motor.id2tok,
        )
        # rows = (erros_base, erros_cand, palavras_ref) — o pareamento é por utterance
        b = paired_bootstrap([(bb[0], cc[0], bb[1]) for bb, cc in zip(base, cand)])
        lo, hi = b["abs_ci95"]
        cruza = lo <= 0 <= hi
        print(f"  {'beam ' + str(largura):<16} {b['wer_cand']:6.2f}% {b['abs_diff_pp']:+8.2f} "
              f"[{lo:+7.2f}; {hi:+7.2f}] {ms:7.1f}"
              f"{'' if cruza else '  ← IC EXCLUI zero'}")
        resultados.append({"largura": largura, "ms": ms, "cruza_zero": cruza, **b})

    h1_confirmada = all(r["cruza_zero"] and abs(r["abs_diff_pp"]) < 0.2 for r in resultados)
    print(f"\n  H1 (beam nu não muda o WER): {'CONFIRMADA' if h1_confirmada else 'REFUTADA'}")

    corpo = ambiente(TEMPLATES).get_template("e6-beam-controle.md.j2").render(
        n=len(quadros), wer_base=wer_base, ms_greedy=ms_greedy,
        resultados=resultados, h1_confirmada=h1_confirmada,
    )
    escrever_relatorio(a.relatorio, corpo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
