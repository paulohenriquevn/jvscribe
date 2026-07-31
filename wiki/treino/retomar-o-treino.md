---
type: Runbook
title: Retomar o treino
description: As quatro flags obrigatórias que não estão no .pt, e a diferença entre os dois pontos de partida.
resource: models/current/finetune/README.md
tags: [treino, icefall, checkpoint, flags]
timestamp: 2026-07-31T00:00:00Z
---

# Retomar o treino

## As quatro flags de arquitetura são obrigatórias

Elas **não estão dentro do `.pt`**. Sem elas o checkpoint não carrega:

```
--num-encoder-layers    2,2,3,4,3,2
--feedforward-dim       512,768,1024,1536,1024,768
--encoder-dim           192,256,384,512,384,256
--encoder-unmasked-dim  192,192,256,256,256,192
```

## Dois pontos de partida, com propósitos diferentes

| arquivo | tamanho | o que carrega | serve para |
|---|---|---|---|
| `checkpoint-124000.pt` | 982 MB | `model` + `optimizer` + `scheduler` + `grad_scaler` + `sampler` | **retomar** o run com o LR schedule intacto |
| `avg-124k-112k.pt` | 257 MB | só pesos | finetune novo — o otimizador reinicia |

O tamanho conta a história: os 982 MB são grandes porque carregam estado de otimização.

## Finetune a partir dos pesos

```bash
python3 zipformer/train.py \
  --do-finetune True --finetune-ckpt <caminho>/avg-124k-112k.pt \
  --init-modules "encoder,ctc_output,phoneme_output" \
  --bpe-model data/lang_bpe_500/bpe.model \
  --use-ctc 1 --use-transducer 0 --use-phoneme-ctc 1 \
  --phoneme-targets-json <caminho>/phoneme_targets.json \
  --base-lr 0.002 --use-fp16 0 \
  <as quatro flags acima>
```

Partir do `avg-124k-112k.pt` começa do modelo **melhor** (15,99%); do `checkpoint-124000.pt`,
do que gerou o segundo (17,32%).

## Continuar o run original

Só o `checkpoint-124000.pt` serve, porque só ele tem `optimizer`/`scheduler`. Coloque-o na
`--exp-dir` e use `--start-batch 124000`. É o caminho que preserva o LR schedule.

## Verificar que um checkpoint é utilizável

```bash
python3 jvscribe/bench/finetune_smoke.py --checkpoint <pt> --bpe <bpe.model> \
    --audio-dir <wavs> --refs <refs.tsv> --icefall <clone> --k2stub <stub>
```

Afirma três coisas e mede cada uma: `load_state_dict` sem chave faltando; CTC loss **25× menor**
que a de um modelo aleatório no mesmo lote (um `.pt` corrompido daria loss de aleatório); e a
loss caindo com o gradiente fluindo.

## Incidente registrado

O `avg-124k-112k.pt` **chegou truncado** da nuvem — 80 MB de 257 MB, disco cheio durante o
salvamento. Foi reconstruído pela média dos dois checkpoints íntegros. O arquivo truncado ficou
preservado como `.corrupt.pt`; peso não se apaga.

E o melhor checkpoint do treino **não está em disco**: o `wer_trajectory.log` registra
`epoch-98.pt` com WER 22,09%, podado antes do download.
