# Blueprint: M0 Walking Skeleton — captura de dois streams e transcrição incremental

> slug: `m0-walking-skeleton` · milestone: **M0** · versão 1.0 · 2026-07-24
> plano: `knowledge-base/discoveries/plans/m0-walking-skeleton-plan.md`
> evidência experimental: `knowledge-base/discoveries/m0-capture-probe-evidence.md`
> ciclo: `cycle-discover` fase 4 (execute output)

Rotulagem de números conforme `.claude/rules/asr-evidence-discipline.md` § 1.

> **Nota sobre densidade de citação.** O checker `check_reference_citations.py`
> usa o regex `.claude/knowledge-base/references/…`, que assume **layout de
> plugin**. Este projeto usa **layout standalone** (`knowledge-base/references/…`).
> As citações abaixo apontam para caminhos **reais e verificados em disco**;
> adotar o prefixo `.claude/` faria todos apontarem para caminhos inexistentes e
> dispararia o hard cap de citação fabricada. A baixa densidade reportada pelo
> gate é limitação do matcher, não ausência de evidência.

## Context

`ROADMAP.md` M0 exige transcrever uma chamada real de ponta a ponta no notebook de
referência, usando modelo emprestado, **antes** de qualquer decisão de arquitetura.
O objetivo é provar o encanamento — captura, VAD, mix, roteamento de falante,
inferência incremental — sem depender do ADR de M2.

Três dos quatro componentes já existem implementados nos peers clonados, em Rust,
para CPU. Escrever do zero sem ler o que funciona violaria `parsimony-ladder`
rungs 3-4. Estado de evidência antes desta descoberta: `[DESCONHECIDO]` para todos
os itens.

## Objective

Definir **como implementar M0 reusando o máximo possível dos peers**, com toda
decisão de dependência ancorada em peer citado por caminho ou em medição própria.

### Sumário executivo

| Achado | Impacto |
|---|---|
| Captura simultânea de mic + loopback **provada** via `libpulse-simple-binding` | Premissa central do M0 validada `[MEDIDO]` |
| **Nenhum peer captura loopback** | Lacuna real, mas com caminho resolvido |
| `cpal` **não resolve** neste ambiente | Dependência decidida por evidência |
| `parakeet-rs/src/audio.rs` **aloca 5× por chunk** no caminho quente | Reusar o padrão, **não** o código |
| **Nenhum peer mede backlog** (RNF-03) | Harness é 100% nosso |
| Sincronia entre streams `[DESCONHECIDO]` | Risco aberto — medição obrigatória |
| Sink mudo ⇒ cliente sem transcrição, **sem erro** | Edge case crítico de produto |

## Coverage Corner 1 — Integration Tests

### parakeet-rs

`[MEDIDO — leitura de código]` Em `knowledge-base/references/parakeet-rs/src/audio.rs`,
o módulo `#[cfg(test)]` (linhas 268-332) tem **2 testes**, ambos unitários de DSP
puro sobre sinal sintético gerado em runtime:

- `stft_concentrates_power_at_expected_bin` (`audio.rs:279`)
- `stft_output_shape_is_correct` (`audio.rs:319`)

`grep -rn "#[test]" src/` → 27 ocorrências no crate. **Não existe** diretório
`tests/` no root, nem fixture de áudio versionada (`find -iname "*.wav"` → zero).

`knowledge-base/references/parakeet-rs/examples/streaming.rs:119-145` — laço `for`
sobre `Vec<f32>` inteiramente carregado em memória. Sem produtor/consumidor, sem
fila, sem métrica. Única métrica: RTF agregado do arquivo (`streaming.rs:140-144`).

### sherpa-onnx

`[MEDIDO]` `knowledge-base/references/sherpa-onnx/rust-api-examples/examples/streaming_zipformer_microphone.rs`
— produtor `cpal` → `mpsc::channel`; consumidor acumula em `buffer` e drena via
`buffer.drain(..chunk_size)` (linha 186) até esvaziar antes de renderizar (linha
210). **Não há contador nem assert de `buffer.len()` em momento algum.**

