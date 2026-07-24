---
slug: m0-walking-skeleton
milestone_id: M0
created_at: 2026-07-24
goal: Transcrever uma chamada real de ponta a ponta no notebook de referência, com dois streams capturados independentemente, provando o encanamento antes de qualquer decisão de arquitetura
baseline_sha: 8e180c2
branch: develop
---

# Plan: M0 Walking Skeleton — captura de dois streams e transcrição incremental

## Goal

Entregar um binário Rust que capture **microfone e áudio do sistema em streams
independentes**, aplique VAD por stream, rotule o falante por roteamento, extraia
log-mel sem alocar no caminho quente, e produza **transcrição incremental** usando
modelo emprestado — sustentando ≥ 5 minutos sem crash e **sem crescimento de
backlog**.

## Context

`ROADMAP.md` M0 é o walking skeleton: prova o encanamento **antes** do ADR de
arquitetura (M2). O blueprint
`knowledge-base/discoveries/blueprints/m0-walking-skeleton-blueprint.md`
(verdict `SHIPPABLE`) fechou as 8 questões de descoberta e produziu 4 ADRs.

Três riscos ficaram abertos no blueprint e **viram obrigação de medição neste
plano**: deriva de sincronia entre streams, custo de CPU do VAD e latência de
captura.

## Baseline Context (deep review of current state)

**Estado do repositório:** `develop` @ `8e180c2`. **Zero arquivos `.rs`** fora de
`knowledge-base/`. Este plano cria o primeiro código de produção do projeto.

### Files that will be touched

| Caminho | Estado | LoC atual | Responsabilidade após o plano |
|---|---|---|---|
| `Cargo.toml` | **novo** | 0 | Workspace raiz |
| `crates/macaw-audio/Cargo.toml` | **novo** | 0 | Manifesto do crate de áudio |
| `crates/macaw-audio/src/lib.rs` | **novo** | 0 | Exports públicos |
| `crates/macaw-audio/src/capture.rs` | **novo** | 0 | Captura dual via libpulse |
| `crates/macaw-audio/src/ring.rs` | **novo** | 0 | Ring buffer sem alocação |
| `crates/macaw-audio/src/features.rs` | **novo** | 0 | log-mel 128 bins, buffers pré-alocados |
| `crates/macaw-audio/src/vad.rs` | **novo** | 0 | VAD por stream + rótulo de falante |
| `crates/macaw-audio/src/metrics.rs` | **novo** | 0 | Backlog, drift, latência |
| `crates/macaw-asr/src/lib.rs` | **novo** | 0 | Wrapper ONNX (encanamento apenas) |
| `crates/macaw-cli/src/main.rs` | **novo** | 0 | Binário de demonstração |
| `tests/fixtures/` | **novo** | 0 | WAV sintético versionado |

### Current callers / dependents

**Nenhum.** Não há código de produção no repositório. Não existe risco de
regressão — todo o comportamento é novo. Os consumidores futuros são M1 (harness
de medição reusa `metrics.rs`) e M6 (runtime otimizado substitui `macaw-asr`).

### Domain glossary

| Termo | Significado neste projeto |
|---|---|
| **stream** | Fluxo de áudio de uma fonte: `mic` (atendente) ou `loopback` (cliente) |
| **loopback / monitor** | Source do PulseAudio que espelha o que sai por um sink |
| **roteamento de falante** | Atribuir falante pela origem do stream, sem modelo de diarização (RF-05) |
| **backlog** | Amostras capturadas e ainda não processadas; RNF-03 exige zero em 99,9% |
| **drift** | Deriva temporal acumulada entre os dois streams |
| **caminho quente** | Código executado a cada chunk; alocação aqui é defeito |
| **encanamento** | O pipeline sem compromisso de qualidade — o que M0 prova |

### Architecture boundaries affected

Conforme `.claude/rules/architecture.md`: `macaw-audio` é **domínio** (DSP puro, sem
I/O de rede); `capture.rs` é **adapter** de infraestrutura (libpulse); `macaw-cli`
é **interface** e único ponto de composição. `macaw-asr` é adapter de inferência —
**descartável por construção**, porque M2 pode trocar a arquitetura inteira.

## Prior Art & Related Work

| Fonte | O que aproveitamos |
|---|---|
| `knowledge-base/references/parakeet-rs/src/audio.rs` | Padrão de cache de `fft_plan` + `mel_basis` (linhas 12-27). **Não** o código de `stft_with_plan` — aloca 5× por chunk |
| `knowledge-base/references/sherpa-onnx/rust-api-examples/examples/streaming_zipformer_microphone.rs` | Desenho mpsc produtor/consumidor com drain antes de renderizar (linhas 186, 210) |
| `knowledge-base/references/sherpa-onnx/rust-api-examples/examples/silero_vad_remove_silence.rs` | Parâmetros do VAD Silero (linhas 47-51) |
| `knowledge-base/discoveries/m0-capture-probe-evidence.md` | Seis experimentos que decidiram a dependência de captura |

## Objective

