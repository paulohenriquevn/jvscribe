# Discovery Plan: M1 — Régua de Medição ASR (harness, augmentação telefônica, test set, baseline)

> **Version 1.0** — Esta descoberta investiga como os peers de referência medem **RTF/RTFx**, calculam **WER**, e constroem **cadeia de augmentação telefônica 8 kHz** e **test sets** de avaliação, para desenhar um harness de medição PT-BR honesto, comparável e reprodutível **antes** de qualquer escolha de arquitetura (M2). Peers em escopo: `sherpa-onnx`, `parakeet-rs`, `icefall`, `lhotse`, `moonshine`. Saída: blueprint em `knowledge-base/discoveries/blueprints/m1-measurement-harness-blueprint.md` cobrindo os quatro cantos (tests/deps/tools/techniques) para os quatro entregáveis do DoD de M1 (`ROADMAP.md` § M1).

**Slug:** `m1-measurement-harness`
**Owner:** paulo (lidera `evaluation-scientist`; apoia `audio-dsp-engineer`, `rust-runtime-engineer`)
**Created:** 2026-07-24
**Version:** 1.1 (absorveu 2 MUST FIX de `knowledge-base/reviews/m1-measurement-harness-edge-cases-2026-07-24.md` — Fase A de Q4 e Q5)
**Time budget:** 10h (quebra por projeto em ADR D1)

## Context

M1 é **pré-requisito de M2** (`ROADMAP.md` § M1 "Dependencies: M0"; `PRD.md` § 8.1 exige medição própria antes de travar arquitetura). O default do projeto é **investigar e medir, não escolher** (`.claude/rules/asr-evidence-discipline.md` § 0). O harness de M1 é o instrumento que torna a decisão de M2 defensável — sem ele, qualquer comparação entre candidatos cai nas falácias § 3 da disciplina de evidência (média sem p99, benchmark curto no chip U, WER público tratado como call center).

Evidência que dispara esta descoberta agora:

1. **O DoD de M1 tem uma tensão estrutural com o escopo.** O DoD pede "test set de call center PT-BR 8 kHz curado por humano" (`ROADMAP.md` § M1), mas áudio real de atendimento exige consentimento + trilho LGPD que está **explicitamente fora de escopo** (`PRD.md` § 3.2 linha "Fora de escopo | ... compliance LGPD"; `ROADMAP.md` § M1 risco 2). A descoberta precisa mapear como construir um test set 8 kHz honesto **sem** áudio proprietário — provável saída: corpus público de fala espontânea PT-BR (`PRD.md` § 7.3) degradado pela cadeia de augmentação telefônica, rotulado como **proxy de canal**, não domínio real.
2. **O risco 1 do ROADMAP é significância estatística** — "WER em 20 min de áudio tem IC largo" (`ROADMAP.md` § M1). A régua precisa reportar intervalo de confiança, não ponto. Nenhum peer clonado implementa bootstrap de WER (verificado: `grep bootstrap` em `icefall/icefall/` retorna só comentários de otimizador), então essa técnica virá de `[LITERATURA]`, não de código emprestável.
3. **RNF-04/RNF-05** exigem sustentação ≥ 10 min sob carga concorrente no chip U de 15 W (`PRD.md` § 6). O ambiente **não tem `stress-ng`** (verificado) — a descoberta precisa achar como gerar carga concorrente reprodutível com o que existe.
4. **M0 já deixou base**: `BacklogCounter` e `DriftMeter` (`crates/macaw-audio/src/metrics.rs`) cobrem RNF-03 e sincronia; o harness de M1 estende, não recomeça (DRY — `.claude/rules/parsimony-ladder.md` rung 4).

Regras do projeto que qualquer padrão emprestado deve respeitar: `.claude/rules/asr-evidence-discipline.md` (rotulagem de proveniência de todo número; as 12 falácias), `.claude/rules/testing.md` (determinismo, AAA, edge vs negative), `.claude/rules/architecture.md` (o harness é infraestrutura de medição — não vaza para o domínio).

## Objective

O blueprint deve permitir decidir **a arquitetura do harness de medição de M1** — quais componentes construir em Rust vs orquestrar em script, como a cadeia de augmentação é montada e validada, como o test set é curado sem violar LGPD, e como o baseline dos três modelos é medido de forma comparável — com evidência citável de cada peer.

Critérios de sucesso mensuráveis do blueprint:

