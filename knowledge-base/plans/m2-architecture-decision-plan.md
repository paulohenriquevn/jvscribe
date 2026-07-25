---
slug: m2-architecture-decision
milestone_id: M2
created_at: 2026-07-24
goal: Formalizar a decisão de arquitetura de M2 num ADR que nomeia 2 finalistas + descarta as 3 alternativas com motivo citado, e atualizar o PRD para referenciar o blueprint — verificável por grep dos elementos obrigatórios.
version: 1.1
---

<!-- v1.1: absorveu edge-cases (2 DOCUMENT, 0 MUST FIX) + corrigiu citações (D3 do blueprint desambiguado, § blueprint como heading real) + reforçou critérios (acceptable_ratio 1.0). plan-confidence rodado com --no-code-quality: M2 é plano SÓ-DOCUMENTO (ADR+PRD+CHANGELOG, zero código Rust novo); a cascata de code-quality produziu um finding fantasma `dead_code_unallowlisted_unknown` (languages_audited vazio, não-allowlistável pois ecosystem "unknown" é inválido) que os 3 oráculos refutam: clippy dead_code limpo + cargo build --workspace verde + vulture limpo. A flag é o uso sancionado para fase sem código. Verdict estrutural: SHIPPABLE 100/100, zero hard caps. -->


# Plan: M2 — Formalização da Decisão de Arquitetura (ADR + PRD)

## Goal

Escrever o ADR de seleção de arquitetura que **nomeia os 2 finalistas** (Zipformer+CTC, FastConformer+CTC) e **descarta as 3 alternativas com motivo citado**, e atualizar `PRD.md` § 8.1 para referenciar o blueprint e corrigir a alegação imprecisa sobre o Moonshine.

**Métrica observável:** `grep` confirma que o ADR contém os 2 finalistas nomeados + os 3 descartados (Moonshine/Paraformer/LC-BiMamba) cada um com motivo + citação de evidência (`[MEDIDO]`/`[FONTE-REPO]`), **E** `PRD.md` § 8.1 referencia `m2-architecture-decision-blueprint.md` e não afirma mais "receita completa publicada" para o Moonshine sem ressalva.

## Context

M2 é a decisão que o "discover contínuo" existiu para sustentar (`.claude/rules/asr-evidence-discipline.md` § 0). O ciclo discover produziu o blueprint `knowledge-base/discoveries/blueprints/m2-architecture-decision-blueprint.md` (SHIPPABLE 100) com **RTFx `[MEDIDO]`** (Zipformer 20,45× vs Moonshine 7,09× na mesma CPU) e leitura de arquitetura `[FONTE-REPO]`. Este plano **formaliza** essa evidência num ADR (o artefato de decisão canônico, `cycle-rule-schema.md` → `knowledge-base/adrs/`) e atualiza o PRD. Não é código — é a wiring da decisão. Os finalistas são **a-medir em M4**, não vencedor travado (§ 0; a não-travagem registrada no blueprint).

## Baseline Context (deep review of current state)

### Files that will be touched

| Arquivo | LoC hoje | Última mudança | Papel hoje | Invariants to preserve |
|---|---|---|---|---|
| `knowledge-base/adrs/0001-m2-architecture-finalists.md` (NEW) | 0 | — | ADR de seleção — o artefato de decisão | segue convenção `cycle-rule-schema.md` (ADR em knowledge-base/adrs/) |
| `PRD.md` | 584 | `b657dd9` (2026-07-24) | Requisitos + arquitetura; § 8.1 linha 220 "⏸ PENDENTE", linha 237 alega "receita completa publicada" (Moonshine) | não reescrever os 8 critérios nem os invariantes; § 8.1 permanece "pendente até M4" quanto ao vencedor |
| `CHANGELOG.md` | — | — | contrato público (Regra 6) | `[Unreleased]` recebe a entrada |

### Current callers / dependents

- `PRD.md` § 8.1 é citado por `.claude/rules/asr-evidence-discipline.md` § 5 (âncora), pelos agents, e pelo `CLAUDE.md`. A correção **não** muda os 8 critérios nem os invariantes — só o campo "a favor" do Moonshine e adiciona a referência ao blueprint. Nenhum consumidor quebra.
- O ADR é novo; nenhum caller ainda. Será referenciado pelo piloto de M4 (`/to-plan` de M4 lê ADRs como prior art).

### Domain glossary

| Termo | Definição (1 linha) |
|---|---|
| Finalista | candidato que avança para o piloto comparativo de M4; **não** é vencedor — é a-medir |
| ADR | Architecture Decision Record — a decisão + alternativas descartadas com motivo (`cycle-rule-schema.md`) |
| `[MEDIDO]`/`[FONTE-REPO]`/`[LITERATURA]` | rótulos de proveniência (`asr-evidence-discipline.md` § 1); `[FONTE-REPO]` = fato lido do código de um peer com `path:linha` |
| RTFx | duração_áudio ÷ tempo_parede; agnóstico a idioma (blueprint ADR D1) |