Um binário que satisfaça o DoD de M0 do `ROADMAP.md`, com **evidência medida** para
cada critério — nenhum número sem rótulo de proveniência
(`.claude/rules/asr-evidence-discipline.md` § 1).

## ADRs

### D1 — Workspace com três crates, não um binário monolítico

**Decisão:** `macaw-audio` (domínio DSP), `macaw-asr` (adapter de inferência),
`macaw-cli` (composição).

**Rationale:** `macaw-asr` é **descartável por construção** — M2 pode trocar a
arquitetura inteira. Isolá-lo atrás de uma fronteira impede que a troca contamine o
DSP, que é estável e independente de arquitetura. `.claude/rules/architecture.md`
§ 2 (DIP).

**Alternativas descartadas:**
- Binário único — rejeitado: acoplaria DSP ao modelo, e M2 forçaria reescrita do que já está correto
- Um crate por arquivo — rejeitado: over-engineering, viola `parsimony-ladder` rung 1

### D2 — Captura via `libpulse-simple-binding`, uma thread por stream

**Decisão:** `Simple::new(..., Some(&source), ...)` em thread dedicada por stream.

**Rationale:** herdado do blueprint D1, decidido por evidência medida. A API
`Simple` é **bloqueante**, o que combina com thread dedicada e mantém o caminho
quente livre de polling.

**Alternativas descartadas:** `cpal 0.16` (não enumera monitores `[MEDIDO]`);
`PULSE_SOURCE` (escopo de processo); subprocesso `parec` (acoplamento externo);
`cpal ≥0.18 + pipewire` (exige PipeWire ≥0.3.53, não é o servidor deste ambiente).

### D3 — Buffers pré-alocados por stream, `FeatureCache` compartilhado via `Arc`

**Decisão:** `padded`, `input`, `output`, `scratch` e janela de Hann como campos
persistentes de `StreamState`; `mel_basis` + `fft_plan` compartilhados read-only.

**Rationale:** blueprint D2 e D3. `parakeet-rs` aloca 5× por chunk — copiar
repetiria o defeito que RNF-01/RNF-07 medem.

**Alternativas descartadas:** portar `audio.rs` verbatim — rejeitado pelo achado
`[MEDIDO]` de alocação; um `FeatureCache` por stream — rejeitado: duplica memória
sem ganho, já que é read-only.

### D4 — Métricas como cidadão de primeira classe desde o dia 1

**Decisão:** `metrics.rs` desde a primeira task, não retrofit.

**Rationale:** RNF-03 (backlog) e os riscos R-M0-1/R-M0-2 exigem medição. Nenhum
peer mede backlog — se não instrumentarmos desde o início, a evidência não existe e
o DoD não pode ser provado.

**Alternativas descartadas:** medir só no fim — rejeitado: exigiria refatorar o
caminho quente depois, e o `technical-program-lead` trata isso como retrabalho
evitável.

## Drawbacks & Risks

| # | Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|---|
| R1 | **Deriva de sincronia entre streams** (R-M0-1 do blueprint) | Média | **Alto** — RF-05 depende | T5.2 mede drift em ≥ 10 min; se > 100 ms, o roteamento precisa de âncora temporal |
| R2 | **Custo do VAD desconhecido** (R-M0-2) | Média | Médio | T5.3 cronometra por janela de 512 amostras |
| R3 | Modelo emprestado é 16 kHz offline; produção é 8 kHz streaming | **Alta** | Baixo em M0 | ADR D4 do blueprint: resultados rotulados `[MEDIDO — encanamento apenas]` |
| R4 | `libpulse` é API C via FFI — panics em thread podem derrubar o processo | Baixa | Alto | Erros tipados, `catch_unwind` na fronteira, teste negativo de source inexistente |
| R5 | Ambiente com PulseAudio nativo pode não representar a frota BYOD | **Alta** | Médio (M8) | Documentado como limite; Q-01 trata |
| R6 | Sink mudo ⇒ cliente sem transcrição, sem erro | Média | **Alto** | T2.3 detecta e sinaliza — é requisito, não opcional |

## Unresolved Questions

- U1 — **Qual limiar de drift entre os dois streams torna o roteamento de falante inválido?** Bloqueia a interpretação de T5.2. Hipótese a testar: deriva acima de 100 ms compromete a atribuição em turnos rápidos de fala. Resolução: definir o limiar após a primeira execução de 10 min; se o drift medido exceder o limiar, R1 escala para decisão de produto.
- U2 — **`min_silence_duration` deve ser 0,1 s ou 0,25 s?** Bloqueia o ajuste fino do VAD. Os dois exemplos do peer divergem (`sense_voice_simulate_...rs:154-165` usa 0,1; `silero_vad_remove_silence.rs:47-51` usa 0,25) e a divergência está registrada no blueprint. Resolução: adotar 0,25 s em M0 por ser o valor mais conservador contra corte de fala, e revisar com dado real de call center em M1.
- U3 — **`max_speech_duration` de 5 s ou 8 s serve para turnos de atendimento?** Bloqueia o ajuste do VAD para fala contínua. Mesma divergência de peers. Resolução: adotar 8 s em M0 (turnos de atendimento costumam ser mais longos que os de assistente de voz) e medir a distribuição real de duração de turno em M1.

