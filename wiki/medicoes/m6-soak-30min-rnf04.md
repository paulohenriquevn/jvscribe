---
type: Medição
title: Soak de 30 min — RNF-04 exercitado pela primeira vez
description: O primeiro soak longo do projeto. Dois invariantes provados, o RNF-04 em si indeterminado por carga.
tags: [medicao, soak, rnf-04, estabilidade, memoria]
timestamp: 2026-07-31T11:31:00Z
---

# Soak de 30 min — RNF-04 exercitado pela primeira vez

Até 2026-07-31 nenhuma corrida deste projeto tinha chegado a 30 minutos. `RNF-04` e `RNF-05`
eram `[DESCONHECIDO]` por ausência de dado, não por resultado ruim. Esta é a primeira corrida
longa; ela **não** fecha o RNF-04, mas fecha duas outras perguntas que estavam abertas junto.

## Hipótese

> Um chip U de 15 W não sustenta turbo. Se houver decaimento térmico, o RTFx do minuto 30 será
> materialmente menor que o do minuto 1, com queda **monotônica** ao longo da corrida.

Critério declarado antes da corrida (`RNF-04`): `RTFx(último) ÷ RTFx(primeiro) ≥ 0,80`.

## Método

```
python3 jvscribe/bench/stress_test.py --audio-dir data/eval/fleurs/wavs \
        --minutos 30 --canais 2 --relatorio soak30.md
```

2 canais (mic + loopback, o caso 1:1 real), janela 6 s, hop 0,5 s, `intra=6 inter=3`, modelo
canônico `models/current/model.int8.onnx`, alimentado no ritmo do relógio de parede.

## Evidência

| | minuto 1 | minuto 30 | mínimo | máximo |
|---|---|---|---|---|
| RTFx | 4,07× | 2,74× | 1,65× | 4,59× |
| RSS (MB) | 581 | 612 | 565 | 704 |
| `commit` (estado do motor) | 64 | 64 | 64 | 64 |

- Razão RNF-04: **0,67**
- p99 de latência: 741 ms (mediana das janelas)
- **Load average durante a corrida: 5–14** — ambiente do próprio usuário (desktop, navegador,
  IDE, agentes), não a corrida.

## Conclusão

**O veredito de RNF-04 é `[INDETERMINADO]`, não "falhou".** `asr-evidence-discipline.md` § 5 é
explícito: máquina sob carga não mede. Três observações sustentam que o número reflete
contenção e não temperatura:

1. **A queda não é monotônica.** O RTFx oscila 1,65–4,59 sem tendência; um decaimento térmico
   desce e não volta. O minuto 8 (4,59×) é melhor que o minuto 1 (4,07×).
2. **Os piores minutos coincidem com os picos de load.** Minutos 29–30 (p99 de 30,9 s e 25,5 s)
   caem exatamente na janela em que o load foi a 14.
3. A máquina hospeda a sessão de trabalho do usuário — ela **não fica ociosa** por 30 minutos.

### O que ESTÁ provado (não depende de tempo de relógio)

| Pergunta | Antes | Agora |
|---|---|---|
| O motor vaza memória numa corrida longa? | `[DESCONHECIDO]` | **Não** `[MEDIDO]`. RSS 581 → 704 → 612 MB: platô, sem crescimento monotônico em 30 min. |
| O teto de estado do motor segura? | `[ESTIMATIVA]` — havia teste curto | **Sim** `[MEDIDO]`. `commit = 64` constante nos 30 minutos, em ambos os canais. `MAX_COMMITTED` funciona sob operação prolongada. |

O teto de estado é o que impede uma ligação de 40 minutos de acumular ~28 mil tuplas no caminho
quente. Antes disto havia teste de unidade; agora há prova em relógio de parede.

## Limitações

- **RNF-04 continua aberto.** Exige repetição em máquina ociosa. O critério e a ferramenta estão
  prontos; falta a bancada.
- **RNF-05 não foi exercitado.** Havia carga concorrente, mas não a declarada (softphone/Zoom).
  Carga de desktop não é substituta — o softphone disputa áudio, não só CPU.
- Áudio em loop de 542 s, não conversa real de 30 min. Mede o motor, não a variedade acústica.

## Consequência para a ferramenta

Esta corrida expôs um defeito em `stress_test.py`: ele emitia **"RNF-04: FALHA"** sem sequer
ler o load average, enquanto `calibrate.py` avisava acima de 1,0 desde sempre. Um veredito
autoritativo produzido a partir de dado que a própria disciplina do projeto rejeita.

Corrigido: a ferramenta registra a carga por janela, marca o veredito `INDETERMINADO (carga)`
acima do limiar, e devolve exit code **2** — indeterminado não é reprovado, para que um CI
ocupado não transforme ruído de ambiente em regressão de produto. Regressão em
`tests/test_stress_invariants.py`.
