# M4 fase 3 — Ablação da cabeça de fonema auxiliar (Zipformer-CTC small)

**Data:** 2026-07-27 · **Corpus:** MLS-PT ~161h train, FLEURS held-out test (919 cuts,
21.471 palavras) · **Recipe:** icefall real `zipformer/train.py` estendido pelo patch
`training/prep_phoneme_head.py` (Regra 9) · **Hardware:** vast.ai RTX 3090 · **Decode:**
`ctc-greedy-search`. Fecha a task #20 — o último item de DoD de M4.

## Hipótese (escrita antes de medir)

Uma cabeça CTC de fonema auxiliar em camada intermediária do encoder (§ 8.1 do PRD:
"supervisão fonética auxiliar, agnóstica ao decoder") regulariza o encoder e **reduz o
WER held-out do Zipformer-CTC small em ≥ 3% relativo** sobre o baseline idêntico sem a
cabeça. Colocação em ~50% da profundidade e peso de loss 0,3, fundamentados em
Lee & Watanabe 2021 (*Intermediate Loss Regularization for CTC-based ASR*).

Refutada se: a melhora relativa ficasse < 3%, ou o IC bootstrap incluísse 0 (melhora não
distinguível de ruído).

## Evidência `[MEDIDO]`

Baseline e candidato treinados 30 épocas no **mesmo** corpus/GPU, decodados com **mesmo**
protocolo (`ctc-greedy-search`, avg=10, mesmo FLEURS test). Único delta: a cabeça de
fonema (patch determinístico). Load do checkpoint do candidato: `load_state_dict` estrito,
559/559 chaves (a cabeça `phoneme_output` é instanciada no decode e não usada — só o
`ctc_output` decide o greedy; zero uso de `strict=False`).

| Config | WER | CER | params |
|---|---|---|---|
| Baseline small (sem cabeça) | **29,97%** (avg=10) | **11,42%** | 22.118.179 |
| **+ cabeça de fonema** | **28,58%** (avg=10) | **10,85%** | 22.134.213 (+16.034, +0,07%) |

> CER de ambos medido pelo mesmo `cer_from_recogs.py` sobre os recogs full-test
> (baseline `training/results/m4-small-baseline/recogs-clean-avg10.txt`; candidato em
> `m4-phoneme-ablation/`). O ~11,0% de versões anteriores deste doc era estimativa a olho
> — o valor medido é 11,42%.
| Baseline (avg=1) | 33,99% | — | — |
| + cabeça (avg=1) | 33,74% | — | — |

**IC bootstrap pareado** (por utterance, B=10.000, seed=42,
`training/scripts/bootstrap_wer_ci.py`):

| Métrica | Ponto | IC 95% |
|---|---|---|
| Δ absoluto (avg=10) | **1,39 p.p.** | [0,77 · 2,01] |
| Melhora relativa | **4,63%** | [2,63% · 6,63%] |
| P(melhora > 0%) | **100,0%** | — |
| P(melhora ≥ 3% da DoD) | **94,1%** | — |

> **Proveniência das probabilidades:** P(>0) e P(≥3%) são emitidas pelo próprio
> `bootstrap_wer_ci.py` (da mesma distribuição, seed=42, B=10.000) — o comando de
> reprodução na seção final as imprime; não vêm de cálculo à parte.

**Critério de aprovação da DoD (declarado explicitamente).** A DoD do ROADMAP ("ablação
≥3%") é avaliada pela **estimativa pontual** da melhora relativa: **4,63% ≥ 3% → atingida**.
O IC 95% é reportado como **qualificação obrigatória**, não como a régua de passagem — e o
qualificador é honesto: o limite inferior (2,63%) fica abaixo de 3% e P(≥3%)=94,1% < 95%,
então a passagem é **no ponto, com evidência fronteiriça** (não folgada). Se em algum
momento o projeto exigir o critério mais estrito (IC-inferior ≥ 3%), esta ablação **não**
o satisfaz a 0,3 de peso — precisaria da varredura de `phoneme_loss_scale` (follow-up).

## Conclusão (apenas o que a evidência sustenta)

**A cabeça de fonema auxiliar melhora o WER de forma inequivocamente significativa**
(P(Δ>0)=100%; IC da diferença exclui 0). A **DoD de ≥3% relativo é atingida no ponto**
(4,63%) e a supervisão fonética do § 8.1 do PRD está **empiricamente validada** para o
Zipformer-CTC small. O CER também cai (**11,42% → 10,85%, −0,57 p.p.**), consistente com
regularização que reduz erro fino, não só fronteira de palavra.

**Caveat honesto (§ 2 — conclusão não excede a evidência):** o limite inferior do IC 95%
da melhora relativa (2,63%) fica **ligeiramente abaixo** do limiar de 3% — a confiança de
exceder estritamente 3% é **94,1%**, não 95%. A DoD é atendida na estimativa central e a
melhora é 100% real, mas o "≥3%" não é garantido no nível de 95% de confiança. Isto é um
**PASS com nota**, não um PASS folgado.

**Limites (o que este experimento NÃO decide):**
- **Peso único.** `phoneme_loss_scale=0,3` `[ESTIMATIVA — literatura]`, não variado. O
  resultado é para esse peso; uma varredura (0,1–0,5) poderia melhorar ou piorar — não
  medido. Um peso melhor poderia levar o IC inteiro acima de 3%; fica como follow-up barato.
- **WER wideband.** FLEURS limpo, não 8 kHz call center (penalidade 2-3× — M5).
- **avg=1 melhora pouco** (0,74% rel) — esperado (checkpoint único mais ruidoso); a decisão
  de DoD usa avg=10, o protocolo canônico.

## Reprodução

```bash
# na instância: patch + alvos + treino
python3 training/prep_phoneme_head.py                      # estende a recipe icefall
python3 training/gen_phonemes.py --data data/pt --splits train,dev
./zipformer/train.py ... --use-phoneme-ctc 1 --phoneme-loss-scale 0.3 \
    --phoneme-targets-json data/pt/phoneme_targets.json --exp-dir zipformer/exp-small-ctc-phoneme
./zipformer/ctc_decode.py ... --exp-dir zipformer/exp-small-ctc-phoneme --use-phoneme-ctc 1 \
    --avg 10 --use-averaged-model 1 --decoding-method ctc-greedy-search
# local: métricas + IC
python3 training/scripts/cer_from_recogs.py <recogs>                      # WER + CER
python3 training/scripts/bootstrap_wer_ci.py <baseline_recogs> <cand_recogs>   # IC bootstrap
```

Artefatos: `training/results/m4-phoneme-ablation/` (recogs/errs/logs do candidato) e
`training/results/m4-small-baseline/recogs-clean-avg10.txt` (baseline re-decodado limpo).
