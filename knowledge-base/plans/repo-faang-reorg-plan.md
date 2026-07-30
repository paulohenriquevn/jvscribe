---
slug: repo-faang-reorg
created_at: 2026-07-30
goal: Reestruturar training/ por pipeline e remover artefatos-ruído, mantendo a suíte pytest 100% verde
---

# Plan: Reorganização FAANG-level do repositório Macaw Voice

> **Version 1.3** — **CORREÇÃO no /review (fresh-eyes pegou wiring cross-linguagem):** `patch_ctc_decode.py`
> (invocado por `run_zipformer_ctc.sh:23`), `download_tagarela_subset.py` (pré-requisito documentado em
> `prep_tagarela.py`) e `gen_phonemes.py` (gera `phoneme_targets.json` do phoneme head vivo) **NÃO são
> ruído** — são helpers vivos da pipeline finetune. Restaurados em `finetune/` (+ `test_gen_phonemes.py`).
> Lista final de deleção: **5 scripts** (prep_mls, prep_nemo, prep_conformer_ctc_decode,
> resume_tagarela_feats, run_pilot_icefall.md) + **2 testes órfãos** (test_prep_nemo, test_prep_mls) + 2 STALE.
> A guarda EC-1 (só `import` Python) não via invocação shell/prosa — lição incorporada.
>
> **Version 1.2** — **CORREÇÃO no implement (a guarda EC-1 disparou):** `prep_icefall.py` **NÃO é
> ruído** — `prep_coraa.py:46` e `prep_tagarela.py:70` importam `prep_icefall.normalize_ptbr` (audit D2).
> Reclassificado de *deletar* → **manter + mover para `finetune/`**; seu teste `test_prep_icefall.py`
> permanece. Testes órfãos adicionais a deletar: `test_prep_nemo.py`, `test_prep_mls.py` (testam módulos
> deletados). Lista final de deleção: 8 código/doc + **3** testes órfãos + 2 STALE.
>
> **Version 1.1** (edge-cases absorvidos: EC-1 padrão de grep `from|import`, EC-2 `mkdir -p` antes do
> `git mv`, EC-3 verificação do grafo de imports completo — ver `knowledge-base/reviews/repo-faang-reorg-edge-cases-2026-07-30.md`)
> — Este plano reestrutura o repositório para que qualquer engenheiro que o abra
> identifique as **três pipelines** (finetune, batch, realtime) em segundos. Faz isso em três
> movimentos seguros e reversíveis-por-git: (1) **deletar** 11 artefatos-ruído tracked (scripts M4
> superseded / one-offs + testes órfãos) e 2 arquivos `results/` marcados `STALE-DO-NOT-USE`; (2)
> **realocar** docs de pesquisa soltos da raiz para `docs/research/`; (3) **reestruturar** os scripts
> planos de `training/` em subdiretórios por pipeline, preservando 100% dos imports e testes verdes via
> `git mv` + um único `training/conftest.py`. Resultado esperado: topo do repo autoexplicativo, zero
> regressão na suíte de testes, `callcenter/` (LGPD) intocado.

## Goal

> "Permitir que um engenheiro que abra o repositório identifique as três pipelines (finetune, batch,
> realtime) em segundos, ao reestruturar `training/` por pipeline e remover 13 artefatos-ruído tracked,
> medido por `python3 -m pytest training/tests -q` retornando **0 failed e 0 errors** após a reorganização."

## Context

O incômodo do dono é concreto e já foi diagnosticado por evidência: o audit Staff-level de 2026-07-25
(`system-design-output/final_report.md § Top 3`) achou "produção misturada com cluster smoke/superseded
num diretório plano" já em M4 (5 arquivos). Em M5 o problema **piorou** — `training/` acumulou 25
scripts `.py`/`.sh` soltos na raiz, misturando o pipeline vivo (batch, finetune, eval telefônico) com
one-offs de M4 (`prep_icefall`, `gen_phonemes`), corpora alternativos nunca usados (`prep_mls`,
`prep_nemo`), o perdedor Conformer (`prep_conformer_ctc_decode`) e patches/resumes de uma vez só
(`patch_ctc_decode`, `resume_tagarela_feats`, `download_tagarela_subset`). Há ainda 2 arquivos em
`training/results/` explicitamente marcados `*.STALE-telephone-38pct-DO-NOT-USE` e docs de pesquisa
(`deep-research-*.md`, `sota-techniques-*.md`) soltos na raiz do repo. O dono decidiu (nesta sessão)
**deletar** (não arquivar) os superseded e conduzir a mudança pelo ciclo formal `/to-plan`.

`target/` (2,5G), `system-design-output/` e binários de `models/` já estão gitignored — não são
escopo de versionamento, apenas ruído de disco (higiene de gitignore cobre o `system-design-output/`).

## Baseline Context (deep review of current state)

### Files that will be touched