## Dependency Graph

`T0` (workspace + fixtures) precede tudo. `T1` (captura) e `T3` (features) são
independentes entre si e podem ser paralelizados. `T2` (VAD + roteamento) depende
de `T1`. `T4` (ONNX) depende de `T3`. `T5` (métricas) depende de `T1` e `T4`. A
fase final de integração depende de todas.

---

## Phase T0: Fundação do workspace

### T0.1 — Workspace Rust com três crates e fixture de áudio versionada

#### Objective

Criar a estrutura de compilação e uma fixture WAV determinística que permita testar
DSP sem baixar modelo.

#### Why this step (action + reasoning — ReAct discipline)

**Ação:** criar workspace e gerar fixture sintética.
**Raciocínio:** o blueprint registrou como lacuna que **nenhum peer versiona
fixture de áudio** — todos exigem download manual. Sem fixture determinística, todo
teste vira dependente de rede e o CI fica não-reprodutível. Criar isso primeiro
destrava todos os testes seguintes.

#### Evidence

`knowledge-base/discoveries/blueprints/m0-walking-skeleton-blueprint.md` §
Coverage Corner 1: *"`find -iname "*.wav"` → zero"* em `parakeet-rs`.

#### Files to edit

`Cargo.toml`, `crates/macaw-audio/Cargo.toml`, `crates/macaw-audio/src/lib.rs`,
`tests/fixtures/tone_440hz_16k.wav`

#### Tasks

1. Workspace raiz com membros `macaw-audio`, `macaw-asr`, `macaw-cli`
2. Gerar `tone_440hz_16k.wav` — 3 s, 16 kHz, mono, 440 Hz, determinístico
3. `cargo build` verde

#### TDD

```
test_fixture_tone_has_expected_properties:
  GIVEN o arquivo tests/fixtures/tone_440hz_16k.wav
  WHEN carregado via hound
  THEN sample_rate == 16000 AND channels == 1 AND samples.len() == 48000
  AND assert!(rms > 0.1)  // não é silêncio
```

#### Concurrency tests

`(none — single-threaded)` — criação de workspace e geração de fixture são
operações sequenciais de build, sem estado compartilhado.

#### Acceptance Criteria

- `cargo build --workspace` termina com exit code 0
- `cargo test -p macaw-audio` executa ≥ 1 teste e reporta 0 falhas
- `soxi -s tests/fixtures/tone_440hz_16k.wav` imprime exatamente `48000`

#### DoD

- [ ] Workspace compila sem warnings
- [ ] Fixture versionada em git (exceção explícita no `.gitignore`)
- [ ] Teste da fixture passa

---

## Phase T1: Captura de dois streams

### T1.1 — Captura dual via libpulse com source por stream

#### Objective

Capturar `mic` e `loopback` simultaneamente, em threads dedicadas, entregando
amostras por canal mpsc.

#### Why this step

**Ação:** implementar `capture.rs`.
**Raciocínio:** é a premissa central do M0 e a única já **provada por experimento**
(`m0-capture-probe-evidence.md`, experimento 6: 48.000 amostras em cada stream,
peak 0,250 e 1,000). Implementar primeiro converte a prova de conceito em código
testável, e destrava T2 e T5.

#### Evidence

`knowledge-base/discoveries/m0-capture-probe-evidence.md` § Experimento 6 e
§ Veredito para Q5.

#### Files to edit

`crates/macaw-audio/src/capture.rs`, `crates/macaw-audio/Cargo.toml`

#### Tasks

1. `CaptureConfig { source: String, sample_rate: u32, channels: u8 }`
2. `spawn_capture(cfg) -> Result<Receiver<Vec<i16>>, CaptureError>` — thread dedicada
3. `CaptureError` tipado: `SourceNotFound`, `ConnectionFailed`, `ReadFailed`
4. `list_sources()` — enumera sources, marcando quais são `.monitor`

#### TDD

```
test_capture_fails_with_typed_error_when_source_does_not_exist:
  GIVEN CaptureConfig com source "fonte-que-nao-existe-xyz"
  WHEN spawn_capture é chamado
  THEN retorna Err(CaptureError::SourceNotFound { .. })
  AND a mensagem contém o nome da source

test_list_sources_identifies_monitor_sources:
  GIVEN o servidor de áudio local
  WHEN list_sources() é chamado
  THEN existe ao menos uma source
  AND toda source cujo nome termina em ".monitor" tem is_monitor == true
```

#### Concurrency tests

```
test_two_captures_run_simultaneously_without_interference:
  GIVEN um null-sink virtual criado para o teste
  WHEN spawn_capture(mic) E spawn_capture(monitor) rodam por 2s
  THEN ambos os receivers entregam > 0 amostras
  AND a contagem de amostras difere em menos de 10%
  AND nenhuma thread entra em panic

test_capture_thread_terminates_cleanly_on_drop:
  GIVEN uma captura ativa
  WHEN o Receiver é dropado
  THEN a thread encerra em < 500ms sem vazar
```