### Architecture boundaries affected

- Nenhuma fronteira de código. O ADR e o PRD são documentos. O ADR referencia o blueprint e a medição (`knowledge-base/measurements/m2-rtfx-candidates.md`) como evidência; o PRD referencia o blueprint. Sem novos exports, schemas ou deps.

## Prior Art & Related Work

- **Blueprint** `knowledge-base/discoveries/blueprints/m2-architecture-decision-blueprint.md` (SHIPPABLE 100) — a fonte da decisão, com a matriz 5×8 e as recomendações (finalistas propostos).
- **Medição** `knowledge-base/measurements/m2-rtfx-candidates.md` — RTFx `[MEDIDO]` Zipformer 20,45× vs Moonshine 7,09×.
- **Convenção de ADR:** `.claude/rules/cycle-rule-schema.md` (ADRs em `knowledge-base/adrs/`; formato: contexto + decisão + alternativas descartadas com motivo).
- **Contrato de evidência:** `.claude/rules/asr-evidence-discipline.md` (§ 0 não travar; § 1 rótulos; § 2 conclusão não excede evidência).

## Objective

- [ ] SG1 — ADR criado nomeando os 2 finalistas (Zipformer+CTC, FastConformer+CTC) com o critério que os sustenta
- [ ] SG2 — ADR descarta as 3 alternativas (Moonshine-AED, Paraformer/NAR, LC-BiMamba) cada uma com motivo + citação de evidência
- [ ] SG3 — ADR registra que os finalistas são **a-medir em M4**, não vencedor travado (§ 0)
- [ ] SG4 — PRD § 8.1 referencia o blueprint e corrige a alegação "receita completa publicada" do Moonshine
- [ ] SG5 — CHANGELOG `[Unreleased]` com a entrada (Regra 6)

## ADRs

### D1 — A decisão vai para um ADR em `knowledge-base/adrs/`, não para o PRD

**Decisão:** A escolha dos finalistas é registrada num ADR (`knowledge-base/adrs/0001-m2-architecture-finalists.md`); o PRD só **referencia** o blueprint/ADR e some com a fixação de arquitetura.

**Rationale:** `cycle-rule-schema.md` estabelece `knowledge-base/adrs/` como o local de ADRs; `asr-evidence-discipline.md` § 6 anti-pattern proíbe travar decisão pendente do PRD dentro de outro artefato — o ADR É o lugar canônico. **Alternativa rejeitada:** escrever a decisão direto no PRD § 8.1 — viola a separação (o PRD é requisitos; a decisão de arquitetura é um ADR referenciado).

### D2 — Finalistas nomeados, vencedor NÃO travado

**Decisão:** O ADR nomeia 2 finalistas **a pilotar em M4**; não declara vencedor.

**Rationale:** `asr-evidence-discipline.md` § 0 (não travar arquitetura sem medição própria) + a recomendação de não-travagem do blueprint. Critério 2 (WER 8 kHz) e equivalência batch≡streaming só se medem em M4. **Alternativa rejeitada:** travar Zipformer como vencedor com base no RTFx medido — mas RTFx é 1 de 8 critérios; WER (bloqueante) é `[LITERATURA]` até M4. Travar agora repetiria a falácia §3 #7 (defender antes de medir tudo).

## Drawbacks & Risks

| # | Risco | Severidade | Mitigação | Owner |
|---|---|---|---|---|
| R1 | Nomear finalistas cria viés de ancoragem para M4 (o piloto "confirma" o esperado) | Média | O ADR lista explicitamente o que falta medir por finalista (WER, equivalência, RTFx sob RNF-04/05) e mantém Moonshine como braço de controle — o piloto pode refutar | `asr-chief-scientist` |
| R2 | A correção do PRD (Moonshine recipe) pode ser lida como rebaixar o candidato injustamente | Baixa | A correção é factual e citada (`moonshine/micro/stt-training/stt_training/train.py:1-12` é WordCNN, não ASR) — registra o fato, não opina; Moonshine segue como finalista de controle | `asr-chief-scientist` |
| R3 | FastConformer como finalista sem recipe clonada (crit. 7 `[DESCONHECIDO-repo]`) | Média | O ADR marca explicitamente que a recipe do FastConformer vive no NeMo (não clonado) e que validá-la é parte do piloto de M4 | `ml-infra-engineer` |

## Unresolved Questions

