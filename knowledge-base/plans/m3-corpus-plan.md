---
slug: m3-corpus
milestone_id: M3
created_at: 2026-07-25
goal: Entregar um pipeline de corpus que gera pseudo-labels filtrados por concordância e manifests Lhotse com augmentação telefônica on-the-fly, validado em áudio real
---

# Plan: M3 — Pipeline de corpus (pseudo-labeling + manifests Lhotse)

## Goal

Entregar um pipeline de corpus que **produz manifests Lhotse com pseudo-labels filtrados por concordância CER e augmentação telefônica on-the-fly**, medido rodando sobre ≥ 20 clips reais de FLEURS pt_br com **todos os testes verdes** (`python3 -m pytest scripts/tests/test_corpus_*.py` exit 0) e a distribuição de CER par-a-par gravada como evidência `[MEDIDO]`.

**NON-NEGOTIABLE:** o pipeline roda de verdade em áudio real (não mock) e grava a distribuição de CER; a augmentação telefônica nunca materializa WAV intermediário em disco; pseudo-label nunca entra em test set (`asr-evidence-discipline § 3 #10`).

## Context

M3 é o risco dominante do projeto (`ROADMAP.md § M3`). Sai do blueprint `knowledge-base/discoveries/blueprints/m3-corpus-blueprint.md` (SHIPPABLE 99,1), que decidiu por evidência `[FONTE-REPO]`: augmentação telefônica on-the-fly via `input_transform` scipy+audioop (o `Narrowband` nativo do lhotse não cobre A-law nem banda — Blueprint § Corner 4/Q2); filtro por concordância como predicado `CutSet.filter` com CER par-a-par e threshold calibrado empiricamente (Blueprint § ADR de filtro); dois modelos whisper distintos como transcritores (parakeet-TAGARELA bloqueado por RAM — Blueprint § ADR de transcritores); e o mapa de licenças com o **risco de licença assumido pelo dono** (Blueprint § Context, decisão de Paulo em 2026-07-25).

## Baseline Context (deep review of current state)

### Files that will be touched

| Arquivo | LoC hoje | Último commit | Papel / por que existe |
|---|---|---|---|
| `scripts/telephone_augment.sh` | 55 | `41b996e` (M1) | Cadeia telefônica sox-CLI (16k→8k+banda+a-law) — referência DSP a portar p/ memória; NÃO editado |
| `scripts/text_normalize_ptbr.py` | ~40 | M1 | Normalizador PT-BR — REUSAR no cálculo de CER |
| `scripts/baseline_fleurs_ptbr.py` | ~90 | M1 | Padrão de transcrição faster-whisper (`WhisperModel(...).transcribe`) — REUSAR o padrão sequencial |
| `scripts/eval_wer.py` | ~80 | M1 | WER+IC com jiwer — REUSAR a métrica de edição p/ CER |
| `scripts/corpus/__init__.py` | 0 | (NEW) | Pacote do pipeline de corpus de M3 |
| `scripts/corpus/telephone_channel.py` | (NEW) | — | Augmentação telefônica on-the-fly em memória (scipy+audioop) |
| `scripts/corpus/agreement_filter.py` | (NEW) | — | CER par-a-par + predicado de filtro + calibração de τ |
| `scripts/corpus/pseudo_label.py` | (NEW) | — | Roda 2 whisper sequenciais → hipóteses PT-BR |
| `scripts/corpus/build_manifest.py` | (NEW) | — | Manifests Lhotse (RecordingSet→SupervisionSet→CutSet) + telephone_channel on-the-fly |
| `scripts/corpus/run_pipeline.py` | (NEW) | — | Orquestra o pipeline ponta-a-ponta sobre FLEURS pt_br; grava evidência |
| `scripts/tests/test_corpus_telephone.py` | (NEW) | — | Testes DSP da augmentação (seno analítico, invariantes) |
| `scripts/tests/test_corpus_agreement.py` | (NEW) | — | Testes do CER par-a-par + filtro |
| `scripts/tests/test_corpus_manifest.py` | (NEW) | — | Teste do manifest + laziness on-the-fly |
| `knowledge-base/corpus/m3-licenses.md` | (NEW) | — | Tabela de licenças + volume + Q-09 |

