---
slug: m9-artifact-governance
version: 1.1
owner: Paulo
created_at: 2026-07-30
milestone_id: M9
generated_by: discover-plan
---

# Discovery Plan: Governança de artefato de modelo, CI e shared kernel

## Context

M9 nasceu da auditoria de system design de 2026-07-30
(`system-design-output/final_report.md`), que mediu três defeitos estruturais:

1. **Dois diretórios disputam o nome `model.int8.onnx`** com vocabulários de tamanhos
   diferentes (502 vs 503 linhas). Apontar para o errado **não gera erro** — gera
   transcrição silenciosamente errada. A armadilha já disparou: o 16,14% de WER no FLEURS
   publicado no CHANGELOG foi medido no modelo que o runtime **não** carrega.
2. **A suíte não roda fora da máquina do dono** — 157 testes Python + suíte Rust, e o
   próprio `CLAUDE.md` registra que `cargo test` verde é sinal falso porque testes de
   integração degradam com `SKIP` silencioso.
3. **7 implementações do colapso CTC e 5 `normalize_ptbr`** com semânticas incompatíveis,
   porque o teste-guarda proíbe import cross-pipeline sem oferecer um `common/` legítimo.

Antes de projetar a solução, é preciso saber **como runtimes de ASR maduros resolvem
exatamente isso** — o projeto tem regra explícita contra reinventar (Regra Inquebrável 9) e
contra decidir por convicção em vez de evidência
(`.claude/rules/asr-evidence-discipline.md` § 0).

## Objective

Produzir um blueprint que responda **como um runtime de ASR em produção declara e valida o
contrato do seu artefato de modelo**, **como um projeto multi-linguagem estrutura CI que
distingue teste executado de teste pulado**, e **onde ficam as fronteiras de um shared
kernel** — com evidência `[FONTE-REPO]` citável linha a linha.

**Critério de sucesso mensurável:** cada uma das 8 questões respondida com ao menos uma
citação `arquivo:linha` que **exibe o fato afirmado** (não vizinhança), e ≥ 1 ADR por
decisão de design que M9 terá de tomar.

## In-Scope / Out-of-Scope

### `knowledge-base/references/sherpa-onnx/`

> **Clone auditado (EC-1):** SHA `116a44e72c5bb631dcdbdb9c176f0304f5fc6fb0`, clonado em
> 2026-07-30 com `--depth 1 --filter=blob:none`. **Toda citação `arquivo:linha` deste plano
> e do blueprint resultante refere-se a este SHA.** Sem essa âncora, a evidência
> `[FONTE-REPO]` perde a reprodutibilidade que a torna mais forte que `[LITERATURA]`
> (`asr-evidence-discipline.md` § 1).

- **In scope:** `sherpa-onnx/csrc/` (contrato de modelo, symbol table, recognizers CTC,
  metadados), `cmake/` (fixação de dependência), `.github/workflows/` (forma do CI).
- **Out of scope, com razão explícita:**
  - `android/`, `ios-swift/`, `flutter/`, `dart-api-examples/`, `harmony-os/` — bindings de
    plataforma móvel; M9 não entrega app.
  - `sherpa-onnx/python/`, `sherpa-onnx/csrc/*tts*`, `*-vad-*`, `*speaker*` — TTS,
    diarização e VAD estão fora do escopo de M9.
  - `scripts/`, `docs/` — geração de release e site; não é contrato de artefato.

### Fontes web (allowlist `.claude/rules/discover-web-allowlist.txt`)

- **In scope:** `docs.github.com` (Actions — job status e condicionais), `k2-fsa.github.io`
  (documentação de export do icefall), `huggingface.co` (especificação de model card),
  `arxiv.org` (Model Cards for Model Reporting, Mitchell et al.).
- **Out of scope:** qualquer domínio fora da allowlist; blogs; conteúdo gerado por LLM.

## ADRs — decisões sobre COMO investigar

### D1 — Um peer profundo em vez de oito rasos

**Decisão:** investigar **apenas `sherpa-onnx`** entre os 8 peers catalogados.

**Alternativas rejeitadas:** (a) os 8 peers — 743 MB e diluição do sinal; (b) `icefall`
apenas — é framework de *treino*, não de runtime, e o contrato de artefato que M9 precisa é
de *carga*, não de export; (c) nenhum peer, só web — perderia a evidência `[FONTE-REPO]`,
que é mais forte que `[LITERATURA]` porque é reproduzível em disco.

**Racional:** `sherpa-onnx` é o caso de referência exato — runtime de ASR em produção, em
C++, que carrega modelos ONNX com `tokens.txt` a partir de um diretório, com 199 workflows
de CI. É o mesmo problema de M9 em um projeto que o resolveu em escala.

