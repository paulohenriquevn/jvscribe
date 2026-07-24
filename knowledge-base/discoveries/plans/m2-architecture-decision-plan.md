# Discovery Plan: M2 — Decisão de Arquitetura (5 candidatos × 8 critérios)

> **Version 1.0** — Esta descoberta avalia os **5 candidatos de arquitetura** (Moonshine-like AED, Zipformer+CTC, FastConformer+CTC, Paraformer/NAR, LC-BiMamba/SSM) contra os **8 critérios fixados** em `PRD.md` § 8.1, produzindo o blueprint que sustenta o ADR de seleção e nomeia **2 finalistas** para o piloto de M4. Peers em escopo: `moonshine`, `icefall`, `funasr`, `sherpa-onnx`, `parakeet-rs`. Saída: blueprint em `knowledge-base/discoveries/blueprints/m2-architecture-decision-blueprint.md`. **Traz RTFx `[MEDIDO]` na CPU-alvo** dos candidatos rodáveis em ONNX (via a régua de M1 + sherpa-onnx); WER e claims de treino-do-zero ficam `[LITERATURA]` — o head-to-head de WER é M4, não M2 (`ROADMAP.md` § M2 risco 1).

**Slug:** `m2-architecture-decision`
**Owner:** paulo (lidera `asr-chief-scientist`; apoiam `streaming-asr-scientist` [crit. 3], `cpu-inference-engineer` [crit. 1, 6], `decoding-biasing-engineer` [crit. 4, 5])
**Created:** 2026-07-24
**Version:** 1.1 (absorveu 1 MUST FIX [EC-1: comparabilidade de tamanho + fundação RTFx-agnóstico-a-idioma, ADR D4] + checkpoints EC-2/EC-3 de `knowledge-base/reviews/m2-architecture-decision-edge-cases-2026-07-24.md`)
**Time budget:** 12h (quebra por projeto em ADR D1)

## Context

M2 é **a decisão que todo o "discover contínuo" existiu para sustentar** (`.claude/rules/asr-evidence-discipline.md` § 0; `PRD.md` § 8.1 "⏸ PENDENTE"). A escolha oscilou três vezes na pesquisa original (FastConformer → Zipformer → Moonshine) e uma versão anterior do PRD chegou a **fixar Zipformer usando benchmarks do Moonshine** — a falácia §3 #2 (generalizar entre arquiteturas sem parentesco) que invalidou os números originais. Esta descoberta existe para **fechar essa decisão por evidência**, não por acumulação de argumentos.

Evidência que dispara a descoberta agora:

1. **M1 entregou a régua** (`crates/macaw-audio/src/harness.rs`, `knowledge-base/measurements/m1-harness-measurement.md`) — agora dá para **medir RTFx real** dos candidatos na CPU, em vez de citar benchmarks de terceiros de arquiteturas sem parentesco. É o insumo que faltava para o critério 1 (bloqueante).
2. **`python sherpa_onnx 1.12.23` está disponível** — roda Zipformer/Paraformer/Parakeet/Moonshine ONNX na CPU. O modelo TAGARELA (`alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx`) já está cacheado. Ou seja, 3-4 das 5 famílias são mensuráveis **hoje**.
3. **Dois critérios são estruturalmente não-mensuráveis em M2:** critério 2 (WER no test set de call center) exige o modelo treinado do zero (M4+); e LC-BiMamba é **inviável via ONNX** (`onnxruntime#27796`, `PRD.md` § 8.1) — não roda para medir. Esses ficam `[LITERATURA]`/`[DESCONHECIDO]` honestos.