| File | LoC today | Papel hoje | Invariantes a preservar |
|---|---|---|---|
| `training/prep_icefall.py` | 141 | Prep M4 superseded (audit `system-design-output/final_report.md` inventory) | DELETAR — nenhum consumidor vivo; só `test_prep_icefall` (também deletado) |
| `training/prep_mls.py` | 110 | Corpus MLS alternativo não usado | DELETAR — importado só por `prep_nemo` (também deletado) |
| `training/prep_nemo.py` | 85 | Corpus NeMo alternativo não usado | DELETAR — `prep_nemo.py:21` importa `prep_mls` |
| `training/prep_conformer_ctc_decode.py` | 162 | Decode do Conformer (perdedor de M4) | DELETAR — nenhum import vivo |
| `training/patch_ctc_decode.py` | 49 | Patch one-off | DELETAR — nenhum import vivo |
| `training/resume_tagarela_feats.py` | 109 | Resume one-off de feats | DELETAR — nenhum import vivo |
| `training/download_tagarela_subset.py` | 96 | Download one-off | DELETAR — nenhum import vivo |
| `training/gen_phonemes.py` | 105 | G2P smoke de M4 | DELETAR — só `test_gen_phonemes` consome |
| `training/run_pilot_icefall.md` | 81 | Runbook M4 | DELETAR — runbook superseded por `run_ft_*.sh` |
| `training/tests/test_prep_icefall.py` | 74 | Teste do módulo deletado | DELETAR junto (`test_prep_icefall.py:17` importa `prep_icefall`) |
| `training/tests/test_gen_phonemes.py` | 35 | Teste do módulo deletado | DELETAR junto |
| `training/results/m4-small-baseline/recogs-test-epoch-30_avg-1.txt.STALE-telephone-38pct-DO-NOT-USE` | — | Resultado STALE marcado DO-NOT-USE | DELETAR |
| `training/results/m4-small-baseline/recogs-test-epoch-30_avg-10_use-averaged-model.txt.STALE-telephone-38pct-DO-NOT-USE` | — | Resultado STALE marcado DO-NOT-USE | DELETAR |
| `deep-research-arquiteturas-alternativas.md` | — | Pesquisa solta na raiz | MOVER → `docs/research/` (via `git mv`) |
| `deep-research-asr-ptbr-cpu-realtime.md` | — | Pesquisa solta na raiz | MOVER → `docs/research/` |
| `sota-techniques-asr-ptbr-cpu.md` | — | Pesquisa solta na raiz | MOVER → `docs/research/` |
| `training/batch_transcribe.py` | 208 | PIPELINE batch (produção, testada) | MOVER → `training/batch/`; `greedy/segment/transcribe_folder` continuam importáveis por nome |
| `training/eval_public_hf.py` | 56 | Benchmark FLEURS | MOVER → `training/batch/`; `eval_public_hf.py:10` importa `batch_transcribe` (co-locar) |
| `training/decode_onnx_local.py` | 124 | Decode CORAA local | MOVER → `training/batch/` |
| `training/bench_rtfx.py` | — | Medição RTFx | MOVER → `training/batch/` |
| `training/prep_coraa.py` | 169 | Prep corpus CORAA (M5) | MOVER → `training/finetune/` |
| `training/prep_tagarela.py` | 295 | Prep corpus TAGARELA (M5) | MOVER → `training/finetune/` |
| `training/prep_finetune.py` | 160 | Datamodule de fine-tune | MOVER → `training/finetune/`; `prep_finetune.py:34` importa `prep_phoneme_head` (co-locar) |
| `training/prep_augment_datamodule.py` | — | Datamodule com augmentação | MOVER → `training/finetune/`; importa `prep_phoneme_head` |
| `training/prep_phoneme_head.py` | — | Patch da cabeça de fonema | MOVER → `training/finetune/` (importado por 2 acima) |
| `training/run_ft_codec.sh`, `run_ft_freeze.sh`, `run_zipformer_ctc.sh` | — | Runbooks de treino | MOVER → `training/finetune/`; referenciam `zipformer/train.py` (path da INSTÂNCIA, não do repo — inalterado) |
| `training/mic_transcribe.py` | 233 | PIPELINE realtime (demo mic) | MOVER → `training/realtime/` |
| `training/measure_realcodec.py` | — | Eval telefônico D1 | MOVER → `training/eval/` |
| `training/measure_callcenter.py` | — | Eval call center real | MOVER → `training/eval/`; `test_measure_callcenter.py:7` importa `measure_callcenter` |
| `training/make_telephone_test.py` | — | Builder de test set telefônico | MOVER → `training/eval/` |
| `training/make_callcenter_cuts.py` | — | Builder de cuts do call center | MOVER → `training/eval/` |
| `training/conftest.py` (NEW) | 0 | — | Adiciona os subdirs de pipeline ao `sys.path` p/ os testes importarem por nome |
| `training/README.md` (NEW) | 0 | — | Mapa das 3 pipelines (o que o eng FAANG lê primeiro) |
| `.gitignore` | ~40 | Ignora `target/`, `models/`… | Adicionar `system-design-output/` |

### Current callers / dependents

