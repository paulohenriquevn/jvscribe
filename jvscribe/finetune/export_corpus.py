"""Torna o corpus preparado PORTÁVEL — para outra máquina, ou para publicação.

O `lhotse` grava caminho ABSOLUTO no manifesto:

    "storage_path": "/content/drive/MyDrive/jvscribe/corpus/feats_train_000.lca"
    "sources": [{"source": "/content/scratch/wav_train/tagarela_train_00000000.wav"}]

Enquanto o treino roda na mesma máquina que extraiu, isso passa despercebido. Mas o
corpus é preparado no Colab e consumido na vast.ai, e lá esses caminhos não existem —
o `load_features()` falharia utterance a utterance, no meio de um treino pago.

Este script reescreve o manifesto com caminhos RELATIVOS à raiz do corpus, e devolve um
diretório que pode ser copiado, montado em outro ponto, ou publicado como dataset.

Sobre publicar: o TAGARELA é `CC-BY-NC-SA-4.0` e o ADR-0006 registra que o dono aceitou
esse risco. ShareAlike significa que um derivado — e um corpus de features derivadas é um
derivado — precisa sair sob a MESMA licença, com atribuição à fonte. O
`--escrever-card` gera o README com essas duas coisas e com a proveniência do rótulo,
que é pseudo-rótulo de máquina e não transcrição humana.

Uso:
    python export_corpus.py --raiz /content/drive/MyDrive/jvscribe/corpus
    python export_corpus.py --raiz ... --escrever-card
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

MANIFESTO = "tagarela_cuts_train.jsonl.gz"

CARD = """---
license: cc-by-nc-sa-4.0
language: [pt]
task_categories: [automatic-speech-recognition]
---

# {nome}

{horas:.0f} h of Brazilian Portuguese speech as precomputed 80-dimensional log-mel
filterbank features, in lhotse `CutSet` format, ready for icefall training.

## Provenance

Derived from [freds0/TAGARELA](https://huggingface.co/datasets/freds0/TAGARELA),
`CC-BY-NC-SA-4.0`. This derivative carries the same license, as ShareAlike requires.

## What was done

1. Shards sampled at uniform spacing across the source, so no region dominates.
2. Utterances dropped when the accent field is not `pt-br`, the text normalizes to
   nothing, the text shows a Whisper hallucination loop, or the character-per-second
   ratio is implausible. The retention rate is printed per cycle by the preparation
   run; it is not restated here, because this script cannot observe it.
3. Audio decoded, downmixed to mono, resampled to 16 kHz.
4. Fbank extracted: 80 mel bins, 10 ms frame shift, stored with `lilcom_chunky`.

## What this is NOT

**The transcriptions are machine-generated and were not verified by a human.** The source
labels come from a Whisper-large-v3 fine-tune, and an independent measurement against
NVIDIA Nemotron-3.5 found the two disagree on 22.7% of words. Disagreement is not error —
without human transcription neither side is known to be right — but it bounds what these
labels can support. Do not use them as a test set or as ground truth.

**Lilcom is lossy compression.** It is the de facto default of lhotse and icefall; its
effect on final WER has not been measured here.

## Paths

Feature paths in the manifest are relative to the directory holding it. Keep them
together, or rewrite them for your layout.
"""


def relativizar(raiz: Path, manifesto: Path, saida: Path) -> dict:
    """Reescreve storage_path e sources como caminhos relativos a `raiz`.

    Um caminho que não está sob `raiz` é deixado como está e contado: mentir sobre ele
    produziria um manifesto que parece portável e falha na primeira leitura.
    """
    n, rel, fora, horas = 0, 0, 0, 0.0
    with gzip.open(manifesto, "rt", encoding="utf-8") as origem, \
            gzip.open(saida, "wt", encoding="utf-8") as destino:
        for linha in origem:
            cut = json.loads(linha)
            n += 1
            horas += cut.get("duration", 0.0)
            for caminho, escrever in _caminhos(cut):
                p = Path(caminho)
                if not p.is_absolute():
                    continue
                try:
                    escrever(str(p.relative_to(raiz)))
                    rel += 1
                except ValueError:
                    fora += 1
            destino.write(json.dumps(cut, ensure_ascii=False) + "\n")
    return dict(cuts=n, relativizados=rel, fora_da_raiz=fora, horas=horas / 3600.0)


def _caminhos(cut: dict):
    """Rende (valor, setter) para cada caminho de arquivo dentro de um cut."""
    feats = cut.get("features")
    if feats and "storage_path" in feats:
        yield feats["storage_path"], lambda v: feats.__setitem__("storage_path", v)
    rec = cut.get("recording")
    for src in (rec or {}).get("sources", []):
        if src.get("type") == "file":
            yield src["source"], (lambda s: lambda v: s.__setitem__("source", v))(src)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", required=True, help="dir do corpus (--out da preparação)")
    ap.add_argument("--manifesto", default=MANIFESTO)
    ap.add_argument("--escrever-card", action="store_true",
                    help="gera o README.md com licença, atribuição e proveniência do rótulo")
    ap.add_argument("--nome", default="tagarela-ptbr-fbank")
    args = ap.parse_args()

    raiz = Path(args.raiz).resolve()
    manifesto = raiz / args.manifesto
    if not manifesto.exists():
        raise SystemExit(f"{manifesto} não existe — a preparação terminou?")

    saida = raiz / args.manifesto.replace(".jsonl.gz", ".portable.jsonl.gz")
    r = relativizar(raiz, manifesto, saida)
    print(f"[export] {r['cuts']} cuts, {r['horas']:.1f} h · "
          f"{r['relativizados']} caminhos relativizados → {saida.name}")
    if r["fora_da_raiz"]:
        raise SystemExit(
            f"[export] {r['fora_da_raiz']} caminhos apontam para FORA de {raiz} e não "
            f"puderam ser relativizados. Mover este corpus quebraria esses cuts na "
            f"primeira leitura. Traga os arquivos para dentro da raiz antes de exportar.")

    if args.escrever_card:
        # O card não afirma a taxa de retenção: este script vê o manifesto FINAL, que já
        # é o que sobrou, e não tem como saber quantas utterances entraram. Inventar o
        # número seria publicar uma medição que ninguém fez.
        card = raiz / "README.md"
        card.write_text(CARD.format(nome=args.nome, horas=r["horas"]), encoding="utf-8")
        print(f"[export] card em {card} — revise antes de publicar")


if __name__ == "__main__":
    main()