- [ ] Todas as 6 research questions respondidas com citação a `knowledge-base/references/`
- [ ] Tabela comparativa de medição de RTF preenchida para `sherpa-onnx` e `parakeet-rs`
- [ ] Recomendação concreta por research question (≥ 1 proposta de decisão cada)
- [ ] Cadeia de augmentação telefônica especificada comando-a-comando (sox), com o que é emprestável de `lhotse` vs próprio
- [ ] Estratégia de test set 8 kHz que respeita LGPD, com rótulo de proveniência honesto
- [ ] `/discover-confidence` verdict ≥ SHIPPABLE_WITH_CAVEATS

## In-Scope / Out-of-Scope

### In-Scope (por projeto de referência)

| Project | Subdiretórios em escopo | Motivo |
|---|---|---|
| `knowledge-base/references/sherpa-onnx/` | `cxx-api-examples/`, `python-api-examples/`, `sherpa-onnx/csrc/*config*.h` | Padrão maduro de medição de RTF e configuração de `num_threads` no runtime ONNX — o backend provável do nosso motor |
| `knowledge-base/references/parakeet-rs/` | `examples/` | Medição de RTF **em Rust** (`Instant`/`elapsed`) — o análogo mais próximo do nosso runtime |
| `knowledge-base/references/icefall/` | `icefall/utils.py` | Cálculo canônico de WER (ins/del/sub, alinhamento) — a referência de comparabilidade com o TAGARELA |
| `knowledge-base/references/lhotse/` | `lhotse/augmentation/`, `test/` | Resample 16k→8k e o padrão de teste determinístico de augmentação |
| `knowledge-base/references/moonshine/` | `scripts/eval-librispeech.py`, `python/pyproject.toml` | Como um peer real orquestra avaliação de WER end-to-end + deps de inferência para o baseline |

### Out-of-Scope (explícito)

| Project / Subdir | Motivo da exclusão |
|---|---|
| `knowledge-base/references/*/` — treino / recipes de modelo (ex.: `icefall/egs/*/ASR/*/train.py`) | M1 é medição, não treino; treino é M3+ |
| `knowledge-base/references/funasr/`, `tract/`, `vibeasr-cpp/` | Redundantes com sherpa/parakeet para as perguntas de RTF/WER; evitam estourar orçamento de 10h (D1) |
| `knowledge-base/references/moonshine/` — arquitetura do modelo (`moonshine/core/`, camadas RoPE) | Candidato de M2, não medição de M1 |
| Qualquer subdir de build/`dist/`/`.venv/`/`target/` em qualquer peer | Artefatos de build |
| Qualquer projeto não clonado em `knowledge-base/references/` | Cross-Project Rule — nunca afirmar feature sem ler a fonte |

## ADRs

### D1 — Time budget + stop conditions

**Decision:** `sherpa-onnx`: 3h · `parakeet-rs`: 1,5h · `icefall`: 2h · `lhotse`: 2h · `moonshine`: 1,5h. Total 10h.

**Rationale:** `sherpa-onnx` é o mais rico (RTF + config de threads + múltiplos exemplos) e o backend provável, logo o mergulho mais fundo. `icefall`/`lhotse` são as fontes canônicas de WER e augmentação — 2h cada para ler a implementação e o teste. `parakeet-rs` e `moonshine` são pontuais (um padrão cada). Peers redundantes ficam fora (D1 out-of-scope) para não estourar o orçamento.

**Alternatives considered:** split igual (rejeitado — sherpa merece mais); deep-dive único em sherpa (rejeitado — perde WER de icefall e augmentação de lhotse, dois entregáveis do DoD).

**Stop condition — per question (mandatory):** Quando a Fase A de uma questão retorna vazio após 3 retries com variações de query (pattern → kind → path alternativo → escopo mais largo), marca a questão BLOCKED com motivo "Fase A exhausted — no hotspots found" e segue. NÃO preencher com hotspots de outra questão.

**Stop condition — per project (mandatory):** Quando o orçamento de um projeto esgota com N questões pendentes, marca todas as restantes daquele projeto BLOCKED com "budget exhausted" e segue. Se todo projeto restante está nesse estado, emite `<promise>BLUEPRINT_BLOCKED</promise>` (NÃO `BLUEPRINT_COMPLETE`) com o relatório honesto de bloqueadas.

**Anti-pattern:** NUNCA fabricar respostas de Fase B para fechar uma questão cuja Fase A esgotou. BLOCKED honesto com motivo é obrigatório (Regra Inquebrável 3; `.claude/rules/asr-evidence-discipline.md` § 4).