### Current callers / dependents

- Módulo `scripts/corpus/` é NOVO — sem callers de produção existentes; os callers são os testes + `run_pipeline.py`. Não altera símbolos públicos existentes (nenhuma regressão em M1/M2).
- `text_normalize_ptbr.normalize_ptbr` e `eval_wer` são importados por `scripts/tests/test_eval_wer.py:20-21` (verificado) — o novo código os **reusa**, não os modifica.

### Domain glossary

- **Pseudo-label:** transcrição gerada por máquina (professor), não humana. Nunca entra em test set (`asr-evidence-discipline § 3 #10`).
- **Filtro por concordância:** descarta segmentos cujos 2 transcritores discordam além de um threshold τ; concordância alta = pseudo-label mais confiável.
- **CER (Character Error Rate):** distância de edição normalizada por caractere entre duas transcrições; preferido a WER p/ PT-BR telefônico (menos sensível a fronteira de palavra).
- **on-the-fly:** augmentação aplicada em RAM no dataloader, nunca materializada em disco por época.
- **Manifest Lhotse:** RecordingSet (áudio) + SupervisionSet (texto/label) → CutSet (unidade de treino).

### Architecture boundaries affected

- Pipeline de corpus é Python, camada de **dados/preparação** — fora do runtime Rust (`crates/`). Não cruza a fronteira do runtime (`rules/architecture.md § 1`). Sem dependência do runtime para o runtime; o corpus alimenta M4/M5 (treino), não o motor de inferência.
- DIP: o pipeline depende de libs externas (whisper, lhotse, scipy) encapsuladas atrás de funções do domínio (rung 4 parsimony) — `telephone_channel`/`agreement_filter` são callables puros testáveis sem I/O.

## Prior Art & Related Work

- **Blueprint interno:** `knowledge-base/discoveries/blueprints/m3-corpus-blueprint.md` (SHIPPABLE 99,1) — fonte primária; os ADRs de síntese e as 5 Recommendations do blueprint.
- **Peers clonados `[FONTE-REPO]`:** `knowledge-base/references/lhotse/` (manifests, on-the-fly, tests), `knowledge-base/references/icefall/egs/librispeech/ASR/local/filter_cuts.py` (padrão de filtro).
- **Código do próprio repo (M1):** `scripts/telephone_augment.sh` (cadeia DSP), `scripts/baseline_fleurs_ptbr.py` (padrão whisper), `scripts/eval_wer.py`/`text_normalize_ptbr.py` (métrica de edição + normalização).
- **Literatura:** receita Granary (filtro por concordância) — `[LITERATURA]` não verificada (allowlist web vazio); tratada como hipótese, não premissa.

## Objective

Cobrir os 4 itens do DoD de M3 (`ROADMAP.md`) com código que roda em áudio real e evidência `[MEDIDO]`, reusando lhotse/whisper/scipy (parsimony rung 4) e respeitando a disciplina de evidência.

## ADRs

### ADR-1 — Augmentação telefônica em memória (scipy+audioop), não sox-CLI nem Narrowband nativo

**Decisão:** implementar a cadeia (16k→8k + banda 300-3400 + A-law round-trip) como callable numpy→numpy com `scipy.signal.resample_poly` + `butter/sosfilt` + `audioop.lin2alaw/alaw2lin`, exposto como transform on-the-fly.

**Rationale:** o `Narrowband` nativo do lhotse não tem A-law nem banda e exige torchaudio (Blueprint § Corner 4/Q2 `[FONTE-REPO]`); a cadeia sox-CLI de M1 usa tempfile por batch (viola "nunca em disco"). scipy/audioop já disponíveis e o lhotse os usa no fallback (`parsimony-ladder.md` rung 4 — reusar). **Alternativa rejeitada:** `Narrowband` nativo — não cobre o requisito; sox subprocess — spawn por batch e não é o padrão do peer.

