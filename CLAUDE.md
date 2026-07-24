# Macaw Voice — ASR PT-BR real-time em CPU

Transcritor de português brasileiro que roda **em tempo real, sobre CPU, no
notebook do atendente** — sem GPU, sem chamada de rede, sem custo por hora
transcrita. A aposta é **especialização**: um modelo que só faz PT-BR telefônico
cabe em dezenas de milhões de parâmetros onde um multilíngue de 600M não fecha
real-time.

Escopo do repositório: **o modelo** e **o motor de inferência**. Plataforma de
frota, compliance LGPD e UI estão fora (`PRD.md` § 3.2).

---

## ⏸ Estado travado: discover contínuo

**Nada de arquitetura está escolhido.** Encoder, decoder, tokenização e tamanho
seguem `PENDENTE` (`PRD.md` § 8.1) até M2 produzir blueprint + ADR e M4 produzir
medição própria.

O default de qualquer sessão é **investigar e medir**, não escolher. Escrever
"vamos de X" em qualquer artefato antes do ADR de M2 é violação de
`.claude/rules/asr-evidence-discipline.md` § 0 — mesmo que X venha a ganhar depois.

| Liberado hoje | Bloqueado por M2 |
|---|---|
| Captura mic + loopback, VAD, ring buffers, log-mel, afinidade de threads | Decoder |
| Harness de medição dos RNFs | Hotwords / word spotter |
| Corpus, augmentação, manifests (M3, paralelo) | Backend do encoder |
| Test set de call center e protocolo de avaliação | Formato de estado/cache do modelo |

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
