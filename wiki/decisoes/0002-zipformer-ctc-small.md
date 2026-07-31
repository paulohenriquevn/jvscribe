---
type: ADR
title: Zipformer-CTC small como finalista (M4)
description: Zipformer domina Conformer nos dois eixos de acurácia. Superseded no eixo tamanho pelo ADR 0003.
tags: [adr, arquitetura, m4, superseded]
timestamp: 2026-07-31T00:00:00Z
---

# ADR 0002 — Finalista de arquitetura ASR de M4: Zipformer-CTC small (22M)

**Status:** Aceito (M4) · **Data:** 2026-07-27 · **Milestone:** M4 (Piloto de decisão)
**Autor:** `asr-chief-scientist` · **Decide:** Zipformer-CTC, tamanho `small` (22M), int8, como o encoder/decoder/tamanho para o alvo CPU real-time — o vencedor que o ADR 0001 deixou a-medir.

## Contexto

O ADR 0001 (M2) nomeou **dois finalistas a pilotar** — Zipformer+CTC e a família Conformer (originalmente FastConformer-CTC) — e Moonshine-AED como controle, deixando explicitamente **a-medir em M4**: (a) qual finalista vence pela curva WER × RTFx, e (b) qual tamanho dentro do vencedor. Aquele ADR foi honesto sobre o elo mais fraco: o RTFx do 2º finalista era `[ESTIMATIVA]`, e a escolha entre finalistas dependia de medição própria (`asr-evidence-discipline.md` § 0), nunca de argumento (falácia § 3 #7).

M4 rodou esse piloto. Este ADR fecha a pendência **por medição**, no mesmo test set, mesma máquina, mesmo decode e mesmo corpus para todos os braços — o único protocolo que torna a diferença atribuível à arquitetura, e não a confound de framework (a razão registrada em `training/results/m4-decision-161h-results.md` para se representar a família Conformer pelo Conformer-icefall e não pelo FastConformer-NeMo).

**Hipótese (escrita antes de olhar o head-to-head), § 2:** *entre os dois finalistas de M2 com params equivalentes e protocolo idêntico, o Zipformer domina o eixo de acurácia; e dentro do Zipformer, o `small` domina a curva WER × RTFx para o alvo CPU real-time.* Refutada se: (a) o Conformer empatasse ou vencesse em WER **ou** CER no mesmo protocolo, ou (b) o `small` não atendesse RNF-07 (≥ 6× em ASR isolado) com folga, ou (c) o ganho de WER do medium/large sobre o small pagasse o custo de compute. Nenhuma das três se sustentou.

## Decisão

**Finalista de M4: Zipformer-CTC, tamanho `small` (22,1M params), deploy int8, para o alvo CPU real-time.** O Conformer-CTC (representante da família Conformer/2º finalista) é rejeitado por perder os dois eixos de acurácia; medium e large do Zipformer são rejeitados por retornos decrescentes medidos.

### Evidência que sustenta a decisão (por critério)

Todos os números abaixo: corpus train = MLS-PT ~161h (CC-BY humano), test = FLEURS held-out (21.471 palavras de ref), icefall real, RTX 3090 para treino/decode, `ctc-greedy-search`. RTFx na i7-1355U de referência. Fontes: `training/results/m4-decision-161h-results.md`, `training/results/runtime-eval-findings.md`.

| Critério (PRD § 8.1) | Evidência | Rótulo |
|---|---|---|
| 1 — RTFx (bloqueante, RNF-07 ≥ 6×) | Zipformer-CTC small int8 na i7-1355U: **41-68× @1 thread / 49-90× @2 threads** (5-30s de clip); pior caso 30s = 41× → **6,8× de folga** sobre o piso; runtime Rust de produção confirma **48-55×** por-utterance (`runtime-eval-findings.md`) | `[MEDIDO]` |
| 2 — WER 8 kHz call center (bloqueante) | **Não é decidido aqui** — WER é wideband FLEURS. Penalidade telefônica medida (band-limit 300-3400 Hz + G.711 A-law, features casadas a 16 kHz) = **1,29× (+8,6pp)**, mais branda que o 2-3× da literatura, mas é **piso** e é **antes** de augmentação. O WER de produção é de M5 | `[MEDIDO]` (piso) / `[LITERATURA]` (fator 2-3×) |
| Acurácia — head-to-head arquitetural (decide o finalista) | **Zipformer-CTC medium (64,25M): WER 28,86% / CER 10,94%** vs **Conformer-CTC medium (64,72M): WER 31,57% / CER 11,90%** (ambos avg=10, params equivalentes +0,7%, mesmo corpus/época/decode/máquina). Zipformer domina os **dois** eixos: **−2,71pp WER, −0,96pp CER**. Parser de CER validado reproduzindo o WER oficial do icefall (31,57%) | `[MEDIDO]` |
| Tamanho — curva WER × RTFx (decide o tamanho) | small(22M) 29,97% / ~11,0% CER · medium(64M) 28,86% / 10,94% · large(147M) 28,87% / 11,14%. Large **empata** com medium (2,3× params, ganho zero); small tem o **mesmo CER (~11%)** do large 7× maior. RTFx: small 49-90× vs medium 17-38× | `[MEDIDO]` |
| Deploy int8 (custo-zero de acurácia) | int8 (27MB) WER 28,21% / CER 10,99% vs fp32 (92MB) WER 28,45% / CER 10,93% (runtime Rust, n=100). Δ 0,24pp WER — dentro do ruído; quantização essencialmente **lossless** aqui | `[MEDIDO]` |
| Equivalência batch≡streaming (bloqueante, RNF-02) | Não medido neste ADR. De-riscada **por construção** no blueprint de streaming causal (treino `--causal 1` aplica máscara chunk-limitada; chunk-16→320ms fecha p99≤500ms com ~180ms de folga) | `[FONTE-REPO]` (blueprint) |

## Alternativas rejeitadas (com motivo)

### Conformer-CTC (representante da família Conformer / 2º finalista de M2) — rejeitado
- **Perde os DOIS eixos de acurácia com params equivalentes** `[MEDIDO]`: +2,71pp WER (31,57% vs 28,86%) e +0,96pp CER (11,90% vs 10,94%), no mesmo corpus, época, decode e máquina. Como o único grau de liberdade que varia é a arquitetura, a diferença é **atribuível à arquitetura** — exatamente o confound que o protocolo idêntico foi desenhado para isolar. **A vantagem de WER do Zipformer é estatisticamente robusta** `[MEDIDO]`: bootstrap pareado por utterance (n=919, B=10.000) dá 2,71 p.p. com **IC95% [2,11 · 3,31], que exclui 0** e P(Conformer melhor)=0,0% — não é ruído do test set (`m4-decision-161h-results.md`, fecha §3 #12 no número que decide o finalista).
- **Acurácia é o eixo primário do projeto** (modelo especializado e preciso). Uma arquitetura que perde em WER *e* CER no eixo primário não é finalista, independentemente da velocidade.
- **RTFx do Conformer em CPU = `[DESCONHECIDO]`** — não exportado nem medido na i7-1355U. Registrado como **não-decisivo, não como medição**: o Conformer já perde no eixo primário, e a arquitetura Zipformer é desenhada para ser mais rápida (stack de downsampling agressivo), tornando improvável que o Conformer compre velocidade suficiente para compensar 2,71pp de WER. **Não afirmamos velocidade do Conformer sem número** — apenas registramos que medi-la não reverteria a perda de acurácia (não concluir além da evidência, § 2).

### Zipformer medium (64M) e large (147M) — rejeitados (retornos decrescentes medidos)
- **Large empata com medium** `[MEDIDO]`: WER 28,87% ≈ 28,86% e CER 11,14% ≈ 10,94% — **2,3× mais parâmetros, ganho zero**. O `epoch-20.pt` do large foi apagado ao consertar o crash de disco cheio, então o large foi decodado avg=9 (baseline epoch-21) ≈ avg=10; diferença desprezível (caveat honesto de `m4-decision-161h-results.md`).
- **Small tem o mesmo CER (~11%) que o large 7× maior** `[MEDIDO]`: no nível de caractere o small é tão bom quanto o modelo 7× maior; o ~1,1pp de WER a mais do small é erro de fronteira-de-palavra/rare-word, não erro acústico.
- **Regime data-bound** (tese R9 do PRD): a capacidade não é o gargalo — o corpus é. Adicionar parâmetros não compra WER com 161h. O small compra 2× de velocidade (49-90× vs 17-38×) por só ~1pp de WER → domina a curva para RNF-07.

### Moonshine-AED — permanece controle, não finalista
- Rebaixado a controle já no ADR 0001 (RTFx ~2× pior medido em M2; hotword fraco; sem recipe from-scratch). M4 não o re-mediu no head-to-head de acurácia; o veredito de M2 se mantém.

## O que este ADR NÃO decide

- **Não decide o WER de produção** (falácia § 3 #6). O WER medido é **wideband FLEURS limpo**, não 8 kHz call center. A penalidade telefônica de deploy e o WER final são de **M5** (augmentação + dados). Este ADR decide **arquitetura e tamanho**, não o número de produção.
- **Não é o FastConformer exato.** O finalista de M2 era FastConformer-CTC (NeMo). Foi substituído por Conformer-CTC-icefall após **4+ falhas honestas de provisionamento do NeMo na vast.ai** (`[MEDIDO — 4+ tentativas]`, documentadas em `m4-decision-161h-results.md`). A troca **serve melhor a intenção científica** (elimina confounds de framework), mas o ADR herda o limite: a família Conformer foi representada pelo Conformer-icefall, não pelo FastConformer exato.
- **Não prova a equivalência batch≡streaming nem o WER causal.** A equivalência está de-riscada **por construção** no blueprint `knowledge-base/discoveries/blueprints/m6-streaming-causal-blueprint.md`, mas o treino causal (`--causal 1`) e a medição de WER por chunk + p99 sob carga são trabalho de M4-fase-3/M6 — **próximo passo, não medido aqui**.
- **O ranking arquitetural foi medido só no `medium` (params casados); o finalista é o `small`.** O eixo "arquitetura" (Zipformer vs Conformer) foi decidido em medium×medium para isolar params; o eixo "tamanho" foi decidido só dentro do Zipformer. A composição **Zipformer∩small nunca foi confrontada com Conformer∩small** — a superioridade arquitetural é **transferida do medium por extrapolação intra-família, não medida no ponto de tamanho escolhido**. Inferência forte (a vantagem arquitetural do Zipformer tende a se manter ou crescer com menos capacidade), mas registrada como limite, não medição.
- **A ablação da supervisão fonética (fase 3) CONCLUIU** — a cabeça de fonema auxiliar dá **−4,63% relativo de WER** (29,97% → 28,58%, IC95% [2,63%, 6,63%]); DoD ≥3% **atingida no ponto** (PASS com nota, IC fronteiriço). O modelo efetivamente entregue passa a ser o `small` COM cabeça de fonema (a cabeça sai do grafo na inferência). Evidência: `training/results/m4-phoneme-ablation-results.md`.

## Consequências

- **Encoder/decoder/tamanho deixam de ser `PENDENTE`** para o alvo CPU real-time: Zipformer-CTC small int8. O runtime v0 (crates `macaw-*`) já roda esse modelo ponta-a-ponta com WER equivalente ao decode Python (`runtime-eval-findings.md`) — a decisão está alinhada com o que já foi construído.
- **`PRD.md` § 8.1** deve passar a referenciar este ADR e mover encoder/decoder/tamanho de `⏸ PENDENTE` para `✅ Decidido (M4)` — a atualização é proposta ao dono do PRD (não reescrita por este agent; `asr-evidence-discipline.md` § 5).
- **M5 herda o alvo**: augmentação telefônica + dados sobre o Zipformer-CTC small, com meta de levar o clean a ~15% (projeção honesta: telefônico ~19% antes de augmentação, dentro do alvo 15-25%).
- **M6 herda o modelo para o trabalho causal/streaming** (treino `--causal 1`, WER por chunk, p99 sob carga).
- **Risco de ancoragem** (o piloto "confirmar" o esperado) mitigado: a hipótese foi escrita antes do head-to-head, o protocolo foi idêntico para todos os braços, e os limites não-medidos estão listados explicitamente.

## Limites e pendências (Regra 3 / § 2)

- RTFx do Conformer em CPU: `[DESCONHECIDO]` — não-decisivo (ver acima), mas não afirmado.
- **RTFx 41-90× é de clip único, offline, sem soak** — herda o caveat de `m4-decision-161h-results.md`: NÃO é o soak sustentado de 10 min sob throttle térmico (RNF-04), nem streaming. Para o critério bloqueante RNF-07 a folga (6,8× no pior caso) torna o risco prático baixo, mas a qualificação de §3 #4/#5 é obrigatória neste artefato de registro.
- **RTFx e int8-lossless foram medidos no `small` SEM a cabeça de fonema** (`model.int8.onnx`, `runtime-eval-findings.md`); o deliverable é o `small` COM cabeça. A cabeça é +0,07% params e **verificadamente ausente do grafo ONNX de decode**, então RTFx/int8-lossless **herdam** a medição do variante-sem-cabeça — isto é `[ESTIMATIVA/FONTE-REPO]` (justificada pela ausência no grafo), **não `[MEDIDO]`** no variante-fonema. "Custo zero em produção" deve ser lido com esse rótulo.
- **CER do `small` (~11%) vem do runtime** (`runtime-eval-findings.md`, 10,99%), não do decode icefall (recogs do small sobrescritos pelo experimento telefônico) — metodologia distinta da coluna medium/large; não-decisivo (small escolhido na curva plana), mas registrado.
- **"int8 essencialmente lossless"** (Δ0,24pp WER, `runtime-eval-findings.md`) é a n=100 **sem IC** nesse delta — direção favorável ao int8, escala pequena, não-decisiva; "dentro do ruído" é medido a n=100, IC não computado.
- **Large decodado avg=9** (não avg=10): o `epoch-20.pt` foi apagado no conserto do crash de disco. "avg=9 ≈ avg=10, diferença desprezível" é `[ESTIMATIVA]` (o checkpoint p/ avg=10 não existe mais), não `[MEDIDO]`; não-decisivo (large rejeitado por retornos decrescentes de qualquer forma).
- WER telefônico 8 kHz real (resolução nativa, ruído acústico, codecs além de A-law): não medido; o 1,29× é piso.
- Equivalência int8 vs fp32 em modo **causal/streaming**: o blueprint alerta que a equivalência fp32 batch≡streaming não transfere automaticamente ao int8 — verificar nos dois em M6.
- Treino causal: pendente (M4-fase-3/M6).

## Referências

- Piloto de decisão M4 (tabela completa + head-to-head + curva): `training/results/m4-decision-161h-results.md`
- Recogs/errs/logs do Conformer-CTC medium: `training/results/m4-conformer-ctc-medium/`
- Eval do runtime Rust (WER, RTFx, int8 lossless): `training/results/runtime-eval-findings.md`
- Blueprint de streaming causal: `knowledge-base/discoveries/blueprints/m6-streaming-causal-blueprint.md`
- ADR de finalistas de M2 (o que este ADR fecha): `knowledge-base/adrs/0001-m2-architecture-finalists.md`
- 8 critérios de decisão + candidatos: `PRD.md` § 8.1
- Disciplina de evidência: `.claude/rules/asr-evidence-discipline.md` (§ 0, § 1, § 2, § 3)