### D2 — Corner "Dependencies" recebe 1 questão, não 3

**Decisão:** alocar o mínimo (1) ao corner de dependências.

**Racional:** M9 **não adiciona dependência alguma** — o DoD é governança, CI e consolidação
de código já existente. A parsimony ladder (`.claude/rules/parsimony-ladder.md`, rung 4)
manda reusar o instalado. Investigar fixação de dependência tem valor apenas indireto (o que
o CI precisa pinar). Alocar 3 questões aqui roubaria orçamento dos corners que decidem
design.

### D3 — Orçamento de tempo por fonte

`sherpa-onnx`: 3 h. Web: 1 h. **Stop condition por questão:** se após 20 min uma questão não
tem citação `arquivo:linha` que exiba o fato, marcar `blocked` com o que foi tentado — nunca
inventar a resposta (`asr-evidence-discipline.md` § 4).

## Research Questions

Total: **8** questões · máx. 3 por corner · mín. 1 por corner. Todos os caminhos citados foram
verificados em disco no SHA `116a44e7` antes desta escrita.

| # | Question | Corner | Reference project(s) | Fase A (broad — ast-grep map) | Fase B (deep — Read at each hotspot) | Expected answer shape |
|---|---|---|---|---|---|---|
| Q1 | Quais arquivos compõem o contrato "diretório de modelo", e como o caminho é resolvido e validado na carga? | techniques | `knowledge-base/references/sherpa-onnx/` | `ast-grep run -p 'bool $NAME::Validate() const { $$$ }' --lang cpp knowledge-base/references/sherpa-onnx/sherpa-onnx/csrc/` para mapear os validadores | Read `csrc/offline-model-config.cc` (261 linhas) e `.h` (129) integralmente | Lista de arquivos obrigatórios + ponto exato onde a ausência é detectada, com `arquivo:linha` |
| Q2 | Como o symbol table (nosso `tokens.txt`) se relaciona com a dimensão de saída do modelo? Há validação, e qual o comportamento no mismatch? | techniques | `knowledge-base/references/sherpa-onnx/` | `grep -rn "NumSymbols\|vocab_size" knowledge-base/references/sherpa-onnx/sherpa-onnx/csrc/` para listar todos os pontos de uso | Read `csrc/symbol-table.h:57` e `csrc/offline-recognizer-ctc-impl.h` (347 linhas) em torno de `:188` | O trecho de validação com a mensagem de erro **ou** a constatação de que não há — as duas respostas valem, com igual honestidade |
| Q3 | Metadados do modelo (vocab, versão, features) são transportados por arquivo externo ou embutidos no ONNX? | techniques | `knowledge-base/references/sherpa-onnx/` | `grep -rln "meta_data\|GetModelMetadata" knowledge-base/references/sherpa-onnx/sherpa-onnx/csrc/` | Read `csrc/offline-sense-voice-model-meta-data.h` e `offline-canary-model-meta-data.h` | Mecanismo nomeado + trade-off (embutido vs externo) com citação |
| Q4 | Como as versões de dependência de build são fixadas, e o que isso informa sobre pinning no nosso `Cargo.toml`? | deps | `knowledge-base/references/sherpa-onnx/cmake/` | SKIP Fase A — text-shape. `grep -rn "URL_HASH\|GIT_TAG\|URL " knowledge-base/references/sherpa-onnx/cmake/` | Read `cmake/googletest.cmake` e `cmake/onnxruntime.cmake` | Padrão de fixação (tag, hash, URL) + se há verificação de integridade |
| Q5 | Qual a forma do CI de um projeto multi-linguagem — como separam matriz de build de execução de teste? | tools | `knowledge-base/references/sherpa-onnx/.github/workflows/` | SKIP Fase A — text-shape. **Amostra fixa (EC-2), não varrer os 199:** `ls .github/workflows/` só para taxonomia por prefixo | Read `.github/workflows/linux.yaml` (529 linhas) integralmente | Estrutura nomeada (matriz, jobs, gates) + como o teste é invocado |
| Q6 | O CI distingue teste **executado** de teste **pulado por falta de artefato**? Se não, como evitam o falso verde? | tools | `knowledge-base/references/sherpa-onnx/` | **Amostra fixa (EC-2):** `grep -rn "if:\|continue-on-error" .github/workflows/linux.yaml` + nos ≤3 workflows que casam `test\|style\|lint`; `grep -rl GTEST_SKIP knowledge-base/references/sherpa-onnx/sherpa-onnx/csrc/` | Read cada ocorrência em contexto | Mecanismo concreto **ou** asserção negativa que nomeia o que foi varrido (EC-3) — é o problema exato do nosso `scripts/test_report.sh` |
| Q7 | Como testam a fronteira modelo↔decoder sem baixar artefatos grandes no CI? | tests | `knowledge-base/references/sherpa-onnx/sherpa-onnx/csrc/` | `grep -c "TEST(" knowledge-base/references/sherpa-onnx/sherpa-onnx/csrc/*-test.cc` para inventário dos 22 | **Amostra de 3 (EC-2)**, os que não dependem de modelo: Read `csrc/context-graph-test.cc` (103), `circular-buffer-test.cc`, `cat-test.cc` | Estratégia nomeada (fixture sintética, download condicional, mock) com citação |
| Q8 | Que fixture determinística sustenta os testes de decode, e ela é versionada no repo? | tests | `knowledge-base/references/sherpa-onnx/` | `grep -rn "testdata\|fixture" knowledge-base/references/sherpa-onnx/sherpa-onnx/csrc/*-test.cc` | Read os pontos de construção de fixture encontrados | Onde a fixture vive, tamanho, e se é gerada ou versionada |