> **Como estes testes são executados.** Cada um roda como `concurrent test` sob
> `cargo test -- --test-threads=8`, repetido 10× para expor ordenação não
> determinística. Estruturas com estado compartilhado são verificadas por
> `loom test` (model-checking de concorrência em Rust, que explora as
> intercalações possíveis). Contadores são validados por `atomic-counter
> invariant`. Threads de captura têm `cancellation propagation` verificada no
> drop. Onde há FFI, roda-se também sob `race detector` (ThreadSanitizer via
> `RUSTFLAGS=-Zsanitizer=thread`).

#### Acceptance Criteria

- Dois `spawn_capture` concorrentes por 2 s entregam ambos `> 0` amostras, com diferença de contagem `< 10%`
- `spawn_capture` com source `"fonte-que-nao-existe-xyz"` retorna `Err(CaptureError::SourceNotFound)` e a mensagem contém o nome informado
- Após `drop(receiver)`, a thread encerra em `< 500 ms` (medido)
- `list_sources()` marca `is_monitor == true` para toda source cujo nome termina em `.monitor`

#### DoD

- [ ] Testes de concorrência passam 10× consecutivas (sem flakiness)
- [ ] `CaptureError` cobre os três modos de falha
- [ ] Nenhuma alocação no laço de leitura (buffer reutilizado)

---

## Phase T2: VAD e roteamento de falante

### T2.1 — VAD por stream com parâmetros do peer

#### Objective

Detectar fala em cada stream independentemente, com janela de 512 amostras.

#### Why this step

**Ação:** integrar VAD por stream.
**Raciocínio:** o VAD é o **prior do roteamento de falante** — quando só o mic está
ativo, é o atendente; só o loopback, é o cliente. Sem ele, o rótulo de falante não
existe e RF-05 não é atendido. Vem depois de T1 porque consome os streams.

#### Evidence

Blueprint § Coverage Corner 4: `threshold=0.5`, `window_size=512`,
`sample_rate=16000` consistentes entre os dois exemplos do peer.

#### Files to edit

`crates/macaw-audio/src/vad.rs`

#### Tasks

1. `VadConfig` com defaults do peer (`threshold` 0,5; `min_speech` 0,25; `min_silence` 0,25 — U2)
2. `SpeechState { Silence, Speech }` por stream
3. Processar em janelas de exatamente 512 amostras

#### TDD

```
test_vad_detects_speech_in_tone_fixture:
  GIVEN a fixture de tom 440 Hz
  WHEN processada pelo VAD em janelas de 512
  THEN ao menos uma janela retorna SpeechState::Speech

test_vad_reports_silence_for_zero_signal:
  GIVEN 48000 amostras de zeros
  WHEN processadas
  THEN todas as janelas retornam SpeechState::Silence

test_vad_rejects_window_of_wrong_size:
  GIVEN uma janela de 256 amostras
  WHEN process_window é chamado
  THEN retorna Err(VadError::InvalidWindowSize { expected: 512, got: 256 })
```

#### Concurrency tests

```
test_vad_instances_are_independent_across_threads:
  GIVEN duas instâncias de Vad, uma por stream, em threads separadas
  WHEN ambas processam 1000 janelas simultaneamente
  THEN o estado de fala de uma não altera o da outra
  AND executar sob `cargo test -- --test-threads=8` 10× consecutivas produz
      resultado idêntico (sem race)
```


> **Como estes testes são executados.** Cada um roda como `concurrent test` sob
> `cargo test -- --test-threads=8`, repetido 10× para expor ordenação não
> determinística. Estruturas com estado compartilhado são verificadas por
> `loom test` (model-checking de concorrência em Rust, que explora as
> intercalações possíveis). Contadores são validados por `atomic-counter
> invariant`. Threads de captura têm `cancellation propagation` verificada no
> drop. Onde há FFI, roda-se também sob `race detector` (ThreadSanitizer via
> `RUSTFLAGS=-Zsanitizer=thread`).

#### Acceptance Criteria

- `process_window` com 256 amostras retorna `Err(VadError::InvalidWindowSize { expected: 512, got: 256 })`
- A fixture de 440 Hz produz ≥ 1 janela com `SpeechState::Speech`
- 48.000 amostras de zeros produzem 0 janelas com `SpeechState::Speech`

#### DoD

- [ ] Os três testes de comportamento passam
- [ ] O teste de concorrência passa 10× consecutivas
- [ ] Contador de alocações registra 0 por janela após aquecimento

### T2.2 — Rótulo de falante por roteamento

#### Objective

Atribuir falante pela origem do stream, sem modelo de diarização.

#### Why this step

**Ação:** derivar falante do par de estados de VAD.
**Raciocínio:** é o achado de maior alavancagem do projeto — no caso 1:1, que é o
dominante, a diarização **não precisa existir**. Custo zero, acurácia 100%.

#### Evidence

`PRD.md` § 5 RF-05; `ROADMAP.md` M0 DoD.

#### Files to edit

`crates/macaw-audio/src/vad.rs`

#### Tasks

1. `Speaker { Agent, Customer, Both, Neither }`
2. `route_speaker(mic: SpeechState, loop: SpeechState) -> Speaker`

#### TDD

