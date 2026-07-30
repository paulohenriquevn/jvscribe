# Review: repo-faang-reorg

**Date:** 2026-07-30
**Branch:** `workspace`
**Reviewer:** 1 agente independente (fresh-eyes) — proporcional a um refactor estrutural (o `/review` de 5–7 agentes é para PRs com lógica nova; aqui a mudança é behavior-preserving, provada por 157 testes + 4 guardas estruturais).
**Findings:** 2 (BLOCKER: 0, HIGH: 1, MEDIUM: 1, LOW: 1, INFO: vários) — **todos resolvidos**.
**Verdict:** **READY_TO_MERGE** (após fix; re-verificado com evidência medida).

## Findings e resolução

| ID | Sev | Finding | Resolução |
|---|---|---|---|
| H1 | HIGH | `finetune/run_zipformer_ctc.sh:23` invoca `python3 patch_ctc_decode.py` (shell→python) — arquivo deletado; sob `set -euo pipefail` aborta o decode | **RESOLVIDO** — `patch_ctc_decode.py` restaurado em `finetune/` (co-locado com o runbook) |
| M1 | MED | `prep_tagarela.py:8,51,157` referencia `download_tagarela_subset.py` (docstring + pré-requisito + msg de `FileNotFoundError`) — deletado | **RESOLVIDO** — `download_tagarela_subset.py` restaurado em `finetune/`; pointer resolve |
| — | preventivo | `gen_phonemes.py` gera `phoneme_targets.json` consumido por `prep_phoneme_head.py:41,291,339` (phoneme head vivo, parte do modelo entregue) | **RESTAURADO** em `finetune/` + `test_gen_phonemes.py` — mesma classe de dependência shell/artefato |
| L1 | LOW | comentários citando `prep_mls`/`prep_conformer_ctc_decode` (deletados de verdade) | **RESOLVIDO** — scrub em `prep_coraa`, `prep_tagarela`, `prep_phoneme_head` |

**Causa da classe de bug:** a guarda EC-1 do plano checava só `^(from|import)` em `.py` — não via invocação shell nem referência em prosa/erro. Lição incorporada no plano (v1.3).

## Invariantes duras (todas OK)
- **LGPD:** `callcenter/` intocado (nenhum path com segmento `callcenter/` no diff).
- **Histórico:** `results/` não-STALE intocado; planos/audits/blueprints/discoveries NÃO reescritos (`audit-trail-rotation`).
- **Estrutura:** raiz de `training/` só tem `README.md` + `conftest.py`; todo script vivo numa pipeline (package-by-feature, ADR D1).
- **Testes:** 157 passed SEM `PYTHONPATH` (conftest resolve); guardas EC-3 (no-cross-pipeline) e EC-5 (no-dup-basename) verdes.
- **Git:** branch `workspace` (não main); zero `Co-Authored-By`; zero secrets; CHANGELOG `[Unreleased]` atualizado.
- **Docs canônicos:** paper §10 (EN+PT-BR) e `PRD.md` com paths novos; `training/README.md` mapeia as 3 pipelines.

## Deleção final (honesta, pós-review)
5 scripts (`prep_mls`, `prep_nemo`, `prep_conformer_ctc_decode`, `resume_tagarela_feats`, `run_pilot_icefall.md`) + 2 testes órfãos (`test_prep_nemo`, `test_prep_mls`) + 2 STALE. Os 5 não têm referência executável/pré-requisito viva (só menções de registro arquivado em `smoke/`, non-blocking).

## Handoff
READY_TO_MERGE → push para `workspace`.