**Rejeitada:** portar o sox-CLI literalmente — materializa WAV em `/tmp` por batch, violando o DoD "nunca em disco" e caro por spawn.

### ADR-2 — Filtro por concordância: CER par-a-par com τ calibrado empiricamente

**Decisão:** o filtro é um predicado `segment→bool` que descarta se CER(hyp1,hyp2) > τ; τ é escolhido a partir da distribuição empírica de CER medida no piloto, não fixado a priori.

**Rationale:** o peer icefall instrui calibrar threshold pela distribuição do dataset (`filter_cuts.py:76-78` `[FONTE-REPO]`); inventar τ violaria `asr-evidence-discipline § 1`. CER > WER para telefonia PT-BR (Blueprint § ADR de filtro). **Alternativa rejeitada:** threshold Granary hardcoded — `[DESCONHECIDO]` e o peer desaconselha hardcode.

### ADR-3 — Dois whisper distintos como transcritores (parakeet diferido)

**Decisão:** transcritores = faster-whisper `small` + `medium`, carregados sequencialmente (RAM). parakeet-TAGARELA é backlog técnico.

**Rationale:** parakeet não roda (cache/export/RAM — Blueprint § Corner 3/Q7 `[FONTE-REPO]`); faster-whisper é MIT/em-cache/provado em M1. Caveat honesto: modelos parentes correlacionam erros (registrado em Drawbacks). **Alternativa rejeitada:** bloquear M3 até habilitar parakeet — desperdiça o caminho viável e a RAM não comporta 2,4 GB.

### ADR-4 — Manifests via lhotse (torch CPU-only), reusando a lib madura

**Decisão:** usar lhotse de verdade (torch CPU-only instalado) para RecordingSet/SupervisionSet/CutSet, com o telephone_channel plugado on-the-fly; DoD pede "manifests Lhotse" explicitamente.

**Rationale:** reusar a lib madura (`parsimony-ladder.md` rung 4) em vez de reimplementar manifest; o DoD nomeia Lhotse. **Alternativa rejeitada:** manifests JSONL próprios (rung 6) — só se a instalação de torch falhar; degrada o DoD.

## Drawbacks & Risks

| Risco | Severidade | Mitigação | Owner |
|---|---|---|---|
| Dois whisper parentes correlacionam erros → concordância superestima confiança | ALTA | Registrar o caveat na evidência; usar tamanhos distintos (small vs medium) como proxy; backlog: habilitar parakeet (arquitetura distinta) | speech-data-scientist |
| `audioop` deprecado (PEP 594, removido em Python 3.13+) | MÉDIA | Import guardado fail-fast; declarar `audioop-lts` como fallback; teste que falha claro se ausente | audio-dsp-engineer |
| torch CPU-only não instala / RAM insuficiente p/ lhotse | MÉDIA | Fallback JSONL próprio (ADR-4 alt) mantém o pipeline funcional sem lhotse; testes do manifest usam skip condicional se lhotse ausente | general |
| RAM apertada (2 whisper) → OOM | MÉDIA | Carregar 1 modelo por vez, `del model` + `gc.collect()` entre eles (padrão M1); tamanhos pequenos (small/medium, não large) | speech-data-scientist |
| τ calibrado num piloto pequeno não generaliza | MÉDIA | Declarar IC/tamanho da amostra; τ é reportado com a distribuição, não como verdade final; re-calibrar em M4 | evaluation |

## Unresolved Questions

- Valor final de τ — resolvido em tempo de execução pela distribuição empírica (não a priori); registrado com a amostra.
- Common Voice na Mozilla Data Collective — termos a re-verificar (não bloqueia M3; FLEURS basta para o piloto).
- Q-09 (acesso Cem Mil Podcasts bruto) — negociação humana, `[DESCONHECIDO]` (Blueprint); documentado, não implementável.

## Dependency Graph