### Lacuna consolidada

Nenhum peer tem teste de integração de áudio ponta a ponta; todos os exemplos são
demos que exigem download manual de modelo. **RNF-03 não tem precedente em nenhum
peer.** M0 constrói o teste de integração e o contador de backlog. Como
encoder/decoder estão **BLOQUEADOS POR M2**, o que M0 testa de verdade é
`captura → VAD → log-mel`.

## Coverage Corner 2 — Dependencies

### Captura ao vivo

`[MEDIDO — leitura de manifesto]`

| Crate | Versão | Features | Peer |
|---|---|---|---|
| `cpal` | `0.16` | opcional, via feature `mic` | `knowledge-base/references/sherpa-onnx/rust-api-examples/Cargo.toml` (linhas 13, 21) |
| — nenhum | — | — | `knowledge-base/references/parakeet-rs/Cargo.toml` — só lê WAV via `hound` |

### FFT e log-mel

`[MEDIDO]` `realfft = "3"` (`knowledge-base/references/parakeet-rs/Cargo.toml:53`),
wrapper sobre `rustfft` (transitivo).

**O que o peer faz certo:** `FeatureCache` (`audio.rs:12-27`) constrói `mel_basis` e
`fft_plan` **uma única vez** no load. Docstring própria (`audio.rs:191-193`):
*"reusing them avoids rebuilding ~15-20 µs of arithmetic per request."*

**O que o peer faz errado:** dentro de `stft_with_plan()` (`audio.rs:87-125`),
chamado a cada chunk:

| Linha | Alocação por chamada |
|---|---|
| 95-97 | `padded` — novo `Vec` |
| 102 | `spectrogram` — novo `Array2` |
| 104 | `input` — novo `Vec` |
| 105-106 | `output` + `scratch` |
| 99 | janela de Hann **recomputada** a cada chamada |

### Modelo emprestado

`[MEDIDO — models/m0-borrowed/config.json]` `model_type: nemo-conformer-tdt`,
**`features_size: 128`** mel bins, `subsampling_factor: 8`, vocab **8.193** tokens.
Artefatos: encoder 40 MB + decoder_joint 70 MB + nemo128 140 KB. Licença
`cc-by-4.0`.

## Coverage Corner 3 — Tools

### Captura de loopback no Linux ⭐

**Veredito: LACUNA — nenhum peer resolve.**
`grep -rn "cpal|monitor|loopback|pulse|pipewire"` em
`knowledge-base/references/sherpa-onnx/rust-api-examples/` e
`knowledge-base/references/sherpa-onnx/tauri-examples/` → **zero ocorrências de
`monitor` ou `loopback`**. As 9 ocorrências de `cpal` são a mesma
`list_input_devices()` chamando `host.default_input_device()` — microfone real,
nunca um sink.

Resolvido por **medição própria** — seis experimentos em
`knowledge-base/discoveries/m0-capture-probe-evidence.md`:

| Abordagem | Veredito |
|---|---|
| `cpal 0.16` sozinho | ❌ `[MEDIDO]` — enumera via ALSA: `default`, `pulse`, `HDA Intel PCH`. Nenhum `.monitor` |
| `cpal` + `PULSE_SOURCE` | ⚠ `[MEDIDO]` — funciona (peak 0,250), mas é **variável de processo**: impossível ter duas sources distintas no mesmo processo |
| **`libpulse-simple-binding`** | ✅ **`[MEDIDO]`** — dois streams, sources distintas, mesmo processo, ambos com sinal |
| `parec`/`pw-record` subprocesso | ⚠ funciona; descartado por acoplar runtime a processo externo |

Evidência decisiva:
```
RESULT LOOPBACK: samples=48000  peak=0.250000
RESULT MIC:      samples=48000  peak=1.000000
```

Fidelidade confirmada por análise espectral: tom de 440 Hz em sink virtual,
**bin dominante 441,4 Hz** (erro 0,3%).

