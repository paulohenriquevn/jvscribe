# M3 — Distribuição de CER par-a-par (evidência [MEDIDO])

**Data:** run do pipeline · **Fonte:** FLEURS pt_br (test), 20 clips reais
**Transcritores:** faster-whisper `small` + `base` (int8, CPU, sequenciais — RAM-safe)
**Métrica:** CER par-a-par (normalizado PT-BR) entre as 2 hipóteses de máquina.

## Estatística da distribuição `[MEDIDO]`

- média 0.049 ± 0.036 · mediana 0.037 · min 0.009 · max 0.161 (n=20)
- **τ calibrado** (manter 80% mais concordantes, percentil empírico): **0.064**
- cuts **mantidos** 16 / **descartados** 4 (invariante § 3 #10: só pool de treino)
- prova on-the-fly: `load_telephone_audio` do 1º cut retorna sr = **8000 Hz** (augmentação em RAM, sem WAV em disco)

## CER por clip

| clip | CER(h1,h2) | mantido? |
|---|---|---|
| fleurs_000 | 0.023 | ✅ |
| fleurs_001 | 0.102 | ❌ descartado |
| fleurs_002 | 0.161 | ❌ descartado |
| fleurs_003 | 0.064 | ✅ |
| fleurs_004 | 0.038 | ✅ |
| fleurs_005 | 0.052 | ✅ |
| fleurs_006 | 0.029 | ✅ |
| fleurs_007 | 0.035 | ✅ |
| fleurs_008 | 0.057 | ✅ |
| fleurs_009 | 0.025 | ✅ |
| fleurs_010 | 0.015 | ✅ |
| fleurs_011 | 0.034 | ✅ |
| fleurs_012 | 0.105 | ❌ descartado |
| fleurs_013 | 0.009 | ✅ |
| fleurs_014 | 0.020 | ✅ |
| fleurs_015 | 0.033 | ✅ |
| fleurs_016 | 0.035 | ✅ |
| fleurs_017 | 0.041 | ✅ |
| fleurs_018 | 0.072 | ❌ descartado |
| fleurs_019 | 0.041 | ✅ |

## Leitura honesta

- Caveat (ADR-3): os 2 whisper são da mesma família → correlacionam erros; a concordância
  superestima confiança. Um 2º transcritor de arquitetura distinta (parakeet) melhora o sinal (backlog).
- τ é derivado da distribuição empírica desta amostra (não a priori); re-calibrar em corpus maior (M4).
