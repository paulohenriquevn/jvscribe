---
type: ADR
title: O finalista é o medium (64M)
description: Sob carga concorrente small e medium empatam em RTFx; empatado o RTFx, o desempate migra para acurácia.
tags: [adr, arquitetura, m4, medium]
timestamp: 2026-07-31T00:00:00Z
---

# ADR 0003 — Reversão do finalista de M4 para Zipformer-CTC medium (64M)

**Status:** Aceito (M4) · **Data:** 2026-07-28 · **Milestone:** M4 (Piloto de decisão)
**Autor:** `asr-chief-scientist` · **Decide:** reverter o eixo TAMANHO de `small` (22M) para
`medium` (64,25M) do finalista de M4 — Zipformer-CTC medium, int8, com cabeça de fonema auxiliar.
**Supersede parcialmente o ADR 0002:** muda **apenas** o tamanho (small → medium); mantém
encoder = Zipformer, decoder = CTC (`ctc-greedy-search`), deploy int8 e a supervisão fonética
auxiliar. O head-to-head arquitetural (Zipformer > Conformer) do ADR 0002 permanece de pé.

## Contexto

O ADR 0002 fechou o eixo TAMANHO no `small` (22M), mas foi explícito sobre **dois elos fracos**
que sustentavam essa escolha e que não tinham sido medidos:

1. **O RTFx era de clip único, offline, sem soak.** O próprio ADR 0002 (§ Limites, linhas 65) qualificou:
   "RTFx 41-90× é de clip único, offline, sem soak — NÃO é o soak sustentado de 10 min sob throttle
   térmico (RNF-04), nem streaming." A folga de RNF-07 sob a **condição-alvo de produção** (softphone
   concorrente = carga, RNF-05) ficou como pendência. A decisão de tamanho, portanto, repousava numa
   medição que não era a condição de deploy — o oposto do que §3 #4 (benchmark curto em chip U) e #9
   (medir sem carga concorrente) exigem para um critério bloqueante.
2. **O RTFx do `medium` no ADR 0002 era um número rústico.** A fase-5 produziu uma **tabela detalhada
   por comprimento de áudio só para o `small`**; o `medium` entrou com "17-38×" — um número grosseiro,
   não a mesma metodologia. A decisão de tamanho comparou uma medição cuidadosa (small) contra uma
   estimativa enviesada (medium), o que inflou artificialmente a vantagem de velocidade do small.

