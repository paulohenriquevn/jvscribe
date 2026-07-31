---
type: Medição
title: M6 — primeira medição de tempo real
description: RTFx do modelo atual no caminho de tempo real, com as condições que invalidaram parte dos números.
tags: [medicao, m6, tempo-real, rtfx]
timestamp: 2026-07-31T00:00:00Z
---

# M6 early — critérios de real-time no modelo atual (Zipformer-CTC small int8)

---

> ## ⚠️ Reetiquetagem obrigatória (2026-07-30)
>
> **Os RTFx abaixo são medição de COMPONENTE em máquina ociosa. Não descrevem o pipeline.**
>
> Todos vieram de `bench_rtfx.py`, que mede **só a inferência ONNX**. O produto entrega
> `fbank → inferência → decode CTC`, e a conta de ponta a ponta é outra. Somar ou comparar as
> duas é a falácia § 3 #11 da `asr-evidence-discipline.md` — "comparar RTFx de componente com
> orçamento de pipeline".
>
> Medição do **pipeline completo** na mesma máquina (i7-1355U), mesma clip de 17,76 s,
> 2 threads, com a máquina em uso normal `[MEDIDO]` 2026-07-30:
>
> | Runtime | RTFx | Mediana |
> |---|---|---|
> | Python (`batch_transcribe.py`) | 5,7 · 6,3 · 6,7 · 7,5 · 8,0 | **6,7×** |
> | Rust (removido em 2026-07-30) | 3,0 · 3,6 · 4,9 · 8,8 · 11,3 · 14,7 | **6,9×** |
>
> **⚠️ CONDIÇÃO DA MEDIÇÃO — leia antes de usar estes números.** As medições acima foram
> tomadas com a máquina em **load average 69,4 sobre 12 cores** (~6× sobrecarregada): um
> `npm ci` a 57% de CPU, quatro containers Docker e a sessão de agente. **Não caracterizam a
> máquina de referência ociosa nem sob carga de softphone.** Registrar isso é obrigatório —
> apresentar número sem condição é a falha de método que este documento existe para corrigir.
>
> O que estes dados **sustentam**: a comparação **relativa** Rust × Python, porque ambos
> rodaram alternadamente sob a mesma carga, na mesma clip. Medianas 6,9× e 6,7× — indistinguíveis.
>
> O que **não** sustentam: qualquer afirmação sobre o RTFx absoluto do produto, e portanto
> qualquer veredito sobre RNF-01/07. **O estado correto de RNF-01/07 é `a re-medir`**, não
> "✅ com folga" nem "abaixo do piso".
>
> Consequência para o placar mais abaixo neste documento: **RNF-01/07 não pode ser dado como
> ✅ com folga**. O critério precisa ser re-medido no pipeline completo, com carga controlada,
> antes de qualquer declaração de viabilidade de tempo real.
>
> Isto não invalida os números originais — eles medem corretamente o que se propuseram a
> medir. Invalida o **uso** que se fez deles como se descrevessem o produto.

---

Iniciado M6 com o modelo que já temos (decisão do dono, 2026-07-26), para de-riscar o
real-time cedo — validando os critérios que **não dependem de M5**. Hardware: **i7-1355U de
referência** (esta máquina). Modelo: `model.int8.onnx` (27MB, int8, exportado do small 22M).

## RNF-07 / RTFx pontual `[MEDIDO]`

| Áudio | RTFx @ 1 thread | RTFx @ 2 threads |
|---|---|---|
| 5-30 s | 41-68× | 49-90× |

Piso RNF-07 = 6×. Folga **7-15×**. (Detalhe em `m4-decision-161h-results.md`.)

## RNF-04 soak (10 min) `[MEDIDO]`

RTFx por janela de 30s ao longo de 10 min, 2 threads: variou **21,6× (pior) a 74,9× (melhor)**.

**Interpretação honesta:** NÃO é throttle térmico (o padrão não é declínio monotônico; o run
terminou *mais rápido* — 74× — do que começou — 50×). A variabilidade é **contenção de CPU**
(esta máquina roda o próprio Claude Code + k3s durante a medição). Conclusões:

- **Pior caso 21,6× = 3,6× o piso de 6×** — sob contenção real, nunca caiu abaixo disso.
- **Throttle térmico não é o limitante** do real-time neste chip para este modelo.
- Duplica como preview informal de **RNF-05** (carga concorrente): sob carga real, aguentou.

**Caveat de método:** o critério RNF-04 "sustentado ≥ 80% do pico" fica confundido pela máquina
compartilhada (pico ocioso vs dips de contenção). Um número RNF-04 **definitivo** exige carga de
fundo controlada (pinar P-cores / parar k3s — precisa de sudo). O piso sob contenção já passa o
requisito com folga, então a viabilidade não muda.

## RNF-05 carga concorrente (4 cores estressados = softphone) `[MEDIDO]`

`bench_rtfx --threads 2` com 4 cores em busy-loop (simula softphone/Zoom):

| Áudio | RTFx sob carga | % do ocioso | vs piso 6× |
|---|---|---|---|
| 5s | 44,2× | 49% | 7,4× |
| 10s | 38,5× | 49% | 6,4× |
| 20s | 32,0× | 49% | 5,3× |
| 30s | 25,0× | 51% | 4,2× |

Sob carga, RTFx ~50% do ocioso, mas pior caso (30s) = 4,2× o piso; utterances realistas
(5-15s) ficam 6-7× **sob carga**. **RNF-05 passa com folga.** (Em streaming, contexto limitado →
custo/chunk constante → vale o número de clip curto.)

## Runtime v0 — decoder CTC implementado (CYCLE de M6) `[MEDIDO]`

`crates/macaw-asr/src/decode.rs` + `lib.rs` (`ctc_logits`/`transcribe`): decode CTC greedy portado
do sherpa (Regra 9) + inferência no `model.int8.onnx` real (contrato `x`/`x_lens`→`log_probs`
corrigido — o `encode()` de M0 era placeholder NeMo). **11/11 testes do crate verdes**; 60 frames →
T=13 (subsampling 4×), vocab 500. Discover→plan→implement todos SHIPPABLE.

**Bloqueio honesto da Fase 3 (transcrição de fala real):** o `macaw-audio` produz **128-bin sem
overlap** (era para o placeholder NeMo de M0); o modelo icefall precisa de **80-bin kaldi 25/10ms**.
Alimentar features erradas dá lixo. Re-alinhar o fbank é tarefa real (validação numérica vs lhotse) —
o decode já funciona sobre `log_probs` corretos; falta a fronteira de features casar. Ver task #25.

## Placar dos 5 critérios de real-time (modelo atual, offline)

| Critério | Estado |
|---|---|
| RNF-01/07 RTFx ≥ 6× | ✅ 41-90× ocioso, 25-44× sob carga |
| RNF-04 soak 10min | ✅ sem throttle térmico; piso 21,6× sob contenção |
| RNF-05 carga concorrente | ✅ 25-44× (4,2-7,4× o piso) |
| RNF-02 latência p99 streaming | ⏳ precisa de modelo causal |
| RNF-03 operação 8 kHz | parcial — penalidade telefônica medida 1,29× (`m4-decision-161h-results.md`) |

**3 dos 5 critérios validados com o modelo que já temos.** Falta streaming (RNF-02, causal) e o
soak definitivo com carga controlada.

## Pendente (não validável no modelo atual)

- **RNF-02 latência p99 streaming** + **equivalência batch≡streaming** — exigem modelo **causal**
  (`zipformer/train.py --causal 1`, ~6h). O small atual é non-causal/offline; medir latência de
  streaming nele seria desonesto.
- **int8 vs fp32 — WER** (o "int8 medido vs alternativas" do DoD de M6): temos RTFx do int8; falta
  confirmar que o int8 não degrada WER vs o fp32 (29,97%).
- **RNF-04 definitivo** com carga de fundo controlada.

## Conclusão parcial

O eixo **velocidade** do objetivo está **fortemente encaminhado** `[MEDIDO]`: RTFx com folga de
7-15× pontual, piso de 3,6× sob contenção de 10 min, sem throttle térmico limitante. Falta fechar
streaming (RNF-02, precisa de causal) e o int8-vs-fp32 WER. **Nada disso torna o WER de M5 trivial**
— este documento é sobre velocidade, não acurácia.
