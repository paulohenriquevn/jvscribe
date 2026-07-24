---
slug: m0-walking-skeleton
milestone_id: M0
version: 1.0
owner: rust-runtime-engineer + audio-dsp-engineer
created_at: 2026-07-24
cycle: cycle-discover (phase 1)
---

# Discovery Plan — M0 Walking Skeleton: captura de dois streams e transcrição incremental

## 1. Context

`ROADMAP.md` M0 exige transcrever uma chamada real de ponta a ponta no notebook de
referência, usando um modelo emprestado, **antes** de qualquer decisão de
arquitetura. O objetivo é provar o encanamento — captura, VAD, mix, roteamento de
falante, inferência incremental — sem depender do ADR de M2.

O que motiva investigar antes de escrever código: três dos quatro componentes de M0
já existem implementados nos peers clonados, em Rust, para CPU. Escrever do zero
sem ler o que já funciona violaria a `parsimony-ladder` (rungs 3 e 4) e a Regra
Inquebrável 9.

Estado de evidência hoje: `[DESCONHECIDO]` para todos os itens abaixo. Nenhum
número de latência, throughput ou consumo de CPU foi medido neste projeto.

## 2. Objective

Produzir um blueprint que responda **como implementar M0 reusando o máximo possível
dos peers**, com critérios mensuráveis:

- Toda decisão de dependência tem um peer que a usa em produção, citado por caminho
- A captura de loopback no Linux tem caminho técnico identificado e testado por alguém
- O VAD escolhido tem custo de CPU conhecido `[LITERATURA]` ou `[MEDIDO]`
- Nenhuma recomendação depende de decisão bloqueada por M2

## 3. Scope

### In scope

| Peer | Subdiretórios investigados |
|---|---|
| `knowledge-base/references/parakeet-rs/` | `src/`, `examples/`, `Cargo.toml` |
| `knowledge-base/references/sherpa-onnx/` | `rust-api-examples/`, `scripts/silero_vad/`, `tauri-examples/` |
| `knowledge-base/references/moonshine/` | `examples/`, `python/` |

### Out of scope (explícito)

| Excluído | Razão |
|---|---|
| `parakeet-rs/src/model_*.rs`, `decoder*.rs` | Dependem da arquitetura — **BLOQUEADO POR M2** |
| `sherpa-onnx/android/`, `ios-*`, `wasm*`, `flutter*`, `nodejs*`, `dart-api*` | Plataformas fora do escopo do M0 (desktop Linux primeiro) |
| `sherpa-onnx/kotlin-api-examples/`, `swift-api-examples/`, `c-api-examples/` | Idem — Rust é a linguagem alvo |
| `moonshine/android/`, `swift/`, `micro/`, `wasm/` | Idem |
| `moonshine/core/` | Runtime C++ próprio; relevante em M6, não em M0 |
| `icefall/`, `lhotse/`, `funasr/`, `tract/`, `vibeasr-cpp/` | Não tocam captura ao vivo; pertencem a M2/M3/M6 |

## 4. ADRs — decisões sobre COMO investigar

### ADR-01 — Investigar apenas o caminho Linux/PipeWire no M0

**Decisão:** a captura de loopback será investigada só para Linux nesta descoberta.

**Rationale:** M0 roda no notebook de referência, que é Linux. Windows (WASAPI) e
macOS (ScreenCaptureKit) são três implementações nativas distintas; investigar as
três agora triplica o custo sem servir ao DoD de M0.

**Alternativa descartada:** investigar as três de uma vez. Rejeitada porque a
portabilidade é problema de M8 (frota BYOD), e antecipá-la viola YAGNI.

### ADR-02 — Time-budget por peer

| Peer | Budget | Justificativa |
|---|---|---|
| `parakeet-rs` | 3h | Menor repo (1,3 MB) e o mais próximo do alvo |
| `sherpa-onnx` | 3h | Grande; investigação restrita a `rust-api-examples/` |
| `moonshine` | 1h | Só para comparar estratégia de captura |

**Stop condition por questão:** se após 45 min uma questão não tiver resposta com
citação de caminho, marcar `blocked` com o motivo e seguir. Não estender.

### ADR-03 — Aceitar modelo emprestado banda larga no M0

**Decisão:** M0 usa `alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx`, que é
16 kHz e offline.

**Rationale:** M0 prova encanamento, não qualidade nem latência. Exigir modelo
8 kHz streaming acopla M0 a M2/M5 e destrói o propósito do walking skeleton.

**Consequência registrada:** nenhum número de WER ou RTFx medido em M0 é válido
para o produto. Rotular todo resultado de M0 como `[MEDIDO — encanamento apenas]`.

## 5. Research questions

**Budget: 8 questões · 2 por corner · dentro do limite de 5-10 e ≤ 3 por corner.**

### Corner A — Integration tests

**Q1.** Como `parakeet-rs` testa o caminho de áudio de ponta a ponta? Existe teste
que exercite decodificação a partir de arquivo sem depender de modelo baixado?
→ *Método:* `Read knowledge-base/references/parakeet-rs/src/audio.rs`; `Grep -rn "#\[test\]" knowledge-base/references/parakeet-rs/src/`
→ *Resposta esperada:* lista de testes existentes + se há fixture de áudio versionada

**Q2.** Os exemplos de streaming dos peers validam ausência de crescimento de
backlog, ou só imprimem texto? Qual o critério de parada deles?
→ *Método:* `Read knowledge-base/references/parakeet-rs/examples/streaming.rs`; `Read knowledge-base/references/sherpa-onnx/rust-api-examples/examples/streaming_zipformer_microphone.rs`
→ *Resposta esperada:* trecho que mostra o laço de consumo e o tratamento de fila