- **`from batch_transcribe import transcribe_folder|greedy|segment|SR`** — produção: `training/eval_public_hf.py:10`; testes: `training/tests/test_batch_transcribe.py:7,75`. Externo (outro repo): não. → move junto para `training/batch/`.
- **`from prep_phoneme_head import apply_patch`** — produção: `training/prep_finetune.py:34`, `training/prep_augment_datamodule.py:52`; testes: `training/tests/test_prep_phoneme_head.py:12`. → move junto para `training/finetune/`.
- **`from prep_mls import download_extract_mls`** — só `training/prep_nemo.py:21` (ambos deletados). Externo: não.
- **`from prep_icefall import SOURCES, normalize_ptbr`** — só `training/tests/test_prep_icefall.py:17` (ambos deletados).
- **`from measure_callcenter import parse_transcript, normalize`** — teste `training/tests/test_measure_callcenter.py:7`. → move junto para `training/eval/`.
- **Imports por `sys.path.insert`** — os testes usam `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` (= `training/`) ou `.../ "scripts"`. Nenhum skill/rule/hook referencia paths de `training/` (grep vazio) — raio de explosão contido ao próprio `training/` + docs.

### Domain glossary

- **Pipeline finetune** — preparar corpus (CORAA/TAGARELA) + rodar o fine-tune/treino (runbooks `run_ft_*.sh` na instância GPU).
- **Pipeline batch** — transcrever pastas/áudios offline (`batch_transcribe.py`) e medir WER em benchmark público (`eval_public_hf.py`).
- **Pipeline realtime** — inferência ao vivo (demo `mic_transcribe.py`; o runtime de produção é Rust em `crates/macaw-*`, fora deste escopo).
- **eval (transversal)** — harnesses de medição telefônica (`measure_*`) e builders de test set (`make_*`).
- **STALE-DO-NOT-USE** — sufixo que o próprio autor pôs em resultados telefônicos inválidos (38% obsoleto).

### Architecture boundaries affected

`rules/architecture.md § 5` reconhece dois estilos válidos: **package-by-layer** e **package-by-feature**.
Este plano adota **package-by-feature** dentro de `training/` (uma pasta por pipeline). Não cruza a
fronteira Rust↔Python (`crates/` permanece intocado). Não altera direção de dependência: os subdirs de
pipeline não importam uns aos outros (cada script é executável isolado); apenas o `conftest.py` os
expõe aos testes. `rules/architecture.md § 6` (anti-god-module) é respeitado — nenhum `utils/` genérico.

## Prior Art & Related Work

- **Interno — audit Staff-level:** `system-design-output/final_report.md § Top 3 risks` (B1 "production
  + smoke cluster share a flat dir", D1 "superseded not excisable", D3 "confirmed-buggy smoke kept
  beside production"). Este plano executa exatamente a remediação que aquele audit recomendou (deletion
  readiness), estendida de M4 (5 arquivos) para o estado M5 (25 arquivos).
- **Interno — regra de rotação:** `.claude/rules/audit-trail-rotation.md § What NEVER rotates` confirma
  que `knowledge-base/plans/`, `blueprints/`, `adrs/`, `CHANGELOG.md` nunca são apagados — o plano só
  toca em código/scripts/docs-de-pesquisa, nunca nesses.
- **Regra de projeto — layout:** `rules/architecture.md § 5` (package-by-feature) e `§ 6` (evitar
  `utils/helpers/common`). `rules/parsimony-ladder.md` (deletar > arquivar quando não há consumidor —
  YAGNI/Rule 9).
- **Patterns skills:** (none identified — não existe `skills/*-patterns/` neste repo; grep vazio).

## Dependencies

(none — este plano NÃO adiciona, remove nem atualiza qualquer dependência de runtime ou dev. É um
refactor de filesystem — `git mv`/`git rm` + um `conftest.py` que usa só stdlib (`sys`, `pathlib`).
Nenhum `requirements*.txt`, `pyproject.toml` de deps, `Cargo.toml` ou lockfile é tocado. `/deps-audit`
é N/A por ausência de superfície de dependência.)

## Objective

- [ ] Sub-goal 1 — 11 artefatos-ruído `.py`/`.md` + 2 testes órfãos + 2 arquivos STALE removidos do git (`git ls-files` não os retorna).
- [ ] Sub-goal 2 — 3 docs de pesquisa realocados para `docs/research/` (raiz do repo sem `deep-research-*` / `sota-techniques-*`).
- [ ] Sub-goal 3 — `training/` sem scripts soltos na raiz: todo `.py`/`.sh` vivo dentro de `finetune/`, `batch/`, `realtime/` ou `eval/`.
- [ ] Sub-goal 4 — `training/conftest.py` criado; `python3 -m pytest training/tests -q` = 0 failed / 0 errors.
- [ ] Sub-goal 5 — `training/README.md` mapeia as 3 pipelines (nome → o que resolve → arquivo de entrada).
- [ ] Sub-goal 6 — `system-design-output/` no `.gitignore`; `git status` limpo de ruído de disco.

## ADRs

### D1 — Agrupar `training/` por pipeline (package-by-feature)