**Consequences:** o halt-loop para de iterar num projeto quando o orçamento esgota; o blueprint expõe bloqueadas na seção `## Blocked questions` como semente da próxima descoberta.

### D2 — Investigation depth

**Decision:** Ler cada arquivo em escopo end-to-end para questões de técnica (Q1-Q4); Grep/Glob de texto para deps e tools (Q5-Q6, arquivos de config/README são text-shape).

**Rationale:** RTF/WER/augmentação são padrões de implementação — precisam da leitura do corpo e dos comentários para capturar intenção e edge-cases. Deps e ferramentas são declarativos (pyproject, num_threads) — Grep basta.

**Consequences:** Q1-Q4 gastam mais orçamento (leitura profunda); Q5-Q6 são rápidas. Trade-off explícito no D1.

### D3 — Test set sob LGPD: descoberta mapeia, não decide o corpus final

**Decision:** A descoberta investiga **como** construir um test set 8 kHz honesto (proxy telefônico de corpus público vs áudio real), mas a escolha final do corpus é decisão de plano/implementação, não de descoberta.

**Rationale:** Áudio real de call center está fora de escopo por LGPD (`PRD.md` § 3.2; `ROADMAP.md` § M1 risco 2). Travar o corpus aqui excederia o mandato da descoberta (`.claude/rules/asr-evidence-discipline.md` § 2 — conclusão não excede evidência). O blueprint proporá opções com trade-offs; o `/to-plan` decide.

**Consequences:** o corner de "test set real" é parcialmente diferido; Q4 foca no **mecanismo de curadoria e no invariante anti-pseudo-label** (`PRD.md` § 7.3), não em obter o áudio.

## Research Questions

| # | Question | Corner | Reference project(s) | Fase A (broad — grep/glob map) | Fase B (deep — Read at each hotspot) | Expected answer shape |
|---|---|---|---|---|---|---|
| Q1 | Como `sherpa-onnx` e `parakeet-rs` medem RTF, e o que precisa mudar para medir **RTFx sustentado ≥ 10 min + p99** sem medir só o turbo do chip U (RNF-01/02/04)? | techniques | `knowledge-base/references/sherpa-onnx/cxx-api-examples/streaming-zipformer-rtf-cxx-api.cc`, `knowledge-base/references/parakeet-rs/examples/streaming.rs` | Grep `rtf\|elapsed\|duration\|num_runs` nos dois arquivos | Ler o bloco de cronometragem de cada um; capturar warmup, nº de runs, o que dividem por quê | Tabela: peer → fórmula de RTF → warmup? → nº runs → cita `path:line`; + gap analysis para sustentação/p99 |
| Q2 | Como `icefall` calcula WER (ins/del/sub, alinhamento) e como estender para reportar **IC via bootstrap** em test set pequeno (risco 1)? | techniques | `knowledge-base/references/icefall/icefall/utils.py` | Grep `def write_error_stats\|def store_transcripts` | Ler `write_error_stats` (linha ~686) end-to-end; capturar estrutura de saída (ins/del/sub/total), granularidade por-utterance | Descrição do algoritmo + estrutura de dados + citação `utils.py:linha`; + esboço de bootstrap sobre a saída por-utterance (`[LITERATURA]`) |
| Q3 | Como montar a cadeia de augmentação telefônica 8 kHz (16k→8k, filtro 300-3400 Hz, **G.711 a-law round-trip**, babble/AGC) — o que é emprestável de `lhotse` vs feito em `sox`? | techniques | `knowledge-base/references/lhotse/lhotse/augmentation/resample.py` | Grep `def resample\|class Resample\|sinc` em `resample.py`; `sox --help` para a-law | Ler `resample.py`; capturar método de reamostragem e precisão | Cadeia comando-a-comando (sox) + o que `lhotse` cobre (resample) vs o que fica no sox (a-law, filtro banda) + citações |
| Q4 | Como `lhotse` testa augmentação de forma **determinística** (fixture + tolerância), e como isso ancora o teste da nossa cadeia + o invariante anti-pseudo-label do test set (`PRD.md` § 7.3)? | tests | `knowledge-base/references/lhotse/test/audio/test_resample_randomized.py`, `knowledge-base/references/lhotse/test/augmentation/test_torchaudio.py` | **(EC-1 fix)** Glob `lhotse/test/audio/*resampl*` + `lhotse/test/augmentation/*.py` (os testes ficam em subdirs, NÃO no topo de `test/`) + Grep `allclose\|rtol\|Resample` neles | Ler o(s) teste(s) de resample/augment; capturar padrão de asserção numérica e fixture | Padrão de teste determinístico (fixture → transform → allclose) + citação `test/…:linha`; mapeado ao nosso `testing.md` |
| Q5 | Que **dependências e comando de execução** o baseline exige (whisper-large-v3, Moonshine, TAGARELA) para rodar sem reinventar decode, e sob que licença? | deps | `knowledge-base/references/moonshine/scripts/eval-librispeech.py`, `knowledge-base/references/moonshine/python/pyproject.toml` | **(EC-2 fix)** Ler os **imports** de `eval-librispeech.py` (linhas ~48-60: `jiwer`, `datasets`, `soundfile`, `scipy`, `whisper.normalizers`) como fonte primária das deps de avaliação; `pyproject.toml` é secundário (deps do runtime moonshine, só `numpy`) | Ler o fluxo de eval end-to-end + as deps declaradas | Deps de avaliação (dos imports) + deps de inferência (pyproject) + licença por modelo; whisper-large-v3/TAGARELA marcados `[LITERATURA]` (model card, fora dos peers — EC-4) + citações |
| Q6 | Que padrões os peers usam para **fixar threads/afinidade** (`num_threads`, config de runtime) que sustentam a fixação de P-cores via `taskset` e a medição sob carga (RNF-05/06)? | tools | `knowledge-base/references/sherpa-onnx/python-api-examples/offline-nemo-parakeet-decode-file.py`, `knowledge-base/references/sherpa-onnx/sherpa-onnx/csrc/offline-diacritization-model-config.h` | Grep `num_threads` nos dois arquivos | Ler como `num_threads` é setado e propagado ao runtime | Mapa: knob de thread → onde entra no runtime + citação; + estratégia `taskset`/carga concorrente sem `stress-ng` |