Regras do projeto que a avaliação respeita: `.claude/rules/asr-evidence-discipline.md` (rotulagem de proveniência; hipótese/evidência/conclusão; as 12 falácias — especialmente #1 GPU→CPU, #2 entre-arquiteturas, #7 defender antes de medir), `.claude/rules/architecture.md` (fronteiras que o runtime alvo impõe).

## Objective

O blueprint deve permitir **redigir o ADR de seleção de arquitetura** — escolher a faixa e nomear 2 finalistas para o piloto de M4 — com cada critério dos 8 sustentado por evidência rotulada por candidato.

Critérios de sucesso mensuráveis do blueprint:

- [ ] Matriz 5 candidatos × 8 critérios preenchida, cada célula com rótulo de proveniência
- [ ] RTFx `[MEDIDO]` na CPU-alvo para todo candidato rodável em ONNX (via régua de M1)
- [ ] Os não-mensuráveis (WER de todos; LC-BiMamba RTFx) explicitamente `[LITERATURA]`/`[DESCONHECIDO]` com o experimento que resolveria (M4)
- [ ] ≥ 1 recomendação de finalista por critério bloqueante, com o trade-off nomeado
- [ ] `/discover-confidence` verdict ≥ SHIPPABLE_WITH_CAVEATS

## In-Scope / Out-of-Scope

### In-Scope (por projeto de referência)

| Project | Subdiretórios em escopo | Candidato / critério que sustenta |
|---|---|---|
| `knowledge-base/references/moonshine/` | `README.md`, `docs/word-level-timestamps.md`, `LICENSE`, `python/pyproject.toml`, `python/` | Moonshine-AED: arquitetura, timestamps (crit. 4), licença (crit. 8) |
| `knowledge-base/references/icefall/` | `egs/ksponspeech/ASR/pruned_transducer_stateless7_streaming/`, `egs/reazonspeech/ASR/zipformer/`, `icefall/utils.py` | Zipformer+CTC: streaming (crit. 3), recipe (crit. 7) |
| `knowledge-base/references/funasr/` | `tests_models/test_paraformer_streaming.py`, `tests_models/test_paraformer.py` | Paraformer/NAR: streaming batch↔incremental (crit. 3) |
| `knowledge-base/references/sherpa-onnx/` | `python-api-examples/offline-*-decode-files.py`, `cxx-api-examples/streaming-zipformer-rtf-cxx-api.cc` | Tool para **rodar e medir RTFx** de todos os candidatos ONNX (crit. 1, 6) |
| `knowledge-base/references/parakeet-rs/` | `examples/streaming.rs` | Runtime Rust alternativo p/ parakeet/TAGARELA (crit. 6 exportabilidade) |

### Out-of-Scope (explícito)

| Project / Subdir | Motivo da exclusão |
|---|---|
| Treino do zero de qualquer candidato | É M3-M6, não M2; M2 decide arquitetura, não treina |
| WER head-to-head no test set de call center | Exige modelo treinado do zero (M4 piloto); em M2 é `[LITERATURA]` (`ROADMAP.md` § M2 risco 1) |
| `knowledge-base/references/lhotse/`, `tract/`, `vibeasr-cpp/` | Não são candidatos de arquitetura; lhotse é dados (M1/M3), tract/vibeasr são runtime genérico |
| LC-BiMamba implementação | Sem peer clonado; inviável via ONNX (`onnxruntime#27796`) — evidência de exclusão vem da literatura, não de código |
| Qualquer subdir de build/`dist/`/`.venv/`/`target/`/`node_modules/` | Artefatos |

## ADRs

### D1 — Time budget + stop conditions

**Decision:** `sherpa-onnx`: 3h (é a ferramenta de medição, o mergulho mais fundo) · `icefall`: 3h (Zipformer streaming + recipe) · `funasr`: 2h (Paraformer) · `moonshine`: 3h (arquitetura + timestamps + o único com benchmark CPU) · `parakeet-rs`: 1h. Total 12h.

**Rationale:** sherpa-onnx é o backend de medição de RTFx (critério 1 bloqueante), logo o mais fundo junto de moonshine (o único candidato com benchmark CPU publicado, referência de método). icefall/funasr sustentam o critério 3 (streaming). Peers de dados/runtime genérico ficam fora (out-of-scope).

**Stop condition — per question (mandatory):** Fase A vazia após 3 retries com variação → questão BLOCKED "Fase A exhausted", segue. NÃO preencher com hotspots de outra questão.

**Stop condition — per project:** orçamento esgotado → restantes BLOCKED "budget exhausted", segue. Todo projeto nesse estado → `<promise>BLUEPRINT_BLOCKED</promise>`.

**Stop condition — medição de RTFx (específica de M2):** se o modelo ONNX de um candidato não baixar/rodar em 20 min de tentativa, marca o RTFx daquele candidato `[DESCONHECIDO — não rodou no ambiente]` com o motivo, e segue — NÃO inventa número nem extrapola de outra arquitetura (falácia §3 #2).

**Anti-pattern:** NUNCA fabricar Fase B nem número de RTFx. `[MEDIDO]` exige o comando exato + hardware + nº de repetições (`asr-evidence-discipline.md` § 1). BLOCKED/DESCONHECIDO honesto é obrigatório (Regra 3).

### D2 — Investigation depth

**Decision:** Leitura profunda do código de arquitetura/streaming (Q1-Q3, Q6); execução real via sherpa-onnx + régua para RTFx (Q4); leitura declarativa de recipe/licença (Q5).

**Rationale:** Arquitetura e streaming precisam da leitura do corpo. RTFx precisa de **execução** (não leitura) — é o diferencial de M2 sobre a pesquisa original que só citou benchmarks alheios. Licença/recipe são declarativos.

**Consequences:** Q4 é a mais cara (baixa e roda modelos); as demais são leitura.

### D3 — M2 mede RTFx e mapeia; NÃO trava a decisão nem mede WER

**Decision:** A descoberta produz o blueprint com evidência por critério; a **escolha e os 2 finalistas** saem do ADR (fase de plano/implementação), não do blueprint. WER de todos os candidatos é `[LITERATURA]` — o head-to-head medido é o piloto de M4.

**Rationale:** `asr-evidence-discipline.md` § 0 (não travar arquitetura em artefato de descoberta) e § 2 (conclusão não excede evidência). O ROADMAP § M2 risco 1 é explícito: a decisão pode depender de medição própria que só M4 fornece. M2 nomeia finalistas **a medir**, não o vencedor.

**Consequences:** o blueprint pode terminar com "2 finalistas a pilotar", não "arquitetura X escolhida". Isso é o DoD de M2, não uma limitação.

### D4 — RTFx é agnóstico a idioma; WER não (fundação do método de M2) — EC-1

**Decision:** O RTFx medido de um modelo ONNX de qualquer idioma (um zipformer inglês de 34M, um paraformer chinês) é **evidência válida do critério 1** para aquela arquitetura+tamanho — porque o encoder faz o mesmo compute independente da língua. Já o **WER é dependente de idioma e de treino**, então permanece `[LITERATURA]` até o piloto de M4. A comparação de RTFx é feita em **faixas de tamanho comparáveis** (~30M/~80M/~123M), anotando os params de cada modelo medido.

**Rationale:** Sem essa distinção, a matriz de RTFx seria maçã-com-laranja (34M vs 600M) ou atacável por "é modelo inglês". Fixá-la é o que torna a medição de M2 defensável sem ter o modelo PT-BR (que só existe em M3+). Contém as falácias §3 #8 (tamanho ≠ velocidade) e evita a #2 (extrapolar entre arquiteturas — aqui NÃO se extrapola, mede-se cada uma).

**Consequences:** onde não houver modelo de tamanho comparável para uma família, o RTFx daquela faixa fica `[DESCONHECIDO]` honesto, não estimado.

## Research Questions

| # | Question | Corner | Reference project(s) | Fase A (broad) | Fase B (deep) | Expected answer shape |
|---|---|---|---|---|---|---|
| Q1 | Qual a **estrutura encoder/decoder** de cada candidato (AED-RoPE vs U-Net-CTC vs NAR) e o que ela implica para tamanho × capacidade? | techniques | `knowledge-base/references/moonshine/README.md`, `knowledge-base/references/icefall/egs/reazonspeech/ASR/zipformer/zipformer.py`, `knowledge-base/references/funasr/tests_models/test_paraformer.py` | Grep `class .*Encoder\|class .*Decoder\|RoPE\|SwiGLU` nos peers | Ler a definição de cada arquitetura; capturar topologia, nº de camadas, mecanismo de atenção | Tabela: candidato → topologia → params publicados → citação `path` |
| Q2 | Cada candidato é **streaming nativo com cache** (critério 3, bloqueante)? Chunk, look-ahead, state caching? | techniques | `knowledge-base/references/icefall/egs/ksponspeech/ASR/pruned_transducer_stateless7_streaming/zipformer.py`, `knowledge-base/references/funasr/tests_models/test_paraformer_streaming.py` | Grep `cache\|chunk\|streaming\|look.?ahead\|left_context` | Ler o caminho streaming de cada um; capturar como o cache/chunk é mantido | Por candidato: streaming nativo sim/não + mecanismo + citação |
| Q3 | **Timestamps por palavra (crit. 4)** e **viabilidade de hotwords (crit. 5)** por família de decoder? | techniques | `knowledge-base/references/moonshine/docs/word-level-timestamps.md`, `knowledge-base/references/icefall/icefall/utils.py` | Grep `timestamp\|word.level\|align\|biasing\|hotword` | Ler como cada família dá timestamps + se hotwords se aplicam (FLToP/WCTC só em CTC; mais difícil em AED) | Por candidato: timestamps (como) + hotwords (viável/difícil) + citação |
| Q4 | **RTFx MEDIDO na CPU-alvo** de cada candidato rodável em ONNX, em **faixas de tamanho comparáveis** (~30M/~80M/~123M) — critério 1 (bloqueante)? | tools | `knowledge-base/references/sherpa-onnx/python-api-examples/offline-nemo-parakeet-decode-file.py`, `knowledge-base/references/sherpa-onnx/cxx-api-examples/streaming-zipformer-rtf-cxx-api.cc` | Ler os runners de sherpa-onnx por família (parakeet, ctc, transducer, moonshine) | Rodar cada candidato ONNX via sherpa_onnx + medir RTFx com a régua de M1 (`RtfxMeter`), **anotando o nº de params de cada modelo** para comparar arquitetura, não tamanho | Por candidato/tamanho: RTFx `[MEDIDO]` (comando+hardware+n+params) OU `[DESCONHECIDO — não rodou]` com motivo. **(EC-1)** |
| Q5 | **Recipe de treino (crit. 7)**, **exportabilidade ONNX (crit. 6)** e **licença (crit. 8)** por candidato? | deps | `knowledge-base/references/icefall/egs/reazonspeech/ASR/zipformer/`, `knowledge-base/references/moonshine/LICENSE`, `knowledge-base/references/moonshine/python/pyproject.toml` | Glob recipes em `icefall/egs/*/ASR/zipformer/`; Grep `license\|LICENSE`; verificar export ONNX | Ler a recipe (train.py/export.py existe?), a licença, e se há caminho ONNX | Por candidato: recipe (madura/ausente) + ONNX (sim/não) + licença + citação |
| Q6 | Como os peers **testam equivalência batch↔streaming** (a fronteira que o critério 3 exige provar)? | tests | `knowledge-base/references/funasr/tests_models/test_paraformer_streaming.py` | Grep `def test.*stream\|assert.*equal\|allclose\|chunk` | Ler o teste de streaming; capturar como asseguram que incremental ≡ batch | Padrão de teste de equivalência + citação `test:linha` |

## Coverage Matrix

| Corner | Questions mapped | Status |
|---|---|---|
| Integration tests | Q6 | Covered |
| Dependencies | Q5 | Covered |
| Tools | Q4 | Covered |
| Techniques | Q1, Q2, Q3 | Covered |

**Coverage: 4/4 corners covered (100%)**

## Halt-loop Checkpoints

| Checkpoint | Assertion | Action if fails |
|---|---|---|
| Before answering Qx | O `knowledge-base/references/{project}/{path}` da Fase A existe | Marca Qx BLOCKED "path not found", segue |
| Per-question Fase A budget | Fase A ≥ 1 hotspot OU 3 retries | Após 3 retries vazios, BLOCKED "Fase A exhausted", segue |
| Q4 medição (crit. M2) | Cada RTFx é `[MEDIDO]` (comando+hardware+n+params) OU `[DESCONHECIDO]` com motivo — NUNCA extrapolado de outra arquitetura | Se um número não tem proveniência, marca `[DESCONHECIDO]` honesto |
| Q4 formato TAGARELA (EC-2) | O modelo parakeet está no formato sherpa (encoder/decoder/joiner + tokens.txt OU nemo-transducer single-file) antes de medir | Cache atual é blob único sem tokens → se não rodar em 20 min, `[DESCONHECIDO — formato incompleto]` e usa parakeet de referência do zoo p/ o RTFx da família |
| Q6 equivalência (EC-3) | O teste de streaming do funasr assere batch ≡ incremental (não só "roda") | Se for só smoke test, reporta honesto que o peer não prova equivalência (vira experimento de M4) |
| After answering Qx | A seção do blueprint sob Qx tem ≥ 1 citação | Re-itera Qx (1 retry) |
| Before promising complete | Os 4 corners preenchidos + a matriz 5×8 tem rótulo em toda célula | Recusa a promessa, continua |

## Acceptance Criteria

- [ ] Todas as 6 research questions respondidas OU BLOCKED com motivo
- [ ] Os 4 corners com seção preenchida
- [ ] Matriz 5 candidatos × 8 critérios com rótulo de proveniência em cada célula
- [ ] RTFx `[MEDIDO]` para os rodáveis; `[DESCONHECIDO]`/`[LITERATURA]` honesto para o resto
- [ ] Toda citação aponta para path real em `knowledge-base/references/`
- [ ] ≥ 1 ADR no blueprint sintetizando o trade-off por critério bloqueante
- [ ] `/discover-confidence` verdict ≥ SHIPPABLE_WITH_CAVEATS
- [ ] Blueprint salvo em `knowledge-base/discoveries/blueprints/m2-architecture-decision-blueprint.md`

## Global Definition of Done

- [ ] Todas as fases completas (plan → edge-cases → plan-confidence → execute → confidence → improve se preciso)
- [ ] Verdict final no header do blueprint
- [ ] Nenhuma citação fabricada; nenhum RTFx extrapolado entre arquiteturas (falácia §3 #2)
- [ ] Coverage Matrix 100%
- [ ] ADRs referenciam `asr-evidence-discipline.md` (rotulagem, § 0, as falácias) e os 8 critérios do `PRD.md` § 8.1
