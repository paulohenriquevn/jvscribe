#!/usr/bin/env python3
"""Portão de confiança e correção pós-decode — o experimento das fases E1/E2.

Protocolo: [`knowledge-base/plans/portao-de-confianca-plan.md`](../../knowledge-base/plans/portao-de-confianca-plan.md).

Vive em `probes/` de propósito (ADR D2 do protocolo): o domínio declarado desta pipeline é
**hipótese de pesquisa que pode dar nulo**, e o teto medido do caminho de correção é ~8% dos
erros. Promover qualquer coisa daqui para `common/` antes que um número autorize seria presumir
o resultado.

Modos:
  --curva      E1: precisão/recall do portão por τ, com IC95% bootstrap sobre utterances
  --corrigir   E2: ΔWER da correção com portão, pareado (ainda não implementado — E2)

Uso:
  python3 jvscribe/probes/portao_correcao_probe.py --curva --n 100
"""
from __future__ import annotations

import argparse
import difflib
import io
import pathlib
import sys
from dataclasses import dataclass

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
import ctc  # noqa: E402  — shared kernel: colapso e confiança por palavra
from engine import Motor  # noqa: E402
from metrics import escrever_relatorio, find_test_parquet  # noqa: E402
from report import ambiente as ambiente_de_relatorio  # noqa: E402
from text import normalize_for_wer_compare as norm  # noqa: E402

_AMBIENTE = ambiente_de_relatorio(pathlib.Path(__file__).resolve().parent / "templates")
_DADOS_BRUTOS = pathlib.Path(__file__).resolve().parents[2] / "wiki" / "medicoes" / "dados-brutos"
TAUS = (0.25, 0.5, 1.0, 1.5, 2.0, 3.0)
MIN_UTTERANCES_PARA_IC = 3      # mesma recusa de `common/stats.comparar_pareado`
SEED = 20260731


@dataclass(frozen=True)
class Avaliacao:
    """Uma palavra do hipótese, com a confiança que a produziu e se ela estava errada."""

    margem: float
    errada: bool


def sinalizar(avaliacoes: list[Avaliacao], tau: float) -> list[bool]:
    """Quais palavras o portão sinaliza. O limiar é ESTRITO — a fronteira é uma só."""
    return [a.margem < tau for a in avaliacoes]


def precisao_recall(avaliacoes: list[Avaliacao], tau: float) -> tuple[float | None, float | None]:
    """`(precisão, recall)`, com `None` onde o denominador não existe.

    Precisão sobre zero sinalizados é **indefinida**, não 100%: um τ que não sinaliza nada
    encerraria a curva num ponto perfeito e falso — e é assim que se escolhe o τ errado.
    """
    flags = sinalizar(avaliacoes, tau)
    n_flag = sum(flags)
    n_err = sum(a.errada for a in avaliacoes)
    prec = (sum(a.errada for a, f in zip(avaliacoes, flags) if f) / n_flag) if n_flag else None
    rec = (sum(f for a, f in zip(avaliacoes, flags) if a.errada) / n_err) if n_err else None
    return prec, rec


def ic95_bootstrap(
    por_utterance: list[list[Avaliacao]],
    tau: float,
    metrica: str,
    n_boot: int = 2000,
    seed: int = SEED,
) -> tuple[float, float] | None:
    """IC95% percentil, reamostrando **utterances** — a unidade de amostragem.

    Palavras da mesma locução são correlacionadas (mesmo locutor, mesmo áudio, mesmo contexto).
    Reamostrá-las como independentes estreitaria o intervalo artificialmente, que é a falácia
    § 3 #12 com uma casa decimal a mais.

    `None` com menos de 3 utterances: um intervalo sobre duas amostras é aritmética, não
    estatística.
    """
    n = len(por_utterance)
    if n < MIN_UTTERANCES_PARA_IC:
        return None
    idx_metrica = 0 if metrica == "precisao" else 1
    rng = np.random.default_rng(seed)
    valores = []
    for _ in range(n_boot):
        amostra = [por_utterance[i] for i in rng.integers(0, n, size=n)]
        v = precisao_recall([a for u in amostra for a in u], tau)[idx_metrica]
        if v is not None:
            valores.append(v)
    if len(valores) < MIN_UTTERANCES_PARA_IC:
        return None
    return float(np.percentile(valores, 2.5)), float(np.percentile(valores, 97.5))


