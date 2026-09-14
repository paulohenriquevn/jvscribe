---
type: Medição
title: T1 — quanto modelo cabe em 2 P-cores
description: >-
  O teto não é linear em parâmetros: há um custo fixo de 68 ms por segundo de áudio que nenhum
  modelo menor remove. Com dois canais, 115M passa o RNF-01 e 600M reprova.
tags: [medicao, m10, t1, cpu, rtfx, streaming, nemotron, rnf]
timestamp: 2026-09-14T00:00:00Z
---

# T1 — o teto de parâmetros em 2 P-cores `[MEDIDO]`

Data: 2026-09-14 · **i7-1355U** (2 P-cores a 5,0 GHz com HT + 8 E-cores, 12 lógicos, AVX-VNNI,
sem AVX-512) · `taskset -c 0-3` em todas as medições · ONNX Runtime CPU, int8, greedy ·
`sherpa-onnx` 1.13.8.

## A pergunta

O `ROADMAP.md` dimensiona o modelo por convicção herdada do ADR 0003, e todo RTFx publicado na
literatura vem de EPYC de 32 núcleos, H100 ou H200. A pergunta que bloqueia o M10 inteiro é
**quantos parâmetros cabem na máquina de referência com dois canais ao vivo** — e ela não se
responde por extrapolação.

## Evidência 1 — RTFx por tamanho, mesma bancada

Dois modelos da **mesma família** (FastConformer cache-aware + RNN-T, int8, decomposto em
encoder/decoder/joiner), medidos na mesma clipe, no mesmo `taskset`, com `num_threads=2`:

| modelo | encoder int8 | params | chunk | RTFx 1 canal | n |
|---|---|---|---|---|---|
| `nemo-streaming-fast-conformer-transducer-en-480ms` | 126 MB | ~115M | 480 ms | **7,11×** (6,23–7,83) | 10 |
| `nemotron-3.5-asr-streaming-0.6b-560ms` | 628 MB | ~600M | 560 ms | **2,15×** (1,77–2,19) | 10 |

O tamanho do encoder int8 em MB serve de proxy direto para parâmetros em milhões — 628 MB para
um modelo declarado como 0.6B fecha a conta.

## Evidência 2 — dois canais não custam overhead, e é o por-canal que decide

Dois streams alimentados em round-robin no mesmo recognizer, como o motor real faz:

| modelo | 1 canal | 2 canais (agregado) | **por canal** | RNF-01 (≥3×) |
|---|---|---|---|---|
| ~115M | 7,56× | 7,50× | **3,75×** | ✅ passa |
| ~600M | 2,46× | 2,45× | **1,22×** | ❌ reprova |

Nos dois casos o agregado com dois canais é **estatisticamente indistinguível** do de um canal
(IC95% do delta cruza zero: `[−0,154; +0,156]` para 115M, `[−0,033; +0,006]` para 600M). O custo
escala com o áudio processado, não com o número de streams — o que valida o desenho de captura
dual e diz que o número a vigiar é sempre o **por canal**.

## Evidência 3 — `threads=4` é metade de `threads=2`

Round-robin pareado, mesma clipe, 2 P-cores, modelo de 600M:

| configuração | mediana | dispersão |
|---|---|---|
| `num_threads=2` | **2,15×** | 1,77–2,19 |
| `num_threads=4` | 1,01× | 0,94–1,05 |

`comparar_pareado`: delta **−1,074×**, IC95% **[−1,147; −0,987]**, n=10 — não cruza zero.

Isto **confirma por medição** a heurística que `jvscribe/common/cpu.py::threads_recomendadas`
já codificava: dois lógicos do mesmo núcleo físico disputam as mesmas unidades SIMD, e o segundo
thread adiciona sincronização sem adicionar vazão. Em 2 P-cores, `intra=2` é o teto útil.

## O modelo de custo — e por que o teto não é linear

Ajustando `tempo_de_CPU_por_segundo_de_áudio = a + b · P` aos dois pontos de dois canais:

```
a = 0,0682 s/s      custo fixo, independente do tamanho do modelo
b = 0,5667 ms/s     por milhão de parâmetros
```

O termo `a` é a descoberta que a extrapolação linear escondia: **mesmo um modelo de tamanho
zero não passaria de 14,7× de RTFx agregado** nesta máquina. Featurização, laço de decodificação
do transducer e gerenciamento de cache não encolhem com o encoder.

