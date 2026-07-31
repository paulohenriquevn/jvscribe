#!/bin/bash
# Treina + decodifica UM tamanho Zipformer-CTC no corpus data/pt (MLS-PT train + FLEURS
# dev/test held-out). Roda NA instância, no dir egs/commonvoice/ASR. Encapsula o que o
# piloto de M4 aprendeu: lang-dir completo (tokens.txt), musan off, decode sem averaging
# cego (o avg-N degenera modelo não-convergido; testamos avg=1 e avg=10).
#
# Flags de tamanho = cópia do RESULTS.md do icefall (Regra 9 — não inventar).
# Uso: bash run_zipformer_ctc.sh <small|medium|large> [num_epochs]
set -euo pipefail
SIZE=${1:?small|medium|large}
EPOCHS=${2:-30}
LD=data/pt/lang_bpe_500
EXP=zipformer/exp-${SIZE}-ctc

case "$SIZE" in
  small)  SZ="--num-encoder-layers 2,2,2,2,2,2 --feedforward-dim 512,768,768,768,768,768 --encoder-dim 192,256,256,256,256,256 --encoder-unmasked-dim 192,192,192,192,192,192"; MAXD=500 ;;
  medium) SZ=""; MAXD=700 ;;   # defaults do zipformer = 64.3M
  large)  SZ="--num-encoder-layers 2,2,4,5,4,2 --feedforward-dim 512,768,1536,2048,1536,768 --encoder-dim 192,256,512,768,512,256 --encoder-unmasked-dim 192,192,256,320,256,192"; MAXD=400 ;;
  *) echo "tamanho inválido: $SIZE"; exit 1 ;;
esac

# 0. decoder CTC adaptado (librispeech->commonvoice) presente?
[ -f zipformer/ctc_decode.py ] || python3 patch_ctc_decode.py

# 1. BPE + lang-dir completo (uma vez; compartilhado entre tamanhos)
if [ ! -f "$LD/bpe.model" ]; then
  mkdir -p "$LD"
  ./local/train_bpe_model.py --lang-dir "$LD" --vocab-size 500 --transcript data/pt/transcript_words.txt
fi
if [ ! -f "$LD/L.pt" ]; then   # L.pt é o artefato final do prepare_lang_bpe (tokens.txt sozinho não basta p/ o decode)
  cp -n data/pt/transcript_words.txt "$LD/transcript_words.txt"
  sed 's/ /\n/g' "$LD/transcript_words.txt" | sort -u | sed '/^$/d' > "$LD/_w.txt"
  { echo '!SIL'; echo '<SPOKEN_NOISE>'; echo '<UNK>'; } | cat - "$LD/_w.txt" | sort | uniq | \
    awk 'BEGIN{print "<eps> 0"} {printf("%s %d\n",$1,NR)} END{printf("#0 %d\n",NR+1);printf("<s> %d\n",NR+2);printf("</s> %d\n",NR+3)}' > "$LD/words.txt"
  rm -f "$LD/_w.txt"
  ./local/prepare_lang_bpe.py --lang-dir "$LD"
fi

# 2. treino: CTC puro, musan off (não temos MUSAN), fp16
env OMP_NUM_THREADS=8 ./zipformer/train.py \
  --world-size 1 --num-epochs "$EPOCHS" --use-fp16 1 --enable-musan 0 \
  --use-ctc 1 --use-transducer 0 --exp-dir "$EXP" \
  --language pt --cv-manifest-dir data/pt --bpe-model "$LD/bpe.model" \
  --base-lr 0.04 --max-duration "$MAXD" $SZ

# 3. decode held-out (FLEURS test): avg=1 (sem averaging) e avg=10 (o melhor vence)
#
# Os dois decodes são INDEPENDENTES — avg=10 pode falhar legitimamente num run curto (não há
# 10 checkpoints) sem invalidar o avg=1. Por isso a falha de um não aborta o outro. Mas ela
# TEM de aparecer: antes havia um `|| true` puro, e um decode quebrado produzia um script com
# exit 0 e nenhum WER — silêncio num script de MEDIÇÃO (error-handling.md § 2).
FALHAS=0
for pair in "1 0" "10 1"; do
  set -- $pair
  if ! python3 ./zipformer/ctc_decode.py --epoch "$EPOCHS" --avg "$1" --use-averaged-model "$2" \
    --exp-dir "$EXP" --lang-dir "$LD" --decoding-method ctc-greedy-search \
    --bpe-model "$LD/bpe.model" --cv-manifest-dir data/pt --language pt \
    --use-ctc 1 --use-transducer 0 --max-duration 400 $SZ; then
    echo "AVISO: decode avg=$1 (use-averaged-model=$2) FALHOU" >&2
    FALHAS=$((FALHAS + 1))
  fi
done

echo "=== WER $SIZE (held-out FLEURS test) ==="
if ! grep -h '%WER' "$EXP"/ctc-greedy-search/*.txt 2>/dev/null | tail -6; then
  echo "ERRO: nenhum %WER produzido — o treino ou os $FALHAS decode(s) falharam" >&2
  exit 1
fi
[ "$FALHAS" -eq 2 ] && { echo "ERRO: os DOIS decodes falharam" >&2; exit 1; }
exit 0