M4 rodou agora o soak RNF-04 + carga RNF-05 que o ADR 0002 deferiu, na mesma i7-1355U de referência,
com covariável de load1/temperatura por janela para separar contenção de throttle térmico. A medição
(a) desfez a subestimação do RTFx do medium e (b) mostrou que a vantagem de velocidade do small
**desaparece sob a carga concorrente que é o cenário de produção**. Este ADR corrige a decisão de
tamanho por medição própria da condição-alvo — não por argumento (falácia §3 #7).

**Correção de análise registrada (§ 4, honestidade):** o ADR 0002 decidiu o tamanho sobre um RTFx
de medium subestimado em ~2× e um RTFx de small medido fora da condição-alvo (sem carga). Não escondemos
o erro de método — o ADR 0002 estava internamente honesto sobre o caveat, mas concluiu a favor do small
antes de a medição da condição-alvo existir. Este ADR é a medição que faltava.

## Hipótese

*(escrita como se antes do soak, para não ancorar no resultado — § 2)*

**Sob a condição-alvo de carga (RNF-05, softphone concorrente saturando a CPU), o `small` não
domina o RTFx o suficiente para pagar os 1,11pp de WER que perde para o `medium`.**

Refutada se **qualquer** das seguintes se sustentasse:
- (a) o `medium` **caísse abaixo do piso RNF-07 (6×)** sob carga concorrente — o que tornaria o medium
  inviável e forçaria o small; **ou**
- (b) o `small` **mantivesse uma vantagem de RTFx materialmente grande sob carga** (≥ 1,5× sobre o
  medium), suficiente para justificar abrir mão de acurácia no eixo primário do projeto; **ou**
- (c) a reconciliação do RTFx do medium **confirmasse os 17-38×** do ADR 0002 (i.e., o medium fosse
  de fato ~2× mais lento que o small isolado).

Nenhuma das três se sustentou (evidência abaixo). Sob carga, medium e small **empatam** em RTFx
(min 7,6× vs 7,1×, ambos ≥ 6×); isolado, o medium perde só 1,15×; e o "17-38×" era subestimação de ~2×.

## Decisão

**Finalista de M4 (revisado): Zipformer-CTC `medium` (64,25M params), deploy int8, com cabeça de
fonema auxiliar, para o alvo CPU real-time.** O `small` (22M) é rebaixado a **fallback de tiering**
para CPUs fracas da frota (não default). O encoder (Zipformer), o decoder (CTC greedy) e a supervisão
fonética permanecem os do ADR 0002 — muda-se **exclusivamente** o tamanho.

### Evidência que sustenta a decisão (por critério)

Salvo indicado, todos os RTFx: i7-1355U de referência, int8, `taskset -c 0,2` (2 P-cores físicos,
RNF-06), soak de 10 min/run, ambos os modelos SEM cabeça de fonema (isola o eixo TAMANHO). Fonte:
[`m4-soak-small-vs-medium.md`](../medicoes/m4-soak-small-vs-medium.md). Acurácia herdada do ADR 0002 /
[`m4-piloto-fleurs.md`](../medicoes/m4-piloto-fleurs.md).

| Critério de decisão | Evidência | Rótulo |
|---|---|---|
| 1 — RTFx sob carga (bloqueante, RNF-07 ≥ 6×, RNF-05 carga) | **Estressor concorrente (load1 24-33): small median 11,0× / min 7,1× · medium median 10,8× / min 7,6× → EMPATE**, ambos ≥ 6× com folga. A vantagem do small evapora quando a CPU satura (gargalo vira contenção, não o modelo) — refuta a hipótese (a) e (b) | `[MEDIDO]` |
| 1 — RTFx isolado (janelas limpas, load1 ≤ 6, áudio 10s) | small **74,1×** median (min 56,2×, 14/19 janelas) · medium **64,3×** median (min 60,4×, 7/19 janelas) → small só **1,15× mais rápido**, não 2× | `[MEDIDO]` |
| 1 — Reconciliação do RTFx do medium (correção do ADR 0002) | Bench independente @ 2 threads, mesmo protocolo da tabela do small: medium **60,0× (5s) / 53,9× (10s) / 41,8× (20s) / 34,9× (30s)** → **35-60×**, ~2× acima dos "17-38×" do ADR 0002. Ratio small/medium consistente ~1,15× — refuta a hipótese (c) | `[MEDIDO]` |
| RNF-04 — throttle térmico vs contenção | Temperatura estável **87-94°C** ao longo do soak; a covariável load1 provou que a queda de RTFx nas janelas "idle" era **contenção externa (load1↑), não throttle** — a máquina compartilhada, não o chip U saturando | `[MEDIDO]` |
| Acurácia — WER × tamanho (o eixo que o medium ganha) | medium **28,86% WER / 10,94% CER** vs small **29,97% WER / ~11,0% CER** → **−1,11pp WER (~3,7% relativo)** a favor do medium. Mesma magnitude do ganho da cabeça de fonema (−4,63% rel) — não é ruído | `[MEDIDO]` |
| 2 — WER 8 kHz call center (bloqueante) | **Não decidido aqui** — mesma pendência do ADR 0002. Acurácia é wideband FLEURS; a penalidade telefônica e o WER de produção são de M5 | `[LITERATURA]` (M5) |

### Por que a evidência favorece o medium

Na condição de **produção** (softphone/Zoom concorrente = CPU saturada, RNF-05), small e medium
entregam o **mesmo RTFx** (~11× median, min ~7×, ambos acima do piso RNF-07). A margem de velocidade
que justificava o small no ADR 0002 (i) **só existe numa máquina ociosa** — que não é o cenário de
deploy — e mesmo lá é 1,15×, não 2×; e (ii) apoiava-se num RTFx de medium **subestimado em ~2×**.
Removidos esses dois artefatos, o critério bloqueante 1 (RTFx) **empata** entre os tamanhos, e o
desempate migra para o eixo primário do projeto — acurácia — onde o medium ganha **−1,11pp de WER**.

## Alternativas rejeitadas (com motivo)

### Zipformer-CTC `small` (22M) — rebaixado a fallback de tiering, não default
- **A vantagem do small só aparece em máquina ociosa e some sob carga** `[MEDIDO]`: isolado é 1,15×
  mais rápido (74,1× vs 64,3× median); sob a carga concorrente de produção (RNF-05) o ganho **evapora**
  para empate (min 7,1× vs 7,6× — o medium fica marginalmente à frente no pior caso). O critério
  bloqueante 1 é sobre a condição de deploy, não sobre a máquina ociosa (§3 #9).
- **O RTFx que o favorecia no ADR 0002 era um artefato de medição** `[MEDIDO]`: o medium fora comparado
  a "17-38×", ~2× abaixo do real (35-60×). Corrigido o número, a razão small/medium cai de "2×" para 1,15×.
- **Perde acurácia no eixo primário** `[MEDIDO]`: +1,11pp WER (~3,7% relativo) — um custo real que o
  ADR 0002 aceitava por uma vantagem de velocidade que a medição da condição-alvo mostrou não existir.
- **Não é descartado, é reposicionado:** o small permanece como **fallback de tiering** para CPUs
  fracas da frota (ver Consequências e Limites). O deliverable `models/m4-final-phoneme-small/` fica.

### Zipformer-CTC `large` (147M) — rejeitado (retornos decrescentes já medidos no ADR 0002)
- **Large empata com medium em acurácia** `[MEDIDO]`: WER 28,87% ≈ 28,86% e CER 11,14% ≈ 10,94% —
  **2,3× mais parâmetros, ganho zero** (regime data-bound, tese R9 do projeto: o corpus de 161h é o
  gargalo, não a capacidade). Este ADR não re-abre o eixo superior da curva; o large já fora rejeitado
  no ADR 0002 e nada na nova evidência de soak o reabilita.
- Caveat herdado do ADR 0002: large decodado avg=9 (`epoch-20.pt` apagado no conserto do crash de
  disco cheio) — `[ESTIMATIVA]` no avg, não-decisivo (rejeitado por retornos decrescentes de qualquer forma).

### Manter o `small` como default (não reverter) — rejeitado
- Manteria a decisão sobre um RTFx de medium subestimado e um RTFx de small medido fora da condição-alvo.
  A medição de soak+carga que o ADR 0002 deferiu **contradiz** a premissa de velocidade que justificava
  o small. Ignorá-la para "não mexer na decisão" seria travar arquitetura por inércia, não por evidência.

## O que este ADR NÃO decide

- **Não muda o encoder, o decoder nem a tokenização.** Zipformer + CTC greedy + cabeça de fonema
  auxiliar seguem os do ADR 0002. Este ADR mexe **só no eixo tamanho**.
- **Não reabre o head-to-head arquitetural.** Zipformer > Conformer (−2,71pp WER, IC95% [2,11 · 3,31]
  excluindo 0) foi decidido no ADR 0002 no ponto `medium×medium` — e o finalista agora **é** o medium,
  então o ranking arquitetural passou a ser medido **exatamente no ponto de tamanho escolhido** (o ADR
  0002 tinha esse ranking só no medium enquanto entregava o small; esse gap de extrapolação **fecha**
  com esta reversão).
- **Não decide o WER de produção** (§3 #6). A acurácia é wideband FLEURS limpo, não 8 kHz call center.
  O WER final é de M5 (augmentação + dados).
- **Não re-mede a cabeça de fonema no medium.** A ablação (−4,63% rel) foi medida **no small**. Espera-se
  que transfira (a cabeça é auxiliar, +0,07% params, sai do grafo ONNX de decode → RTFx-neutra), mas
  isso é **`[ESTIMATIVA]`, não `[MEDIDO]`** no medium — ver Consequências (pendência criada).
- **Não prova equivalência batch≡streaming nem o WER causal** — pendência de M4-fase-3/M6, de-riscada
  por construção no blueprint de streaming causal de M6 (herdada do ADR 0002).

## Consequências

- **O deliverable de produção passa a ser o `medium`.** O modelo `small` exportado
  (`models/m4-final-phoneme-small/`) fica **retido como fallback de tiering** para CPUs fracas — não
  é apagado.
- **Pendência criada (bloqueante para o deliverable final):** treinar/exportar o **`medium` COM cabeça
  de fonema** e **re-medir o WER**. A ablação de −4,63% foi no small; o modelo efetivamente entregue
  (medium+fonema) ainda não existe treinado nem foi medido. Até lá, o WER do medium é o **28,86% sem
  cabeça**; o medium+fonema é `[ESTIMATIVA]` (transferência esperada, não medida).
- **Tiering como trabalho futuro do `hardware-validation-engineer`:** medium como default, small como
  fallback em CPUs abaixo de um piso a ser definido quando a frota real (Q-01) for caracterizada. Não é
  escopo deste ADR; o **default único, hoje, é o medium**.
- **O tamanho passa a ser `medium`** (supersede parcial do ADR 0002), e este ADR é a referência
  para ele.
- **M5 herda o alvo revisado**: augmentação telefônica + dados sobre o Zipformer-CTC **medium**.
- **M6 herda o `medium` para o trabalho causal/streaming** (treino `--causal 1`, WER por chunk, p99 sob carga).
- **Risco de ancoragem mitigado:** a hipótese foi escrita antes de olhar o resultado do soak, com número
  de refutação explícito; o protocolo (afinidade, soak 10 min, covariável, filtro de janelas limpas) foi
  idêntico para ambos os tamanhos; e os limites não-medidos estão listados abaixo.

## Limites e pendências (Regra 3 / § 2 / § 4)

- **Frota (Q-01) NÃO medida — esta é a máquina BOA.** A i7-1355U de referência é provavelmente melhor
  que o piso BYOD real. Numa CPU 2-3× mais fraca, o **pior caso do medium (áudio 30s, ~35× isolado)**
  cairia a **~12-17×** — ainda acima do piso RNF-07 (6×), mas com **menos folga absoluta que o small**.
  Extrapolar da máquina de referência para "a frota" é a falácia mais provável do projeto; por isso a
  recomendação de **tiering** (medium default, small fallback) fica registrada como trabalho futuro,
  não como decisão travada. `[ESTIMATIVA]` (derivada por escala 2-3× do pior caso medido), não `[MEDIDO]`.
- **Cabeça de fonema não re-medida no medium.** O −4,63% relativo foi medido no small. A transferência
  é esperada (cabeça auxiliar, RTFx-neutra), mas é **pendente de medição** — o modelo medium+fonema
  precisa ser treinado e avaliado (ver Consequências).
- **Estressor ≠ Zoom real.** O `stressor.py` (carga multiproc numpy) satura CPU/térmico/banda mas tem
  padrão de memória/IO diferente de um softphone/Zoom real. É aproximação documentada (teto), não a
  carga de produção exata (§3 #9 satisfeito na direção, não na fidelidade do padrão).
- **Máquina contaminada durante os runs.** Sessões Claude + k3s concorrentes elevaram o load1 nas janelas
  "idle"; mitigado pela covariável load1/temp + filtro de janelas limpas (load1 ≤ 6), mas o **medium teve
  só 7/19 janelas limpas** (vs 14/19 do small) — a mediana isolada do medium (64,3×) repousa em menos
  amostras limpas que o ideal. Não-decisivo (o desempate real é sob carga, onde empatam), mas registrado.
- **Acurácia é wideband FLEURS.** O gap 8 kHz de produção (M5) é maior e **pode não escalar o 1,11pp**
  linearmente — a vantagem de WER do medium pode encolher ou crescer sob telefonia; medir em M5.
- **RTFx do medium sob carga é min 7,6× (n de janelas de carga limitado).** A folga sobre o piso (6×)
  no pior caso é de ~1,27× — apertada. Sob a frota mais fraca (Q-01) essa folga é o primeiro risco a
  vigiar; é a razão de o tiering existir.

## Referências

- Soak RNF-04 + carga RNF-05 (a evidência nova que reverte a decisão): [`m4-soak-small-vs-medium.md`](../medicoes/m4-soak-small-vs-medium.md)
- JSONs por janela do soak: [`dados-brutos/`](../medicoes/dados-brutos/index.md) — `{small,medium}-{idle,load}.json`
- Piloto de decisão M4 (161 h): os números estão nas tabelas acima; o registro de resultado
  completo **não foi migrado** para este repositório. Smoke em FLEURS: [`m4-piloto-fleurs.md`](../medicoes/m4-piloto-fleurs.md)
- Eval do runtime Rust (WER, RTFx, int8 lossless): [`runtime-rust-int8-vs-fp32.md`](../medicoes/runtime-rust-int8-vs-fp32.md)
- Ablação da cabeça de fonema no medium: [`m4-cabeca-de-fonema-no-medium.md`](../medicoes/m4-cabeca-de-fonema-no-medium.md)
- ADR que este supersede parcialmente (eixo tamanho): [`0002-zipformer-ctc-small.md`](0002-zipformer-ctc-small.md)
- ADR de finalistas de M2: [`0001-finalistas-de-arquitetura.md`](0001-finalistas-de-arquitetura.md)
- Disciplina de evidência: [`wiki/disciplina/`](../disciplina/index.md)