## Coverage Matrix

Every Coverage Corner MUST have at least one Research Question mapped to it.

| Corner | Questions mapped | Status |
|---|---|---|
| tests | Q7, Q8 | Covered |
| deps | Q4 | Covered — mínimo justificado por D2 |
| tools | Q5, Q6 | Covered |
| techniques | Q1, Q2, Q3 | Covered (teto) |

**Coverage: 4/4 corners covered (100%)** · 8 questões, dentro do orçamento 5-10.

## Halt-loop Checkpoints

Uma questão só pode ser marcada `done` quando:

1. A resposta cita ≥ 1 `arquivo:linha` **dentro de `knowledge-base/references/`** ou uma URL
   da allowlist, e
2. a linha citada **exibe o fato afirmado** — citar vizinhança é a falácia § 3 #2 da
   disciplina de evidência, e foi o vetor da falha de método já cometida neste projeto, e
3. a resposta declara o que **não** foi possível determinar, quando aplicável.

Uma questão vira `blocked` (não `done`) quando a fonte não contém a resposta. `blocked` com
razão é resultado válido; resposta plausível sem lastro não é.

### Checkpoints adicionais absorvidos do edge-case review

- **EC-3 — asserção negativa exige escopo nomeado.** Se a varredura amostral de Q6 não achar
  mecanismo de distinção skip-vs-run, a questão só pode ser `done` com a asserção negativa
  explícita — *"a amostra X, Y, Z não contém mecanismo W"* — nomeando o que foi varrido.
  Ausência **não observada** não é ausência (`asr-evidence-discipline.md` § 2).
- **EC-4 — Q3 pode ser respondível só pela metade.** Se os headers `*-model-meta-data.h`
  mostrarem apenas o **consumo** do metadata e não como ele é **gravado**, registrar resposta
  parcial e apontar o script de export correspondente — ou declarar que o export está fora do
  clone. Não inferir o mecanismo de escrita.

## Acceptance Criteria

- [ ] As 8 questões estão `done` ou `blocked` com razão explícita
- [ ] Todo caminho `knowledge-base/references/...` citado no blueprint resolve em disco
- [ ] Os 4 coverage corners aparecem populados no blueprint
- [ ] ≥ 1 ADR por decisão de design que M9 terá de tomar (contrato de artefato, forma do CI,
      fronteira do shared kernel)
- [ ] Toda afirmação numérica carrega rótulo de proveniência
      (`[MEDIDO]`/`[LITERATURA]`/`[FONTE-REPO]`/`[ESTIMATIVA]`/`[DESCONHECIDO]`)
- [ ] O blueprint declara explicitamente o que **não** foi investigado

## Global Definition of Done

Blueprint em `knowledge-base/discoveries/blueprints/m9-artifact-governance-blueprint.md`
com verdict ≥ `SHIPPABLE_WITH_CAVEATS` em `/discover-confidence`, conforme
`.claude/rules/discover-blueprint-golden-rule.md`.

## Regras de projeto citadas

- `.claude/rules/asr-evidence-discipline.md` — § 0 (discover contínuo), § 1 (rótulos de
  proveniência), § 3 #2 (generalizar sem parentesco), § 4 (honestidade sobre incerteza)
- `.claude/rules/architecture.md` — § 2 (DIP) e § 3 (coesão de módulo) delimitam onde o
  shared kernel pode morar sem violar a fronteira já validada dos crates
- `.claude/rules/testing.md` — § 5 (convenção de pareamento de teste) e § 6 (anti-patterns)
  balizam o que o CI de M9 tem de provar
- `.claude/rules/parsimony-ladder.md` — rung 4, base do ADR-D2