```
test_speaker_routing_truth_table:
  GIVEN (Speech, Silence) THEN Speaker::Agent
  GIVEN (Silence, Speech) THEN Speaker::Customer
  GIVEN (Speech, Speech)  THEN Speaker::Both      // sobreposição
  GIVEN (Silence,Silence) THEN Speaker::Neither
```

#### Concurrency tests

`(none — single-threaded)` — `route_speaker` é função pura sem estado
compartilhado; recebe dois valores e retorna um.

#### Acceptance Criteria

- Os 4 pares de entrada da tabela-verdade produzem exatamente `Agent`, `Customer`, `Both` e `Neither`
- `cargo test test_speaker_routing_truth_table` reporta 0 falhas

#### DoD

- [ ] Função pura, sem I/O, testável isoladamente
- [ ] Os 4 casos cobertos por asserção explícita

### T2.3 — Detecção de sink mudo (falha silenciosa)

#### Objective

Detectar e sinalizar quando o sink está mudo ou com volume zero.

#### Why this step

**Ação:** consultar estado do sink na inicialização e periodicamente.
**Raciocínio:** o blueprint registrou como **edge case crítico** `[MEDIDO]`: com o
sink mudo, o loopback captura silêncio legítimo e **o cliente deixa de ser
transcrito sem erro visível**. Falha silenciosa é o pior modo de falha possível
aqui — é exatamente o que `.claude/rules/error-handling.md` § 1 proíbe.

#### Evidence

`m0-capture-probe-evidence.md` § Experimento 2: `Sink Mudo: sim | Volume: 0%`
produziu 44 bytes de WAV vazio.

#### Files to edit

`crates/macaw-audio/src/capture.rs`

#### Tasks

1. `SinkHealth { muted: bool, volume_pct: u8 }`
2. Emitir `Warning::SinkMuted` quando `muted || volume_pct == 0`

#### TDD

```
test_sink_health_reports_muted_state:
  GIVEN um sink com mute ativo
  WHEN check_sink_health é chamado
  THEN retorna SinkHealth { muted: true, .. }

test_warning_emitted_when_sink_is_silent:
  GIVEN SinkHealth { muted: true, volume_pct: 0 }
  WHEN evaluate_health é chamado
  THEN retorna Some(Warning::SinkMuted)
```

#### Concurrency tests

`(none — single-threaded)` — a consulta de estado do sink é uma chamada pontual à
API do servidor de áudio, sem estado compartilhado entre threads.

#### Acceptance Criteria

- Com o sink em mute, `check_sink_health()` retorna `SinkHealth { muted: true, .. }`
- Com `muted: true`, `evaluate_health()` retorna `Some(Warning::SinkMuted)`
- A execução do CLI com sink mudo imprime a string `SinkMuted` em stderr

#### DoD

- [ ] Warning aparece na saída do CLI, verificável por grep na saída

---

## Phase T3: Extração de features sem alocação

### T3.1 — log-mel 128 bins com buffers pré-alocados

#### Objective

Extrair log-mel compatível com o modelo emprestado, **sem alocar no caminho quente**.

#### Why this step

**Ação:** implementar `features.rs` com estado pré-alocado.
**Raciocínio:** o blueprint mediu que `parakeet-rs` aloca 5× por chunk. Copiar
repetiria o defeito que RNF-01/RNF-07 existem para medir. Esta é a diferença entre
reusar o padrão e reusar o problema.

#### Evidence

Blueprint § Coverage Corner 2 — tabela de alocações (`audio.rs` linhas 95-106, 99);
`models/m0-borrowed/config.json`: `features_size: 128`.

#### Files to edit

`crates/macaw-audio/src/features.rs`

#### Tasks

1. `FeatureCache { mel_basis, fft_plan }` — construído 1×, compartilhado via `Arc`
2. `StreamState { padded, input, output, scratch, hann }` — pré-alocados por stream
3. `extract(&mut self, chunk) -> &[f32]` — retorna slice do buffer interno

#### TDD

```
test_mel_output_has_128_bins:
  GIVEN um chunk de 512 amostras
  WHEN extract é chamado
  THEN output.len() % 128 == 0

test_extract_does_not_allocate_after_warmup:
  GIVEN StreamState inicializado e uma chamada de aquecimento
  WHEN extract é chamado 100× com allocation counter ativo
  THEN o contador de alocações permanece 0

test_stft_concentrates_power_at_expected_bin:
  GIVEN a fixture de 440 Hz
  WHEN extract é chamado
  THEN o bin de maior energia corresponde a 440 Hz ± 1 bin
```

#### Concurrency tests

```
test_feature_cache_is_shared_safely_across_streams:
  GIVEN um FeatureCache em Arc e dois StreamState independentes
  WHEN duas threads chamam extract() 1000× simultaneamente
  THEN os espectrogramas produzidos são idênticos aos produzidos sequencialmente
  AND nenhuma thread entra em panic
  AND executar sob `cargo test -- --test-threads=8` 10× produz resultado idêntico

test_stream_states_do_not_share_working_buffers:
  GIVEN dois StreamState com entradas diferentes
  WHEN processados concorrentemente
  THEN a saída de cada um corresponde à sua própria entrada (sem cross-talk)
```