```
Fase 1 (telephone_channel) ─┐         [independente — sem modelos/torch]
Fase 2 (agreement_filter) ──┼─→ Fase 3 (pseudo_label real) ─→ Fase 4 (manifest lhotse) ─→ Fase 5 (licenças+volume) ─→ Integration
                            │         [Fase 3 usa Fase 2; Fase 4 usa Fase 1+3]
Fase 1 e 2 paralelizáveis. Fase 3 precisa de whisper (RAM sequencial). Fase 4 precisa torch/lhotse (ADR-4).
```

## Phase 1: Augmentação telefônica on-the-fly

**Objective:** implementar a cadeia telefônica em memória, testável por invariantes DSP, sem materializar em disco.

### T1.1 — TelephoneChannel (scipy+audioop)

#### Objective
Callable `apply(samples: np.ndarray, sr: int) -> (np.ndarray, 8000)` que aplica 16k→8k + banda 300-3400 + A-law round-trip em memória.

#### Why this step (action + reasoning)
Ação: escrever `telephone_channel.py` com resample_poly + butter/sosfilt + audioop a-law. Raciocínio: ADR-1 decidiu memória sobre sox-CLI porque o DoD exige "nunca em disco" e o Narrowband nativo não cobre A-law/banda (Blueprint § Corner 4/Q2 `[FONTE-REPO]`); scipy/audioop já disponíveis (rung 4).

#### Evidence
Blueprint § Corner 4/Q2 (proposta scipy+audioop, `[MEDIDO]` audioop resolve em 3.10); `scripts/telephone_augment.sh:45-49` (a cadeia sox de referência).

#### Files to edit
- `scripts/corpus/__init__.py` (NEW)
- `scripts/corpus/telephone_channel.py` (NEW, < 120 LoC)
- `scripts/tests/test_corpus_telephone.py` (NEW)

#### Deep file dependency analysis
Sem dependentes existentes (módulo novo). Importa `scipy.signal`, `audioop` (guardado), `numpy`. Não toca M1/M2.

#### Deep Dives
`audioop` guardado: `try: import audioop except ImportError: import audioop_lts as audioop` com fail-fast claro se nenhum existir (`error-handling.md § 2`).

**MUST-FIX (edge-case) — conversão de tipo A-law:** `audioop.lin2alaw(fragment, width)` espera **bytes PCM int16** (`width=2`), não float numpy. A cadeia correta: `float32 [-1,1] → int16 → .tobytes() → lin2alaw → alaw2lin → np.frombuffer(int16) → float32`. Clampar a `[-1,1]` antes de `*32767` para não estourar o int16. O resample scipy sai float; converter só no estágio a-law.
**MUST-FIX (edge-case) — filtro estável:** usar `butter(order=4, [300,3400], 'band', fs=8000, output='sos')` + `sosfilt` (não `b,a`+`lfilter`) — SOS é numericamente estável em passa-banda estreito; ordem 4 evita ringing. Aplicar após o resample (fs já = 8000).

#### TDD
- RED: `test_downsample_to_8k` — sinal 16k entra, saída tem sr=8000 e len≈metade.
- RED: `test_bandpass_attenuates_out_of_band` — seno a 5000 Hz (fora da banda 300-3400) é atenuado ≥ 20 dB vs seno a 1000 Hz (dentro).
- RED: `test_alaw_roundtrip_preserves_within_tolerance` — seno 1000 Hz após a-law round-trip mantém correlação ≥ 0.95 com o original resampleado (a-law é lossy mas preserva forma).
- RED: `test_no_tempfile_created` — chamar apply() não cria arquivo em /tmp (contar arquivos antes/depois).
- RED (negativo): `test_rejects_empty_array` — array vazio → ValueError tipado com mensagem clara.
- GREEN: implementar o mínimo. REFACTOR: extrair helpers de filtro.

#### Concurrency tests
(none — single-threaded) — callable puro sem estado compartilhado

