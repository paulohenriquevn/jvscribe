# Discover Edge Case Review — m5-scale-model-wer

Date: 2026-07-28
Discovery plan analyzed: knowledge-base/discoveries/plans/m5-scale-model-wer-plan.md
Research questions analyzed: 6
Edge cases found: 4 (MUST FIX: 1, SHOULD TEST: 1, DOCUMENT: 2)

## MUST FIX

### EC-1: os `finetune.py` do icefall são TRANSDUCER; nosso modelo é CTC
- **Affected question:** Q1, Q2
- **Family:** Interpretation
- **Scenario:** os recipes de fine-tune verificados (`egs/commonvoice/ASR/pruned_transducer_stateless7_streaming/finetune.py`, `egs/wenetspeech/ASR/pruned_transducer_stateless2/finetune.py`) são todos **transducer** (`pruned_transducer_stateless`). Nosso finalista é **Zipformer-CTC** (`--use-ctc 1 --use-transducer 0`). Durante `/discover-execute`, Q2 pode concluir "não existe recipe de fine-tune CTC" e ficar BLOCKED, quando na verdade o mecanismo de fine-tune do icefall é **carregar um checkpoint base no `train.py` e continuar com LR menor** (o `finetune.py` só adiciona `--use-mux` p/ misturar corpora).
- **Impact:** blueprint incompleto ou BLOCKED numa question central; risco de re-trabalho no plano de implementação.
- **Suggested fix:** adicionar método de fallback a Q2 — "se não houver recipe de fine-tune CTC dedicado, ler como `zipformer/train.py` carrega um checkpoint (`--start-epoch`/`load_checkpoint`) e tratar fine-tune = continuar treino do base com LR menor + `--base-lr` reduzido, comparando com o `--do-finetune`/`--use-mux` do transducer."

## SHOULD TEST

### EC-2: a composição da augmentação com o `telephone_channel.py` de M3 é código NOSSO, não do ref
- **Affected question:** Q3
- **Suggested halt-loop checkpoint:** antes de fechar Q3, o blueprint deve capturar **COMO transforms customizados compõem com os built-in do lhotse** (o `input_transform`/`CutSet.map` que M3 já usou em `scripts/corpus/build_manifest.py`) — não só as classes `CutMix`/`Reverb` do lhotse. Assertar que a ordem telefone∘ruído∘reverb é justificada por leitura do mecanismo de composição, não suposição.

## DOCUMENT

### EC-3: MUSAN + BUT ReverbDB são datasets grandes de baixar
- **Accepted risk:** Q4 responde o "como baixar"; o tamanho (MUSAN ~11GB, RIR datasets) é nota de recurso, não bloqueio de blueprint. A decisão de baixar/quais entra no `/to-plan`, com o custo. Aceito documentar como pendência de recurso, não resolver no discover.

### EC-4: a cabeça de fonema precisa de alvos de fonema no CORAA para o fine-tune
- **Accepted risk:** se o fine-tune mantiver a cabeça de fonema ativa, precisa rodar `gen_phonemes.py` no texto do CORAA (como no medium+fonema). Alternativa: fine-tune só com a cabeça CTC principal (a de fonema é auxiliar, regularizadora — pode desligar no fine-tune). É decisão de implementação (`/to-plan`), não de discover; documentado.

## Summary

| Question | Edges found | MUST FIX | SHOULD TEST | DOCUMENT |
|----------|-------------|----------|-------------|----------|
| Q1 | 1 | 1 (compartilhado c/ Q2) | 0 | 0 |
| Q2 | 2 | 1 | 0 | 1 (EC-4) |
| Q3 | 1 | 0 | 1 | 0 |
| Q4 | 1 | 0 | 0 | 1 (EC-3) |
| Q5 | 0 | 0 | 0 | 0 |
| Q6 | 0 | 0 | 0 | 0 |

**Verdict:** DISCOVERY PLAN NEEDS ADJUSTMENT (1 MUST FIX — o fallback CTC em Q2)