> **Como estes testes são executados.** Cada um roda como `concurrent test` sob
> `cargo test -- --test-threads=8`, repetido 10× para expor ordenação não
> determinística. Estruturas com estado compartilhado são verificadas por
> `loom test` (model-checking de concorrência em Rust, que explora as
> intercalações possíveis). Contadores são validados por `atomic-counter
> invariant`. Threads de captura têm `cancellation propagation` verificada no
> drop. Onde há FFI, roda-se também sob `race detector` (ThreadSanitizer via
> `RUSTFLAGS=-Zsanitizer=thread`).

#### Acceptance Criteria

- Contador de alocações registra exatamente `0` em 100 chamadas após aquecimento
- `output.len() % 128 == 0` para qualquer chunk de entrada
- O bin de maior energia para a fixture de 440 Hz está a ≤ 1 bin do esperado
- `FeatureCache` compila sob `assert_impl_all!(FeatureCache: Send, Sync)`

#### DoD

- [ ] Teste de zero-alocação passa
- [ ] Os dois testes de concorrência passam 10× consecutivas
- [ ] `FeatureCache` é `Send + Sync` verificado em tempo de compilação

---

## Phase T4: Inferência e transcrição incremental

### T4.1 — Wrapper ONNX e laço de transcrição incremental

#### Objective

Alimentar o modelo emprestado com features e emitir texto incrementalmente.

#### Why this step

**Ação:** integrar `ort` com os três grafos do modelo.
**Raciocínio:** fecha o encanamento. Deliberadamente o **último** componente e o
mais isolado — M2 pode descartá-lo inteiro, e a fronteira de crate garante que
isso não contamine o DSP.

#### Evidence

`models/m0-borrowed/`: `encoder-model.onnx` (40 MB), `decoder_joint-model.onnx`
(70 MB), `nemo128.onnx` (140 KB), `vocab.txt` (8.193 tokens) `[MEDIDO]`.

#### Files to edit

`crates/macaw-asr/src/lib.rs`, `crates/macaw-cli/src/main.rs`

#### Tasks

1. Carregar os três grafos ONNX via `ort`
2. `transcribe_chunk(&mut self, features) -> Result<String, AsrError>`
3. CLI imprime texto incremental com rótulo de falante

#### TDD

```
test_asr_returns_typed_error_when_model_file_missing:
  GIVEN um caminho de modelo inexistente
  WHEN AsrEngine::load é chamado
  THEN retorna Err(AsrError::ModelNotFound { path })

test_vocab_loads_expected_token_count:
  GIVEN models/m0-borrowed/vocab.txt
  WHEN carregado
  THEN token_count == 8193
```

#### Failure scenarios

Ver § Failure scenarios abaixo.

#### Concurrency tests

```
test_asr_engine_is_not_shared_between_threads:
  GIVEN um AsrEngine
  WHEN se tenta movê-lo para duas threads simultaneamente
  THEN o compilador rejeita (AsrEngine é !Sync por design — sessão ONNX é
       stateful e um único consumidor a drena)
  AND o teste documenta essa restrição via assert_not_impl_any!(AsrEngine: Sync)
```


> **Como estes testes são executados.** Cada um roda como `concurrent test` sob
> `cargo test -- --test-threads=8`, repetido 10× para expor ordenação não
> determinística. Estruturas com estado compartilhado são verificadas por
> `loom test` (model-checking de concorrência em Rust, que explora as
> intercalações possíveis). Contadores são validados por `atomic-counter
> invariant`. Threads de captura têm `cancellation propagation` verificada no
> drop. Onde há FFI, roda-se também sob `race detector` (ThreadSanitizer via
> `RUSTFLAGS=-Zsanitizer=thread`).

#### Acceptance Criteria

- `AsrEngine::load("/caminho/inexistente")` retorna `Err(AsrError::ModelNotFound { path })` com o caminho na mensagem
- `vocab.txt` carregado reporta exatamente `8193` tokens
- A execução do CLI sobre a fixture imprime ≥ 1 linha de texto antes de terminar
- Cada linha impressa é prefixada por `[Agent]` ou `[Customer]`

#### DoD

- [ ] CLI transcreve a fixture e imprime texto
- [ ] Rótulo de falante acompanha cada segmento
- [ ] Restrição de `!Sync` documentada em teste

---

## Phase T5: Instrumentação e medição

### T5.1 — Contador de backlog

#### Objective

Medir amostras capturadas e ainda não processadas, continuamente.

#### Why this step

**Ação:** instrumentar a fila entre captura e processamento.
**Raciocínio:** RNF-03 exige backlog zero em 99,9% das amostras, e o blueprint
provou que **nenhum peer mede isso**. Sem instrumentação, o DoD de M0 não é
provável — seria afirmação sem evidência.

#### Files to edit

`crates/macaw-audio/src/metrics.rs`

#### TDD