#### Acceptance Criteria
- `python3 -m pytest scripts/tests/test_corpus_telephone.py -q` retorna exit 0 (todos os testes DSP verdes).
- `grep -c "audioop" scripts/corpus/telephone_channel.py` retorna ≥ 1 (a-law real, não stub).
- `grep -cE "subprocess|tempfile|NamedTemporary" scripts/corpus/telephone_channel.py` retorna 0 (nenhuma materialização em disco).

#### DoD
`python3 -m pytest scripts/tests/test_corpus_telephone.py -q` exit 0.

## Phase 2: Filtro por concordância (CER par-a-par)

**Objective:** CER par-a-par entre 2 hipóteses + predicado de filtro + função de calibração de τ.

### T2.1 — agreement_filter

#### Objective
`pairwise_cer(hyp1, hyp2) -> float` (normalizado PT-BR) + `agree(hyp1, hyp2, tau) -> bool` + `calibrate_tau(cer_list, keep_fraction) -> float`.

#### Why this step (action + reasoning)
Ação: escrever `agreement_filter.py` reusando `text_normalize_ptbr.normalize_ptbr` + distância de edição (jiwer/`eval_wer`). Raciocínio: ADR-2 — o predicado é o contrato `CutSet.filter` (Blueprint § Corner 4/Q3 `[FONTE-REPO]`); τ calibrado pela distribuição (não a priori).

#### Evidence
`icefall/.../filter_cuts.py:76-78,124` (`[FONTE-REPO]` — predicado + calibrar por distribuição); `scripts/text_normalize_ptbr.py` (normalização a reusar).

#### Files to edit
- `scripts/corpus/agreement_filter.py` (NEW, < 100 LoC)
- `scripts/tests/test_corpus_agreement.py` (NEW)

#### Deep file dependency analysis
Reusa `text_normalize_ptbr.normalize_ptbr` (import de `scripts/`). Sem alterar M1.

#### Deep Dives
**MUST-FIX (edge-case) — CER, não WER:** `jiwer` calcula WER por padrão; para CER usar `jiwer.cer(ref, hyp)` (existe na API) OU, se indisponível, `jiwer.process_characters`/Levenshtein char-level. Normalizar ambas as hipóteses com `normalize_ptbr` ANTES de computar (para "voce"≡"você"). Como não há referência humana (são 2 hipóteses de máquina), o CER é **simétrico**: reportar `cer(h1,h2)` tratando uma como "ref" — a assimetria de jiwer.cer é aceitável pois só ordena por magnitude de discordância (documentar a escolha).

#### TDD
- RED: `test_cer_identical_is_zero` — hipóteses idênticas → CER 0.
- RED: `test_cer_totally_different_is_high` — textos disjuntos → CER > 0.5.
- RED: `test_cer_normalizes_ptbr` — "voce" vs "você" (só acento/caixa) → CER baixo após normalização.
- RED: `test_agree_respects_tau` — par com CER 0.1 e tau 0.2 → True; tau 0.05 → False.
- RED: `test_calibrate_tau_matches_distribution` — dado [0.0,0.1,0.2,0.3,0.9], keep_fraction 0.8 → τ no percentil-80 (0.3).
- RED (negativo): `test_calibrate_empty_raises` — lista vazia → ValueError tipado.

#### Concurrency tests
(none — single-threaded) — funções puras

#### Acceptance Criteria
- `python3 -m pytest scripts/tests/test_corpus_agreement.py -q` retorna exit 0 (CER e filtro verdes).
- `grep -c "normalize_ptbr" scripts/corpus/agreement_filter.py` retorna ≥ 1 (normalização PT-BR antes do CER).
- `grep -c "percentile\|quantile" scripts/corpus/agreement_filter.py` retorna ≥ 1 (τ derivado da distribuição, não constante).

#### DoD
`python3 -m pytest scripts/tests/test_corpus_agreement.py -q` exit 0.

## Phase 3: Pseudo-labeling real (2 whisper) + benchmark de concordância

**Objective:** rodar 2 whisper sequenciais sobre FLEURS pt_br real, gerar hipóteses e medir a distribuição de CER par-a-par (`[MEDIDO]`).

### T3.1 — pseudo_label + run sobre FLEURS

