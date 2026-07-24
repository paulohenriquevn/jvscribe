---
slug: m1-measurement-harness
milestone_id: M1
created_at: 2026-07-24
goal: Entregar a régua de medição de M1 — harness dos 5 critérios de real-time, cadeia de augmentação telefônica 8 kHz, WER com IC 95% via bootstrap, e baseline medido — todos os números rotulados [MEDIDO], com `cargo test --workspace` verde.
version: 1.1
---

<!-- v1.1: absorveu 5 SHOULD TEST de knowledge-base/reviews/m1-measurement-harness-edge-cases-plan-2026-07-24.md (EC-1..EC-5) no TDD das tasks. Nenhum MUST FIX. -->
<!-- plan-confidence: SHIPPABLE_WITH_CAVEATS (89.6, zero hard caps; completude 100, risco_estrutural 74). deps-audit: PASS (zero CVE). Caveats explícitos: 3 critérios de aceite heuristicamente "weak" (acceptable_ratio 0.824 ≥ 0.80) e densidade de adjetivos de prosa nas seções de risco/racional — palavras da disciplina de evidência (honesto/frágil), mantidas por carregarem sentido. Autoriza /implement (cycle-plan: ≥ SHIPPABLE_WITH_CAVEATS). -->


# Plan: M1 — Régua de Medição ASR (harness, augmentação, WER+IC, baseline)

## Goal

Implementar a régua de medição de M1 que produz um relatório com RTFx sustentado, latência p99, razão térmica, backlog e **WER com intervalo de confiança 95%** para ≥ 1 modelo baseline sobre o test set 8 kHz proxy, com **todos os números rotulados `[MEDIDO]`** e `cargo test --workspace` + a suíte de teste da augmentação/WER verdes.

**Métrica observável:** `cargo test --workspace` verde **E** existe `knowledge-base/measurements/m1-baseline-report.md` com ≥ 1 linha de WER no formato `WER = X% [IC95: A%–B%]` gerada por execução real da régua (não placeholder).

## Context

M1 é a régua que torna a decisão de M2 defensável (`PRD.md` § 8.1; `.claude/rules/asr-evidence-discipline.md` § 0). O design vem do blueprint `knowledge-base/discoveries/blueprints/m1-measurement-harness-blueprint.md` (verdict SHIPPABLE 99.7), que estabeleceu por leitura direta dos peers: (a) nenhum peer mede RTFx sustentado/p99 — construção própria sobre o padrão de `sherpa`/`parakeet`; (b) `icefall.write_error_stats` é por-utterance → bootstrap de IC viável; (c) `lhotse` só cobre resample, a cadeia G.711 é `sox`; (d) `jiwer` calcula WER (não reinventar), mas o normalizador EN não serve para PT-BR. Decisões-chave já tomadas nos ADRs D1/D2/D3 do blueprint (construção própria informada por padrões; test set v1 é proxy de canal sobre corpus público sob LGPD; terminologia RTFx fixada).

## Baseline Context (deep review of current state)

### Files that will be touched

| Arquivo | LoC hoje | Última mudança | Papel hoje | Invariants to preserve |
|---|---|---|---|---|
| `crates/macaw-audio/src/metrics.rs` | 216 | `ca02488` | `BacklogCounter` (p50/p95/p99 via `backlog_percentiles:132`), `DriftMeter` | API pública existente intacta; percentis via VecDeque cap 4096 (review H4) |
| `crates/macaw-audio/src/lib.rs` | — | M0 | re-exports do crate | não quebrar re-exports existentes |
| `crates/macaw-asr/src/lib.rs` | 242 | M0 | `AsrEngine::load:137` + `encode:205` — subject do RTFx | assinatura de `encode` intacta |
| `crates/macaw-cli/src/main.rs` | 259 | M0 | modos `fixture`/`live`/`serve` | adicionar modo `bench` sem quebrar os existentes |
| `scripts/` (NEW: `telephone_augment.sh`, `eval_wer.py`, `run_baseline.py`, `text_normalize_ptbr.py`) | 0 | — | orquestração de augmentação + baseline | — |
| `crates/macaw-audio/src/harness.rs` (NEW) | 0 | — | `RtfxMeter`, `LatencyHistogram`, `ThermalRatio` | — |

### Current callers / dependents

- `metrics.rs::BacklogCounter` — chamado em `crates/macaw-cli/src/main.rs:182` (run_live) e `app.rs`. Estender (não modificar assinatura) preserva os callers.
- `metrics.rs::backlog_percentiles:132` — padrão de percentil reusável pelo `LatencyHistogram` (DRY).
- `AsrEngine::encode` — chamado em `main.rs:111` (run_fixture) e `app.rs`. O `RtfxMeter` o chama em laço; sem mudança de assinatura.
- `taskset` — verificado disponível (`command -v taskset`). `sox` — verificado com encoding `a-law`. `stress-ng` — **ausente** (gerador de carga alternativo, ADR D4).

