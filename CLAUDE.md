# Macaw Voice — ASR PT-BR real-time em CPU

Transcritor de português brasileiro que roda **em tempo real, sobre CPU, no
notebook do atendente** — sem GPU, sem chamada de rede, sem custo por hora
transcrita. A aposta é **especialização**: um modelo que só faz PT-BR telefônico
cabe em dezenas de milhões de parâmetros onde um multilíngue de 600M não fecha
real-time.

Escopo do repositório: **o modelo** e **o motor de inferência**. Plataforma de
frota, compliance LGPD e UI estão fora (`PRD.md` § 3.2).

---

## ✅ Estado: M4 decidiu o finalista — Zipformer-CTC small (22M), int8 [ADR 0002]

**M4 (piloto de decisão) fechou a arquitetura por medição.** O ADR
`knowledge-base/adrs/0002-m4-architecture-finalist.md` (Aceito, 2026-07-27) trava
encoder/decoder/tamanho: **Zipformer-CTC `small` (22M), int8**. Fecha o que o ADR 0001
(M2) deixou a-medir. A escolha é output de ciclo (discover + piloto medido), não de
documento — exatamente como `.claude/rules/asr-evidence-discipline.md` § 0 exige.

**Como venceu `[MEDIDO]`** (mesmo corpus 161h / test FLEURS / decode `ctc-greedy-search`
/ máquina): head-to-head com params equivalentes → **Zipformer domina os dois eixos de
acurácia** (WER 28,86% vs Conformer 31,57%; CER 10,94% vs 11,90%). Curva WER×RTFx decide
o tamanho → **small domina** (mesmo CER ~11% do large 7× maior, RTFx 49-90× na i7-1355U
vs piso 6× do RNF-07; retornos decrescentes — regime data-bound R9). O 2º finalista
medido foi **Conformer-CTC (icefall)**, não FastConformer-NeMo (un-provisionable, 4+
falhas; trocado para eliminar confounds de framework). Evidência:
`training/results/m4-decision-161h-results.md`.

**Histórico `[MEDIDO]` de M2:** transducer/CTC é ~2× mais rápido que AED em CPU
(Zipformer 20M = 15,90 ± 2,06× vs Moonshine tiny 27M = 7,93 ± 0,72×, n=10) — a razão que
selecionou a família CTC/transducer e descartou Moonshine-AED antes do piloto de M4.

**Ainda a-medir (não travado pelo ADR 0002):** WER 8 kHz call center (penalidade 2-3×) e
o WER final são de **M5** (augmentação + dados); a **equivalência batch≡streaming** e o
treino causal são **M4-fase-3/M6** (de-riscados por construção no blueprint
`m6-streaming-causal-blueprint.md`, mas não medidos). A cabeça de fonema (M4 fase 3) está
em curso.

| Desbloqueado pelo ADR 0002 | Ainda a-medir (M4-fase-3 / M5 / M6) |
|---|---|
| Encoder/decoder final = **Zipformer-CTC small** — backend, export ONNX, formato de cache | WER 8 kHz call center (M5) + WER final |
| Runtime v0 (decoder CTC greedy em Rust) sobre o modelo travado | Equivalência batch≡streaming + treino causal (M4-fase-3/M6) |
| Hotwords / word spotter afinados ao decoder CTC escolhido | Ablação da supervisão fonética ≥3% (M4 fase 3, em curso) |

> **Nota de manutenção:** `.claude/rules/asr-evidence-discipline.md` § 0 (LOCKED) ainda
> descreve o estado pré-M4 ("nada de arquitetura escolhido"). Sua pré-condição —
> "M4 produza medição própria" — foi satisfeita pelo ADR 0002; atualizá-la exige um ADR
> próprio (protocolo de mudança de regra LOCKED). Pendente.

---

## Onde está o quê

| Documento | Papel |
|---|---|
| `PRD.md` | Requisitos (RF/RNF), arquitetura e pendências, riscos, questões abertas |
| `ROADMAP.md` | Milestones M0-M8 com DoD, dependências e riscos |
| `CHANGELOG.md` | Toda mudança relevante (Regra Inquebrável 6) |
| `.claude/rules/asr-evidence-discipline.md` | **Contrato de evidência** — leia antes de concluir qualquer coisa |
| `.claude/agents/README.md` | O time de 12 especialistas, papéis e alocação por fase |
| `knowledge-base/references/_catalog.md` | 8 peers clonados, licenças e o que estudar em cada |
| `knowledge-base/grills/` | Decisões tomadas, com racional e alternativas descartadas |
| `deep-research-*.md`, `sota-techniques-*.md` | Levantamento de estado da arte, com nível de verificação por fonte |

---

## Roteamento — qual agent para qual tarefa

Invoque pelo nome via Task/Agent. Detalhes de cada um em `.claude/agents/README.md`.