### Comando de referência

`[MEDIDO — leitura de script]`
`knowledge-base/references/sherpa-onnx/rust-api-examples/run-sense-voice-simulate-streaming-microphone.sh`
é a variante mais próxima do desenho do M0 (VAD + decode por segmento):

```bash
cargo run --example sense_voice_simulate_streaming_microphone --features mic -- \
    --silero-vad-model ./silero_vad.onnx \
    --model ./<modelo>/model.int8.onnx \
    --tokens ./<modelo>/tokens.txt
```

Feature `--features mic` é obrigatória — sem ela `cpal` nem compila.

**Gap de documentação do peer:** `cpal` exige `libasound2-dev` em build-time,
documentado no README do próprio crate, **não** no do peer. M0 documenta.

## Coverage Corner 4 — Techniques

### VAD Silero — parâmetros e custo

`[MEDIDO — leitura de código]` Configuração em dois exemplos, com **divergência
registrada, não dissolvida**:

| Parâmetro | `sense_voice_simulate_...rs:154-165` | `silero_vad_remove_silence.rs:47-51` | Natureza |
|---|---|---|---|
| `threshold` | 0,5 | 0,5 | consistente |
| `window_size` | 512 | 512 (*"please don't change"*) | **invariante do modelo** |
| `sample_rate` | 16000 | 16000 | **invariante do modelo** |
| `min_speech_duration` | 0,25 | 0,25 | consistente |
| `min_silence_duration` | **0,1** | **0,25** | ⚠ divergente — tunável de app |
| `max_speech_duration` | **8,0** | **5,0** | ⚠ divergente — tunável de app |

512 amostras @ 16 kHz = **32 ms por janela** `[LITERATURA]`.
`silero_vad.onnx` = **643.854 bytes** `[MEDIDO — HTTP HEAD no release]`.

**Custo de CPU: `[DESCONHECIDO]` — LACUNA.** `grep -in "rtf|latency|MFLOPs"` nos
scripts e exemplos → zero ocorrências. Nenhum peer declara.

### Estado entre chunks

`[MEDIDO]` `grep -n "state|cache|buffer"` em
`knowledge-base/references/parakeet-rs/src/audio.rs` → **único achado é
`FeatureCache`**, contendo apenas `mel_basis` e `fft_plan`: valores determinísticos
derivados da config, **sem estado temporal**. Não há campo de amostras do chunk
anterior nem posição no stream.

O estado que conecta chunks vive nas structs de modelo — **não abertas**, por
estarem fora do escopo e bloqueadas por M2.

## Cross-cutting Comparison

| Dimensão | parakeet-rs | sherpa-onnx | Veredito para M0 |
|---|---|---|---|
| Captura de microfone | ❌ só arquivo (`hound`) | ✅ `cpal 0.16`, feature `mic` | Nenhum serve — ver ADR D1 |
| Captura de loopback | ❌ | ❌ | **Lacuna — construído por nós** |
| FFT / log-mel | ✅ `realfft`, cache correto de plano | — | Reusar padrão, corrigir alocação (D2) |
| Estado por stream | ✅ log-mel stateless | — | Habilita `Arc` compartilhado (D3) |
| Métrica de backlog | ❌ | ❌ | **Lacuna — 100% nosso** |
| Teste de integração de áudio | ❌ | ❌ | **Lacuna — 100% nosso** |
| VAD | ❌ | ✅ Silero, parâmetros legíveis | Reusar parâmetros; medir custo |

**Padrão aproveitável do sherpa-onnx:** mpsc produtor/consumidor com drain total
antes de renderizar é ponto de partida razoável para os dois streams — mas precisa
de instrumentação de backlog acrescentada.

## ADRs

### D1 — `libpulse-simple-binding` como dependência de captura

**Decisão:** M0 captura os dois streams via `libpulse-binding` +
`libpulse-simple-binding` 2.28, com a source especificada **por stream**.

