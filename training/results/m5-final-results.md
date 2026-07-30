# M5 — Resultados finais (fine-tune espontâneo PT-BR)

Deliverable de M5: **Zipformer-CTC medium (64M) + cabeça de fonema**, fine-tunado em
CORAA+TAGARELA, quantizado int8, medido **no hardware-alvo (notebook CPU, ONNX Runtime)**.
Todo número carrega rótulo de proveniência (`.claude/rules/asr-evidence-discipline.md § 1`).

## Modelo entregue

- **Arquitetura:** Zipformer-CTC medium 64M + fonema aux (herdada de M4, ADR 0003).
- **Deliverable:** média de checkpoints (`avg` de checkpoint-124000 + checkpoint-112000 do
  run de 10 épocas) — a alavanca de averaging derrubou o WER (ver abaixo).
- **Formato:** ONNX int8 (70 MB) exportado via `export-onnx-ctc.py` (cabeça de fonema
  removida na inferência — é auxiliar de treino). Artefatos: `model.int8.onnx`,
  `bpe.model` (vocab 500), `tokens.txt`.

## Números medidos `[MEDIDO]`

Ambiente: **notebook i7 12-core, ONNX Runtime int8, CPU, greedy CTC**, test CORAA humano
completo (12.676 utts, 11,24 h de áudio). Comando: `decode_onnx_local.py --threads 6 --batch 8`.

| Recorte | WER | CER | Alvo | Status |
|---|---|---|---|---|
| **Wideband espontâneo** (modelo médio) | **23,31%** | 11,28% | ≤25% / < M4 27,46% | ✅ PASSA |
| **Real-time (RTFx CPU)** | **34,69×** | — | RNF-07 ≥6× | ✅ PASSA (5,8×) |
| **Telefônico-proxy 8 kHz** (bandpass, single) | **31,97%** | 16,46% | ≤25% | ❌ não bate — e o proxy era otimista |
| **Call center REAL 8 kHz** (áudio humano-transcrito) | **40,13%** | — | ≤25% | ❌ gap real ~15 pp (ver caveats) |

**Contexto:** o wideband 23,31% já está **abaixo do M4 (27,46%)**, que era em fala **lida**
(FLEURS, mais fácil); M5 mede fala **espontânea** (mais difícil). O averaging levou o single
de 25,81% (full-test int8) para **23,31%**.

## Trajetória do run (evidência) `[MEDIDO]`

WER wideband (subset 1k, greedy, GPU) por *low* de época — o padrão é: melhor logo após cada
fronteira de época (o WER degrada dentro da época = overfitting ao pseudo-rótulo TAGARELA):

| início de época | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|
| WER | 42,5 | 36,5 | 33,7 | 32,6 | 29,1 | 28,5 | 25,96 | **24,73** |

Config vencedora (após diagnóstico registrado no `CLAUDE.md § Contexto que evita erros
repetidos`): base-lr **0,03** (não
0,0001, que prendia o head fresco no prior de blank → WER 100%), fp16, max-dur 500, 10 épocas,
eager-load + num-workers 2, encoder do M4 + heads frescos (bpe.model do M4 perdido).

## DoDs

- **DoD wideband espontâneo:** ✅ 23,31% (bate M4 e ≤25%).
- **DoD real-time CPU (RNF-07):** ✅ 34,69× (o requisito central — cabe no notebook do atendente).
- **DoD#3 telefônico 8 kHz ≤25%:** ❌ **em aberto.** Baseline honesto no **call center REAL** =
  **40,13% [MEDIDO]** (`measure_callcenter.py`, greedy, modelo entregue) — pior que o proxy
  bandpass (31,97%), que subestimava o canal (falácia § 3 #6). A **continuação D2**
  (warm-start + augmentação on-the-fly) **FALHOU** `[MEDIDO]`: colapsou o modelo para near-blank
  (WER ~98% em wideband e telefônico; `ctc_output.norm` 245→108) por LR alto (0,006 vs ~0,0045
  recomendado) + choque de augmentação a 100% sobre um modelo convergido. Caminho corrigido em
  `knowledge-base/discoveries/blueprints/m5-8khz-telephone-wer-blueprint.md`.
  **Caveats do 40,13%** (direciona, não conclui — § 3 #12): 9 min → IC largo; 2 interlocutores
  no mono; granularidade de 30s; máscaras de PII contam como erro.

## Validação real-world (qualitativa)

Clip real de call-center 8 kHz nativo (`callcenter/`, não versionada — LGPD): o modelo **sem**
augmentação telefônica transcreveu de forma **fragmentada** ("alão"≈alô, "é sério", "tudo bem é
que quem tá falando", "todo lugar") — confirma que o DoD#3 exige a continuação D2. RTFx 18,4×
mesmo nessa clip.

## Metodologia de reprodução

1. Treino: `run_finetune.sh 10` na instância (icefall commonvoice zipformer + patches M5).
2. Averaging: `average_checkpoints([ckpt-124000, ckpt-112000])`.
3. Export ONNX: `export-onnx-ctc.py --epoch 98 --avg 1` (checkpoint médio, fonema removido).
4. Medição: `decode_onnx_local.py` no notebook (ONNX int8, CPU) sobre `cv-pt_cuts_test.jsonl.gz`
   (CORAA humano) e `coraa_tel` (telefônico-proxy). WER via `jiwer`.

## Proveniência

Todos os WER/RTFx acima são `[MEDIDO]` (comando + hardware + full-test). A referência de
viabilidade ≤25% em espontâneo é `[LITERATURA]` (Parakeet-TDT 0.6B + TAGARELA, 10-21%, porém
600M = 9× o nosso 64M). Backup dos artefatos: `models/m5-final-medium-phoneme/backup/`.

## Phase 2 — baseline D1 (real-codec mono-falante) `[MEDIDO]`

`measure_realcodec.py --checkpoint avg_124_112 --n 500 --codec pool` (CORAA test mono-falante
degradado pelo codec-pool GSM/Opus/G.711): **36,88% WER**. Contexto: bandpass-proxy dava 31,97%
(otimista — codec inócuo); call real mono-misto 40,13%. O codec-pool realista é a condição de
deploy honesta (D1). O FT (Phase 4) precisa cobrir ~12 pp para o alvo ≤25%.