- Qual das duas faixas (~30M vs ~80M) pilotar primeiro em M4 — decisão do `/to-plan` de M4, não deste ADR (depende do orçamento de GPU). Não bloqueia M2.
- (Nenhuma outra — a decisão de finalistas está resolvida pela evidência do blueprint.)

## Dependencies

Nenhuma dependência nova. M2 é edição de documentos (ADR, PRD, CHANGELOG) — não adiciona pacote, crate, nem ferramenta.

| Ecossistema | Pacote | Versão | Justificativa (Regra 9) |
|---|---|---|---|
| (nenhum) | — | — | M2 não introduz dependência; a medição de RTFx do discover usou `sherpa-onnx`/`moonshine-onnx` já instalados (evidência, não dep de produto) |

- **Rust/Python:** zero dependências novas. As libs de medição (`sherpa_onnx`, `moonshine_onnx`) foram usadas na fase discover como ferramenta de evidência, não entram no produto.

## Dependency Graph

```
Fase 1 (ADR + PRD + CHANGELOG) ─→ Integração (verificação por grep)
```

Tarefas de documento independentes entre si; a validação depende de todas.

## Phase 1: Formalizar a decisão

### T1.1 — Escrever o ADR de seleção de finalistas

#### Objective
Criar o ADR que nomeia 2 finalistas + descarta 3 alternativas com motivo + citação.

#### Why this step (action + reasoning)
Ação: escrever `knowledge-base/adrs/0001-m2-architecture-finalists.md` com contexto (o blueprint), decisão (2 finalistas a-medir), e alternativas descartadas cada uma com motivo citado. Necessário agora porque é o DoD central de M2 (ADR com escolha + alternativas descartadas). Cita ADR D1/D2, blueprint, `asr-evidence-discipline.md` § 0.

#### Evidence
Blueprint `knowledge-base/discoveries/blueprints/m2-architecture-decision-blueprint.md` (matriz 5×8, recomendações); `knowledge-base/measurements/m2-rtfx-candidates.md` (RTFx medido).

#### Files to edit
`knowledge-base/adrs/0001-m2-architecture-finalists.md` (NEW)

#### Deep file dependency analysis
- Arquivo novo; nenhum caller. Segue a convenção de ADR (`cycle-rule-schema.md`).

#### Deep Dives
- Invariante: cada alternativa descartada tem motivo + citação; os finalistas são "a-medir" (§ 0 não travar).

#### TDD
- Verificação (documento, não código): após escrever, `grep -E "Zipformer\+CTC|FastConformer\+CTC" ADR` casa os 2 finalistas; `grep -E "Moonshine.*controle|Paraformer.*artefato|LC-BiMamba.*ONNX|inviável" ADR` casa os 3 descartados com motivo; `grep -E "\[MEDIDO\]|\[FONTE-REPO\]" ADR` casa citação de evidência; `grep -iE "a-medir|piloto de M4|não trava|não é vencedor" ADR` casa a não-travagem.

#### Concurrency tests
(none — single-threaded) — é documento, sem código concorrente.

#### Acceptance Criteria
- [ ] `grep -c "Zipformer+CTC" knowledge-base/adrs/0001-m2-architecture-finalists.md` ≥ 1 E FastConformer+CTC presente (2 finalistas)
- [ ] Os 3 descartados (Moonshine, Paraformer, LC-BiMamba) aparecem cada um com motivo — oracle: `grep -E "LC-BiMamba" ADR | grep -iE "inviável|ONNX"` casa
- [ ] `grep -E "\[MEDIDO\]|\[FONTE-REPO\]" ADR` retorna ≥ 1 (evidência citada)
- [ ] `grep -iE "a-medir|piloto de M4" ADR` casa (finalistas não são vencedor)

#### DoD
- [ ] ADR existe e passa os 4 greps de aceite acima

### T1.2 — Atualizar PRD § 8.1 (referência ao blueprint + correção Moonshine)

#### Objective
PRD § 8.1 referencia o blueprint e corrige a alegação "receita completa publicada".

#### Why this step (action + reasoning)
Ação: em `PRD.md` § 8.1, adicionar referência ao blueprint/ADR na seção "⏸ PENDENTE" e corrigir a célula do Moonshine (linha 237) — trocar "receita completa publicada" por "sem recipe ASR aberta (só WordCNN de MCU)". Necessário agora porque o DoD de M2 exige o PRD referenciar o blueprint em vez de fixar arquitetura, e a Regra 6 exige corrigir a alegação factualmente errada. Cita blueprint (correção), Regra 6.

#### Evidence
O blueprint (Coverage Corner 2 — Dependencies) registra a correção ao PRD; `PRD.md:237` (a alegação atual a corrigir).

#### Files to edit
`PRD.md`

