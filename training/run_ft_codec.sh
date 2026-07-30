#!/bin/bash
# Phase 4 (plano m5-8khz-telephone-wer) — FT GENTIL CORRIGIDO com codec-pool realista.
#
# Corrige o colapso do D2 (near-blank) cujas causas medidas foram: base-lr 0.006 (alto),
# warm-start de checkpoint MÉDIO (scheduler Eden reinicia no pico) e augmentação a 100%.
# Correções (ADR D2/D3 do plano):
#   - base-lr 0.002 (~1/10 do treino, como manda o icefall FT)
#   - warm-start de checkpoint ÚNICO (checkpoint-124000.pt, 24,73% wideband), NÃO o avg
#   - codec-pool realista (GSM/Opus/G.711) via telephone_channel_transform atualizado, p=0.5
#     (metade do batch fica limpa = âncora de alinhamento do CTC, antídoto ao colapso)
#   - fp32 (--use-fp16 0) para não repetir o colapso de grad_scale sob choque de augmentação
#   - warmup_batches=4000 já é default no train.py:709
# DEFERIDO (para não patchar o modelo com risco agora): --use-mux (inexistente neste recipe;
#   o p=0.5 cumpre o papel) e bandwidth-embedding (muda dim de entrada do artefato — follow-up).
set -euo pipefail
cd /workspace/icefall/egs/commonvoice/ASR

CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=1 python3 zipformer/train.py \
  --world-size 1 --num-epochs 3 --start-epoch 1 --use-fp16 0 \
  --exp-dir zipformer/exp-m5-ft-codec \
  --manifest-dir data/mux --cv-manifest-dir data/mux --language pt \
  --bpe-model data/lang_bpe_500/bpe.model \
  --do-finetune True --finetune-ckpt zipformer/exp-m5-finetune/checkpoint-124000.pt \
  --init-modules "encoder,ctc_output,phoneme_output" \
  --use-ctc 1 --use-transducer 0 --use-phoneme-ctc 1 \
  --phoneme-targets-json /workspace/phoneme_targets_m5.json \
  --base-lr 0.002 --lr-epochs 3 --lr-batches 5000 \
  --enable-musan 1 --enable-telephone-aug 1 --on-the-fly-feats True \
  --num-workers 2 --max-duration 300 \
  --num-encoder-layers 2,2,3,4,3,2 \
  --feedforward-dim 512,768,1024,1536,1024,768 \
  --encoder-dim 192,256,384,512,384,256 \
  --encoder-unmasked-dim 192,192,256,256,256,192
