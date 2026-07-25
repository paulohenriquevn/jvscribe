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

**Resultado `[MEDIDO]`:** CER par-a-par média **0,049 ± 0,036** · mediana 0,037 · min 0,009 · max 0,161 (n=20). **τ calibrado (percentil-80 empírico) = 0,064**. Filtro: **16 mantidos / 4 descartados**. Prova on-the-fly: `load_telephone_audio` do 1º cut retorna **8000 Hz** (augmentação em RAM, sem WAV em disco). A distribuição estreita (CER baixo entre small e base) é esperada e confirma o caveat ADR-3: modelos parentes concordam muito — o sinal de concordância superestima confiança até um 2º transcritor de arquitetura distinta entrar.

## Decisões de escopo honestas

- **Tamanhos small+base** (não small+medium do "ex." do ADR-3) — ambos leves, seguros na RAM da máquina; 2 tamanhos distintos cumprem "2 whisper distintos". medium fica para quando houver mais RAM (backlog).
- **Caveat ADR-3:** os 2 whisper são parentes → correlacionam erros; a concordância superestima confiança. 2º transcritor de arquitetura distinta (parakeet-TAGARELA) é backlog técnico (Blueprint § Corner 3/Q7 — bloqueado por RAM/export).
- **telephone via função de carregamento on-the-fly** (`load_telephone_audio`), não `AudioTransform` nativo do lhotse — porque a cadeia muda sr (16k→8k) + banda+A-law sem equivalente nativo (evita reimplementar `reverse_timestamps`); equivale ao `input_transform` recomendado no blueprint.
- **Risco de licença (TAGARELA NC-SA) assumido pelo dono** (registrado em `m3-licenses.md` com proveniência).

## Validação de integração

- `python3 -m pytest scripts/tests/test_corpus_*.py`: 17 testes verdes.
- Pipeline rodou em áudio real; augmentação on-the-fly confirmada (8 kHz, sem WAV em disco).
- CHANGELOG `[Unreleased]` atualizado (Regra 6).
