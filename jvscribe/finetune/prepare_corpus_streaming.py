"""Baixa e prepara o TAGARELA em CICLOS, para que o parquet saia do disco antes do próximo entrar.

O `prep_tagarela.py` sozinho assume que os shards já estão todos em disco. Isso torna o
parquet o item dominante do pico: 1.500 h são ~157 shards = **107,7 GB** que ficam parados
até o fim da extração, enquanto as features crescem por cima.

Aqui o ciclo é:

    baixa G shards  →  prepara esses G  →  apaga os parquets  →  próximo grupo

e o parquet vivo passa a ser o de UM grupo. Medido contra uma sessão do Colab com 117,5 GB
livres `[MEDIDO]`:

    | modo                         | pico em 1.500 h | teto do disco |
    |------------------------------|-----------------|---------------|
    | baixar tudo, depois preparar |      166,0 GB   |       800 h   |
    | em ciclos (este script)      |       66,5 GB   |     2.523 h   |

O teto deixa de ser o parquet e passa a ser só a feature acumulada, que é o único artefato
que precisa mesmo sobreviver até o treino.

Invariantes que este script existe para manter:

  - **id de cut único no corpus.** Cada ciclo continua a contagem do anterior (`id_offset`),
    porque um ciclo que recomeça em `tagarela_00000000` produz manifesto com id duplicado —
    e o lhotse aceita isso em silêncio.
  - **o parquet só é apagado depois que as features do grupo estão em disco.** Apagar antes
    deixaria o grupo sem áudio E sem feature, com o shard já consumido da rede.
  - **retomada.** Um ciclo já concluído tem manifesto próprio; reexecutar pula o que existe
    em vez de rebaixar 8 GB. Sessão do Colab morre; o trabalho feito não.

Uso:

    python prepare_corpus_streaming.py \\
        --out /content/data/tagarela_1500h \\
        --horas-alvo 1500 --shards-por-ciclo 12
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from lhotse import CutSet, Fbank, FbankConfig

import download_tagarela_subset as DL
import prep_tagarela as PT

# `[MEDIDO]` 31 shards do TAGARELA renderam 296,8 h depois dos filtros de accent, texto,
# alucinação e razão char/s (wiki/medicoes/m10-t3-smoke-pipeline-e-qualidade-do-rotulo.md).
#
# ⚠️ Uma segunda amostra, de 12 shards em outra faixa do corpus, rendeu 10,85 h/shard —
# 13% acima desta constante. A taxa varia com o shard, e 31 shards não bastam para fixá-la.
# NÃO ajuste este número sem propósito: ele decide QUANTOS shards, e o número de shards
# decide QUAIS (`select_indices` espaça uniformemente). Mudá-lo invalida todo plano já em
# curso — `travar_plano` transforma isso em erro em vez de corpus misturado.
HORAS_POR_SHARD = 296.8 / 31

# Acima disto a rede está fora, não "alguns shards ruins": seguir produziria um corpus
# silenciosamente menor que o alvo. Mesmo espírito do `MAX_FRACAO_DECODE_ERROR` do prep —
# fail-soft por item, fail-fast em massa.
MAX_FRACAO_SHARD_PERDIDO = 0.10


def shards_para_horas(horas: float) -> int:
    if horas <= 0:
        raise ValueError(f"horas-alvo deve ser > 0 (recebido: {horas})")
    return max(1, round(horas / HORAS_POR_SHARD))


def travar_plano(out: Path, indices: list[int]) -> None:
    """Grava a lista de shards no primeiro run e recusa qualquer run que a contradiga.

    A retomada pula ciclo por NOME de manifesto (`..._000.jsonl.gz`), e os índices vêm de
    `select_indices(total, n)`, que depende de `--horas-alvo`. Mudar o alvo entre execuções
    muda quais shards o plano pede, mas não muda os nomes: os ciclos prontos continuariam
    sendo pulados enquanto guardam shards que o novo plano não escolheu.

    O resultado seria um corpus meio de um plano e meio de outro, sem erro e sem aviso —
    e a lista `selected_shards.txt` que serve de auditoria descreveria só metade dele.
    """
    plano = out / "plano_de_shards.txt"
    linha = ",".join(str(i) for i in indices)
    if not plano.exists():
        plano.write_text(linha + "\n", encoding="utf-8")
        return
    anterior = plano.read_text(encoding="utf-8").strip()
    if anterior != linha:
        antes = anterior.split(",")
        raise RuntimeError(
            f"[stream] esta execução pede {len(indices)} shards e {plano.name} registra "
            f"{len(antes)}. O alvo mudou entre execuções.\n"
            f"Os ciclos já prontos seriam reaproveitados mesmo guardando shards que o novo "
            f"plano não escolheu — corpus meio de um plano, meio de outro, sem erro.\n"
            f"Ou volte ao alvo original, ou comece em uma --out limpa.")


def grupos(indices: list[int], tamanho: int) -> list[list[int]]:
    if tamanho <= 0:
        raise ValueError(f"shards-por-ciclo deve ser > 0 (recebido: {tamanho})")
    return [indices[i:i + tamanho] for i in range(0, len(indices), tamanho)]


def ciclo(idx_grupo: list[int], n: int, args, out: Path, extractor, id_offset: int) -> dict:
    """Um ciclo completo: baixa o grupo, prepara, apaga o parquet.

    Devolve o dict de `prep_tagarela.prepare`, de onde o chamador tira `kept` para o
    offset do próximo ciclo.
    """
    sufixo = f"_{n:03d}"
    manifesto = out / f"tagarela_cuts_train{sufixo}.jsonl.gz"
    if manifesto.exists() and manifesto.stat().st_size > 0:
        cuts = CutSet.from_file(str(manifesto))
        kept = len(cuts)
        print(f"[stream] ciclo {n}: manifesto já existe ({kept} cuts) — pulando", flush=True)
        return dict(textos=[], horas=sum(c.duration for c in cuts) / 3600.0,
                    kept=kept, show_counts={}, manifesto=manifesto, retomado=True,
                    perdidos=[])

    raw = out / f"raw{sufixo}"
    raw.mkdir(parents=True, exist_ok=True)
    perdidos = []
    for i in idx_grupo:
        try:
            DL.download_shard(i, args.total_shards, args.pattern, raw, args.token)
        except (subprocess.CalledProcessError, RuntimeError) as e:
            # Um shard vale ~9,6 h de 1.500: derrubar 14 ciclos por 0,6% do corpus é
            # desproporcional. Mas perder shard também não pode ser invisível — ele é
            # contado, relatado, e a perda em massa aborta.
            perdidos.append(i)
            print(f"[stream] ciclo {n}: shard {i:05d} PERDIDO após os retries ({e})",
                  flush=True)
    if len(perdidos) > max(1, len(idx_grupo) * MAX_FRACAO_SHARD_PERDIDO):
        raise RuntimeError(
            f"[stream] ciclo {n}: {len(perdidos)}/{len(idx_grupo)} shards perdidos "
            f"({', '.join(f'{i:05d}' for i in perdidos)}) — isso é a rede fora, não shard "
            f"ruim. Corrija a conexão; não monte corpus de treino com buraco em silêncio.")
    if not list(raw.glob("*.parquet")):
        raise RuntimeError(f"[stream] ciclo {n}: nenhum shard baixado — rede indisponível.")
    print(f"[stream] ciclo {n}: {len(idx_grupo) - len(perdidos)}/{len(idx_grupo)} shards "
          f"em {raw}", flush=True)

    r = PT.prepare(raw, out, extractor, args.num_jobs, None,
                   shards_per_batch=args.shards_por_lote,
                   drop_audio=True, id_offset=id_offset, sufixo=sufixo)
    # Só agora: as features do grupo estão gravadas e o parquet não é mais necessário.
    shutil.rmtree(raw, ignore_errors=True)
    r["retomado"] = False
    r["perdidos"] = perdidos
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--horas-alvo", type=float, default=1500.0)
    ap.add_argument("--shards-por-ciclo", type=int, default=12,
                    help="shards baixados e preparados por ciclo — define o parquet vivo")
    ap.add_argument("--shards-por-lote", type=int, default=4,
                    help="sublote dentro do ciclo — define o wav vivo")
    ap.add_argument("--num-jobs", type=int, default=8)
    ap.add_argument("--total-shards", type=int, default=1764)
    ap.add_argument("--pattern", default=DL.SHARD_PATTERN)
    ap.add_argument("--token", default="")
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    extractor = Fbank(FbankConfig(num_mel_bins=80))

    n_shards = shards_para_horas(args.horas_alvo)
    indices = DL.select_indices(args.total_shards, n_shards)
    travar_plano(out, indices)
    lotes = grupos(indices, args.shards_por_ciclo)
    print(f"[stream] alvo {args.horas_alvo:.0f} h → {len(indices)} shards "
          f"({HORAS_POR_SHARD:.2f} h/shard [MEDIDO]) em {len(lotes)} ciclos", flush=True)

    id_offset, horas = 0, 0.0
    show_counts: dict[str, int] = {}
    manifestos, perdidos = [], []
    for n, g in enumerate(lotes):
        r = ciclo(g, n, args, out, extractor, id_offset)
        id_offset += r["kept"]
        horas += r["horas"]
        for show, c in r["show_counts"].items():
            show_counts[show] = show_counts.get(show, 0) + c
        manifestos.append(r["manifesto"])
        perdidos.extend(r["perdidos"])
        print(f"[stream] ciclo {n + 1}/{len(lotes)}: {horas:.1f} h acumuladas", flush=True)

    todos = CutSet.from_cuts(c for m in manifestos for c in CutSet.from_file(str(m)))
    ids = [c.id for c in todos]
    if len(set(ids)) != len(ids):
        raise RuntimeError(
            f"[stream] {len(ids) - len(set(ids))} ids duplicados no manifesto consolidado — "
            f"o offset entre ciclos não foi respeitado. Treinar assim veria a mesma "
            f"utterance mais de uma vez, sem erro e sem aviso.")
    todos.to_file(str(out / "tagarela_cuts_train.jsonl.gz"))
    if show_counts:
        PT._write_coverage_report(out, show_counts, sum(show_counts.values()))
    # O transcript sai do manifesto CONSOLIDADO, não do acumulado em memória: um ciclo
    # retomado não devolve textos (ele nunca rodou nesta execução), e o `transcript_words`
    # é o que treina o BPE. Montá-lo do acumulado deixaria o tokenizer cego para os ciclos
    # que a sessão anterior preparou — sem erro, e com vocabulário errado.
    textos_finais = [sup.text for c in todos for sup in c.supervisions if sup.text]
    (out / "transcript_words.txt").write_text("\n".join(textos_finais) + "\n",
                                              encoding="utf-8")

    print(f"[stream] pronto: {len(ids)} cuts, "
          f"{sum(c.duration for c in todos) / 3600:.1f} h [MEDIDO] → "
          f"tagarela_cuts_train.jsonl.gz", flush=True)
    if perdidos:
        # O corpus é menor do que o alvo pedia, e isso precisa estar escrito em algum
        # lugar que sobreviva ao scrollback.
        nota = (f"{len(perdidos)}/{len(indices)} shards perdidos na rede "
                f"(~{len(perdidos) * HORAS_POR_SHARD:.0f} h a menos que o alvo): "
                f"{', '.join(f'{i:05d}' for i in perdidos)}\n")
        (out / "shards_perdidos.txt").write_text(nota, encoding="utf-8")
        print(f"[stream] ⚠️  {nota}[stream] registrado em {out / 'shards_perdidos.txt'}",
              flush=True)


if __name__ == "__main__":
    main()