#### Objective
`transcribe_pair(audio_paths, sizes=("small","medium")) -> {id: (hyp1, hyp2)}` sequencial (RAM), e um runner que grava a distribuição de CER + τ calibrado.

#### Why this step (action + reasoning)
Ação: reusar o padrão `WhisperModel(size, device="cpu", compute_type="int8").transcribe(...)` de `baseline_fleurs_ptbr.py`, carregando um modelo por vez com `del`+`gc.collect()`. Raciocínio: ADR-3 — 2 whisper distintos como proxy; RAM exige sequencial (Blueprint § Corner 3/Q7 `[FONTE-REPO]` EC-3).

#### Evidence
`scripts/baseline_fleurs_ptbr.py:81,84,86` (`[FONTE-REPO]` padrão sequencial); Blueprint § ADR de transcritores.

#### Files to edit
- `scripts/corpus/pseudo_label.py` (NEW, < 120 LoC)
- `scripts/tests/test_corpus_agreement.py` (append: teste do transcribe com mock)

#### Deep file dependency analysis
Importa `faster_whisper.WhisperModel` (instalado, M1). Reusa `agreement_filter` (Fase 2). O runner lê FLEURS do cache (parquet direto, padrão M2).

#### Deep Dives
Carga sequencial: transcreve TODO o set com modelo #1, `del`, `gc.collect()`, então modelo #2 — nunca ambos residentes (EC-3 RAM).

#### TDD
- RED: `test_transcribe_pair_loads_sequentially` (mock 2 modelos) — assere que model#1 é liberado (`del`) antes de model#2 instanciar (via ordem de chamadas mockadas).
- RED: `test_transcribe_pair_returns_two_hyps_per_id` — mock → dict com tupla de 2.
- GREEN + o runner real (não unit — roda no Integration).

#### Concurrency tests
(none — single-threaded) — carga sequencial explícita

#### Acceptance Criteria
- `python3 -m pytest scripts/tests/test_corpus_agreement.py -k sequential -q` retorna exit 0 (carga sequencial RAM-safe provada com mock).
- `grep -cE "del |gc.collect" scripts/corpus/pseudo_label.py` retorna ≥ 2 (libera cada modelo antes do próximo).
- Após o Integration, `test -s knowledge-base/corpus/m3-cer-distribution.md` sai 0 e o arquivo contém ≥ 20 linhas de CER por clip (`[MEDIDO]`).

#### DoD
`python3 -m pytest scripts/tests/test_corpus_agreement.py -q` exit 0 (parte mock); a run real é validada na Integration.

## Phase 4: Manifests Lhotse com augmentação on-the-fly

**Objective:** construir CutSet a partir de RecordingSet+SupervisionSet(text=pseudo_label) com o TelephoneChannel plugado on-the-fly, provando laziness.

### T4.1 — build_manifest

#### Objective
`build_cutset(wav_dir, labels: dict) -> CutSet` via `RecordingSet.from_dir` → `SupervisionSet.from_segments(text=...)` → `CutSet.from_manifests`, e anexar o telephone effect lazy.

#### Why this step (action + reasoning)
Ação: usar a API lhotse verificada (Blueprint § Corner 3/Q6 `[FONTE-REPO]`) com `input_strategy=AudioSamples` p/ on-the-fly. Raciocínio: ADR-4 — reusar lhotse (DoD pede); EC-4 — o default PrecomputedFeatures materializa em disco, então usar AudioSamples/OnTheFlyFeatures.

#### Evidence
`lhotse/.../recording_set.py:110`, `supervision.py:212-216,539`, `cut/set.py:378` (`[FONTE-REPO]`); Blueprint § Corner 4/Q1 (EC-4).

#### Files to edit
- `scripts/corpus/build_manifest.py` (NEW, < 120 LoC)
- `scripts/tests/test_corpus_manifest.py` (NEW)

