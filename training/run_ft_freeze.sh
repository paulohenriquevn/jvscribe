#!/bin/bash
# Phase 4b (plano m5-8khz) — FT COLLAPSE-PROOF: encoder profundo CONGELADO, adapta só o
# frontend (encoder_embed 0,61M) + cabeças (ctc 0,26M + fonema 0,035M) = ~0,9M treináveis (~1,4%).
#
# Motivo: full-FT com codec-aug colapsa o greedy p/ ~98% (D2 e o run gentil, MEDIDO 2×). Com o
# corpo do encoder (63M) fixo na representação boa (37% real-codec), o modelo NÃO PODE driftar
# para blank; o frontend adapta ao canal telefônico. É o equivalente barato de um adapter
# (research asr-chief). FREEZE_ENCODER=1 dispara o patch em train.py (antes do optimizer).
set -euo pipefail
cd /workspace/icefall/egs/commonvoice/ASR

FREEZE_ENCODER=1 CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=1 python3 zipformer/train.py \
  --world-size 1 --num-epochs 3 --start-epoch 1 --use-fp16 0 \
  --exp-dir zipformer/exp-m5-ft-freeze \
  --manifest-dir data/mux --cv-manifest-dir data/mux --language pt \
  --bpe-model data/lang_bpe_500/bpe.model \
  --do-finetune True --finetune-ckpt zipformer/exp-m5-finetune/checkpoint-124000.pt \
  --init-modules "encoder,ctc_output,phoneme_output" \
  --use-ctc 1 --use-transducer 0 --use-phoneme-ctc 1 \
  --phoneme-targets-json /workspace/phoneme_targets_m5.json \
  --base-lr 0.002 --lr-epochs 3 --lr-batches 5000 \
  --enable-musan 1 --enable-telephone-aug 1 --on-the-fly-feats True \
  --num-workers 10 --max-duration 300 \
  --num-encoder-layers 2,2,3,4,3,2 \
  --feedforward-dim 512,768,1024,1536,1024,768 \
  --encoder-dim 192,256,384,512,384,256 \
  --encoder-unmasked-dim 192,192,256,256,256,192