```
test_backlog_counter_reports_zero_when_consumer_keeps_up:
  GIVEN produtor a 100 amostras/s e consumidor a 200/s
  WHEN roda por 1s
  THEN p99 do backlog == 0

test_backlog_counter_detects_growth_when_consumer_is_slow:
  GIVEN produtor a 200/s e consumidor a 100/s
  WHEN roda por 1s
  THEN backlog final > 0 AND is_growing() == true
```

#### Concurrency tests

```
test_backlog_counter_is_accurate_under_concurrent_producer_consumer:
  GIVEN um produtor e um consumidor em threads separadas por 5s
  WHEN o contador é lido 1000× durante a execução
  THEN nenhuma leitura retorna valor negativo ou impossível
  AND o total produzido menos o total consumido iguala o backlog final
  AND executar 10× consecutivas produz o mesmo invariante (sem race no contador)
```


> **Como estes testes são executados.** Cada um roda como `concurrent test` sob
> `cargo test -- --test-threads=8`, repetido 10× para expor ordenação não
> determinística. Estruturas com estado compartilhado são verificadas por
> `loom test` (model-checking de concorrência em Rust, que explora as
> intercalações possíveis). Contadores são validados por `atomic-counter
> invariant`. Threads de captura têm `cancellation propagation` verificada no
> drop. Onde há FFI, roda-se também sob `race detector` (ThreadSanitizer via
> `RUSTFLAGS=-Zsanitizer=thread`).

#### Acceptance Criteria

- Com produtor a 100/s e consumidor a 200/s, o p99 do backlog é exatamente `0`
- Com produtor a 200/s e consumidor a 100/s, `is_growing()` retorna `true` e o backlog final é `> 0`
- `metrics.backlog_percentiles()` retorna os três valores p50, p95 e p99

#### DoD

- [ ] p50/p95/p99 de backlog expostos e verificáveis
- [ ] Invariante produzido − consumido == backlog validado sob concorrência

### T5.2 — Medição de deriva de sincronia (R1)

#### Objective

Quantificar a deriva temporal entre os dois streams ao longo de ≥ 10 minutos.

#### Why this step

**Ação:** comparar contagem de amostras e timestamps dos dois streams no tempo.
**Raciocínio:** o `audio-dsp-engineer` identificou que mic e sink-monitor são
devices distintos, sem garantia de sincronia pela biblioteca. Minha medição
confirmou apenas contagem igual em 3 s — o que **não prova** ausência de deriva.
RF-05 depende disso, e assumir sincronia sem medir seria a falácia #7 de
`.claude/rules/asr-evidence-discipline.md` § 3.

#### Files to edit

`crates/macaw-audio/src/metrics.rs`, `crates/macaw-cli/src/main.rs`

#### TDD

```
test_drift_is_zero_for_identical_synthetic_streams:
  GIVEN dois streams sintéticos com a mesma cadência
  WHEN medidos por 1000 janelas
  THEN drift_ms.abs() < 1.0

test_drift_detects_injected_skew:
  GIVEN dois streams com 5% de diferença de cadência
  WHEN medidos por 1000 janelas
  THEN drift_ms cresce monotonicamente AND drift_ms > 10.0
```

#### Concurrency tests

```
test_drift_measurement_does_not_perturb_capture_threads:
  GIVEN duas capturas ativas e o medidor de drift lendo a cada 100ms
  WHEN roda por 30s
  THEN a contagem de amostras de cada stream é a mesma que sem o medidor
       ativo (tolerância 1%)
  AND o medidor nunca bloqueia a thread de captura (medido por latência
       máxima de escrita no canal)
```


> **Como estes testes são executados.** Cada um roda como `concurrent test` sob
> `cargo test -- --test-threads=8`, repetido 10× para expor ordenação não
> determinística. Estruturas com estado compartilhado são verificadas por
> `loom test` (model-checking de concorrência em Rust, que explora as
> intercalações possíveis). Contadores são validados por `atomic-counter
> invariant`. Threads de captura têm `cancellation propagation` verificada no
> drop. Onde há FFI, roda-se também sob `race detector` (ThreadSanitizer via
> `RUSTFLAGS=-Zsanitizer=thread`).

#### Acceptance Criteria

- O relatório imprime drift em ms, com CPU, duração da execução e nº de amostras
- A execução de validação tem duração medida `>= 600` segundos
- O drift é reportado como série temporal, não apenas valor final

#### DoD

- [ ] Relatório de drift anexado ao artefato de M0
- [ ] Se drift > 100 ms, U1 é respondida no plano e R1 escalado explicitamente

### T5.3 — Custo de CPU do VAD (R2)

#### Objective

Medir o custo por janela de 512 amostras.

#### Why this step

**Ação:** cronometrar `process_window`.
**Raciocínio:** o blueprint registrou custo `[DESCONHECIDO]` — nenhum peer declara.
Afirmar "VAD é barato" sem medir seria a falácia #8 (confundir tamanho de modelo
com custo de inferência).

#### TDD

```
test_vad_cost_is_measured_and_reported:
  GIVEN 1000 janelas de 512 amostras
  WHEN cronometradas
  THEN o relatório contém média E desvio-padrão
  AND o número de repetições é registrado
```

#### Concurrency tests