#### Deep file dependency analysis
Importa `lhotse` (requer torch — ADR-4). Reusa `telephone_channel` (Fase 1). Teste usa `pytest.importorskip("lhotse")` p/ degradar limpo se torch/lhotse ausente (Drawbacks).

#### Deep Dives
on-the-fly: o telephone effect é aplicado no carregamento (via transform anexado OU input_transform), não gravado. Teste replica `test_lowpass_using_resampling` (Blueprint § Corner 1/Q8): assertar transform anexado antes de `load_audio()`.

#### TDD
- RED: `test_manifest_has_text_supervision` — CutSet gerado tem `supervisions[0].text == label`.
- RED: `test_telephone_applied_lazily` — o effect está registrado no cut/recording ANTES de materializar; `load_audio()` retorna 8 kHz.
- RED: `test_no_disk_materialization` — construir o CutSet não escreve WAV em disco (conta arquivos).
- GREEN + REFACTOR.

#### Concurrency tests
(none — single-threaded)

#### Acceptance Criteria
- `python3 -m pytest scripts/tests/test_corpus_manifest.py -q` retorna exit 0 (manifest + laziness verdes; `importorskip` reportado se lhotse ausente).
- O teste `test_manifest_has_text_supervision` assere `cutset[0].supervisions[0].text == label` (grep do assert ≥ 1).
- O teste `test_telephone_applied_lazily` assere `load_audio()` retorna sampling_rate == 8000 (grep do assert ≥ 1).

#### DoD
`python3 -m pytest scripts/tests/test_corpus_manifest.py -q` exit 0.

## Phase 5: Licenças, volume e Q-09

**Objective:** documentar a tabela de licenças com veredito comercial, o volume final e a resposta a Q-09.

### T5.1 — Documento de licenças, volume e Q-09

#### Objective
Documento com tabela `fonte → licença → veredito → rótulo`, volume declarado (fontes comercialmente limpas + TAGARELA com risco assumido), e Q-09 respondida.

#### Why this step (action + reasoning)
Ação: consolidar Blueprint § Corner 2/Q5 num documento de DoD. Raciocínio: DoD item 4 exige "licença de cada fonte mapeada com veredito"; a decisão de risco do dono (Blueprint § Context) é registrada com proveniência.

#### Evidence
Blueprint § Corner 2/Q5 (tabela de licenças); decisão do dono 2026-07-25.

#### Files to edit
- `knowledge-base/corpus/m3-licenses.md` (NEW)

#### TDD
(documento — sem TDD de código; validado por comandos grep na Integration).

#### Concurrency tests
(none — single-threaded)

#### Acceptance Criteria
- `grep -cE "CC-BY|CC0|NC-SA" knowledge-base/corpus/m3-licenses.md` retorna ≥ 4 (5 fontes com licença rotulada).
- `grep -c "Q-09" knowledge-base/corpus/m3-licenses.md` retorna ≥ 1 (Q-09 respondida com termos).
- `grep -ciE "risco.*assumido" knowledge-base/corpus/m3-licenses.md` retorna ≥ 1 (decisão do dono registrada).

#### DoD
`grep -cE "CC-BY|CC0|NC-SA" knowledge-base/corpus/m3-licenses.md` retorna ≥ 4 E `grep -c "Q-09" ...` retorna ≥ 1.

## Dependencies

Todas já instaladas no ambiente (torch/lhotse instalados nesta sessão; demais de M1). Veredito `/deps-audit` (OSV, 2026-07-25): **0 CVE** nas deps de M3.

| Dependência | Versão | Licença | CVE (OSV) | Rung parsimony |
|---|---|---|---|---|
| torch | 2.13.0+cpu | BSD-3 (PyTorch Foundation) | não auditável via PyPI (CPU wheel); sem CVE crítico conhecido | 4 — reusar (lhotse exige) |
| lhotse | 1.33.0 | Apache-2.0 | 0 | 4 — reusar (DoD pede manifests Lhotse) |
| faster-whisper | 1.2.1 | MIT | 0 | 4 — reusar (transcritor, M1) |
| scipy | 1.11.4 | BSD-3 | 0 | 4 — reusar (resample+filtro) |
| numpy | 1.26.4 | BSD-3 | 0 | 4 — reusar |
| jiwer | 3.1.0 | Apache-2.0 | 0 | 4 — reusar (CER) |
| audioop | stdlib | PSF | n/a (stdlib, deprecado PEP 594) | 2 — stdlib |

