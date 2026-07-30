# Macaw Voice — ASR PT-BR real-time em CPU

Transcritor de português brasileiro que roda **em tempo real, sobre CPU, no
notebook do atendente** — sem GPU, sem chamada de rede, sem custo por hora
transcrita. A aposta é **especialização**: um modelo que só faz PT-BR telefônico
cabe em dezenas de milhões de parâmetros onde um multilíngue de 600M não fecha
real-time.

Escopo do repositório: **o modelo** e **o motor de inferência**. Plataforma de
frota, compliance LGPD e UI estão fora (`PRD.md` § 3.2).

---

## ✅ Estado: M4 decidiu o finalista — Zipformer-CTC medium (64M), int8 [ADR 0003 supersede 0002]

**M4 (piloto de decisão) fechou a arquitetura por medição.** O finalista é
**Zipformer-CTC `medium` (64M), int8, + cabeça de fonema auxiliar** —
`knowledge-base/adrs/0003-m4-finalist-medium.md` (Aceito), que **supersede o eixo tamanho**
do ADR 0002 (`small`) após medição de soak/carga. Fecha o que o ADR 0001 (M2) deixou
a-medir. A escolha é output de ciclo (discover + piloto medido + soak), não de documento.

**Como venceu `[MEDIDO]`** (mesmo corpus 161h / test FLEURS / decode `ctc-greedy-search`):
head-to-head com params equivalentes → **Zipformer domina Conformer nos dois eixos de
acurácia** (WER 28,86% vs 31,57%, IC95% do delta [2,11, 3,31] exclui 0). O **tamanho** foi
decidido por **soak RNF-04 + carga RNF-05** na i7-1355U: sob a condição-alvo (carga
concorrente) small e medium **empatam** em RTFx (min 7,1× vs 7,6×, ambos ≥6×); isolado o
small é só 1,15× mais rápido (não 2× — o RTFx do medium no ADR 0002 estava subestimado
~2×). Empatado o RTFx, o desempate migra para acurácia → **medium ganha −1,11pp WER**.
A cabeça de fonema **transferiu ao medium** `[MEDIDO]`: WER 28,86% → **27,49%** (−4,74%
rel, IC95% [2,79, 6,72], P(≥3%)=95,7%) — o **deliverable final de M4** é o medium+fonema,
27,49% WER / 10,53% CER wideband (`training/results/m4-medium-phoneme-ablation-results.md`,
modelo em `models/m4-final-medium-phoneme/`). Evidência de decisão:
`training/results/m4-decision-161h-results.md`, `soak-small-vs-medium-results.md`.

**Histórico `[MEDIDO]` de M2:** transducer/CTC é ~2× mais rápido que AED em CPU
(Zipformer 20M = 15,90 ± 2,06× vs Moonshine tiny 27M = 7,93 ± 0,72×, n=10) — a razão que
selecionou a família CTC/transducer e descartou Moonshine-AED antes do piloto de M4.

**Ainda a-medir (não travado pelo ADR 0002):** WER 8 kHz call center (penalidade 2-3×) e
o WER final são de **M5** (augmentação + dados); a **equivalência batch≡streaming** e o
treino causal são **M4-fase-3/M6** (de-riscados por construção no blueprint
`m6-streaming-causal-blueprint.md`, mas não medidos). A cabeça de fonema (M4 fase 3)
**concluiu**: −4,63% relativo de WER (29,97% → 28,58%), DoD ≥3% atingida no ponto (PASS
com nota, IC fronteiriço [2,63%, 6,63%]).

| Desbloqueado pelo ADR 0002 | Ainda a-medir (M4-fase-3 / M5 / M6) |
|---|---|
| Encoder/decoder final = **Zipformer-CTC small** — backend, export ONNX, formato de cache | WER 8 kHz call center (M5) + WER final |
| Runtime v0 (decoder CTC greedy em Rust) sobre o modelo travado | Equivalência batch≡streaming + treino causal (M4-fase-3/M6) |
| Hotwords / word spotter afinados ao decoder CTC escolhido | Ablação da supervisão fonética: **concluída** (−4,63% rel, PASS com nota) |

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

**A arquitetura está correta — o gargalo de M5 é dado/generalização `[MEDIDO]`.** O
finetune M5 faz *overfitting*, não *underfitting*: no melhor ponto de cada época
(logo após o reshuffle) train ctc ≈ val ctc (~0,23 ≈ 0,23), mas **dentro de cada
época** a val loss sobe acima da train (0,23 → 0,29-0,34) e o WER no CORAA humano
degrada. Overfitting **prova que a capacidade do encoder é suficiente** — um modelo
pequeno demais faria o oposto. Logo, não se muda a arquitetura (seria retrabalho
contra a medição de M4); o tamanho 64M é o **certo dado o constraint** RNF-07 (≥6×
RTFx em CPU) — `large`/`XL` violariam real-time. A alavanca é **dado (qualidade >
quantidade**, pois o overfitting é ao ruído dos pseudo-rótulos Whisper do TAGARELA).

**Antes de colher dado novo (caro), 3 alavancas grátis atacam o MESMO overfitting `[ESTIMATIVA]`:**

1. **Augmentação LIGADA** — o run de convergência de M5 rodou com `--enable-musan 0`
   e telephone off (para isolar a convergência primeiro). Religar a cadeia
   Reverb→Noise→Telephone (ADR D2 do plano M5, já preparada) + SpecAugment mais
   forte + weight decay é **regularização que reduz overfitting de graça**. Bônus:
   ataca também o DoD#3 (WER telefônico 8 kHz).
2. **Checkpoint averaging (`--avg`)** — suaviza a oscilação intra-época; como os
   melhores checkpoints são pós-shuffle (início de época), a média deles tende a
   bater abaixo do melhor single. É o que o recipe 69M-CTC do icefall usa no decode.
3. **Beam search + LM no decode** — melhora WER ~10-20% relativo `[LITERATURA]` sem
   tocar modelo nem dado. O decode de M5 hoje é greedy CTC (o piso).

Ordem de valor/custo: terminar o run + averaging + beam/LM → medir; se platôar acima
do alvo, religar augmentação num run curto de continuação; só então investir em dado
(menos TAGARELA / mais humano / Q-09). Plano M5:
`knowledge-base/plans/m5-scale-model-wer-plan.md` (ADR D2 = augmentação).

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