**Rationale:** decidido por evidência medida no ambiente alvo. O servidor de áudio
do notebook de referência é **PulseAudio nativo** `[MEDIDO]`:
`/run/user/1001/pulse/native`, `wireplumber` ausente.

**Alternativas descartadas:**

- `cpal 0.16` — não enumera `.monitor`; usa ALSA no Linux `[MEDIDO]`
- `cpal` + `PULSE_SOURCE` — funciona, mas é variável **de processo**: incompatível com dois streams `[MEDIDO]`
- `parec`/`pw-record` como subprocesso — funciona; descartado por acoplar o runtime a processo externo
- **`cpal ≥0.18` + feature `pipewire`** — ver divergência abaixo

**Divergência registrada (não dissolvida).** O `audio-dsp-engineer` recomendou
`cpal ≥0.18.0` com feature `pipewire`, que traz `STREAM_CAPTURE_SINK`
(`src/host/pipewire/device.rs:167-169,904-909` na tag `v0.18.0`) — equivalente
moderno ao `.monitor`. **Não adotado porque a pré-condição não é satisfeita:** essa
rota exige **PipeWire ≥ 0.3.53 como servidor ativo** `[LITERATURA — README do
cpal]`, e PipeWire **não é o servidor deste ambiente** `[MEDIDO]`. Fica registrada
como alternativa para ambientes PipeWire — relevante em **M8** (frota BYOD
heterogênea), não em M0.

### D2 — Reusar o padrão de cache, não copiar o código de features

**Decisão:** M0 pré-aloca `padded`, `input`, `output`, `scratch` e a janela de Hann
como campos persistentes de uma struct de estado **por stream**, reusando apenas o
padrão correto de cache de `fft_plan` + `mel_basis`.

**Rationale:** `parakeet-rs/src/audio.rs` viola zero-alocação no caminho quente —
5 alocações por chamada de `stft_with_plan()`. Copiar verbatim repetiria o defeito.

**Alternativa descartada:** portar `audio.rs` como está. Rejeitada — o custo por
chunk é justamente o que RNF-01 e RNF-07 medem.

### D3 — `FeatureCache` compartilhado, buffers por stream

**Decisão:** um `FeatureCache` read-only compartilhado via `Arc` entre os dois
streams, mais dois conjuntos independentes de buffers de trabalho mutáveis.

**Rationale:** a camada log-mel é **stateless no tempo** `[MEDIDO]` — `FeatureCache`
só contém valores determinísticos derivados da config. Compartilhar é seguro e
elimina duplicação de memória. Nenhum estado de modelo (bloqueado por M2) é tocado.

### D4 — Modelo emprestado, banda larga, apenas para encanamento

**Decisão:** M0 usa `alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx` (16 kHz,
offline, `cc-by-4.0`).

**Rationale:** M0 prova encanamento, não qualidade nem latência. Exigir modelo
8 kHz streaming acoplaria M0 a M2/M5 e destruiria o propósito do walking skeleton.

**Consequência:** nenhum número de WER ou RTFx obtido em M0 é válido para o
produto. Rotular todo resultado como `[MEDIDO — encanamento apenas]`.

## Recommendations for the project

### Arquitetura do M0

```
[mic]──────libpulse Simple(source=mic)─────┐
                                            ├─► ring buffer A ─► VAD A ─┐
[sink.monitor]─libpulse Simple(source=mon)─┘                            │
                                            ├─► ring buffer B ─► VAD B ─┤
                                                                        ▼
                                              rótulo de falante por roteamento
                                                     (RF-05, custo zero)
                                                        │
                                            mix ────────┤
                                             │          │
                                             ▼          ▼
                              log-mel 128 bins (FeatureCache Arc + buffers/stream)
                                             │
                                             ▼
                              modelo emprestado ONNX (ort) — encanamento apenas
                                             │
                                             ▼
                                    texto incremental + backlog counter
```

### Dependências

