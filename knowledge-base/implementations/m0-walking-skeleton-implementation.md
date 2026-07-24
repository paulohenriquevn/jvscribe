# Implementação — M0 Walking Skeleton

> 2026-07-24 · plano `knowledge-base/plans/m0-walking-skeleton-plan.md` (SHIPPABLE)
> branch `develop` · rotulagem conforme `.claude/rules/asr-evidence-discipline.md`

## Resultado

**34 testes passando, zero falhas, clippy limpo em todo o workspace.** O
encanamento do walking skeleton está provado de ponta a ponta com evidência
medida: captura dual → VAD → roteamento → features → encoder ONNX de 600M.

```
$ cargo run -p macaw-cli
fixture: 48000 amostras (3.00s a 16000 Hz)
VAD: 93/93 janelas com fala
encoder 600M: saída [1, 1024, 12] em 126ms para 2.98s de áudio (RTF 0.04 — [MEDIDO — encanamento apenas])
pipeline completo: captura → VAD → features → encoder ✓
```

## Tasks e wiring triad

| Task | Entrega | Caller de produção | Teste de integração | Métrica de runtime |
|---|---|---|---|---|
| T0.1 | Workspace + fixture | — | `fixture_test` | — |
| T1.1 | Captura dual libpulse | `macaw-cli live` | `capture_test` (6) | `active_capture_threads()` |
| T2.1 | VAD por stream | `macaw-cli` ambos modos | `vad_detection_test` (3) | — |
| T2.2 | Roteamento de falante | `macaw-cli live` | `vad_speaker_routing_test` | — |
| T2.3 | Detecção de sink mudo | `capture.rs` | `capture_test` | `Warning::SinkMuted` |
| T3.1 | log-mel zero-alocação | `macaw-cli` ambos modos | `features_*` (5) | contador `stats_alloc` |
| T4.1 | Encoder + forward pass | `macaw-cli fixture` | `forward_pass_test` | RTF `[MEDIDO]` |
| T5.1 | Contador de backlog | `macaw-cli live` | `metrics_test` (5) | p50/p95/p99 |
| T5.2 | Deriva entre streams | `macaw-cli`/probe | `metrics_test` | série temporal |
| T5.3 | Custo do VAD | teste | `vad_cost_test` | 3,49 µs/janela |

## Evidência medida (rótulos de proveniência)

| Métrica | Valor | Rótulo |
|---|---|---|
| Captura simultânea mic + loopback | 48.000 amostras/stream em 3s, ambos com sinal | `[MEDIDO]` |
| Fidelidade do loopback | tom 440 Hz → bin 441,4 Hz (erro 0,3%) | `[MEDIDO]` |
| Deriva entre streams | offset de partida 1,44s constante; drift em regime ≈ 0 | `[MEDIDO]` |
| log-mel no caminho quente | **0 alocações** após aquecimento (100 chamadas) | `[MEDIDO]` via `stats_alloc` |
| Custo do VAD | **3,49 ± 0,36 µs/janela** = 9165× real-time (n=5000) | `[MEDIDO]` |
| Encoder 600M carrega | 2,19s (pesos reais de 2,3 GB) | `[MEDIDO]` |
| Forward pass do encoder | `[1,1024,12]` em 126ms para 2,98s de áudio | `[MEDIDO — encanamento apenas]` |
| Encerramento limpo de thread | contador volta a zero em < 500ms após drop | `[MEDIDO]` |

## Achados de infraestrutura resolvidos por evidência (não contorno)

1. **glibc**: o binário que o `ort` baixa exige glibc ≥ 2.38; o ambiente tem 2.35.
   Solução: build manylinux 1.23 do ONNX Runtime via `load-dynamic`
   (`scripts/setup_onnxruntime.sh`, `ORT_DYLIB_PATH` em `.cargo/config.toml`).
2. **ABI**: pedir feature `api-24` a um dylib 1.23 causava **hang** no
   `commit_from_file`. `api-23` casa a ABI — modelo de 140 KB passou de travar para
   carregar em 23 ms.
3. **Pesos externos**: `encoder-model.onnx` referencia
   `encoder-model.onnx.data` (2,3 GB), que precisou de download robusto via
   `hf` (curl truncava). `scripts/setup_model.sh`.
4. **Otimização de grafo**: com `Level3`, o encoder não abria em 180s. Desabilitada
   em M0 (é escopo de M6); load ficou instantâneo.
5. **Teste de thread frágil**: `/proc/self/status` é global do processo e ruidoso
   sob execução paralela. Substituído por `active_capture_threads()`, contador
   próprio determinístico — que também é observabilidade de produção.
6. **Metodologia de drift**: o teste original media contagem total desde o spawn,
   conflacionando offset de partida com paridade de taxa. Corrigido para medir taxa
   em regime após warmup, guiado pelo experimento em `m0-drift-evidence.md`.
7. **Bugs de wiring do CLI** (surfaçados pelo smoke test de integração):
   `record_consumed` não era chamado (backlog crescia por falta de instrumentação,
   não por overflow); `@DEFAULT_SINK@.monitor` literal não resolvia — corrigido via
   `list_sources()`.

## DoD de M0 — nota de honestidade

O critério do ROADMAP *"chamada real de ≥ 5 min transcrita em tempo real sem
crescimento de backlog"* é **estruturalmente impossível com o modelo emprestado**
(600M offline) — e essa impossibilidade é a premissa do projeto. Análise completa e
proposta de correção do DoD em
`knowledge-base/discoveries/m0-borrowed-model-dod-analysis.md`. O que M0 prova é o
**encanamento**: a fronteira features→modelo funciona sobre dados reais. A
transcrição real-time sustentada pertence a M5/M6 (modelo próprio streaming).

## Limites

- Ambiente único (PulseAudio nativo, Ubuntu 22.04, glibc 2.35). PipeWire/macOS/
  Windows não cobertos — Q-01/M8.
- VAD é heurística energia+ZCR, não Silero — troca prevista para M1 (mesmo traço
  `SpeechDetector`).
- Decode TDT completo (encoder→texto) não implementado — BLOQUEADO POR M2.
- Modelo emprestado e ONNX Runtime não versionados (grandes; scripts de setup).