`(none — single-threaded)` — a cronometragem roda em thread única, sobre janelas
pré-carregadas em memória, justamente para isolar o custo do VAD de qualquer
contenção.

#### Acceptance Criteria

- O relatório imprime média, desvio-padrão e nº de repetições (`>= 1000`)
- O relatório declara o modelo de CPU obtido de `/proc/cpuinfo`
- O custo por janela é comparado com o orçamento de 32 ms (duração de áudio da janela), com o veredito explícito de quantas vezes real-time o VAD atinge

#### DoD

- [ ] Número publicado com rótulo `[MEDIDO]`, média ± desvio e nº de repetições

---

## Coverage Matrix

| Claim do Goal | Task(s) | Verificação |
|---|---|---|
| Captura mic e sistema em streams independentes | T1.1 | `test_two_captures_run_simultaneously_without_interference` |
| VAD por stream | T2.1 | `test_vad_detects_speech_in_tone_fixture` |
| Rótulo de falante por roteamento | T2.2 | `test_speaker_routing_truth_table` |
| log-mel sem alocação no caminho quente | T3.1 | `test_extract_does_not_allocate_after_warmup` |
| Transcrição incremental | T4.1 | Validação de integração (fase final) |
| Sem crescimento de backlog | T5.1 | `test_backlog_counter_reports_zero_when_consumer_keeps_up` |
| Sustenta ≥ 5 min sem crash | Fase final | Execução real cronometrada |
| Falha silenciosa detectada | T2.3 | `test_warning_emitted_when_sink_is_silent` |
| Deriva de sincronia conhecida | T5.2 | `test_drift_detects_injected_skew` + execução de 10 min |
| Custo do VAD conhecido | T5.3 | `test_vad_cost_is_measured_and_reported` |

**Cobertura: 10/10 claims mapeados = 100%.** Nenhuma lacuna.

## Failure scenarios (when I/O external)

M0 tem três fronteiras de I/O externo: servidor de áudio, sistema de arquivos
(modelo ONNX) e o runtime `ort`.

| Cenário | Comportamento exigido | Teste |
|---|---|---|
| Source de áudio inexistente | `Err(CaptureError::SourceNotFound)` com o nome citado | `test_capture_fails_with_typed_error_when_source_does_not_exist` |
| Servidor de áudio indisponível | `Err(CaptureError::ConnectionFailed)`, sem panic | teste negativo com socket inválido |
| Sink mudo / volume zero | `Warning::SinkMuted` visível; captura continua | `test_warning_emitted_when_sink_is_silent` |
| Arquivo de modelo ausente | `Err(AsrError::ModelNotFound { path })` | `test_asr_returns_typed_error_when_model_file_missing` |
| Modelo ONNX corrompido | `Err(AsrError::InvalidModel)`, mensagem com o arquivo | teste com bytes inválidos |
| Stream encerra no meio | Thread finaliza limpo; consumidor recebe `Err` de canal fechado | `test_capture_thread_terminates_cleanly_on_drop` |
| Consumidor mais lento que produtor | Backlog cresce e é **reportado**, nunca silenciado | `test_backlog_counter_detects_growth_when_consumer_is_slow` |

Nenhum destes cenários pode resultar em panic ou em silêncio — conforme
`.claude/rules/error-handling.md` § 2.

## Global Definition of Done

- [ ] Todos os testes de todas as fases passam
- [ ] `cargo clippy` sem warnings
- [ ] Zero alocações no caminho quente `[MEDIDO]`
- [ ] Chamada real de ≥ 5 min transcrita sem crash e com backlog p99 == 0
- [ ] Drift medido em execução de ≥ 10 min `[MEDIDO]`
- [ ] Custo do VAD medido com média ± desvio `[MEDIDO]`
- [ ] `CHANGELOG.md` atualizado
- [ ] Nenhum número sem rótulo de proveniência

## Final Phase: Integration Validation (MANDATORY)

### Execution

1. Iniciar o CLI capturando mic + monitor do sink em uso
2. Reproduzir áudio de fala em português no sistema por ≥ 5 min
3. Falar ao microfone intercalando com o áudio reproduzido
4. Registrar: texto transcrito, rótulos de falante, backlog p50/p95/p99, drift, RTFx

### Acceptance Criteria

- Processo sobrevive ≥ 5 min sem crash
- Backlog p99 == 0
- Rótulo de falante alterna corretamente entre `Agent` e `Customer`
- Texto aparece incrementalmente
- Todos os números com rótulo `[MEDIDO — encanamento apenas]`

### If Validation Fails

Registrar o modo de falha, **não contorná-lo**. Se o backlog crescer, o gargalo é
identificado por profiling antes de qualquer otimização. Se o drift inviabilizar o
roteamento, U1 é respondida e R1 escala para decisão de produto — nunca se assume
sincronia.

## Related

- Blueprint: `knowledge-base/discoveries/blueprints/m0-walking-skeleton-blueprint.md`
- Evidência: `knowledge-base/discoveries/m0-capture-probe-evidence.md`
- Milestone: `ROADMAP.md` M0
- Contrato de evidência: `.claude/rules/asr-evidence-discipline.md`