Daí o teto, por alvo de RNF:

| alvo por canal | agregado | teto de parâmetros |
|---|---|---|
| 2× | 4× | 321M |
| **3× (RNF-01)** | **6×** | **174M** |
| 4× (com margem) | 8× | 100M |

## Evidência 4 — WER no domínio de atendimento `[MEDIDO]`, amostra pequena

`data/eval/leitura/` é áudio de atendimento simulado (protocolo, CPF, fatura, valores), 110 s,
com referência humana. Régua `normalize_for_wer_compare`:

| hipótese | WER | CER |
|---|---|---|
| jvscribe 64M (`hipotese.txt`) | 51,25% | 51,55% |
| jvscribe 64M (`hipotese_bruta.txt`) | 38,12% | 40,16% |
| **Nemotron-3.5 0.6B** | **16,88%** | **13,86%** |

Os erros do modelo atual neste áudio são do tipo que mais custa em atendimento: `a Beatriz` →
`abea atriz`, `dia 15 de março` → `vinte e cinco de março`, `o pagamento de` → `o pagamento de
amento de`. O Nemotron acerta os três e ainda entrega pontuação e capitalização.

⚠️ **São 160 palavras de referência.** O intervalo sobre uma amostra desse tamanho é largo demais
para sustentar a magnitude, e a proveniência das hipóteses do jvscribe (checkpoint, configuração,
data) não foi verificada. A direção é inequívoca; o número não é reportável como resultado.

## Limitações — o que esta medição NÃO estabelece

1. **Confusão de variável no vocabulário.** O modelo de 115M tem **1.025** tokens; o de 600M tem
   **13.088**. Um vocabulário 12,8× maior encarece o joiner, que é invocado a cada passo de tempo.
   Parte do custo extra do Nemotron não é "ser maior" — é "ser multilíngue". Logo, **174M é um teto
   conservador**: um monolíngue PT-BR com vocabulário da ordem do atual (500) deveria caber mais.
2. **Chunks diferentes.** 480 ms contra 560 ms. Chunk menor implica mais chamadas e mais overhead,
   ou seja, o modelo de 115M foi medido em condição ligeiramente **pior** e ainda assim venceu.
3. **RNF-05 não exercitado** — nenhuma medição teve softphone ativo ou carga concorrente.
4. **RNF-04 não exercitado** — sem soak de 30 min. Há um sinal a investigar: numa bateria o RTFx
   caiu de 2,19× para 1,77× ao longo de 10 rodadas, e o áudio de 110 s rendeu 1,73× contra 2,4×
   das clipes de ~12 s. Pode ser térmica, pode ser crescimento de estado. **Não foi diagnosticado.**
5. **Dois pontos não descrevem uma curva.** O ajuste `a + b·P` é a reta que passa por eles; a
   linearidade entre 115M e 600M não foi verificada com um ponto intermediário.
6. **O modelo de 115M é inglês.** Só o custo computacional transfere; nada de acurácia.

## Conclusão

**O Nemotron-3.5 0.6B não fecha o RNF-01 nesta máquina: 1,22× por canal contra o alvo de 3×.**
Ele entra no M10 como **professor** (T3) e como régua de referência (T2) — não como produto.

**O teto de parâmetros é ~174M** para fechar o RNF-01 com dois canais, e conservador pelo item 1
das limitações. Isto **sustenta o ADR-001**: o modelo pode sair de 64M para a faixa de 120–150M
com margem, o que é a folga de 2–3× que o plano previa — mas **refuta a estimativa linear de 245M**
que a primeira leitura sugeria, porque o custo fixo de 68 ms/s não escala com o modelo.

## Como reproduzir

```bash
# artefatos
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/\
sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-560ms-int8-2026-06-11.tar.bz2
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/\
sherpa-onnx-nemo-streaming-fast-conformer-transducer-en-480ms-int8.tar.bz2

# medição (scripts de sessão, não versionados)
taskset -c 0-3 python3 t1_gate_cpu.py --model-dir <dir> --wav <wav> --threads 2 4 --repeticoes 10
taskset -c 0-3 python3 t1_dois_canais.py <dir> <wav1> <wav2> 8
```

> Nota de proveniência: os dois scripts de medição viveram no diretório de trabalho da sessão e
> **não foram versionados**. Reescrevê-los para caminhos do repositório documentaria uma execução
> que não houve. O que transfere é o protocolo descrito acima, não o caminho do arquivo.