### Corner B — Dependencies

**Q3.** Qual crate cada peer usa para captura de microfone ao vivo, em que versão, e
com quais features?
→ *Método:* `Read knowledge-base/references/sherpa-onnx/rust-api-examples/Cargo.toml`; `Read knowledge-base/references/parakeet-rs/Cargo.toml`
→ *Resposta esperada:* tabela crate → versão → features → peer que usa

**Q4.** Qual a cadeia de dependências para FFT/log-mel em Rust nos peers, e ela
evita alocação no caminho quente?
→ *Método:* `Grep -n "realfft\|rustfft\|mel" knowledge-base/references/parakeet-rs/Cargo.toml knowledge-base/references/parakeet-rs/src/audio.rs`
→ *Resposta esperada:* crate escolhido + evidência de buffer reutilizado ou não

### Corner C — Tools

**Q5.** Como se captura o **áudio do sistema** (loopback) no Linux — qual API,
qual crate, e algum peer faz isso ou todos só capturam microfone?
→ *Método:* `Grep -rn "cpal\|monitor\|loopback\|pulse\|pipewire" knowledge-base/references/sherpa-onnx/rust-api-examples/ knowledge-base/references/sherpa-onnx/tauri-examples/`
→ *Resposta esperada:* veredito explícito — resolvido por peer, ou lacuna que M0 precisa cobrir sozinho

**Q6.** Qual o comando exato para rodar o exemplo de microfone do `sherpa-onnx` e
quais artefatos externos ele exige?
→ *Método:* `Read knowledge-base/references/sherpa-onnx/rust-api-examples/README.md`; `ls knowledge-base/references/sherpa-onnx/rust-api-examples/`
→ *Resposta esperada:* comando reproduzível + lista de modelos a baixar

### Corner D — Techniques

**Q7.** Como o VAD Silero é integrado no `sherpa-onnx` — janela, threshold,
tamanho do modelo e custo declarado?
→ *Método:* `ls knowledge-base/references/sherpa-onnx/scripts/silero_vad/`; `Grep -rn "vad" knowledge-base/references/sherpa-onnx/rust-api-examples/examples/`
→ *Resposta esperada:* parâmetros de configuração + custo `[LITERATURA]` se declarado

**Q8.** Como `parakeet-rs` mantém estado entre chunks no modo streaming, e o que
isso implica para um ring buffer de dois streams independentes?
→ *Método:* `Read knowledge-base/references/parakeet-rs/examples/streaming.rs`; `Grep -n "state\|cache\|buffer" knowledge-base/references/parakeet-rs/src/audio.rs`
→ *Resposta esperada:* modelo de estado + se é reaproveitável para dois streams

## 6. Coverage Matrix

| # | Corner | Método declarado | Formato da resposta | Status |
|---|---|---|---|---|
| Q1 | Integration tests | Read + Grep em `parakeet-rs/src/` | lista de testes + fixtures | mapeado |
| Q2 | Integration tests | Read de 2 exemplos de streaming | trecho de código do laço | mapeado |
| Q3 | Dependencies | Read de 2 `Cargo.toml` | tabela crate/versão/features | mapeado |
| Q4 | Dependencies | Grep em `Cargo.toml` + `audio.rs` | crate + evidência de alocação | mapeado |
| Q5 | Tools | Grep em 2 diretórios | veredito resolvido/lacuna | mapeado |
| Q6 | Tools | Read README + ls | comando + artefatos | mapeado |
| Q7 | Techniques | ls + Grep | parâmetros + custo | mapeado |
| Q8 | Techniques | Read + Grep | modelo de estado | mapeado |

**Cobertura: 8/8 questões mapeadas a método = 100%.** Nenhuma questão deferida.
Todos os quatro corners têm ≥ 1 e ≤ 3 questões.

## 7. Halt-loop checkpoints

Para `/discover-execute`, uma sub-tarefa só pode ser marcada `done` quando:

1. A questão tem resposta com **citação de caminho que existe em disco**
2. Todo número na resposta carrega rótulo de `.claude/rules/asr-evidence-discipline.md` § 1
3. Quando a resposta é "não existe no peer", isso é registrado como **lacuna
   explícita** com o que M0 terá de construir — não como falha da questão

## 8. Acceptance Criteria

- [ ] As 8 questões respondidas ou marcadas `blocked` com motivo
- [ ] Toda citação `knowledge-base/references/...` resolve via `Path.exists()`
- [ ] Os 4 corners populados no blueprint
- [ ] ≥ 1 ADR no blueprint sobre o que reusar vs construir
- [ ] Veredito explícito sobre Q5 (loopback) — é o único item sem solução conhecida
- [ ] Nenhuma recomendação toca item bloqueado por M2

## 9. Global Definition of Done

Blueprint em `knowledge-base/discoveries/blueprints/m0-walking-skeleton-blueprint.md`
com verdict ≥ `SHIPPABLE_WITH_CAVEATS` em `/discover-confidence`, conforme
`.claude/rules/discover-blueprint-golden-rule.md`.

## 10. Rules citadas

- `.claude/rules/asr-evidence-discipline.md` § 0 (discover contínuo — M0 é trabalho liberado) e § 1 (rotulagem de números)
- `.claude/rules/parsimony-ladder.md` rungs 3-4 — reusar antes de escrever é o motivo desta descoberta existir
- `.claude/rules/testing.md` § 2 — o blueprint deve indicar em que nível da pirâmide cada verificação de M0 cai
- `.claude/rules/cycle-discover.md` — contrato do ciclo
