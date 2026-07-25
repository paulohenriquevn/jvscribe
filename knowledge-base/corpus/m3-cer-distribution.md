# M3 — Distribuição de CER par-a-par (evidência [MEDIDO])

**Data:** 2026-07-25T05:23:32 · **Hardware:** 13th Gen Intel(R) Core(TM) i7-1355U (int8, CPU, cpu_threads=1)
**Comando exato:** `python3 scripts/corpus/run_pipeline.py --n 20 --keep 0.8 --sizes small base` — **1 run, n=20 clips** de FLEURS pt_br (não repetições)
**Transcritores:** faster-whisper `small` + `base` (sequenciais — RAM-safe)
**Métrica:** CER **direcional** de hyp₂ contra hyp₁ (modelo #1 como referência),
ambas normalizadas PT-BR. Não é simétrica; ordena por magnitude de discordância.

## Estatística da distribuição `[MEDIDO]`

- **spread** entre clips: média 0.055 ± 0.051 (σ amostral) · mediana 0.035 · min 0.000 · max 0.195 (n=20)
- **incerteza** da média (≠ spread): SEM 0.011 → IC95% ≈ [0.032, 0.077]
- **τ calibrado** (percentil-80 empírico): **0.072** · IC95% bootstrap [0.038, 0.164] (2000 reamostragens, seed fixa)
- **manifest filtrado**: 16 cuts mantidos == 16 aprovados pelo filtro (review B-1: o filtro É aplicado ao manifest)
- prova on-the-fly: `load_telephone_audio` do 1º cut retorna sr = **8000 Hz** (augmentação em RAM, sem WAV em disco)

## CER por clip

| clip | CER(h1→h2) | mantido? |
|---|---|---|
| fleurs_000 | 0.023 | ✅ |
| fleurs_001 | 0.102 | ❌ descartado |
| fleurs_002 | 0.195 | ❌ descartado |
| fleurs_003 | 0.164 | ❌ descartado |
| fleurs_004 | 0.038 | ✅ |
| fleurs_005 | 0.052 | ✅ |
| fleurs_006 | 0.029 | ✅ |
| fleurs_007 | 0.035 | ✅ |
| fleurs_008 | 0.041 | ✅ |
| fleurs_009 | 0.025 | ✅ |
| fleurs_010 | 0.000 | ✅ |
| fleurs_011 | 0.034 | ✅ |
| fleurs_012 | 0.113 | ❌ descartado |
| fleurs_013 | 0.009 | ✅ |
| fleurs_014 | 0.020 | ✅ |
| fleurs_015 | 0.033 | ✅ |
| fleurs_016 | 0.035 | ✅ |
| fleurs_017 | 0.034 | ✅ |
| fleurs_018 | 0.072 | ✅ |
| fleurs_019 | 0.041 | ✅ |

## Leitura honesta (caveats do review)

- **H-1 (par de transcritores):** esta run usou `small`+`base`, não o `small`+`medium` do ADR-3. `base` é mais próximo de `small` que `medium` → dois modelos adjacentes correlacionam erros **ainda mais**; a distribuição estreita (média 0.055) é parcialmente artefato do par, não sinal de qualidade. small+medium fica para quando houver RAM/tempo.
- **M-2 (fração mantida é tautológica):** manter ~80% aqui é por construção (`keep_fraction=0.8` calibra τ na MESMA amostra). Não é evidência de qualidade dos pseudo-labels; medir qualidade exige um conjunto com referência humana (M4/fine-tune), que não existe neste piloto.
- **M-3 (fonte-piloto):** os clips vêm do split `test` do **FLEURS** — usado aqui como **fonte-piloto de conveniência**, NÃO o test set de call-center do produto (`PRD § 7.3`). Nenhum pseudo-label toca a suíte de avaliação; o invariante § 3 #10 é respeitado por convenção do operador (o split train/test do produto é materializado fora deste módulo).
- **Caveat ADR-3 (correlação):** os 2 whisper são da mesma família → correlacionam erros; a concordância superestima confiança. Um 2º transcritor de arquitetura distinta (parakeet) melhora o sinal (backlog).
- **Escopo estatístico:** n=20 é piloto; o IC de τ (percentil de 20 pontos) é largo (ver acima). Re-calibrar em corpus maior em M4 — este τ não é verdade final, é o operacional do piloto.
