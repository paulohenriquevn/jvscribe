# Runbook — Piloto de M4 com a recipe REAL do icefall (não wrapper próprio)

Regra 9: **copiar/reusar a recipe testada dos autores do Zipformer**, não reescrever o
loop/loss/model. O único código nosso é a **preparação de dados** (baixar o corpus e
nomear os cuts no formato que o datamodule do icefall já espera) — zero mudança na
recipe. Isto elimina a classe de bugs do wrapper `train_ctc.py` (ex.: máscara de
padding faltando).

## Por que a recipe real, não o `train_ctc.py`

`train_ctc.py` foi o smoke (provou k2/CUDA/corpus/GPU). Ele tem defeitos confirmados
(sem `src_key_padding_mask`, cabeça de fonema ad-hoc, configs por escala). O `AsrModel`
+ `train.py` do icefall fazem tudo correto: `make_pad_mask`, CTC, ScaledAdam+Eden,
model-averaging, checkpoint/resume nativo (`--start-epoch`/`--save-every-n`).

## Pré-requisitos

- Crédito vast.ai: **~$98-200** (grade de 12 combinações; ver Blueprint § Q7). O smoke
  já validou a infra por $0,35.
- Imagem: `k2fsa/icefall:torch2.4.1-cuda12.1` (k2+icefall+lhotse+torch+CUDA casados).
- Corpus de ~500 h: FLEURS (~10 h) + MLS-PT (~161 h, CC-BY) + Common Voice pt (CC0) +
  subset de TAGARELA (~300 h, risco de licença assumido pelo dono). `training/prep_icefall.py`
  baixa e emite os cuts + fbank no formato do datamodule.

## Passos (na instância)

```bash
# 0. provisionar + SSH (ver training/README ou o histórico de M4)
vastai create instance <OFFER> --image k2fsa/icefall:torch2.4.1-cuda12.1 --disk 200 --ssh --direct

# 1. copiar a recipe (já vem na imagem em /workspace/icefall)
cd /workspace/icefall/egs/commonvoice/ASR

# 2. preparar os dados no formato do datamodule (nosso único código)
#    emite data/pt/  cv-pt_cuts_{train,dev,test}.jsonl.gz + feats + data/pt/lang_bpe_500/bpe.model
python3 /workspace/prep_icefall.py --out data/pt --hours 500 --lang pt

# 3. treinar o BPE com o script DA RECIPE (não o nosso)
./local/train_bpe_model.py --lang-dir data/pt/lang_bpe_500 --vocab-size 500 \
    --transcript data/pt/transcript_words.txt

# 4. TREINO — recipe real, CTC puro, 3 tamanhos (a curva WER×RTFx)
for cfg in small medium large; do
  ./zipformer/train.py --world-size 1 --use-ctc 1 --use-transducer 0 \
     --use-attention-decoder 0 --num-epochs 30 --use-fp16 1 --enable-musan 0 \
     --lang pt --cv-manifest-dir data/pt --bpe-model data/pt/lang_bpe_500/bpe.model \
     --exp-dir zipformer/exp_$cfg  <FLAGS-DE-TAMANHO-DO-RESULTS.md-$cfg>
  # checkpoint/resume nativo: --start-epoch N retoma de epoch-{N-1}.pt (GPU spot)
done

# 5. DECODE — WER com o script DA RECIPE (ctc-greedy, auto-suficiente)
for cfg in small medium large; do
  ./zipformer/ctc_decode.py --use-ctc 1 --decoding-method ctc-greedy-search \
     --lang pt --bpe-model data/pt/lang_bpe_500/bpe.model \
     --exp-dir zipformer/exp_$cfg --epoch 30 --avg 10
done

# 6. curva WER×RTFx: WER de (5); RTFx exportando ONNX (export-onnx-ctc.py) e medindo
#    na CPU-alvo (i7-1355U) com a régua de M1 (RNF-04/05).
```

## Supervisão fonética (a decisão do dono)

Extensão do `model.py` do icefall (adicionar uma 2ª cabeça `encoder_dim → num_phones`
ao `AsrModel`, com alvos do `gen_phonemes.py`), **não** um wrapper novo. A ablação é o
mesmo treino com/sem essa cabeça — medida no **held-out** (não no set de treino, para
não repetir o overfitting do smoke). Critério: manter só se ganho ≥ 3% relativo de WER.

## Flags de tamanho (copiar do RESULTS.md, não inventar)

| cfg | flags (de `egs/librispeech/ASR/RESULTS.md`) | params |
|---|---|---|
| small | `--num-encoder-layers 2,2,2,2,2,2 --encoder-dim 192,256,256,256,256,256 --feedforward-dim 512,768,768,768,768,768` | 22,1M |
| medium | (ver RESULTS.md:206) | 64,3M |
| large | `--num-encoder-layers 2,2,4,5,4,2 --encoder-dim 192,256,512,768,512,256` | 147,0M |

## Estado

- ✅ Infra validada (smoke, $0,35): k2/CUDA/corpus/treino/decode rodam na imagem oficial.
- ⏳ Piloto real: aguarda crédito ($98-200) + o corpus de 500 h + dias de treino.
- Este runbook + `prep_icefall.py` são a preparação; o treino é lançado quando o crédito estiver disponível.