def avaliar(n_utterances: int) -> list[list[Avaliacao]]:
    """Transcreve N utterances de FLEURS e marca cada palavra como certa ou errada.

    O alinhamento é `difflib` sobre as palavras normalizadas pela régua **de comparação**
    (`normalize_for_wer_compare`) — a mesma de todo WER publicado. Usar a régua de treino aqui
    inflaria o erro por acento, defeito que este repositório já pagou.
    """
    import pyarrow.parquet as pq
    import soundfile as sf
    from lhotse import Fbank, FbankConfig

    motor = Motor.carregar()
    fb = Fbank(FbankConfig(num_mel_bins=80))
    pf = pq.ParquetFile(find_test_parquet())

    por_utterance: list[list[Avaliacao]] = []
    for lote in pf.iter_batches(batch_size=32, columns=["audio", "transcription"]):
        for linha in lote.to_pylist():
            if len(por_utterance) >= n_utterances:
                return por_utterance
            x, sr = sf.read(io.BytesIO(linha["audio"]["bytes"]), dtype="float32")
            if x.ndim > 1:
                x = x[:, 0]
            feats = np.asarray(fb.extract(x, sr), dtype=np.float32)
            lp, _ = motor.sessao.run(
                ["log_probs", "log_probs_len"],
                {"x": feats[None], "x_lens": np.array([feats.shape[0]], dtype=np.int64)},
            )
            palavras = ctc.greedy_palavras(lp[0], motor.id2tok)
            hyp = [norm(p.texto) for p in palavras]
            ref = norm(linha["transcription"]).split()

            avaliacoes: list[Avaliacao] = []
            for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(
                a=ref, b=hyp, autojunk=False
            ).get_opcodes():
                # `insert` produz palavras de hipótese sem referência: são erro, e o portão
                # deveria pegá-las. `delete` não tem palavra emitida, logo não entra aqui.
                if tag == "equal":
                    avaliacoes += [Avaliacao(palavras[j].margem, False) for j in range(j1, j2)]
                elif tag in ("replace", "insert"):
                    avaliacoes += [Avaliacao(palavras[j].margem, True) for j in range(j1, j2)]
            if avaliacoes:
                por_utterance.append(avaliacoes)
    return por_utterance


def render_curva(por_utterance: list[list[Avaliacao]], cmd: str) -> str:
    import datetime

    planas = [a for u in por_utterance for a in u]
    base = sum(a.errada for a in planas) / len(planas)
    linhas = []
    for tau in TAUS:
        prec, rec = precisao_recall(planas, tau)
        ic = ic95_bootstrap(por_utterance, tau, "precisao")
        linhas.append({
            "tau": tau,
            "sinalizado": sum(sinalizar(planas, tau)) / len(planas),
            "precisao": prec, "recall": rec, "ic": ic,
            "ganho": (prec / base) if prec else None,
            # o critério de morte: o limite INFERIOR do IC tem de ficar acima da taxa base
            "separa": bool(ic and ic[0] > base),
        })
    return _AMBIENTE.get_template("e1-curva-do-portao.md.j2").render({
        "agora": datetime.datetime.now().isoformat(timespec="seconds"),
        "cmd": cmd, "n_utterances": len(por_utterance), "n_palavras": len(planas),
        "n_erradas": sum(a.errada for a in planas), "base": base, "linhas": linhas,
        "seed": SEED,
    })


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--curva", action="store_true", help="E1: precisão/recall do portão por τ")
    ap.add_argument("--n", type=int, default=100, help="utterances de FLEURS")
    ap.add_argument("--out", type=pathlib.Path, default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    if not a.curva:
        raise SystemExit("nenhum modo escolhido — use --curva (E1). --corrigir chega em E2.")

    cmd = f"python3 jvscribe/probes/portao_correcao_probe.py --curva --n {a.n}"
    texto = render_curva(avaliar(a.n), cmd)
    destino = a.out or _DADOS_BRUTOS / f"e1-curva-do-portao-n{a.n}.md"
    print(texto)
    try:
        escrever_relatorio(destino, texto, force=a.force)
    except FileExistsError as e:
        raise SystemExit(f"\n⚠️  NÃO gravado: {e}\nMesma configuração já medida.") from e
    print(f"\nevidência gravada em {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