### Domain glossary

| Termo | Definição (1 linha) |
|---|---|
| RTFx | duração_do_áudio ÷ tempo_de_parede; maior = mais rápido; alvo ≥ 3× (RNF-01), ≥ 6× ASR isolado (RNF-07). Fixado no ADR D3 do blueprint contra a inversão dos peers |
| Razão térmica | RTFx(minuto 30) ÷ RTFx(minuto 1); alvo ≥ 80% (RNF-04); mede throttling do chip U de 15 W |
| Warmup | N iterações descartadas antes de medir (turbo/cache frios mentem, falácia §3 #4) |
| Bootstrap IC | reamostrar utterances com reposição B vezes, recomputar WER, reportar percentil 2,5–97,5 como IC 95% |
| Proxy de canal | test set 8 kHz = corpus público PT-BR (transcrição humana) degradado pela cadeia telefônica; NÃO é áudio real de call center (LGPD, ADR D2 do blueprint) |
| G.711 a-law | codec telefônico 8 kHz banda estreita; round-trip encode→decode introduz a degradação do canal |

### Architecture boundaries affected

- `harness.rs` é **infraestrutura de medição** dentro de `macaw-audio` — não vaza para o domínio (`.claude/rules/architecture.md` § 1). Mede o `AsrEngine` (adaptador) via a API pública, sem acoplar ao backend ONNX.
- Os scripts Python (`eval_wer.py`, `run_baseline.py`) são **orquestração externa** — camada de interface, fora dos crates. Reusam `jiwer` (lib estabelecida) e chamam os modelos HF. Fronteira: os scripts não importam nada dos crates; comunicam por arquivos (WAV in, JSON/texto out).

## Prior Art & Related Work

- **Blueprint interno** `knowledge-base/discoveries/blueprints/m1-measurement-harness-blueprint.md` (SHIPPABLE 99.7) — fonte de design primária, 10 citações verificadas.
- **Peers**: `sherpa-onnx/cxx-api-examples/streaming-zipformer-rtf-cxx-api.cc:94-130` (padrão RTF), `parakeet-rs/examples/streaming.rs:139-146` (RTFx em Rust), `icefall/icefall/utils.py:686` (WER por-utterance), `lhotse/test/audio/test_resample_randomized.py:28-47` (teste determinístico com tolerância), `moonshine/scripts/eval-librispeech.py:54-60` (fluxo de eval + jiwer).
- **Base de M0 reusada**: `crates/macaw-audio/src/metrics.rs` (percentis, backlog).
- **Lib externa**: `jiwer` (WER — Não-Reinvente, `.claude/rules/parsimony-ladder.md` rung 4).

## Objective

- [ ] SG1 — `RtfxMeter` mede RTFx com warmup e reporta valor sustentado sobre um laço de N iterações (Fase 1)
- [ ] SG2 — `LatencyHistogram` reporta p50/p95/p99 reusando o padrão de percentil de `metrics.rs` (Fase 1)
- [ ] SG3 — `ThermalRatio` reporta RTFx(min30)÷RTFx(min1) sobre um soak de ≥ 10 min (Fase 1)
- [ ] SG4 — cadeia de augmentação telefônica em `sox` (16k→8k + banda 300-3400 + a-law round-trip) com teste determinístico de tolerância (Fase 2)
- [ ] SG5 — `eval_wer.py` calcula WER + IC 95% via bootstrap por-utterance, reusando `jiwer` + normalizador PT-BR próprio, com teste de valores conhecidos (Fase 3)
- [ ] SG6 — `run_baseline.py` mede ≥ 1 modelo baseline sobre o test set 8 kHz proxy e emite `knowledge-base/measurements/m1-baseline-report.md` com WER+IC real (Fase 4)
- [ ] SG7 — modo `macaw-cli bench` fixa os P-cores via `taskset` e integra harness → relatório (Fase 1 + Integração)

## ADRs

### D1 — Harness em Rust, orquestração de baseline/augmentação em script

**Decisão:** O laço de medição sustentada (RTFx, p99, térmica, backlog) é Rust em `macaw-audio/src/harness.rs`, reusando `metrics.rs`. A augmentação (`sox`) e o baseline (WER + modelos HF) são scripts (`shell`/Python) em `scripts/`.

**Rationale:** Cada ferramenta na sua fronteira (`.claude/rules/architecture.md` § 3). O harness mede o `AsrEngine` in-process com precisão de `Instant` (padrão `parakeet-rs/examples/streaming.rs`). WER reusa `jiwer` (Python, Não-Reinvente) — portar para Rust reinventaria a lib (viola `parsimony-ladder.md` rung 4). **Alternativa rejeitada:** tudo em Rust — reinventaria jiwer e o loader de datasets HF, sem ganho. **Alternativa rejeitada:** tudo em Python — perderia a precisão e a integração in-process do RTFx com o `AsrEngine` Rust.

### D2 — RTFx com warmup e medição sustentada, nunca run único frio

**Decisão:** `RtfxMeter` descarta `warmup_iters` iterações antes de medir e reporta RTFx sobre uma janela sustentada; a razão térmica compara min30/min1.

**Rationale:** sherpa inclui o run frio na média e mede arquivo curto; parakeet mede run único (`streaming.rs:144`) — ambos caem na falácia §3 #4 (benchmark curto mede turbo). O chip U de 15 W não sustenta turbo (`PRD.md` RNF-04). **Alternativa rejeitada:** copiar o padrão sherpa (média de N runs sem warmup) — mede o turbo e mente sobre produção.

### D3 — WER sempre com IC; nunca ponto isolado

**Decisão:** `eval_wer.py` sempre reporta `WER = X% [IC95: A%–B%]` via bootstrap por-utterance (B ≥ 1000).

**Rationale:** Risco 1 do ROADMAP (20 min de áudio → IC largo); falácia §3 #12 (conclusão sem IC). `icefall.write_error_stats` recebe `results` por-utterance (`utils.py:718`) → reamostragem viável. **Alternativa rejeitada:** reportar WER pontual como icefall/moonshine fazem por padrão (agregado corpus-wide) — esconde a incerteza que é o ponto do risco 1.

### D4 — Carga concorrente reprodutível sem stress-ng

**Decisão:** O gerador de carga (RNF-05) são N processos presos aos E-cores via `taskset` rodando trabalho de CPU contínuo (ex.: `openssl speed` em loop), com o ASR preso aos P-cores; o modo `bench` documenta e mede sob essa carga.

**Rationale:** `stress-ng` ausente no ambiente (verificado). O que importa (`asr-evidence-discipline.md` §3 #9) é a carga ser dimensionável e registrada, não a ferramenta. **Alternativa rejeitada:** exigir stress-ng — bloquearia a medição por uma dependência ausente, quando o efeito (contenção de CPU) é reproduzível com o que existe.

## Drawbacks & Risks

| # | Risco | Severidade | Mitigação | Owner |
|---|---|---|---|---|
| R1 | Baseline dos 3 modelos é caro (whisper-large-v3 ~3 GB, corpus, inferência CPU lenta) e pode exceder o ambiente | **Alta** | Fase 4 mede primeiro o modelo mais leve (Moonshine) sobre um slice pequeno-mas-real com IC reportado (o IC largo É o resultado honesto do risco 1); protocolo reprodutível documentado para os demais; corpus como parâmetro | `evaluation-scientist` |
| R2 | Soak de ≥ 10 min do RtfxMeter requer o encoder emprestado de 600M carregado e é lento | Média | O soak usa o encoder de M0 já presente (`models/m0-borrowed`); número rotulado `[MEDIDO — encanamento apenas]` (não é número de produto); teste unitário usa um subject-mock rápido para o determinismo | `rust-runtime-engineer` |
| R3 | Normalizador PT-BR próprio pode divergir do que o WER "justo" exige (números por extenso, "pra/para") | Média | Teste de valores conhecidos com pares ref/hyp PT-BR curados; normalização documentada e versionada | `ptbr-phonetics-scientist` |
| R4 | Test set proxy ≠ call center real (domain gap R4 do PRD) | Média (aceita) | Rótulo honesto (ADR D2 do blueprint): "proxy de canal", gap medido depois; nunca reportado como domínio real | `evaluation-scientist` |
| R5 | `taskset`/afinidade pode não isolar throttling térmico de verdade num sandbox | Média | Reportar razão térmica com a metodologia exata (comando, hardware, nº de repetições) por `asr-evidence-discipline.md` §1; se o ambiente não sustentar 10 min, marcar `[DESCONHECIDO]` honesto em vez de número frágil | `hardware-validation-engineer` |

## Unresolved Questions

- Qual corpus público exato para o test set proxy v1 (Common Voice PT CC0 vs MLS-PT CC-BY)? — decidido na Fase 4 por licença + disponibilidade; ambos são aceitáveis por `PRD.md` § 7.3. Não bloqueia as Fases 1-3.
- Tamanho mínimo do test set para IC "aceitável" — é empírico; o bootstrap **reporta** o IC seja qual for o tamanho (o ponto do risco 1), então não é bloqueante.

## Dependencies

Novas dependências introduzidas por este plano (o harness Rust **não** adiciona crate novo — reusa `metrics.rs`/`AsrEngine` existentes). As deps são todas do lado Python de orquestração (ADR D1).

| Ecossistema | Pacote | Versão | Justificativa (Regra 9 — Não-Reinvente) |
|---|---|---|---|
| Python | `jiwer` | `>=3.0,<4.0` | Cálculo canônico de WER/CER (ins/del/sub + alinhamento). Alternativas rejeitadas: implementar edit distance à mão (reinventa, viola Regra 9), `evaluate.load('wer')` da HF (traz `datasets`+`evaluate` pesados só para WER). Usado por `moonshine/scripts/eval-librispeech.py:57`. Pin < 4.0 evita o major novo não testado (latest 4.0.0). |
| Python | `soundfile` | `>=0.12,<1.0` | Leitura de WAV para o eval. Alternativas rejeitadas: `scipy.io.wavfile` (não lê a-law/formatos amplos), `wave` stdlib (sem float direto). libsndfile é padrão da indústria; usado pelo mesmo peer. |
| Python | `numpy` | `>=1.24,<3.0` | Aritmética do bootstrap (reamostragem vetorizada). Alternativa rejeitada: laços Python puros (ordens de magnitude mais lento para B≥1000). Já é dep transitiva universal. |
| Python | `openai-whisper` | `>=20231117` | Inferência do baseline whisper-large-v3. Alternativas rejeitadas: `faster-whisper` (CTranslate2 — mais rápido mas adiciona toolchain de conversão de modelo; mantido como fallback se a inferência CPU for inviável, R1), `transformers` puro (mais pesado). Não reimplementar Whisper (Regra 9). Versão date-based; pin no piso estável conhecido. |

- **Rust:** nenhuma dependência nova. `sox`/`taskset` são ferramentas de sistema (não deps de pacote), verificadas presentes no ambiente.
- **Licenças:** `jiwer` (Apache-2.0), `soundfile` (BSD-3), `numpy` (BSD-3) — todas permissivas, compatíveis. `openai-whisper` (MIT). Confirmar CVE no deps-audit.

## Dependency Graph

```
Fase 1 (harness Rust) ──┐
Fase 2 (augmentação sox) ┼─→ Fase 4 (baseline: usa augmentação + WER) ─→ Integração
Fase 3 (WER+IC Python) ──┘
```

- Fases 1, 2, 3 são **independentes** e paralelizáveis.
- Fase 4 **depende** de 2 (cadeia para gerar o test set 8 kHz) e 3 (eval de WER).
- Integração depende de todas.

## Phase 1: Harness de medição em Rust

### T1.1 — `RtfxMeter` com warmup e RTFx sustentado

#### Objective
Medir RTFx = áudio/parede sobre um subject de inferência, descartando warmup, reportando RTFx sustentado.

#### Why this step (action + reasoning — ReAct discipline)
Ação: criar `harness.rs` com `RtfxMeter` que recebe um `impl Fn` (o subject, ex.: `AsrEngine::encode`) e a duração de áudio processada, cronometra com `Instant`, descarta `warmup_iters`. Necessário agora porque RNF-01/07 são a espinha da régua e todo o resto (baseline) reporta RTFx — sem terminologia fixada (D3) e warmup (D2), o número mente. Cita ADR D2/D3 e `parakeet-rs/examples/streaming.rs:139-146`.

#### Evidence
`parakeet-rs/examples/streaming.rs:144` (`duration/elapsed`), `sherpa-onnx/…rtf-cxx-api.cc:120` (média sem warmup — o anti-padrão). `crates/macaw-asr/src/lib.rs:205` (`encode` é o subject real).

#### Files to edit
`crates/macaw-audio/src/harness.rs` (NEW), `crates/macaw-audio/src/lib.rs` (re-export), `crates/macaw-audio/tests/harness_test.rs` (NEW)

#### Deep file dependency analysis
- `harness.rs` novo; `lib.rs` só ganha `pub mod harness;`. Nenhum caller existente afetado.
- Subject genérico (`Fn(&[f32]) -> Result<...>`) para não acoplar ao `AsrEngine` (DIP) — testável com mock rápido.

#### Deep Dives
- Invariante: RTFx = audio_secs/wall_secs; wall_secs > 0 (guard contra divisão por zero → erro tipado, `error-handling.md`); warmup_iters < total_iters.

#### TDD
- RED: `test_rtfx_discards_warmup` — subject mock cujo 1º run é artificialmente lento (sleep) e os demais rápidos; asserir que RTFx reportado ≈ o dos runs rápidos (warmup descartado), com tolerância.
- RED: `test_rtfx_zero_wall_time_is_typed_error` (negative case) — subject instantâneo (wall≈0) retorna erro tipado, não `inf`.
- RED: `test_rtfx_warmup_ge_total_is_typed_error` (EC-1, negative) — `warmup_iters >= total_iters` → `HarnessError` tipado (medição sem iterações é config inválida).
- GREEN: implementar `RtfxMeter`.

#### Concurrency tests (only when applicable)
(none — single-threaded) — o `RtfxMeter` mede em laço sequencial; não há estado compartilhado mutável entre threads nesta task.

#### Acceptance Criteria
- [ ] RTFx reportado ignora os `warmup_iters` primeiros runs
- [ ] wall_secs = 0 → `HarnessError` tipado (não inf/NaN)
- [ ] `cargo test -p macaw-audio harness` verde

#### DoD
- [ ] `cargo test -p macaw-audio` verde · `cargo clippy -p macaw-audio -- -D warnings` limpo

### T1.2 — `LatencyHistogram` (p50/p95/p99) reusando o padrão de percentil

#### Objective
Registrar latências por chunk e reportar p50/p95/p99 (RNF-02 ≤ 500 ms p99).

#### Why this step (action + reasoning)
Ação: `LatencyHistogram` com `record(Duration)` e `percentiles() -> (p50,p95,p99)`, reusando a lógica de `backlog_percentiles` de `metrics.rs:132` (VecDeque cap para memória limitada, review H4). Necessário agora porque RNF-02 é p99 e a falácia §3 #3 (média esconde a cauda) é motivo de recusa. Cita `metrics.rs:132`.

#### Evidence
`crates/macaw-audio/src/metrics.rs:132` (`backlog_percentiles` — padrão a reusar).

#### Files to edit
`crates/macaw-audio/src/harness.rs`, `crates/macaw-audio/tests/harness_test.rs`

#### Deep file dependency analysis
- Reusa o algoritmo de percentil já testado (DRY); não duplica a lógica de ordenação/índice.

#### Deep Dives
- Invariante: p50 ≤ p95 ≤ p99; janela limitada (cap) para não crescer sem limite (review H4).

#### TDD
- RED: `test_latency_percentiles_known_distribution` — inserir distribuição conhecida (1..=100 ms), asserir p50≈50, p95≈95, p99≈99.
- RED: `test_latency_window_is_bounded` (edge) — inserir > cap amostras, asserir que o histograma não excede o cap.
- RED: `test_latency_percentiles_empty_is_unambiguous` (EC-2, edge) — sem amostras, a API sinaliza "sem dados" (`Option::None` ou `n=0`), nunca `(0,0,0)` que se confunde com latência zero.
- GREEN: implementar.

#### Concurrency tests (only when applicable)
(none — single-threaded) nesta task; se compartilhado entre threads no soak, T1.3 cobre via atomic/coleta pós-join.

#### Acceptance Criteria
- [ ] p50/p95/p99 corretos para distribuição conhecida · janela limitada ao cap

#### DoD
- [ ] `cargo test -p macaw-audio` verde · clippy limpo

### T1.3 — `ThermalRatio` + soak de ≥ 10 min + modo `bench` com `taskset`

#### Objective
Medir RTFx(min30)÷RTFx(min1) sobre soak sustentado e expor via `macaw-cli bench`, preso aos P-cores por `taskset`.

#### Why this step (action + reasoning)
Ação: `ThermalRatio` agrega RTFx por janela temporal; modo `bench` no CLI roda o soak sobre o encoder de M0, preso aos P-cores. Necessário agora porque RNF-04 (estabilidade térmica) é um dos 5 critérios e o chip U mente em 30s. Cita ADR D2/D4, `PRD.md` RNF-04.

#### Evidence
`PRD.md` § 6 RNF-04; `crates/macaw-cli/src/main.rs:41` (dispatch de modos a estender).

#### Files to edit
`crates/macaw-audio/src/harness.rs`, `crates/macaw-cli/src/main.rs`, `scripts/bench.sh` (NEW, wrapper `taskset`), `crates/macaw-audio/tests/harness_test.rs`

#### Deep file dependency analysis
- `main.rs:41` dispatch ganha braço `bench` sem quebrar `fixture`/`live`/`serve`.
- `bench.sh` usa `taskset -c` (P-cores) + o gerador de carga do ADR D4 nos E-cores.

#### Deep Dives
- Invariante: razão térmica ∈ (0, ~1.2]; se o ambiente não sustentar 10 min, reportar `[DESCONHECIDO]` honesto (R5), nunca número frágil.

#### TDD
- RED: `test_thermal_ratio_computes_min30_over_min1` — alimentar RTFx sintético por janela (min1=6.0, min30=5.0), asserir razão ≈ 0.83.
- RED: `test_thermal_ratio_zero_baseline_is_typed_error` (EC-3, negative) — RTFx(min1)=0 → `HarnessError` tipado (não `inf`/`NaN`).
- GREEN: implementar o agregador (o soak real de 10 min é validação de integração, não teste unitário — determinismo por injeção de janelas).

#### Concurrency tests (only when applicable)
Posture do agregador: `ThermalRatio` recebe amostras já coletadas (pós-join ou via canal), sem estado compartilhado mutável — **(none — single-threaded)** no agregador em si. Para o soak que coleta de threads de captura (M0), um **atomic-counter** de amostras é validado sob acesso **concurrent** por N threads: `test_thermal_sample_count_concurrent` incrementa de N threads e assere a contagem final == N×iter (invariante de atomic-counter, sem perda por corrida).

#### Acceptance Criteria
- [ ] Razão térmica correta para janelas conhecidas — oracle: `cargo test -p macaw-audio test_thermal_ratio` retorna exit 0
- [ ] `macaw-cli bench` emite RTFx/p99/térmica/backlog e retorna exit 0 — oracle: `cargo run -p macaw-cli -- bench 2>&1 | grep -E 'RTFx|p99'`
- [ ] `bench.sh` fixa P-cores via `taskset` — oracle: `grep 'taskset -c' scripts/bench.sh` casa

#### DoD
- [ ] `cargo test -p macaw-audio` verde · clippy limpo · `macaw-cli bench` executa sem panic

## Phase 2: Cadeia de augmentação telefônica (sox)

### T2.1 — `telephone_augment.sh`: 16k→8k + banda 300-3400 + G.711 a-law round-trip

#### Objective
Degradar um WAV 16 kHz para o canal telefônico 8 kHz de forma determinística e reprodutível.

#### Why this step (action + reasoning)
Ação: script `sox` com os 4 estágios (resample, banda, a-law encode, decode). Necessário agora porque a Fase 4 precisa da cadeia para gerar o test set 8 kHz, e é DoD de M1. Cita ADR do blueprint (Corner4/Q3), `sox` a-law verificado.

#### Evidence
`lhotse/lhotse/augmentation/resample.py:126` (só resample — o que falta); `sox --help` (a-law nativo).

#### Files to edit
`scripts/telephone_augment.sh` (NEW), `crates/macaw-audio/tests/augmentation_test.rs` (NEW — invoca o script e verifica a saída)

#### Deep file dependency analysis
- Script novo, sem dependência dos crates. O teste Rust invoca o script via `Command` (como `capture_test.rs` já faz com `pactl`/`sox`) e verifica propriedades do WAV de saída.

#### Deep Dives
- Invariante: saída é 8 kHz mono; duração ≈ entrada (tolerância 1 amostra, padrão `lhotse` test); round-trip a-law preserva a forma dentro da tolerância do codec.

#### TDD
- RED: `test_augment_output_is_8khz_mono` — gerar tom 16 kHz (sox, como `capture_test`), rodar a cadeia, asserir header 8 kHz mono e duração dentro de tolerância.
- RED: `test_augment_missing_input_is_error` (negative) — input inexistente → script sai com código de erro (fail-fast).
- RED: `test_augment_band_attenuates_above_3400hz` (edge) — tom de 4 kHz é atenuado após a banda (energia cai).
- GREEN: escrever o script.

#### Concurrency tests
(none — single-threaded) — pipeline sequencial de subprocessos.

#### Acceptance Criteria
- [ ] Saída é 8 kHz mono — oracle: `soxi -r out.wav` retorna `8000` e `soxi -c out.wav` retorna `1`
- [ ] Banda atenua energia acima de 3400 Hz — oracle: `test_augment_band_attenuates_above_3400hz` retorna exit 0
- [ ] Input inexistente falha com exit code não-zero — oracle: `./scripts/telephone_augment.sh /nao/existe.wav; echo $?` imprime não-zero
- [ ] Teste degrada graciosamente se `sox` ausente (padrão `capture_test.rs` — SKIP com `eprintln!`)

#### DoD
- [ ] `cargo test -p macaw-audio augmentation` verde (ou SKIP explícito se sox ausente)

## Phase 3: WER com IC via bootstrap (Python + jiwer)

### T3.1 — normalizador PT-BR + `eval_wer.py` com bootstrap IC

#### Objective
Calcular WER + IC 95% por bootstrap por-utterance, reusando `jiwer`, com normalização PT-BR.

#### Why this step (action + reasoning)
Ação: `text_normalize_ptbr.py` (caixa, pontuação, números por extenso, "pra/para", acentos) + `eval_wer.py` que lê pares (ref, hyp) por-utterance, normaliza, computa WER via `jiwer`, e reamostra B≥1000 vezes para o IC. Necessário agora porque WER+IC é o coração da comparabilidade e ataca o risco 1. Cita ADR D3, `moonshine/scripts/eval-librispeech.py:57` (jiwer), `icefall/icefall/utils.py:718` (por-utterance).

#### Evidence
`moonshine/scripts/eval-librispeech.py:54-60` (jiwer + EnglishTextNormalizer — o EN que não serve); `icefall/icefall/utils.py:686` (estrutura por-utterance).

#### Files to edit
`scripts/text_normalize_ptbr.py` (NEW), `scripts/eval_wer.py` (NEW), `scripts/tests/test_eval_wer.py` (NEW), `scripts/requirements-eval.txt` (NEW — jiwer pinado)

#### Deep file dependency analysis
- Scripts Python isolados dos crates (fronteira D1). `jiwer` é dep externa (deps-audit valida).

#### Deep Dives
- Invariante: WER ∈ [0, ∞); IC_low ≤ WER ≤ IC_high; bootstrap determinístico com seed fixa (teste reprodutível, `testing.md` § 6 — sem aleatoriedade não-injetada).

#### TDD
- RED: `test_wer_known_pairs` — pares ref/hyp com WER conhecido (ex.: 1 substituição em 4 palavras = 25%), asserir WER exato.
- RED: `test_ptbr_normalizer` — "R$ 100" / "cento e cinquenta" / "pra" normalizados de forma canônica.
- RED: `test_bootstrap_ci_brackets_wer` — com seed fixa, IC_low ≤ WER ≤ IC_high e IC é mais largo para N pequeno (edge).
- RED: `test_bootstrap_ci_single_utterance` (EC-4, edge) — N=1 utterance, seed fixa → IC degenerado (`IC_low == IC_high == WER`) sem crash; relatório deixa claro que N=1 dá IC sem informação.
- RED: `test_wer_empty_reference_is_error` (negative) — referência vazia → erro tipado, não divisão por zero.
- GREEN: implementar.

#### Concurrency tests
(none — single-threaded).

#### Acceptance Criteria
- [ ] WER exato para pares conhecidos · IC contém o WER · normalizador PT-BR determinístico · seed fixa → resultado reprodutível

#### DoD
- [ ] `python3 -m pytest scripts/tests/test_eval_wer.py` verde

## Phase 4: Baseline sobre test set 8 kHz proxy

### T4.1 — `run_baseline.py`: test set proxy + ≥ 1 modelo → relatório WER+IC

#### Objective
Gerar o test set 8 kHz proxy (corpus público + Fase 2) e medir ≥ 1 modelo baseline com WER+IC real.

#### Why this step (action + reasoning)
Ação: baixar um slice pequeno-mas-real de corpus público PT-BR (transcrição humana), aplicar `telephone_augment.sh`, rodar ≥ 1 modelo (Moonshine primeiro — leve), computar WER+IC via `eval_wer.py`, emitir `knowledge-base/measurements/m1-baseline-report.md`. Necessário agora porque é o DoD final de M1 (baseline medido) e prova a régua ponta-a-ponta. Cita ADR D2 do blueprint (proxy), R1.

#### Evidence
`moonshine/scripts/eval-librispeech.py` (fluxo load→transcribe→normalize→jiwer). `PRD.md` § 7.3 (corpus público, invariante anti-pseudo-label).

#### Files to edit
`scripts/run_baseline.py` (NEW), `knowledge-base/measurements/m1-baseline-report.md` (NEW — gerado), `scripts/tests/test_run_baseline.py` (NEW)

#### Deep file dependency analysis
- Orquestra Fase 2 (augmentação) + Fase 3 (WER). Test set NUNCA contém pseudo-label (invariante `PRD.md` § 7.3) — o loader rejeita manifesto marcado pseudo-label (teste).

#### Deep Dives
- Invariante: cada número no relatório tem rótulo `[MEDIDO]` com comando/hardware/nº de repetições (`asr-evidence-discipline.md` § 1); test set sem pseudo-label.

#### TDD
- RED: `test_baseline_report_has_ci_and_provenance` — dado um resultado mock de 1 modelo, o relatório gerado contém `WER = X% [IC95: A%–B%]` e rótulo `[MEDIDO]`.
- RED: `test_testset_rejects_pseudolabel` (negative) — manifesto com flag pseudo-label → erro (invariante `PRD.md` § 7.3).
- RED: `test_baseline_empty_testset_is_error` (EC-5, negative) — 0 utterances válidas → falha fast com "0 utterances mensuráveis", sem divisão por zero nem WER falso.
- GREEN: implementar; rodar de verdade sobre o slice → número real no relatório.

#### Concurrency tests
(none — single-threaded). A orquestração de `run_baseline.py` é sequencial; a inferência dos modelos é subprocesso externo, sem estado compartilhado no nosso código.

#### Acceptance Criteria
- [ ] `knowledge-base/measurements/m1-baseline-report.md` contém ≥ 1 WER com IC real (execução, não placeholder) · test set rejeita pseudo-label · rótulo de proveniência presente

#### DoD
- [ ] `python3 -m pytest scripts/tests/test_run_baseline.py` verde · relatório gerado por execução real

## Coverage Matrix

| Requisito / DoD de M1 (ROADMAP) | Task(s) | Status |
|---|---|---|
| Harness 5 critérios: RTFx sustentado ≥ 10 min | T1.1, T1.3 | Mapped |
| Harness: latência p99 | T1.2 | Mapped |
| Harness: backlog | (reusa `metrics.rs` M0) + T1.3 integra | Mapped |
| Harness: curva térmica | T1.3 | Mapped |
| Harness: carga concorrente + taskset P-cores | T1.3 (ADR D4) | Mapped |
| Augmentação: 16k→8k, banda, a-law round-trip | T2.1 | Mapped |
| Augmentação: babble/AGC | T2.1 (estágios sox adicionais) + Unresolved | Mapped (parcial — babble/AGC como extensão de T2.1) |
| Test set 8 kHz sem pseudo-label, recorte regional | T4.1 (proxy, ADR D2 blueprint) | Mapped |
| Baseline: TAGARELA + Moonshine + whisper-large-v3 | T4.1 (≥1 medido; protocolo p/ os 3, R1) | Mapped |
| WER com IC (risco 1) | T3.1 | Mapped |

## Global Definition of Done

- [ ] `cargo test --workspace` verde · `cargo clippy --workspace --all-targets -- -D warnings` limpo
- [ ] `python3 -m pytest scripts/tests/` verde
- [ ] `knowledge-base/measurements/m1-baseline-report.md` com ≥ 1 WER+IC real, rotulado `[MEDIDO]`
- [ ] Todo número de medição tem rótulo de proveniência (`asr-evidence-discipline.md` § 1)
- [ ] CHANGELOG `[Unreleased]` atualizado (Regra 6)
- [ ] Arquivos novos ≤ 500 LoC cada (`architecture.md`)
- [ ] `/code-quality` verdict ∉ {FAIL_HARD, INVALID}

## Failure scenarios (when I/O external)

A régua toca I/O externo: subprocessos `sox`/`taskset`, download de corpus/modelos, inferência ONNX/HF.

| Dependência externa | Modo de falha | Como o teste reproduz | Comportamento esperado |
|---|---|---|---|
| `sox` (subprocess) | binário ausente | ambiente sem sox (o teste checa `which sox`) | SKIP explícito com `eprintln!` (padrão `capture_test.rs`), não falha alheia |
| `sox` (subprocess) | input inválido | path inexistente | erro tipado / exit code não-zero (T2.1 negative) |
| Download de corpus | rede indisponível / 404 | mock: URL inválida | `run_baseline.py` falha fast com mensagem clara (não silencioso) |
| Modelo HF | modelo ausente / OOM | mock: caminho de modelo inexistente | erro claro com contexto (qual modelo, qual passo) |
| Inferência ONNX (encoder M0) | encoder ausente | `models/m0-borrowed` ausente | mensagem clara (como M0 já faz em `main.rs:124`) |

## Final Phase: Integration Validation (MANDATORY)

### Execution
1. `cargo test --workspace` + `cargo clippy --workspace --all-targets -- -D warnings`
2. `python3 -m pytest scripts/tests/`
3. `macaw-cli bench` (soak curto de smoke — janela reduzida) executa e imprime RTFx/p99/térmica/backlog sem panic
4. Chaos pass: rodar cada linha de `## Failure scenarios` (sox ausente simulado, input inválido, modelo ausente) e observar o comportamento esperado
5. `run_baseline.py` sobre o slice real → `knowledge-base/measurements/m1-baseline-report.md` com WER+IC real

### Acceptance Criteria
- [ ] Todas as suítes verdes · clippy limpo
- [ ] `knowledge-base/measurements/m1-baseline-report.md` gerado por execução real com WER+IC rotulado `[MEDIDO]`
- [ ] Failure scenarios exercitados — cada linha observada
- [ ] `macaw-cli bench` roda sem panic

### If Validation Fails
Voltar ao `/implement` (não editar o plano). Se a Fase 4 esbarrar em limite de compute do ambiente (R1), reduzir o slice e reportar o IC largo honesto — nunca fabricar número (`asr-evidence-discipline.md` § 4).
