"""Medição de erro de transcrição — **a primitiva e a estatística, num módulo só**.

Todo número de acurácia deste projeto passa por aqui:

| função | responde |
|---|---|
| `word_edit_distance` | quantas edições separam referência e hipótese (o **numerador**) |
| `per_utterance_errors` | pareia dois recogs do icefall sobre o MESMO test set |
| `paired_bootstrap` | a diferença entre dois modelos é **significativa**? |

## Por que este módulo existe (consolidação de 2026-07-31)

O domínio estava em `tools/wer_core.py` + `tools/bootstrap_wer_ci.py` — dentro de `tools/`,
uma pasta que acumulava sete domínios sem relação. `word_edit_distance` tem **7 consumidores**
em quatro pipelines; uma primitiva desse alcance pertence ao shared kernel, não a uma lixeira.

## ⚠️ A estatística NÃO é intercambiável com `common/stats.py`

`stats.comparar_pareado` compara medições **escalares** (ms de latência) pela **média das
diferenças pareadas**. Aqui a estatística é **razão de somas** — `sum(erros)/sum(palavras)` —
porque não se faz média de WERs por utterance: uma frase de 2 palavras pesaria igual a uma de
40.

`[MEDIDO]` no mesmo par de utterances, os dois métodos dão **4,76 p.p. e 26,25 p.p.** — 5,5×
de diferença. Trocar um pelo outro mudaria em silêncio todo delta de WER publicado. Os dois
módulos são vizinhos e permanecem **separados de propósito**.

## Concordância com `jiwer`

`word_edit_distance` e `jiwer.process_words` concordam em **4.000 pares aleatórios** `[MEDIDO]`
— por isso `eval/eval_wer.py` (que usa jiwer) e este módulo produzem o mesmo numerador. Sem
essa verificação, seriam duas réguas de contagem de erro, o defeito que este repositório já
pagou três vezes no texto.

Puro: sem I/O, sem numpy, sem soundfile. Ferramentas de texto e seus testes importam daqui
sem arrastar a stack de áudio.
"""
from __future__ import annotations

import ast
import random
import re
from pathlib import Path


def word_edit_distance(ref: list[str], hyp: list[str]) -> int:
    """Levenshtein (S+D+I) sobre sequências — o numerador do WER/CER."""
    m, n = len(ref), len(hyp)
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        cur = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[n]


# ── adaptador do formato `recogs-*.txt` do icefall ───────────────────────────────────
# Fica aqui, e não num módulo à parte, porque `per_utterance_errors` abaixo é seu único
# consumidor de biblioteca — separá-los criava um arquivo de 91 linhas cuja razão de
# existir era só "parsear o que a função seguinte precisa".
# `<utt>:\tref=['a', 'b', ...]` — captura o rótulo (ref|hyp) e a lista literal.
LINE = re.compile(r":\t(ref|hyp)=(\[.*\])$")


def parse_recogs(text: str) -> dict[str, tuple[list[str], list[str]]]:
    """Parseia um recogs do icefall em {utt: (ref_words, hyp_words)} (puro, testável).

    Falha alto (`ValueError`) se ref/hyp ficarem desemparelhados (caso negativo:
    recogs truncado ou corrompido não pode virar um número silenciosamente).
    """
    refs: dict[str, list[str]] = {}
    hyps: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = LINE.search(line)
        if not m:
            continue  # timestamp_hyp e afins são ignorados
        utt = line.split(":", 1)[0]
        words = ast.literal_eval(m.group(2))
        (refs if m.group(1) == "ref" else hyps)[utt] = words

    if not refs and not hyps:
        raise ValueError("recogs vazio — nenhuma linha ref=/hyp= (arquivo corrompido/formato errado?)")
    unpaired = set(refs) ^ set(hyps)
    if unpaired:
        raise ValueError(f"ref/hyp desemparelhados em {len(unpaired)} utterances: {sorted(unpaired)[:3]}")
    return {utt: (refs[utt], hyps[utt]) for utt in refs}


def score_recogs(text: str) -> dict:
    """Computa WER+CER de um recogs do icefall (lógica pura, sem I/O — testável)."""
    parsed = parse_recogs(text)
    refs = {u: r for u, (r, _) in parsed.items()}
    hyps = {u: h for u, (_, h) in parsed.items()}

    tot_cerr = tot_chars = tot_werr = tot_words = 0
    for utt, ref in refs.items():
        hyp = hyps[utt]
        tot_werr += word_edit_distance(ref, hyp)
        tot_words += len(ref)
        ref_c, hyp_c = list("".join(ref)), list("".join(hyp))
        tot_cerr += word_edit_distance(ref_c, hyp_c)
        tot_chars += len(ref_c)

    return {
        "utterances": len(refs),
        "words": tot_words,
        "chars": tot_chars,
        "werr": tot_werr,
        "cerr": tot_cerr,
        "wer": 100.0 * tot_werr / max(tot_words, 1),
        "cer": 100.0 * tot_cerr / max(tot_chars, 1),
    }