## Coverage Matrix

| Corner | Questions mapped | Status |
|---|---|---|
| Integration tests | Q4 | Covered |
| Dependencies | Q5 | Covered |
| Tools | Q6 | Covered |
| Techniques | Q1, Q2, Q3 | Covered |

**Coverage: 4/4 corners covered (100%)**

## Halt-loop Checkpoints

| Checkpoint | Assertion | Action if fails |
|---|---|---|
| Before answering Qx | O `knowledge-base/references/{project}/{path}` declarado na Fase A existe | Marca Qx BLOCKED "path not found", segue |
| Per-question Fase A budget | Fase A retornou ≥ 1 hotspot OU 3 retries de variação tentados | Após 3 retries vazios, marca Qx BLOCKED "Fase A exhausted"; segue |
| After answering Qx | A seção do blueprint sob Qx tem ≥ 1 citação | Re-itera Qx (1 retry) |
| Mid-loop sanity | Citações a `knowledge-base/references/` ≥ 1 / 200 palavras de prosa | Adiciona citações aos parágrafos sub-citados (1 retry) |
| Q2 granularidade (EC-3) | O blueprint capturou a estrutura **por-utterance** de `write_error_stats` (`results: List[Tuple[cut_id, ref, hyp]]`), não só o WER agregado corpus-wide | Re-lê `utils.py` e registra a saída por-segmento como insumo do bootstrap; sem ela o IC é impossível |
| Per-project time budget | Orçamento do projeto não esgotado | Ao esgotar, marca restantes BLOCKED "budget exhausted"; avança |
| Before promising complete | Os 4 corners têm seção preenchida | Recusa a promessa, continua iterando |

## Acceptance Criteria

- [ ] Todas as research questions respondidas OU marcadas BLOCKED com motivo
- [ ] Os quatro corners com seção preenchida no blueprint
- [ ] Toda citação no blueprint aponta para path real em `knowledge-base/references/`
- [ ] ≥ 1 seção ADR no blueprint sintetizando decisões
- [ ] Orçamento respeitado por projeto
- [ ] `/discover-confidence` verdict ≥ SHIPPABLE_WITH_CAVEATS
- [ ] Blueprint salvo em `knowledge-base/discoveries/blueprints/m1-measurement-harness-blueprint.md`

## Global Definition of Done

- [ ] Todas as fases completas (plan → edge-cases → plan-confidence → execute → confidence → improve se preciso)
- [ ] Verdict final de `/discover-confidence` registrado no header do blueprint
- [ ] Nenhuma citação fabricada
- [ ] Coverage Matrix 100%
- [ ] ADRs referenciam princípio das regras do projeto (`asr-evidence-discipline.md`, `testing.md`, `parsimony-ladder.md` — KISS/YAGNI/DRY/Não-Reinvente) e âncoras do `PRD.md`
