---
type: Medição
title: RNF medidos ao vivo, dois canais
description: Primeira medição dos critérios de real-time sobre o pipeline completo.
tags: [medicao, rnf, tempo-real, m6]
timestamp: 2026-07-31T00:00:00Z
---

# App de transcrição ao vivo em dois canais — primeira medição de RNF `[MEDIDO]`

Data: 2026-07-31 · `jvscribe/realtime/live_transcribe.py` · modelo `models/current/model.int8.onnx`
(WER 15,99%) · i7 12-core, ONNX int8, 4 threads, sem carga concorrente declarada.

## Hipótese

A app captura mic (ATENDENTE) e loopback (CLIENTE) em paralelo, transcreve os dois e atende
os critérios de real-time (RNF-01..05).

## Evidência 1 — o roteamento de falante funciona

Áudios de referência do FLEURS tocados nas caixas entram pelo loopback e são rotulados
CLIENTE. Verificado contra a transcrição humana:

| | texto |
|---|---|
| referência (`a001`) | construída pelos egípcios no século 3 a.c. a grande pirâmide é uma das muitas grandes estruturas… construídas para honrar os mortos |
| **CLIENTE** (loopback) | construída pelos egiípcios no século **tris antes de cristo** a grande pirâmide é uma das muitas grandes estruturas… construídas para **punrar** para as mortos |

Nenhuma diarização envolvida — o papel vem da origem do stream, como previsto.

**Caveat do setup:** com alto-falantes abertos, o microfone capta as caixas e o ATENDENTE
espelha o CLIENTE por crosstalk acústico. Isso é fenômeno do teste, não do produto: numa
ligação real o atendente usa headset. Medir crosstalk com headset é trabalho do
`audio-dsp-engineer`, e continua `[DESCONHECIDO]`.

## Evidência 2 — o custo de decode cresce com a janela `[MEDIDO]`

Mediana de 5 decodes por ponto, mesma clip, 4 threads. A coluna de ocupação é
`2 canais × decode ÷ hop` — quanto da CPU o pipeline consome só decodificando.

| janela | decode | ocupação (2 canais, hop 0,5 s) | |
|---|---|---|---|
| 2 s | 86 ms | 34,5% | OK |
| 4 s | 142 ms | 56,8% | OK |
| 6 s | 172 ms | 69,0% | OK |
| 8 s | 218 ms | 87,3% | satura |
| 10 s | 262 ms | **104,9%** | **satura** |
| 12 s | 264 ms | 105,4% | satura |

**A janela default de 10 s pedia mais de 100% da CPU.** O default passou para 6 s por
medição, não por preferência.

## Evidência 3 — varredura de configuração ao vivo `[MEDIDO]`

| janela / hop | RTFx (RNF-01 ≥3×) | p99 (RNF-02 ≤500 ms) | backlog (RNF-03 ≤0,1%) |
|---|---|---|---|
| 10 s / 0,6 s — *antes do fix de dreno* | 3,48× ✅ | 792 ms ❌ | **100,0%** ❌ |
| 10 s / 0,6 s | 3,66× ✅ | 789 ms ❌ | 3,0% ❌ |
| 10 s / 0,3 s | 2,14× ❌ | 777 ms ❌ | 4,4% ❌ |
| 6 s / 0,5 s — **default atual** | **3,73×** ✅ | 620 ms ❌ | 2,5% ❌ |
| 2 s / 0,3 s | 3,06× ✅ | **513 ms** ❌ | 3,2% ❌ |

## Conclusões — e só o que a evidência sustenta

**1. RNF-01 (RTFx ≥ 3×) está atendido** em toda configuração que não satura: 3,06× a 3,73×.
Hop menor **piora** o RTFx (2,14× a 0,3 s com janela de 10 s) porque redecodifica a janela
inteira mais vezes — a intuição "hop menor = mais responsivo" é falsa neste desenho.

**2. Um defeito de encanamento explicava a maior parte da falha, não o modelo.**
`DualCapture.read()` devolvia **um** chunk por stream por chamada, enquanto o `parec` produz
~30/s por canal. O backlog crescia sem limite — medido de 101 → 227 chunks em 4,4 s. Corrigido
para drenar a fila com teto por stream; o backlog caiu de **100% para 2,5%** das amostras.
Diagnosticar isso como "modelo lento" teria levado a otimizar a coisa errada.

**3. RNF-02 não fecha, e o motivo é arquitetural — não é o modelo.** A latência tem piso
`hop + decode(própria) + decode(do outro canal)`, porque os dois canais decodificam em série.
Na melhor configuração possível — janela de 2 s, o mínimo com texto ainda utilizável — o p99
chega a **513 ms**, a 2,6% do alvo. Descer mais exigiria janela menor que 2 s, e aí o
LocalAgreement-2 perde o contexto de que precisa para confirmar palavra.

Isto **quantifica a necessidade de M6**: redecodificar a janela inteira a cada hop não fecha
RNF-02 em dois canais. Um decoder streaming-causal — que processa só o chunk novo mantendo o
cache do encoder — remove o termo `decode(janela)` da conta. O blueprint já existe
(`m6-streaming-causal-blueprint.md`); esta medição dá o número que justifica executá-lo.

## Limitações

- **RNF-04 e RNF-05 não foram exercitados.** As corridas têm ~30 s; o critério térmico exige
  30 min, e nenhuma teve carga concorrente. O relatório da app marca ambos ❌ por *condição
  não satisfeita*, não por falha medida — a distinção está em `veredito_condicoes()`.
- **A métrica de backlog é enviesada por construção.** Ela amostra a fila logo após cada
  decode, quando o `parec` já enfileirou o áudio que chegou durante o processamento. Os 2,5%
  são um teto, não uma medida de saturação real; o sinal confiável é a *tendência* (antes do
  fix crescia sem limite; agora não cresce).
- **A latência medida é `chegada do 1º chunk não processado → fim do decode`**, não
  literalmente "fim da fala → texto". É um proxy conservador — inclui a espera pelo hop.
- Corridas curtas, uma máquina, sem repetição. Nenhum número aqui tem intervalo de confiança.

## Reprodução

```bash
python3 jvscribe/realtime/live_transcribe.py --duracao 32 --relatorio out.md
python3 jvscribe/realtime/live_transcribe.py --duracao 1800 --com-carga   # soak RNF-04/05
```
