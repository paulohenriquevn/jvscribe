# Review consolidado — M2 (Decisão de arquitetura)

**Data:** 2026-07-25 · **Slug:** m2-architecture-decision · **Cycle:** `/review`
**Veredito:** **READY_TO_MERGE** (nenhum BLOCKER; o único HIGH corrigido e validado; todos os MEDIUM/LOW endereçados)

## Escopo revisado

Artefatos de M2 (doc-only + um fix de teste Rust):
- `knowledge-base/adrs/0001-m2-architecture-finalists.md` (a decisão)
- `knowledge-base/measurements/m2-rtfx-candidates.md` (evidência RTFx)
- `knowledge-base/discoveries/blueprints/m2-architecture-decision-blueprint.md`
- `PRD.md` § 8.1 (bloco "Atualização M2")
- `crates/macaw-cli/src/app.rs` + `crates/macaw-cli/tests/server_concurrency_test.rs` (fix flaky)

## Agentes (3, em paralelo)

| Agente | Foco | BLOCKER? |
|---|---|---|
| `streaming-asr-scientist` | streaming/cache, precisão de citação | Não |
| `evaluation-scientist` | rigor de evidência do ADR (rótulos, falácias) | Não |
| `general-purpose` (rust+cross-validation) | fix Rust sem regressão + DoD coberto | Não |

## Findings e resolução

### HIGH

| ID | Finding | Resolução | Evidência |
|---|---|---|---|
| **CV-01** | `cargo test --workspace` não deterministicamente verde: `vad_cost_test.rs:88` usava bound absoluto no **pior-caso** (max de 1 janela) — sensível a preempção do scheduler sob carga paralela. Mesmo anti-pattern que o fix de M2 corrigiu no teste irmão. | **Corrigido:** gate movido do `max` absoluto para o **p99** (métrica de cauda robusta a outlier de amostra única, exigida por RNF-02); `max` permanece como log `[MEDIDO]`, não como gate. | `vad_cost_test.rs:88`; validado 3/3 isolado + **2/2 workspace sob carga máxima de CPU** (12 cores em `yes`) + baseline verde. |

### MEDIUM

| ID | Finding | Resolução |
|---|---|---|
| **F1** | RTFx `[MEDIDO]` reportou só mediana; `asr-evidence-discipline § 1` exige **média ± desvio**. | **Re-medido com N=10 + dispersão.** Descoberta material: a mesma clip (tokens idênticos 193/49) deu Zipformer **15,90 ± 2,06×** vs tiny **7,93 ± 0,72×** → razão **~2×**, não ~2,9×. A diferença é carga de CPU — exatamente o valor de reportar dispersão. Magnitude corrigida em TODOS os artefatos; direção (transducer > AED) permanece, com separação limpa (intervalos não sobrepõem). Script + log salvos como evidência reprodutível. |
| **F2 / CV-04** | FastConformer co-finalista com RTFx "≈Zipformer" rotulado `[LITERATURA]` — resíduo da falácia §3 #2 (analogia de família); encoders diferem (Zipformer U-Net/k2 vs FastConformer Conformer+subsampling 8×/NeMo). | Rótulo corrigido para **`[ESTIMATIVA]`** com premissa e ressalva explícitas; registrado como **elo mais fraco**; ação de M4 (medir na mesma régua via `parakeet-rs`, mensurável agora) nomeada. |
| **F3** | "A diferença amplia para áudio longo" apresentada dentro de `[MEDIDO]` — extrapolação além dos 12 s. | Rotulada **`[ESTIMATIVA]`** com mecanismo (custo AED ∝ tokens + self-attention O(n²)); conclusão medida reduzida a "~2× em 12 s". |
| **STREAM-ADR-01** | ADR citava `test_paraformer_streaming.py:24-26` (config de chunk) para "modelo -online distinto" — linha não exibe o fato (anti-pattern §6, o vetor da falha original). | Citação corrigida para `:13` (nome do modelo `-online`) + `test_paraformer.py:12` (offline), **verificadas em disco**. |

### LOW / INFO

| ID | Finding | Resolução |
|---|---|---|
| **F4** | `[FONTE-REPO]` usado extensivamente mas não definido na SoT (`asr-evidence-discipline § 1` só define 4 rótulos). | **Registrado na SoT** como 5º rótulo (fato de código lido em peer clonado; mais forte que `[LITERATURA]`, exige citação `arquivo:linha` que exibe o fato). CHANGELOG atualizado. |
| **F5** | Modelo AED inglês em áudio pt_br pode inflar tokens → deprime RTFx do AED. | Caveat de justeza adicionado (measurement § 4): gap medido é **teto** da vantagem do transducer; direção robusta, magnitude a confirmar. |
| **STREAM-ADR-02** | "um encoder dois modos" citado só em `:62-69` (prova cache, não modos). | Citação ampliada: `forward` (batch, `:487`) + `streaming_forward` (incremental, `:573`), verificadas. |
| **BP-03** | "7 tensores de cache" impreciso — são **7 categorias por encoder** (`7 * num_encoders`). | Corrigido no ADR + blueprint (2 ocorrências). |
| **STREAM-BP-05** | Matriz "✅ nativo" sem qualificar mecanismo vs equivalência. | Coluna Streaming marcada com `†` → nota "mecanismo lido, não equivalência (= M4)". |
| **RUST-01 / STREAM-POS-04 / CV-02 / CV-03** | INFO/positivos (margem do discriminante aceitável; equivalência honestamente deferida; T1.1/T1.2 entregues). | Sem ação — registrados. |

## Hard gates (`cycle-review`)

| Gate | Estado |
|---|---|
| Failing tests on branch | ✅ **Verde** — CV-01 corrigido; workspace 2/2 sob carga máxima + baseline |
| New secrets committed | ✅ Nenhum |
| Direct commit to `main` | ✅ Trabalho em `develop` |
| Co-Authored-By trailer | ✅ Ausente (política do usuário) |
| CHANGELOG atualizado | ✅ `[Unreleased]` com as correções do review |

## Conclusão

Todos os 3 agentes recomendaram READY_TO_MERGE condicionado às correções — **todas aplicadas e validadas com evidência**. A re-medição (F1) foi a de maior valor: corrigiu a magnitude de ~3× para ~2× com dispersão real, exatamente o tipo de rigor que a `asr-evidence-discipline` existe para forçar. A decisão de arquitetura (2 finalistas: Zipformer+CTC e FastConformer+CTC; Moonshine controle) **não muda** — a direção da evidência é robusta. **Veredito: READY_TO_MERGE.**
