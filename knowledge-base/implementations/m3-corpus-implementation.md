# M3 — Pipeline de corpus: resumo de implementação

**Plano:** `knowledge-base/plans/m3-corpus-plan.md` (SHIPPABLE)
**Promise:** IMPLEMENTATION_COMPLETE
**Data:** 2026-07-25

## O que foi entregue (DoD de M3)

| DoD (ROADMAP) | Entregável | Evidência |
|---|---|---|
| Q-09 respondida | `knowledge-base/corpus/m3-licenses.md` § Q-09 | `[DESCONHECIDO]` honesto + termos publicados |
| Pipeline pseudo-labeling com filtro por concordância | `scripts/corpus/pseudo_label.py` + `agreement_filter.py` | 2 whisper sequenciais + CER par-a-par + τ empírico |
| Manifests Lhotse com augmentação on-the-fly | `scripts/corpus/build_manifest.py` + `telephone_channel.py` | CutSet com telephone on-the-fly (8 kHz, sem disco) |
| Volume + licença de cada fonte com veredito | `knowledge-base/corpus/m3-licenses.md` | tabela de 6 fontes + volume + risco assumido |

## Componentes (TDD, 17 testes verdes)

| Módulo | Papel | Testes |
|---|---|---|
| `telephone_channel.py` | Augmentação G.711 on-the-fly (scipy resample+butter SOS + audioop A-law), em memória | 6 (invariantes DSP: downsample 8k, banda atenua fora, A-law preserva forma, sem tempfile, negativo) |
| `agreement_filter.py` | CER par-a-par (normalizado PT-BR) + predicado `agree` + `calibrate_tau` (percentil empírico) | 7 (CER 0/alto/normalizado, agree/τ, calibração, negativos) |
| `pseudo_label.py` | 2 whisper sequenciais (RAM-safe: `del`+`gc` entre modelos) | 1 (prova sequencialidade via contador de instâncias vivas = 1) |
| `build_manifest.py` | Manifests Lhotse (RecordingSet→SupervisionSet(text)→CutSet) + `load_telephone_audio` on-the-fly | 3 (text na supervisão, telephone lazy → 8k, sem materialização em disco) |
| `run_pipeline.py` | Orquestrador ponta-a-ponta sobre FLEURS pt_br | Integration Validation |

## Evidência [MEDIDO] (Integration Validation)

Pipeline real sobre 20 clips FLEURS pt_br: 2 whisper (`small`+`base`, int8 CPU
sequenciais) → CER par-a-par → τ calibrado → filtro → manifest com telephone on-the-fly.
Distribuição gravada em `knowledge-base/corpus/m3-cer-distribution.md`.

**Resultado `[MEDIDO]`** (i7-1355U, 1 run, n=20 clips): spread média **0,055 ± 0,051** (σ amostral) · mediana 0,035 · min 0,000 · max 0,195. Incerteza da média: SEM 0,011 → **IC95% [0,032, 0,077]**. **τ (percentil-80 empírico) = 0,072**, com **IC95% bootstrap [0,038, 0,164]** (largo — n=20 é piloto). **Manifest filtrado: 16 cuts == 16 aprovados** (o filtro É aplicado ao manifest — review B-1). on-the-fly a **8000 Hz** confirmado. A distribuição estreita confirma o caveat ADR-3: modelos parentes (small/base, mais próximos ainda que small/medium) correlacionam erros — a concordância superestima confiança até um 2º transcritor de arquitetura distinta entrar (backlog). Todos os 10 findings do `/review` (1 BLOCKER + 3 HIGH + 6 MEDIUM/LOW) corrigidos e revalidados (`knowledge-base/reviews/m3-corpus-review-2026-07-25.md`).

## Decisões de escopo honestas

- **Tamanhos small+base** (não small+medium do "ex." do ADR-3) — ambos leves, seguros na RAM da máquina; 2 tamanhos distintos cumprem "2 whisper distintos". medium fica para quando houver mais RAM (backlog).
- **Caveat ADR-3:** os 2 whisper são parentes → correlacionam erros; a concordância superestima confiança. 2º transcritor de arquitetura distinta (parakeet-TAGARELA) é backlog técnico (Blueprint § Corner 3/Q7 — bloqueado por RAM/export).
- **telephone via função de carregamento on-the-fly** (`load_telephone_audio`), não `AudioTransform` nativo do lhotse — porque a cadeia muda sr (16k→8k) + banda+A-law sem equivalente nativo (evita reimplementar `reverse_timestamps`); equivale ao `input_transform` recomendado no blueprint.
- **Risco de licença (TAGARELA NC-SA) assumido pelo dono** (registrado em `m3-licenses.md` com proveniência).

## Validação de integração

- `python3 -m pytest scripts/tests/test_corpus_*.py`: 17 testes verdes.
- Pipeline rodou em áudio real; augmentação on-the-fly confirmada (8 kHz, sem WAV em disco).
- CHANGELOG `[Unreleased]` atualizado (Regra 6).