| Se a tarefa é… | Agent |
|---|---|
| Avaliar candidatos de arquitetura, desenhar o piloto, redigir o ADR de seleção | `asr-chief-scientist` |
| Verificar se um candidato é streaming de verdade; chunk, look-ahead, cache | `streaming-asr-scientist` |
| Auditar corpus, pseudo-labeling, filtro por concordância, vazamento treino/teste | `speech-data-scientist` |
| G2P, BPE, alvos da cabeça fonética, code-switching, erro por sotaque | `ptbr-phonetics-scientist` |
| Estimar ou medir RTFx, quantização int8, escolha de backend, profiling | `cpu-inference-engineer` |
| Captura, ring buffers, VAD, log-mel, afinidade de threads, soak test | `rust-runtime-engineer` |
| G.711, filtro telefônico, AGC, crosstalk, simulador de canal | `audio-dsp-engineer` |
| Viabilidade de hotwords e timestamps por família de decoder | `decoding-biasing-engineer` |
| Ambiente de treino, GPU preemptível, checkpoint/resume, custo por run | `ml-infra-engineer` |
| Protocolo de medição, WER por recorte, IC, p99, curva térmica | `evaluation-scientist` |
| Piso real da frota BYOD, tiering, CPUs sem AVX-VNNI | `hardware-validation-engineer` |
| Sequenciar trabalho, arbitrar dependência, proteger a decisão pendente | `technical-program-lead` |

**Divergência entre agents é resultado de valor.** Registre-a e nomeie o
experimento que a resolve — não dissolva por senioridade.

---

## Roteamento — qual skill para qual ciclo

Ciclo completo em `.claude/rules/cycle-*.md`. Lista completa de skills: `/plan-help`.

| Momento | Skill | Produz |
|---|---|---|
| Requisitos ainda vagos | `/grill-me {slug}` | Log de decisões em `knowledge-base/grills/` |
| Investigar prior art antes de decidir | `/discover-plan` → `/discover-edge-cases` → `/discover-plan-confidence` → `/discover-execute` → `/discover-confidence` | Blueprint em `knowledge-base/discoveries/blueprints/` |
| Planejar implementação | `/to-plan` → `/edge-case-plan` → `/deps-audit` → `/plan-confidence` | Plano em `knowledge-base/plans/` |
| Implementar plano aprovado | `/implement {slug}` | Commits com TDD + wiring triad |
| Auditar código pós-implementação | `/code-quality` | Auditoria em `knowledge-base/audits/` |
| Revisar antes do merge | `/review {slug}` | Findings por severidade |
| Cortar release | `/release` | Tag semver + PR `develop → main` |
| Adicionar feature ao roadmap | `/roadmap-feature` | Novo milestone em `ROADMAP.md` |

**M2 sai de um ciclo `/discover-*` completo**, não de conversa. É a razão de a
arquitetura estar pendente.

---

## Regras invioláveis deste projeto

Além das Regras Inquebráveis globais (`~/.claude/CLAUDE.md`):

**1. Todo número carrega rótulo de proveniência.** `[MEDIDO]` / `[LITERATURA]` /
`[ESTIMATIVA]` / `[DESCONHECIDO]`. Sem rótulo, o número não existe. Detalhes e
exigências por rótulo em `.claude/rules/asr-evidence-discipline.md` § 1.

**2. Hipótese, evidência e conclusão são seções distintas.** Conclusão que excede a
evidência é defeito de severidade máxima — mesmo quando a conclusão se prova certa
depois.

**3. As 12 falácias de `asr-evidence-discipline.md` § 3 são motivo de recusa.** As
que mais aparecem aqui: usar benchmark de GPU para justificar CPU; generalizar
entre arquiteturas sem parentesco; reportar média sem p99; benchmark curto em chip
U; tratar WER público como equivalente a call center 8 kHz.

**4. `knowledge-base/references/` é read-only.** Material de estudo clonado.
Achados vão para `knowledge-base/discoveries/blueprints/`. Exceção: metadados do
projeto com prefixo `_` na raiz (ex.: `_catalog.md`). Dois hooks enforçam isso.

**5. Pseudo-label nunca entra no test set.** Mede concordância com o professor, não
acurácia (`PRD.md` § 7.3).

---

## Contexto que evita erros repetidos

**O risco dominante é o corpus, não a arquitetura.** 8.972 h disponíveis contra as
15.000-94.000 h que a receita de referência usa para modelos monolíngues pequenos —
num regime (treino do zero) que a própria fonte identifica como o que *mais* precisa
de dados. Q-09 (acesso às ~76k h brutas do Cem Mil Podcasts) vale mais para o WER
final do que qualquer escolha de encoder.

**O orçamento de CPU é do pipeline, não do modelo.** Taxas somam pelo inverso: ASR
a 3× somado a diarização a 3× dá 1,5×. Por isso RNF-07 exige ASR isolado ≥ 6×
(`PRD.md` § 6).

**Máquina de referência ≠ piso da frota.** Todo dimensionamento assume um i7-1355U
medido; o parque BYOD real é desconhecido (Q-01) e provavelmente muito pior.
Extrapolar do notebook de referência para "a frota" é a falácia mais provável neste
projeto.

**No caso 1:1 — o dominante — diarização não precisa existir.** Mic é o atendente
por construção, loopback é o cliente. Roteamento de stream, custo zero, acurácia
100%. Modelo de diarização só entra no caso de 3 falantes.