Nenhuma dependência nova precisa ser adicionada além de torch/lhotse (já instaladas). O scan global do ambiente pessoal reporta CVEs em pacotes não relacionados a M3 (fora de escopo).

## Coverage Matrix

| DoD de M3 (ROADMAP) | Task(s) | Status |
|---|---|---|
| Q-09 respondida (acesso Cem Mil Podcasts + termos) | T5.1 (+ Blueprint) | Coberto |
| Pipeline pseudo-labeling com filtro por concordância | T2.1 + T3.1 | Coberto |
| Manifests Lhotse com augmentação telefônica on-the-fly | T1.1 + T4.1 | Coberto |
| Volume final + licença de cada fonte com veredito comercial | T5.1 | Coberto |

**Coverage: 4/4 gaps covered (100%)**

## Global Definition of Done

- [ ] `python3 -m pytest scripts/tests/test_corpus_*.py -q` exit 0 (todos verdes).
- [ ] Pipeline rodou em ≥ 20 clips reais de FLEURS pt_br; distribuição de CER gravada (`[MEDIDO]`).
- [ ] Augmentação telefônica não materializa WAV em disco (teste `test_no_disk_materialization`/`test_no_tempfile_created`).
- [ ] Cada arquivo novo < 500 LoC (`rules/architecture.md`).
- [ ] Nenhum símbolo pendurado (todo módulo tem caller/teste).
- [ ] CHANGELOG `[Unreleased]` atualizado (Regra 6).
- [ ] Tabela de licenças + volume + Q-09 documentados.

## Failure scenarios (when I/O external)

O pipeline toca I/O externo (modelos whisper, leitura de áudio, lhotse):

- **faster-whisper OOM / modelo ausente:** teste com mock cobre a lógica; o runner real usa carga sequencial + `del`/`gc` (T3.1); se OOM, fail-fast com mensagem clara (não silêncio).
- **lhotse/torch ausente:** `pytest.importorskip("lhotse")` degrada o teste de manifest de forma explícita (reportado, não mascarado); fallback JSONL documentado (ADR-4 alt).
- **áudio corrompido/vazio no dir:** `RecordingSet.from_dir` + validação → segmento inválido rejeitado com erro tipado, não NaN silencioso.
- **`audioop` ausente (Python 3.13+):** import guardado fail-fast com instrução de instalar `audioop-lts` (T1.1).

## Final Phase: Integration Validation (MANDATORY)

**Objective:** validar que o pipeline funciona num workload real — não só unit tests.

### Execution
1. `python3 -m pytest scripts/tests/test_corpus_*.py -q` — todos verdes.
2. `python3 scripts/corpus/run_pipeline.py --n 20` — roda o pipeline ponta-a-ponta sobre 20 clips FLEURS pt_br: 2 whisper → CER par-a-par → τ calibrado → filtro → manifest lhotse com telephone on-the-fly. Grava `knowledge-base/corpus/m3-cer-distribution.md`.
3. Verificar que o manifest gerado tem supervisões com `text` e áudio 8 kHz on-the-fly.

### Acceptance Criteria
- Todos os testes verdes.
- `m3-cer-distribution.md` existe com CER por clip + τ + nº de cuts mantidos/descartados (`[MEDIDO]`).
- Manifest CutSet válido gerado; augmentação on-the-fly confirmada (áudio 8 kHz, sem WAV intermediário em disco).
- Tabela de licenças + Q-09 presentes.

### If Validation Fails
Voltar ao `/implement` (não editar o plano). Se o bloqueio for estrutural (torch não instala, RAM insuficiente), acionar o fallback ADR-4 (JSONL) e registrar; se persistir, BLOCKED honesto ao humano.