def per_utterance_errors(baseline_text: str, cand_text: str) -> list[tuple[int, int, int]]:
    """[(werr_base, werr_cand, n_ref_words)] por utterance, sobre o MESMO test set.

    Falha alto se os conjuntos de utterances divergirem (test sets diferentes → o
    pareamento seria inválido) ou se a referência de uma utterance diferir entre os
    dois arquivos (não é o mesmo alvo → comparação sem sentido).
    """
    base = parse_recogs(baseline_text)
    cand = parse_recogs(cand_text)
    if set(base) != set(cand):
        raise ValueError(f"conjuntos de utterances diferem ({len(set(base) ^ set(cand))} sem par)")
    rows = []
    for utt, (ref_b, hyp_b) in base.items():
        ref_c, hyp_c = cand[utt]
        if ref_b != ref_c:
            raise ValueError(f"referência difere na utterance {utt} — não é o mesmo test set")
        rows.append((word_edit_distance(ref_b, hyp_b), word_edit_distance(ref_c, hyp_c), len(ref_b)))
    return rows


def _wer_pair(rows: list[tuple[int, int, int]]) -> tuple[float, float]:
    eb = sum(r[0] for r in rows)
    ec = sum(r[1] for r in rows)
    w = sum(r[2] for r in rows) or 1
    return 100.0 * eb / w, 100.0 * ec / w


def paired_bootstrap(
    rows: list[tuple[int, int, int]], n_boot: int = 10000, seed: int = 42, dod_threshold: float = 3.0
) -> dict:
    """IC 95% (percentil) da diferença de WER e da melhora relativa, por reamostragem
    de utterances com reposição. `rows` = saída de per_utterance_errors. Emite também
    P(melhora>0) (significância) e P(melhora>=dod_threshold) (confiança de bater a DoD)
    da MESMA distribuição bootstrap — os números do artefato de decisão saem deste
    comando, não de um snippet à parte (proveniência fechada; review M4)."""
    if not rows:
        raise ValueError("nenhuma utterance pareada — recogs vazios ou test sets disjuntos?")
    wer_base, wer_cand = _wer_pair(rows)
    abs_diff = wer_base - wer_cand                      # p.p. que o candidato reduz
    rel_impr = 100.0 * abs_diff / wer_base if wer_base else 0.0
    rng = random.Random(seed)
    n = len(rows)
    diffs, rels = [], []
    n_gt0 = n_ge_thr = 0
    for _ in range(n_boot):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        wb, wc = _wer_pair(sample)
        diffs.append(wb - wc)
        rel = 100.0 * (wb - wc) / wb if wb else 0.0
        rels.append(rel)
        n_gt0 += rel > 0.0
        n_ge_thr += rel >= dod_threshold
    diffs.sort()
    rels.sort()
    lo, hi = int(0.025 * n_boot), int(0.975 * n_boot)
    return {
        "wer_base": wer_base, "wer_cand": wer_cand,
        "abs_diff_pp": abs_diff, "abs_ci95": (diffs[lo], diffs[hi]),
        "rel_impr_pct": rel_impr, "rel_ci95": (rels[lo], rels[hi]),
        "p_gt0_pct": 100.0 * n_gt0 / n_boot,
        "dod_threshold": dod_threshold, "p_ge_thr_pct": 100.0 * n_ge_thr / n_boot,
        "n_utt": n, "n_boot": n_boot, "seed": seed,
    }


def find_test_parquet() -> Path:
    """Localiza o parquet do FLEURS pt_br test no cache local do HuggingFace.

    Mora aqui — e não num harness específico — porque `eval/` e `probes/` precisam do MESMO
    test set. Enquanto vivia em `eval_runtime_wer.py`, o probe importava cross-pipeline para
    alcançá-lo, furando a regra "cross-pipeline apenas a partir de common/".
    """
    cands = list(
        Path.home().glob(
            ".cache/huggingface/hub/datasets--google--fleurs/snapshots/*/"
            "parquet-data/pt_br/test-*.parquet"
        )
    )
    if not cands:
        raise SystemExit("parquet de teste FLEURS pt_br não encontrado no cache HF local")
    return sorted(cands)[0]


def escrever_relatorio(destino: str | Path, texto: str, *, force: bool = False) -> Path:
    """Grava um relatório de medição — **recusando sobrescrever** um já existente.

    Os três scripts de baseline gravavam num caminho fixo dentro de `wiki/medicoes/`. Um deles
    (`eval/baseline_fleurs_ptbr.py`) foi executado com `n=2` durante o live test de 2026-07-31
    e **substituiu o baseline real de M1** — 12 utterances e 3 modelos — por uma corrida de
    duas. Só o git salvou.

    Medição publicada é evidência: sobrescrevê-la tem de ser um ato deliberado, não o efeito
    colateral de um teste rápido. Por isso o default é recusar, e `--force` é explícito.

    Raises:
        FileExistsError: quando o destino já existe e `force` é falso.
    """
    p = Path(destino)
    if p.exists() and not force:
        raise FileExistsError(
            f"{p} já existe e é evidência publicada. Rode com `--force` para substituir "
            f"deliberadamente, ou aponte `--out` para outro caminho. "
            f"(Uma corrida curta já apagou um baseline completo aqui.)"
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto if texto.endswith("\n") else texto + "\n", encoding="utf-8")
    return p
