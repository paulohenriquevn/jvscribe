# Review pré-merge — M0 Walking Skeleton

> 2026-07-24 · `cycle-review` · 2 revisores independentes (runtime + evidência)
> Verdict inicial: **NEEDS_FIXES** → após remediação: **READY_TO_MERGE**

## Revisores

- `rust-runtime-engineer` — arquitetura, concorrência, error-handling, wiring
- `evaluation-scientist` — disciplina de evidência, metodologia de medição

Ambos rodaram `cargo test --workspace` e `cargo clippy --all-targets -- -D warnings`
independentemente. Nenhum editou código.

## Findings e resolução

| Sev | Finding | Resolução |
|---|---|---|
| **BLOCKER** | B1 — `.cargo/config.toml` com path absoluto commitado; quebra qualquer outro checkout | ✅ `relative = true` — build reprodutível, validado rodando de subdiretório |
| **BLOCKER** | B2 — T2.3 (sink mudo) sem caller de produção; falha silenciosa continuava silenciosa | ✅ `run_live` chama `check_sink_health`+`evaluate_health`; `sink_muted_integration_test` prova o path |
| HIGH | H1 — `DriftMeter` (T5.2) sem caller; probe reimplementava a lógica | ✅ `run_live` usa `DriftMeter::record`; drift aparece na saída |
| HIGH | H2 — RTF single-shot sem warmup, apresentado como `[MEDIDO]` limpo | ✅ forward pass aquecido, n=10, média±desvio; rótulo "só encoder, aquecido, grafo não-otimizado" |
| HIGH | H3 — `ring::SampleRing` código morto; clippy não pega `pub` órfão | ✅ módulo removido; audit corrigido com a lição de método |
| HIGH | H4 — histórico de backlog/drift cresce sem limite; `percentiles` reordena tudo | ✅ janela deslizante `VecDeque` cap `MAX_HISTORY=4096` |
| MEDIUM | M1 — alocação no laço de captura contradiz DoD de T1.1 | ✅ documentado como desvio consciente (transferência de posse pelo canal) |
| MEDIUM | M2 — `classify_latest` aloca `Vec` por janela | ✅ reescrito com slice + `drain(..consumed)` único, sem alocação por janela |
| MEDIUM | M3 — plano desatualizado vs. correção de DoD do ROADMAP | ✅ Goal, T4.1 AC e Integração Final do plano alinhados |
| MEDIUM | M4 — testes fazem skip silencioso reportando `ok` | ✅ `scripts/test_report.sh` conta executados vs. SKIPs |
| MEDIUM | M5 — `SpeechDetector` trait não usado no composition root | ✅ `classify_latest` recebe `&mut dyn SpeechDetector` |
| LOW | HIGH-1/MEDIUM-1 (evidência) — claims excediam a evidência ("impossível", drift em horas) | ✅ docs reescritos separando escopo de claim; `[DESCONHECIDO]` onde devido |
| LOW | LOW-2 — comentário "quantizado 40MB" contradiz "2,3GB fp32" | ✅ reconciliado |
| LOW | hound duplicado em deps + dev-deps | ✅ removido de `[dependencies]` |

## O que os revisores confirmaram correto (verificado, não assumido)

- Zero `unwrap`/`expect`/`panic!` em caminho de produção; erros tipados em toda parte
- Fronteiras de arquitetura respeitadas: `macaw-audio` não depende de `ort`/`macaw-asr`; composição só no CLI
- `macaw-asr` não vaza tipos do `ort` na API pública
- Reordenação `[frame][mel]`→`[mel*n_frames]` row-major correta
- `extract` zero-alocação **provado** por `stats_alloc`
- Tabela-verdade de roteamento de falante completa
- Decisão de não implementar o decoder (bloqueado por M2) correta e disclosed

## Estado final

- **30 testes, 0 falhas** (34 − 5 do `ring` removido + 1 novo de integração B2)
- `cargo clippy --workspace --all-targets -- -D warnings`: limpo
- Evidências aquecidas com cauda: VAD p99 3,66 µs / max 17,94 µs; encoder 137±27 ms (n=10)

## Verdict: READY_TO_MERGE

Ambos os BLOCKERs corrigidos e provados. Todos os HIGH resolvidos. Nenhum finding
residual acima de LOW documentado.
