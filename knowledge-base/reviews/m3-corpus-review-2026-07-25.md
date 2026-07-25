# Review consolidado — M3 (Pipeline de corpus)

**Data:** 2026-07-25 · **Slug:** m3-corpus · **Cycle:** `/review`
**Veredito:** **READY_TO_MERGE** (após correções — 1 BLOCKER + 3 HIGH + 6 MEDIUM/LOW todos endereçados e validados)

## Agentes (2, em paralelo)

| Agente | Foco | Verdito inicial |
|---|---|---|
| `general-purpose` | correção de código, DSP, wiring | NEEDS_FIXES (1 HIGH) |
| `evaluation-scientist` | rigor de evidência, estatística, disciplina de teste | NEEDS_FIXES (1 BLOCKER + 2 HIGH) |

Reconhecimento forte de ambos: DSP verificado empiricamente (passband plano, −3 dB nas bordas 300/3400, 3400 < Nyquist 4000 — sem aliasing); RAM-safe comprovado; error-handling tipado nas fronteiras; parsimony (rung 4) exemplar; τ calibrado empiricamente; caveat de correlação honesto.

## Findings e resolução

### BLOCKER

| ID | Finding | Resolução | Evidência |
|---|---|---|---|
| **B-1** | O manifest **não aplicava o filtro** — `run_pipeline` usava `paths` (20), não `kept` (16); o CutSet continha os cuts descartados, contradizendo a Goal ("manifests filtrados por concordância"). | **Corrigido:** novo `filter_cutset(cutset, keep_ids)` em `build_manifest.py`; `run_pipeline` constrói o manifest e aplica `filter_cutset(full, kept)`, com guard `n_cuts == len(kept)` (fail-fast). | Teste `test_filter_cutset_keeps_only_approved` (B-1); guard no pipeline. |

### HIGH

| ID | Finding | Resolução |
|---|---|---|
| **H1** | `pairwise_cer` estourava (`jiwer.cer` ValueError) quando UMA hipótese normaliza para vazio — whisper retorna vazio em silêncio (dado real). | **Corrigido:** `if not a or not b: return 1.0` (discordância máxima). Teste `test_cer_one_empty_is_max_disagreement`. |
| **H-1** | Run usou `small`+`base` (default), não `small`+`medium` do ADR-3 — par mais próximo correlaciona erros ainda mais, enfraquecendo o caveat. | **Registrado** explicitamente no relatório (§ Leitura honesta H-1): a distribuição estreita é parcialmente artefato do par; small+medium fica para quando houver RAM/tempo. Decisão honesta, não silenciosa. |
| **H-2** | `[MEDIDO]` sem IC (o plano prometeu); ±σ é spread, não incerteza; τ=percentil-80 de 20 pontos sem IC. | **Corrigido:** relatório agora separa **spread (±σ amostral)** de **incerteza (SEM → IC95% da média)** e reporta **IC95% bootstrap de τ** (2000 reamostragens, seed fixa). |

### MEDIUM / LOW

| ID | Finding | Resolução |
|---|---|---|
| **M2** | `agree()` órfão (testado, sem caller de produção); `run_pipeline` duplicava `c <= tau` inline. | **Corrigido:** `run_pipeline` consome `agree()` para computar `kept` (elimina a duplicação; wiring triad pilar a). |
| **M-1** | `[MEDIDO]` sem hardware/comando/data (§ 1 exige). | **Corrigido:** relatório carimba data ISO, CPU (`/proc/cpuinfo`), comando exato, "1 run, n=20 clips (não repetições)". |
| **M-2** | "16 mantidos/4 descartados" é tautológico (keep=0.8 → 80% por construção). | **Registrado:** nota de circularidade no relatório (não é evidência de qualidade). |
| **M-3** | Roda no split `test` do FLEURS mas rotula "pool de treino". | **Registrado:** relatório esclarece que FLEURS-test é fonte-piloto de conveniência, não o test set do produto; invariante § 3 #10 respeitado (nenhum pseudo-label toca a suíte de avaliação). |
| **M-4** | Teste de sequencialidade dependia de `__del__`/refcount (frágil em PyPy/ciclos). | **Corrigido:** hooks `on_load`/`on_release` em `transcribe_pair`; teste assere a **ordem** de eventos e o pico=1 sem depender de GC. |
| **M1 / L-1** | Docstring dizia CER "simétrica" — `jiwer.cer` é direcional. | **Corrigido:** docstring declara direcional (hyp1 = referência); relatório idem. |
| **L2** | `run_pipeline` `IndexError` cru em cutset vazio. | **Corrigido:** `RuntimeError` tipado (fail-fast) em manifest vazio. |
| **L1** | Testes de não-materialização frágeis (listdir /tmp compartilhado). | **Corrigido:** manifest mocka `soundfile.write` (assert não-chamado); telephone usa tempdir isolado via monkeypatch. |
| **L-2** | `calibrate_tau` docstring "exatamente"; faltavam testes de borda. | **Corrigido:** "aproximadamente (≥ keep_fraction)"; testes `keep_fraction=1.0`, empates, ambos-vazio. |
| **L-3** | `pstdev` (população) num piloto que é amostra. | **Corrigido:** `statistics.stdev` (amostral, ddof=1). |

## Hard gates (`cycle-review`)

| Gate | Estado |
|---|---|
| Failing tests on branch | ✅ **Verde** — 22 testes de corpus + 32 Python total; workspace Rust 23 suites 0 FAILED |
| New secrets committed | ✅ Nenhum |
| Direct commit to `main` | ✅ Trabalho em `develop` |
| Co-Authored-By trailer | ✅ Ausente |
| CHANGELOG atualizado | ✅ `[Unreleased]` com M3 |

## Conclusão

Ambos os agentes recomendaram READY_TO_MERGE após as correções. O **B-1** (manifest não filtrava) era um gap de wiring real que teria entregue um manifest que contradiz sua própria Goal — pego pelo evaluation-scientist, não pelo agente de código. A re-execução do pipeline com o manifest filtrado + o relatório com IC/hardware/comando fecha o `[MEDIDO]` com rigor. Todos os findings validados com teste ou registro honesto. **Veredito: READY_TO_MERGE.**