**Decisão:** subdirs `finetune/`, `batch/`, `realtime/`, `eval/` em vez de um diretório plano.
**Rationale:** `.claude/rules/architecture.md § 5` lista package-by-feature como válido e "escala melhor";
o audit Staff-level de 2026-07-25 (`system-design-output/final_report.md`, finding B1) apontou o
diretório plano como o defeito estrutural nº 1. A meta do dono ("entender as pipelines em segundos") é
exatamente o que screaming-architecture por feature entrega.
**Alternativa rejeitada:** (a) **package-by-layer** (`prep/`, `train/`, `decode/`) — rejeitado: esconde a
noção de pipeline que o dono quer visível; (b) **manter plano + prefixos de nome** (`ft_prep_*`,
`batch_*`) — rejeitado: não resolve o cluster, só renomeia.
**Consequências:** habilita leitura em segundos; constrange scripts a rodarem via seu subdir (path do
script vira sys.path[0], mantendo cross-imports co-locados).

### D2 — Preservar imports via um único `training/conftest.py` (não editar cada `sys.path`)

**Decisão:** `conftest.py` na raiz de `training/` insere cada subdir de pipeline no `sys.path`; os testes
seguem importando por nome (`from batch_transcribe import …`).
**Rationale:** KISS (`.claude/rules/parsimony-ladder.md` rung 5). pytest auto-carrega `conftest.py` do
rootdir antes de coletar os testes; um arquivo centraliza o que seriam ~10 edições de `sys.path`
espalhadas (DRY). Não há pytest config hoje (sem `pyproject`/`pytest.ini`/`conftest`), então é aditivo.
**Alternativa rejeitada:** (a) **`pyproject.toml [tool.pytest] pythonpath`** — rejeitado: exige pytest ≥7
garantido e introduz um pyproject só para isso; conftest é mais universal; (b) **transformar em package
`macaw_train/` com `__init__.py` + imports qualificados** — rejeitado agora: reescreveria todos os
imports e os runbooks (YAGNI para o objetivo de organização; pode ser follow-up).
**Consequências:** testes verdes sem tocar em cada arquivo; scripts rodados como `python3
training/<pipe>/x.py` continuam achando co-módulos.

### D3 — Deletar (não arquivar) os superseded/one-offs

**Decisão:** `git rm` nos 11 arquivos + 2 testes órfãos + 2 STALE.
**Rationale:** decisão explícita do dono nesta sessão; `git` preserva o histórico recuperável; Rule 9 /
YAGNI (`.claude/rules/parsimony-ladder.md`) — código sem consumidor vivo é passivo. O audit Staff-level
(finding D3) classificou o smoke como "net liability".
**Alternativa rejeitada:** **arquivar em `training/archive/`** — oferecido ao dono, recusado (quer a
árvore mínima "FAANG-limpa").
**Consequências:** árvore mínima; se um script deletado for necessário, recupera-se por `git log
--follow` / `git show`.

### D4 — `callcenter/` e `results/` (exceto STALE) são invioláveis

**Decisão:** nunca `git mv`/`rm` em `callcenter/` (LGPD, nem versionado) nem em `results/*` que não
tenham o sufixo `STALE-DO-NOT-USE`.
**Rationale:** `CLAUDE.md` (LGPD) + `.claude/rules/audit-trail-rotation.md` (resultados medidos são registro).
**Alternativa rejeitada:** mover `results/` para dentro das pipelines — rejeitado: quebraria os paths
citados no paper/CLAUDE.md e nos registros de proveniência.
**Consequências:** proveniência dos números do paper preservada; zero risco LGPD.

## Drawbacks & Risks

| Drawback / Risco | Severidade | Mitigação | Owner |
|---|---|---|---|
| Mover módulos quebra cross-imports em runtime (ex.: `eval_public_hf`→`batch_transcribe`) | Alta | Co-locar módulos que se importam no MESMO subdir (D1); atualizar `sys.path.insert` hardcoded para o próprio dir; T-integração roda os scripts | Claude |
| Testes deixam de coletar por `sys.path` apontar para `training/` (sem os módulos) | Alta | `training/conftest.py` (D2) insere os subdirs; T2.1 tem teste RED que importa 1 módulo por pipeline | Claude |
| Deletar `prep_mls` sem deletar `prep_nemo` deixa import quebrado | Média | Deletar o par junto (Baseline: `prep_nemo.py:21`); T1.1 verifica `grep` de survivors | Claude |
| Paths citados no paper/CLAUDE.md (`training/batch_transcribe.py`) ficam obsoletos após o move | Média | T3.2 atualiza refs em `CLAUDE.md`, paper e `results/` no MESMO commit do move | Claude |
| `git mv` de `.sh` runbooks que referenciam `zipformer/train.py` (path da instância) | Baixa | Os runbooks referenciam paths da INSTÂNCIA GPU, não do repo — inalterados pelo move (Baseline) | Claude |
| Regressão silenciosa não coberta por teste (script sem teste, ex.: `bench_rtfx`) | Média | Fase de Integration Validation roda `--help`/import-smoke de cada script movido | Claude |

## Unresolved Questions

- Q1 — Existe um segundo `mic_transcribe.py` sob `models/…/` (citado no paper §10)? Se sim, o move do de
  `training/` não deve colidir — confirmar antes do T2.x que os dois são distintos (o de `models/` fica).
- Q2 — Algum notebook/CI externo (fora do repo) referencia `training/<script>.py` por path absoluto?
  Assumido "não" (nenhum CI no repo referencia; `grep` de skills/rules vazio) — se o dono souber de um
  consumidor externo, vira MUST-FIX.
