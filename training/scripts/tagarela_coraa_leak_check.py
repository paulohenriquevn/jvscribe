"""Cross-check de vazamento CROSS-CORPUS TAGARELA(train) × CORAA-test (F2 da revisão).

A garantia estrutural do `prep_tagarela.py` (sem flag de split dev/test) impede o TAGARELA
de VIRAR manifesto de test. Ela NÃO cobre o caso em que um mesmo conteúdo/locutor aparece
tanto no TAGARELA-train (podcasts) quanto no test CORAA humano — que inclui **TEDx** e
figuras públicas plausivelmente também presentes em podcasts. Overlap assim vazaria
características de locutor do train para o test e inflaria o ganho medido de WER
(invariante §7.3 / falácia §3 #10, na dimensão CONTEÚDO, não id).

Este script torna o risco DEMONSTRÁVEL onde é verificável: os segmentos TEDx do CORAA
codificam um `videoID` (YouTube) no `file_path`. Se algum token do `path` de um utterance
do TAGARELA casa um `videoID` do TEDx no test CORAA, é vazamento comprovado → exit 1
(reportar como BLOCKER). Sem interseção, exit 0 e o risco residual (não-verificável para
ALIP/SP2010/NURC, sem chave pública) fica DECLARADO no deliverable de M5 (Regra 3).

Roda NA INSTÂNCIA (onde o parquet TAGARELA e o metadata CORAA coexistem). A lógica pura
(`tedx_video_ids`, `path_tokens`, `find_leaks`) é testada offline com dados sintéticos.

Uso (na instância):
  python3 tagarela_coraa_leak_check.py \
      --tagarela-parquet-dir /workspace/tagarela_raw/data \
      --coraa-meta /workspace/coraa_work/metadata_test_final.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys

# tokens < este comprimento são ruído (videoIDs do YouTube têm 11 chars); o limiar evita
# casar tokens curtos/comuns ("de", "sp", números de segmento) e gerar falso-positivo.
MIN_TOKEN_LEN = 8
_SPLIT = re.compile(r"[/\-_.\s]+")


def tedx_video_ids(coraa_meta_csv: str) -> set[str]:
    """Conjunto de videoIDs dos segmentos TEDx do CORAA (mesma extração do
    `coraa_speaker_overlap.py`: basename sem o sufixo `-{seg}`)."""
    ids: set[str] = set()
    with open(coraa_meta_csv, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("dataset") == "TEDx Talks":
                stem = os.path.splitext(os.path.basename(row["file_path"]))[0]
                ids.add(re.sub(r"-\d+$", "", stem))
    return ids


def path_tokens(path: str) -> set[str]:
    """Tokens de um path do TAGARELA (split em / - _ . espaço), filtrados por comprimento
    mínimo para sensibilidade sem ruído."""
    return {t for t in _SPLIT.split(path or "") if len(t) >= MIN_TOKEN_LEN}


def find_leaks(tagarela_paths, tedx_ids: set[str]) -> dict[str, set[str]]:
    """Mapeia cada path do TAGARELA que casa ≥1 videoID do TEDx → os ids casados.
    Dict vazio = sem vazamento demonstrável."""
    leaks: dict[str, set[str]] = {}
    if not tedx_ids:
        return leaks
    for path in tagarela_paths:
        hit = path_tokens(path) & tedx_ids
        if hit:
            leaks[path] = hit
    return leaks


def _iter_tagarela_paths(parquet_dir: str):
    import pyarrow.parquet as pq  # import local: a lógica pura não depende de pyarrow
    from pathlib import Path
    for shard in sorted(Path(parquet_dir).glob("*.parquet")):
        pf = pq.ParquetFile(shard)
        for batch in pf.iter_batches(columns=["path"]):
            yield from batch.to_pydict()["path"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tagarela-parquet-dir", required=True)
    ap.add_argument("--coraa-meta", required=True, help="metadata_test_final.csv do CORAA")
    args = ap.parse_args()

    tedx = tedx_video_ids(args.coraa_meta)
    print(f"[leak-check] {len(tedx)} videoIDs TEDx no test CORAA", flush=True)
    if not tedx:
        print("[leak-check] AVISO: nenhum segmento TEDx no metadata — cross-check inócuo "
              "(o risco residual cross-corpus permanece não-verificável; declarar em M5).",
              flush=True)
    leaks = find_leaks(_iter_tagarela_paths(args.tagarela_parquet_dir), tedx)
    if leaks:
        print(f"[leak-check] VAZAMENTO: {len(leaks)} path(s) do TAGARELA casam videoID TEDx "
              f"do test CORAA — BLOCKER (§7.3):", flush=True)
        for path, ids in list(leaks.items())[:20]:
            print(f"  {path}  ←  {sorted(ids)}", flush=True)
        sys.exit(1)
    print("[leak-check] OK: nenhum path do TAGARELA casa videoID TEDx do test CORAA. "
          "Risco residual cross-corpus (locutores sem chave pública: NURC/ALIP/SP2010) "
          "permanece NÃO-VERIFICÁVEL — declarar como caveat no deliverable de M5.",
          flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
