"""Amostrador ESTRATIFICADO do TAGARELA (freds0/TAGARELA) — o subset auditável que
`prep_tagarela.py` consome (F6 da revisão de corpus: antes, este script era citado no
docstring do prep mas não existia no repo → a representatividade do subset não era
auditável).

O TAGARELA tem 1764 shards parquet (~8.972h, ~1,21TB). M5 (D4) precisa de ~500h. Baixar
o corpus inteiro é inviável (disco/tempo). A estratégia: escolher `--num-shards` shards
**espaçados uniformemente** ao longo dos 1764 (não os N primeiros — os shards do HF
tendem a agrupar show/episódio, então os N primeiros super-representariam poucos shows).
O espaçamento uniforme amostra ao longo de todo o corpus, reduzindo o viés show/episódio.

A DECISÃO de amostragem é a função pura `select_indices` (testada offline) — a parte de
rede (curl) só materializa a seleção. O script escreve `selected_shards.txt` (a lista
exata de shards baixados) para a amostragem ser 100% auditável a posteriori.

CAVEAT honesto (§4 evidence-discipline): espaçamento uniforme de shards reduz o viés
show/episódio SE os shards não estiverem perfeitamente ordenados por show; e ainda assim
super-representa shows com mais shards (proporcional ao volume). Sem metadado de show por
shard, a estratificação é por posição, não por show — o relatório de cobertura por show
do `prep_tagarela.py` (`show_distribution.txt`) mede o resultado real e sinaliza domínio.

Uso (na instância, HF_TOKEN no ambiente se o dataset for gated):
  python3 download_tagarela_subset.py --out /workspace/tagarela_raw/data \
      --num-shards 120 --total-shards 1764
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

REPO = "freds0/TAGARELA"
# padrão de nome de shard no HF (config default). Ajustável via --pattern se o dataset
# usar outro layout (ex.: split diferente de "train").
SHARD_PATTERN = "data/train-{i:05d}-of-{total:05d}.parquet"


def select_indices(total: int, num: int) -> list[int]:
    """Índices de shards espaçados uniformemente ao longo de [0, total-1], INCLUINDO os
    extremos (0 e total-1), determinístico e sem duplicatas.

    Retorna `min(num, total)` índices no caso geral; pode retornar MENOS que `num` quando
    total é pequeno e o arredondamento colide (dedup) — comportamento honesto/documentado,
    não silencioso (o chamador vê len(idx) < num)."""
    if total <= 0 or num <= 0:
        raise ValueError(f"total e num devem ser > 0 (total={total}, num={num})")
    if num >= total:
        return list(range(total))
    if num == 1:
        return [0]
    # linspace(0, total-1, num) arredondado; set → dedup; sorted → ordem estável
    return sorted({round(i * (total - 1) / (num - 1)) for i in range(num)})


def download_shard(i: int, total: int, pattern: str, out: Path, token: str) -> Path:
    rel = pattern.format(i=i, total=total)
    dest = out / Path(rel).name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    url = f"https://huggingface.co/datasets/{REPO}/resolve/main/{rel}"
    cmd = ["curl", "-sfL", "--retry", "3", url, "-o", str(dest)]
    if token:
        cmd[1:1] = ["-H", f"Authorization: Bearer {token}"]
    subprocess.run(cmd, check=True)  # -f: falha explícita em HTTP 4xx/5xx (fail-fast)
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="dir destino dos shards (= --parquet-dir do prep)")
    ap.add_argument("--num-shards", type=int, default=120, help="quantos shards baixar (~500h)")
    ap.add_argument("--total-shards", type=int, default=1764, help="total de shards do TAGARELA")
    ap.add_argument("--pattern", default=SHARD_PATTERN, help="template do nome do shard no HF")
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("HF_TOKEN", "")
    idx = select_indices(args.total_shards, args.num_shards)
    print(f"[subset] {len(idx)} shards selecionados (espaçamento uniforme sobre "
          f"{args.total_shards}): {idx[:5]}…{idx[-3:]}", flush=True)

    selected = []
    for i in idx:
        dest = download_shard(i, args.total_shards, args.pattern, out, token)
        selected.append(f"{i}\t{dest.name}")
        print(f"[subset] shard {i:05d} → {dest.name}", flush=True)

    (out / "selected_shards.txt").write_text("\n".join(selected) + "\n", encoding="utf-8")
    print(f"[subset] pronto: {len(selected)} shards em {out} "
          f"(lista auditável em selected_shards.txt)", flush=True)


if __name__ == "__main__":
    main()