- Q3 — `results/` deve ganhar subpastas por milestone além do atual? Fora de escopo deste plano
  (D4 congela `results/`); registrar como follow-up se o dono quiser.

## Dependency Graph

```
Phase 1 (noise removal) ──▶ Phase 2 (restructure) ──▶ Phase 3 (docs/refs) ──▶ Phase 4 (integration)
   │ deleta + realoca          │ git mv + conftest        │ README + refs        │ pytest full + smokes
   └─ independente do move      └─ precisa da árvore limpa  └─ precisa dos paths   └─ gate final
                                   antes de agrupar             finais
```

Phase 1 e a realocação de docs (T1.2) são independentes e poderiam paralelizar, mas rodam sequenciais
para manter commits atômicos por escopo.

---

## Phase 1: Remoção de ruído (deletar + realocar + gitignore)

**Objective:** remover do git todos os artefatos-ruído e realocar os docs de pesquisa, sem tocar em nada vivo.

### T1.1 — Deletar scripts superseded/one-off + testes órfãos + STALE

#### Objective
`git rm` nos 9 scripts/runbook M4-superseded, 2 testes órfãos e 2 arquivos STALE.

#### Why this step (action + reasoning)
1. **O que faz:** remove `prep_icefall.py`, `prep_mls.py`, `prep_nemo.py`, `prep_conformer_ctc_decode.py`,
   `patch_ctc_decode.py`, `resume_tagarela_feats.py`, `download_tagarela_subset.py`, `gen_phonemes.py`,
   `training/run_pilot_icefall.md`, `training/tests/test_prep_icefall.py`, `training/tests/test_gen_phonemes.py` e os 2
   `results/*.STALE-*`.
2. **Por que agora:** são a causa-raiz do defeito B1/D1/D3 do audit; deletar ANTES de reestruturar evita
   mover lixo. O dono decidiu deletar (D3). Nenhum survivor os importa (Baseline § Current callers).

#### Evidence
`system-design-output/final_report.md § 3` (inventário: `prep_icefall` = superseded, `gen_phonemes` =
smoke) · `prep_nemo.py:21` importa `prep_mls` (par) · `test_prep_icefall.py:17` importa `prep_icefall` ·
`ls training/results/*/*.STALE-telephone-38pct-DO-NOT-USE` (2 arquivos).

#### Files to edit
```
training/prep_icefall.py — git rm
training/prep_mls.py — git rm
training/prep_nemo.py — git rm
training/prep_conformer_ctc_decode.py — git rm
training/patch_ctc_decode.py — git rm
training/resume_tagarela_feats.py — git rm
training/download_tagarela_subset.py — git rm
training/gen_phonemes.py — git rm
training/run_pilot_icefall.md — git rm
training/tests/test_prep_icefall.py — git rm (teste do módulo deletado)
training/tests/test_gen_phonemes.py — git rm (teste do módulo deletado)
training/results/m4-small-baseline/recogs-test-epoch-30_avg-1.txt.STALE-telephone-38pct-DO-NOT-USE — git rm
training/results/m4-small-baseline/recogs-test-epoch-30_avg-10_use-averaged-model.txt.STALE-telephone-38pct-DO-NOT-USE — git rm
```

#### Deep file dependency analysis
Cada arquivo acima: sem consumidor vivo (Baseline § Current callers confirma que só os pares
deletados/testes órfãos os referenciam). Downstream: nenhum survivor importa esses nomes.

#### Deep Dives
- Invariante antes/depois: `python3 -m pytest training/tests -q` verde (os testes órfãos somem JUNTO com
  os módulos — a suíte não deve referenciar nome deletado).
- Edge case: se algum survivor importar um nome deletado, o `grep` de verificação FALHA a task.

#### TDD
- **RED/guarda (EC-1 — pega `from X import` E `import X`):** `grep -REn "^(from|import) (prep_icefall|prep_mls|prep_nemo|prep_conformer_ctc_decode|patch_ctc_decode|resume_tagarela_feats|download_tagarela_subset|gen_phonemes)\b" training/ --include='*.py' | grep -vE "tests/test_prep_icefall|tests/test_gen_phonemes|prep_nemo.py"` deve retornar **vazio** ANTES de deletar (prova que só os órfãos/pares deletados os usam). O padrão `import prep_mls` sozinho NÃO pega `from prep_mls import` — daí o `^(from|import)`.
- **GREEN:** após `git rm`, `python3 -m pytest training/tests -q` = 0 failed / 0 errors (coleta sem erro de import).

#### Acceptance criteria
- `git ls-files training/` não retorna nenhum dos 13 paths acima.
- `pytest training/tests` verde.

#### DoD
- `git status` mostra as 13 deleções staged; `pytest training/tests -q` sai 0.

### T1.2 — Realocar docs de pesquisa para docs/research/

#### Objective
Mover os 3 docs de pesquisa soltos da raiz para `docs/research/` via `git mv` (histórico preservado).

#### Why this step (action + reasoning)
1. **O que faz:** `git mv deep-research-arquiteturas-alternativas.md deep-research-asr-ptbr-cpu-realtime.md sota-techniques-asr-ptbr-cpu.md docs/research/`.
2. **Por que agora:** a raiz do repo é o primeiro contato do eng FAANG; docs de pesquisa soltos poluem o
   "topo legível". `docs/research/` é o lar semântico correto (`rules/architecture.md § 3` — coesão).