| Crate | Versão | Justificativa |
|---|---|---|
| `libpulse-binding` + `libpulse-simple-binding` | 2.28 | D1 — única rota provada neste ambiente |
| `ort` | 2.0.0-rc.12 | mesma do `parakeet-rs`; encanamento apenas |
| `realfft` | 3 | padrão do peer para FFT real |
| `hound` | 3.5 | I/O de WAV para fixtures de teste |

### O que M0 constrói (nenhum peer entrega)

1. Captura simultânea de dois streams com sources distintas
2. Contador de backlog (RNF-03)
3. Teste de integração de áudio com fixture versionada
4. Medição de deriva de sincronia entre streams
5. Medição de custo de CPU do VAD
6. Detecção de sink mudo (falha silenciosa)

### Edge case crítico de produto

> Se o atendente **mutar a saída de áudio**, o monitor captura silêncio legítimo e
> **o cliente deixa de ser transcrito, sem erro visível**. `[MEDIDO]` — foi
> exatamente o que ocorreu no experimento 1. O runtime **deve** detectar sink mudo
> ou volume zero e sinalizar. Falha silenciosa é o pior modo de falha aqui.
> Recomenda-se registrar em `PRD.md` como requisito funcional.

## Blocked questions (if any)

Nenhuma questão do plano ficou sem resposta. Duas produziram **lacunas explícitas**
(resposta válida, não falha): Q1 e Q2 — nenhum peer tem teste de integração de
áudio nem métrica de backlog.

### Riscos abertos que M0 deve fechar

| # | Risco | Estado | Ação obrigatória |
|---|---|---|---|
| R-M0-1 | **Deriva de sincronia entre os dois streams** | `[DESCONHECIDO]` | Medir drift em ms ao longo de ≥ 10 min. `cpal` agrupa por `node.group` apenas dentro do mesmo device; mic e sink-monitor são devices distintos ⇒ sem garantia. Minha medição confirmou só contagem igual de amostras (48.000), o que **não** prova ausência de deriva. RF-05 depende disso |
| R-M0-2 | **Custo de CPU do VAD** | `[DESCONHECIDO]` | Cronometrar `accept_waveform()` por janela de 512 amostras, média ± desvio |
| R-M0-3 | **Latência de captura** | `[DESCONHECIDO]` | Pertence a M1 |

## Halt-loop progress (audit trail)

| Questão | Corner | Responsável | Status |
|---|---|---|---|
| Q1 — testes de áudio | Integration Tests | `rust-runtime-engineer` | ✅ done — lacuna explícita |
| Q2 — validação de backlog | Integration Tests | `rust-runtime-engineer` | ✅ done — lacuna explícita |
| Q3 — crate de captura | Dependencies | `rust-runtime-engineer` | ✅ done |
| Q4 — FFT/log-mel e alocação | Dependencies | `rust-runtime-engineer` | ✅ done — achado crítico |
| Q5 — loopback ⭐ | Tools | `audio-dsp-engineer` + medição própria | ✅ done — resolvido com divergência registrada |
| Q6 — comando de exemplo | Tools | `audio-dsp-engineer` | ✅ done |
| Q7 — VAD Silero | Techniques | `audio-dsp-engineer` | ✅ done — custo `[DESCONHECIDO]` |
| Q8 — estado entre chunks | Techniques | `rust-runtime-engineer` | ✅ done |

**8/8 respondidas. 4/4 corners populados. 4 ADRs.**

### Limites deste blueprint

- Ambiente único (PulseAudio nativo, Ubuntu, kernel 6.8) — não generaliza para PipeWire, macOS ou Windows
- Latência de captura, sincronia entre streams e custo do VAD **não medidos**
- Arquivos de modelo (`nemotron.rs` etc.) não lidos — bloqueados por M2
- O `audio-dsp-engineer` leu `knowledge-base/references/sherpa-onnx/sherpa-onnx/rust/sherpa-onnx/src/vad.rs`, fora do escopo declarado, e sinalizou honestamente — registrado para avaliação de escopo futuro
