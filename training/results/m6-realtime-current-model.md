# M6 early — critérios de real-time no modelo atual (Zipformer-CTC small int8)

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