#### Evidence
`ls *.md` na raiz retorna os 3 além de `README/CHANGELOG/CLAUDE/PRD/ROADMAP`.

#### Files to edit
```
deep-research-arquiteturas-alternativas.md — git mv → docs/research/
deep-research-asr-ptbr-cpu-realtime.md — git mv → docs/research/
sota-techniques-asr-ptbr-cpu.md — git mv → docs/research/
docs/research/ (NEW dir) — criado pelo git mv
```

#### Deep file dependency analysis
Docs de leitura; se `README.md`/`CLAUDE.md` linkarem para eles por path relativo da raiz, T3.2 atualiza os links.

#### TDD
- **Guarda:** `grep -rl "deep-research-\|sota-techniques-asr" README.md CLAUDE.md ROADMAP.md docs/` lista os arquivos que citam esses paths → T3.2 os corrige. Nenhum código importa `.md`.
- **GREEN:** `test -d docs/research && ls docs/research/*.md | wc -l` = 3.

#### Acceptance criteria
- `ls *.md` na raiz não retorna mais `deep-research-*`/`sota-techniques-*`.

#### DoD
- 3 arquivos em `docs/research/`; raiz limpa.

### T1.3 — Higiene de gitignore

#### Objective
Adicionar `system-design-output/` ao `.gitignore` (é output de audit local, ignorado por convenção).

#### Why this step
1. **O que faz:** acrescenta uma linha a `.gitignore`.
2. **Por que agora:** `system-design-output/` já está ignorado por check-ignore mas não consta
   explicitamente; explicitar evita commit acidental do relatório local.

#### Evidence
`git check-ignore system-design-output` retorna o path (ignorado), mas não há entrada nomeada no `.gitignore` atual.

#### Files to edit
```
.gitignore — adicionar "system-design-output/" sob seção de outputs locais
```

#### TDD
- **GREEN:** `git check-ignore system-design-output/` retorna o path; `grep -q "system-design-output" .gitignore`.

#### Acceptance criteria
- `.gitignore` contém `system-design-output/`.

#### DoD
- `grep system-design-output .gitignore` casa.

---

## Phase 2: Reestruturar training/ por pipeline

**Objective:** mover cada script vivo para seu subdir de pipeline e garantir imports/testes verdes.

### T2.1 — Criar conftest.py e provar imports por pipeline (TDD RED→GREEN)

#### Objective
Adicionar `training/conftest.py` que expõe os subdirs de pipeline ao `sys.path`, com um teste que importa 1 módulo de cada pipeline.

#### Why this step (action + reasoning)
1. **O que faz:** cria `training/conftest.py` (insere `finetune/ batch/ realtime/ eval/` no `sys.path`) e
   `training/tests/test_pipeline_layout.py` que faz `from batch_transcribe import greedy`,
   `from prep_phoneme_head import apply_patch`, etc.
2. **Por que agora:** é o mecanismo (D2) que mantém os imports por nome funcionando DEPOIS do move. Escrever
   o teste ANTES do move o torna RED (módulos ainda na raiz → conftest aponta para subdirs vazios), e GREEN
   após T2.2 mover os arquivos. É a rede de segurança de toda a Fase 2.

#### Evidence
Testes atuais importam por nome via `sys.path.insert(0, parents[1])` (Baseline § Current callers); sem
`conftest.py`/pytest config no repo (Step 1).

#### Files to edit
```
training/conftest.py (NEW) — insere subdirs de pipeline no sys.path
training/tests/test_pipeline_layout.py (NEW) — importa 1 símbolo por pipeline (RED antes do move)
                                              + test_no_duplicate_module_basenames (EC-5)
                                              + import-por-nome resolve nos 2 CWDs (EC-4)
```

#### Deep Dives / Pseudo-code
```python
# training/conftest.py
import sys, pathlib
_root = pathlib.Path(__file__).parent
for _d in ("finetune", "batch", "realtime", "eval"):
    p = str(_root / _d)
    if p not in sys.path:
        sys.path.insert(0, p)
```
Invariante: conftest é carregado por pytest antes de coletar `tests/`; a ordem garante que
`from batch_transcribe import …` resolva via `training/batch/`.

#### TDD
- **RED:** `test_pipeline_layout.py` importando `from batch_transcribe import greedy` FALHA enquanto
  `batch_transcribe.py` estiver na raiz de `training/` (conftest aponta p/ `batch/` inexistente).
- **GREEN:** passa após T2.2.

#### Acceptance criteria
- `training/conftest.py` existe; `test_pipeline_layout.py` cobre os 3 pipelines + eval.

#### DoD
- Teste RED confirmado antes do move (evidência no log do `/implement`).

### T2.2 — git mv dos scripts vivos para os subdirs

#### Objective
Mover cada script para `finetune/`, `batch/`, `realtime/` ou `eval/`, co-locando módulos que se importam.