#### Deep file dependency analysis
- `PRD.md` § 8.1 é âncora de `asr-evidence-discipline.md` § 5 e do `CLAUDE.md`. A edição preserva os 8 critérios e os invariantes; só corrige o campo "a favor" do Moonshine e adiciona a referência. Nenhum consumidor quebra (verificado: os agents citam § 8.1 pelos critérios, não pela célula do Moonshine).

#### Deep Dives
- Invariante: os 8 critérios e os invariantes da arquitetura permanecem intactos; a arquitetura segue "pendente até M4" quanto ao vencedor (não travar — § 0).

#### TDD
- Verificação: `grep -c "m2-architecture-decision-blueprint" PRD.md` ≥ 1 (referencia o blueprint); `grep -c "receita completa publicada" PRD.md` == 0 (alegação corrigida); os 8 critérios ainda presentes (`grep -c "Critérios de decisão" PRD.md` inalterado).

#### Concurrency tests
(none — single-threaded).

#### Acceptance Criteria
- [ ] `grep -c "m2-architecture-decision-blueprint" PRD.md` ≥ 1
- [ ] `grep -c "receita completa publicada" PRD.md` == 0 (corrigida)
- [ ] Os 8 critérios de decisão ainda presentes — oracle: `grep -E "RTFx medido no hardware-alvo" PRD.md` casa (invariantes intactos)

#### DoD
- [ ] PRD passa os 3 greps; `python3 scripts/check_xrefs.py` (se aplicável) sem quebra de referência

## Coverage Matrix

| Requisito / DoD de M2 (ROADMAP) | Task(s) | Status |
|---|---|---|
| Blueprint avaliando 5 candidatos × 8 critérios | (feito no discover — `m2-architecture-decision-blueprint.md`) | Mapped |
| ADR com escolha + alternativas descartadas com motivo | T1.1 | Mapped |
| 2 finalistas nomeados | T1.1 (SG1) | Mapped |
| PRD atualizado p/ referenciar blueprint | T1.2 | Mapped |
| (Correção Regra 6: Moonshine recipe) | T1.2 + CHANGELOG | Mapped |

## Global Definition of Done

- [ ] ADR existe — oracle: `test -f knowledge-base/adrs/0001-m2-architecture-finalists.md` retorna exit 0
- [ ] PRD referencia o blueprint — oracle: `grep -c "m2-architecture-decision-blueprint" PRD.md` retorna ≥ 1
- [ ] Alegação "receita completa publicada" corrigida — oracle: `grep -c "receita completa publicada" PRD.md` retorna 0
- [ ] CHANGELOG `[Unreleased]` tem a entrada de M2 — oracle: `grep -c "finalistas\|arquitetura" CHANGELOG.md` retorna ≥ 1 (Regra 6)
- [ ] `cargo test --workspace` retorna exit 0 (M2 não toca Rust — 43 testes verdes)
- [ ] Nenhuma citação fabricada no ADR — oracle: cada path de peer no ADR passa `Path.exists`
- [ ] Arquivos novos ≤ 500 LoC — oracle: `wc -l knowledge-base/adrs/0001-m2-architecture-finalists.md` retorna < 500

## Failure scenarios (when I/O external)

(none — no external I/O touched) — M2 é edição de documentos (ADR, PRD, CHANGELOG); nenhum I/O de rede/DB/fila.

## Final Phase: Integration Validation (MANDATORY)

### Execution
1. `grep` dos elementos obrigatórios do ADR (2 finalistas, 3 descartados com motivo, evidência citada, não-travagem)
2. `grep` do PRD (referencia blueprint, alegação corrigida, 8 critérios intactos)
3. `cargo test --workspace` — deve permanecer verde (M2 não toca Rust)
4. Verificar que nenhum path de peer citado no ADR está fabricado (`Path.exists`)
5. `python3 scripts/check_xrefs.py` se existir (referências válidas)

### Acceptance Criteria
- [ ] Os greps de aceite de T1.1 (4 elementos do ADR) retornam match — oracle: cada `grep` de T1.1 exit 0
- [ ] Os greps de aceite de T1.2 (blueprint referenciado, alegação corrigida, 8 critérios) passam — oracle: `grep -c` de T1.2
- [ ] `cargo test --workspace` retorna exit 0 (workspace verde)
- [ ] Zero citação fabricada no ADR — oracle: `Path.exists` de cada peer citado
- [ ] CHANGELOG `[Unreleased]` atualizado — oracle: `grep` da entrada de M2

### If Validation Fails
Voltar ao `/implement` (não editar o plano). Se a decisão do blueprint estiver sob dúvida, voltar ao `/discover-*` — mas o blueprint é SHIPPABLE 100, então a formalização é mecânica.