#### Why this step (action + reasoning)
1. **O que faz:** `git mv` conforme o mapa da Baseline (batch: `batch_transcribe`, `eval_public_hf`,
   `decode_onnx_local`, `bench_rtfx`; finetune: `prep_coraa`, `prep_tagarela`, `prep_finetune`,
   `prep_augment_datamodule`, `prep_phoneme_head`, `run_ft_*.sh`, `run_zipformer_ctc.sh`; realtime:
   `mic_transcribe`; eval: `measure_realcodec`, `measure_callcenter`, `make_telephone_test`,
   `make_callcenter_cuts`).
2. **Por que agora:** materializa D1. Co-locar pares que se importam (`eval_public_hf`↔`batch_transcribe`,
   `prep_finetune`↔`prep_phoneme_head`) preserva os cross-imports em runtime sem editar código.

#### Evidence
Baseline § Current callers (pares de import) + § Files that will be touched (destino por arquivo).

#### Files to edit
```
mkdir -p training/{finetune,batch,realtime,eval}           # EC-2: git mv exige dir-destino existir
# EC-3: ANTES de mover, extrair o grafo completo de imports intra-training e confirmar co-location:
#   grep -REn "^(from|import) [a-z_]+" training/*.py  → cada par (importador, importado) no MESMO subdir
git mv training/batch_transcribe.py training/batch/          # + eval_public_hf, decode_onnx_local, bench_rtfx
git mv training/prep_coraa.py training/finetune/             # + prep_tagarela, prep_finetune, prep_augment_datamodule, prep_phoneme_head, run_ft_*.sh, run_zipformer_ctc.sh
git mv training/mic_transcribe.py training/realtime/
git mv training/measure_realcodec.py training/eval/          # + measure_callcenter, make_telephone_test, make_callcenter_cuts
training/tests/test_no_cross_pipeline_imports.py (NEW)       # EC-3: assert nenhum par de import cai em subdirs diferentes
```

#### Deep file dependency analysis
`eval_public_hf.py:10 from batch_transcribe` → resolve porque ambos vão p/ `batch/`. Se
`eval_public_hf.py` tiver `sys.path.insert(0, ".../training")` hardcoded, T2.3 corrige.
`prep_finetune.py:34` / `prep_augment_datamodule.py:52 from prep_phoneme_head` → ambos p/ `finetune/`.
**EC-3 (co-location exaustiva):** os 2 pares acima foram achados por grep pontual; o grafo COMPLETO
(`grep -REn "^(from|import)"`) roda antes do move para garantir que nenhum outro par (ex.: `measure_*`
→ `decode_onnx_local`, `make_*` → finetune) caia cross-pipeline; se cair, ajustar o mapa de destino.

#### TDD
- **GREEN:** `test_pipeline_layout.py` (de T2.1) passa; `python3 -m pytest training/tests -q` = 0 failed.

#### Acceptance criteria
- `git ls-files training/ | grep -vE 'tests/|results/|conftest' | grep -v '/'` retorna **vazio** (nenhum script solto na raiz).

#### DoD
- Suíte verde; nenhum `.py`/`.sh` na raiz de `training/`.

### T2.3 — Corrigir sys.path hardcoded nos scripts movidos

#### Objective
Ajustar qualquer `sys.path.insert` com path absoluto/relativo a `training/` dentro dos scripts movidos.

#### Why this step
1. **O que faz:** troca inserts hardcoded (ex.: `sys.path.insert(0, "/…/jvscribe/training")` em
   `eval_public_hf.py`) para o dir do próprio arquivo, ou remove (script roda do seu subdir).
2. **Por que agora:** sem isso, rodar `python3 training/batch/eval_public_hf.py` procuraria
   `batch_transcribe` em `training/` (agora vazio) e falharia em runtime — não coberto pelos testes de import.

#### Evidence
`eval_public_hf.py` importa `batch_transcribe` e (na variante conhecida) insere o path de `training/`.

#### Files to edit
```
training/batch/eval_public_hf.py — corrigir/remover sys.path.insert
(demais scripts movidos — auditar cada um por sys.path hardcoded a "training/")
```

#### TDD
- **GREEN (smoke):** `python3 -c "import sys; sys.path.insert(0,'training/batch'); import eval_public_hf"` (import puro) sem erro; e no T4, execução de `--help` quando aplicável.

#### Acceptance criteria
- Nenhum script movido contém path absoluto a `training/` que quebre fora da CWD raiz.

#### DoD
- Import-smoke de cada script movido passa.

---

## Phase 3: Documentar as 3 pipelines + atualizar referências

**Objective:** tornar o topo do repo autoexplicativo e consertar paths citados que o move invalidou.

### T3.1 — training/README.md com o mapa das 3 pipelines

#### Objective
Criar `training/README.md` que apresenta cada pipeline no formato nome → problema que resolve → entrada.

#### Why this step
1. **O que faz:** escreve um README curto com uma tabela das 3 pipelines + eval, apontando o arquivo de entrada de cada uma.
2. **Por que agora:** é o artefato que cumpre a Goal ("entender em segundos"). Sem ele, a estrutura por pastas ajuda mas não é autoexplicativa.

#### Evidence
Goal do plano; `rules/public-copy.md` (README outcome-shaped).

#### Files to edit
```
training/README.md (NEW) — mapa das pipelines
```

#### TDD
- **GREEN:** `grep -q "finetune" training/README.md && grep -q "batch" && grep -q "realtime"`; markdownlint opcional.

#### Acceptance criteria
- README cita as 3 pipelines + eval com arquivo de entrada de cada.

#### DoD
- Arquivo existe e lista os entrypoints reais (paths resolvem).

### T3.2 — Atualizar referências de path invalidadas pelo move

#### Objective
Corrigir menções a `training/<script>.py` em `CLAUDE.md`, paper (`docs/paper/*`), `results/`, `README.md`.

#### Why this step
1. **O que faz:** `grep -rn "training/batch_transcribe\|training/eval_public_hf\|training/measure_\|training/prep_\|deep-research-\|sota-techniques-"` fora de `training/` e atualiza os paths para o novo local.
2. **Por que agora:** os números do paper citam `training/batch_transcribe.py` (§10) — proveniência quebra se o path sumir. Deve ir no MESMO PR do move (Drawback "paths obsoletos").

#### Evidence
Paper §10 lista `training/batch_transcribe.py`, `training/eval_public_hf.py`, `training/measure_*.py`.

#### Files to edit
```
docs/paper/macaw-voice-cpu-asr.md — paths de §10
docs/paper/macaw-voice-cpu-asr.pt-br.md — paths de §10
CLAUDE.md — refs a training/<script>
(qualquer results/*.md que cite os paths)
```

#### TDD
- **GREEN:** `grep -rn "training/batch_transcribe.py\|training/eval_public_hf.py" docs/ CLAUDE.md` só retorna paths NOVOS (`training/batch/…`).

#### Acceptance criteria
- Nenhuma referência a path antigo de script movido sobra em docs tracked.

#### DoD
- `grep` de paths antigos = vazio (fora do git history).

---

## Phase 4: Integration Validation (gate final)

**Objective:** provar que a reorganização não quebrou nada — a suíte inteira verde + smokes de execução.

### T4.1 — Suíte completa + smokes + build Rust

#### Objective
Rodar toda a validação de ponta a ponta.

#### Why this step
1. **O que faz:** `pytest training/tests` + `pytest scripts/tests` + import-smoke de cada script movido + `cargo build` (crates intocado, deve continuar verde) + verificação estrutural (topo legível).
2. **Por que agora:** é o gate "eat your own cooking" — o plano só está pronto quando o full-chain passa.

#### Evidence
`rules/cycle-implement.md § Integration validation`.

#### Files to edit
```
(nenhum — fase de verificação)
```

#### TDD / Verificação
```
python3 -m pytest training/tests scripts/tests -q          # 0 failed / 0 errors
for f in training/batch/*.py training/finetune/*.py training/realtime/*.py training/eval/*.py; do \
  python3 -c "import ast,sys; ast.parse(open('$f').read())"; done   # parse-smoke
cargo build --offline 2>/dev/null || cargo build            # crates inalterado
git ls-files training/ | grep -vE 'tests/|results/|README|conftest' | grep -v '/' | wc -l   # == 0
```

#### Acceptance criteria
- `pytest` verde; nenhum script solto na raiz de `training/`; `cargo build` OK; CHANGELOG atualizado.

#### DoD
- Todos os comandos acima saem 0; CHANGELOG `[Unreleased]` registra a reorganização.

---

## Coverage Matrix

| Requisito (do escopo) | Task(s) |
|---|---|
| (1) Deletar scripts superseded/one-off + testes órfãos | T1.1 |
| (1) Deletar arquivos STALE de results/ | T1.1 |
| (2) Realocar docs de pesquisa da raiz | T1.2 |
| (4) Higiene de gitignore (system-design-output) | T1.3 |
| (3) conftest para preservar imports | T2.1 |
| (3) Reestruturar training/ por pipeline (git mv) | T2.2 |
| (3) Corrigir sys.path hardcoded | T2.3 |
| Goal: 3 pipelines legíveis "em segundos" | T3.1 (README) + D1 (estrutura) |
| Não quebrar proveniência (paths do paper) | T3.2 |
| Meta-métrica: pytest 0 failed/0 errors | T2.1, T2.2, T4.1 |
| callcenter/ + results/ (não-STALE) invioláveis | D4 (invariante de todas as tasks) |

## Global Definition of Done

- [ ] `python3 -m pytest training/tests scripts/tests -q` = **0 failed / 0 errors**.
- [ ] `git ls-files training/ | grep -vE 'tests/|results/|README|conftest' | grep -v '/'` = **vazio** (nenhum script solto).
- [ ] 13 artefatos-ruído fora do git; 3 docs em `docs/research/`; `system-design-output/` no `.gitignore`.
- [ ] `training/README.md` mapeia as 3 pipelines com entrypoints que resolvem.
- [ ] Nenhuma referência a path antigo de script movido em docs tracked (`grep` vazio).
- [ ] `cargo build` verde (crates intocado).
- [ ] `callcenter/` intocado; `results/` sem alterações além dos 2 STALE.
- [ ] CHANGELOG `[Unreleased]` atualizado (Regra Inquebrável 6).
- [ ] Budget de LoC: nenhum arquivo novo > 500 LoC (README/conftest são pequenos).
