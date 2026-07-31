---
type: Índice
title: Medições
description: Todo número, com hipótese, evidência e limitações separadas. Nenhum sem condição ao lado.
tags: [medicao, evidencia]
timestamp: 2026-07-31T00:00:00Z
---

# Medições

Cada documento separa **hipótese**, **evidência** e **limitações**. Conclusão que excede a
evidência é defeito de severidade máxima — ver [../disciplina/index.md](../disciplina/index.md).

## Por milestone

| documento | o que mediu |
|---|---|
| [m1-harness.md](m1-harness.md) | O instrumento, antes do experimento |
| [m1-baseline.md](m1-baseline.md) | Régua inicial multi-modelo |
| [m2-rtfx-candidatos.md](m2-rtfx-candidatos.md) | Transducer/CTC ~2× mais rápido que AED em CPU |
| [m5-modelo-final.md](m5-modelo-final.md) | O finetune que produziu o modelo entregue |
| [m6-profile-por-operador.md](m6-profile-por-operador.md) | Onde o tempo realmente está |
| [m6-topologia-de-cpu.md](m6-topologia-de-cpu.md) | CPU híbrida, `perf`, e o limite do instrumento |
| [m6-rnf-ao-vivo.md](m6-rnf-ao-vivo.md) | Os critérios de real-time sobre o pipeline completo |
| [m6-soak-30min-rnf04.md](m6-soak-30min-rnf04.md) | O primeiro soak de 30 min — sem vazamento, estado limitado, RNF-04 indeterminado por carga |
| [composicao-do-erro-e-o-que-cada-remedio-alcanca.md](composicao-do-erro-e-o-que-cada-remedio-alcanca.md) | O erro em três terços — e nenhuma intervenção alcança mais que um |
| [e0-instrumento-de-confianca.md](e0-instrumento-de-confianca.md) | O portão custa +0,31% — e o desenho que a execução refutou |
| [reprodutibilidade.md](reprodutibilidade.md) | O artefato publicado transcreve **e** treina |
| [benchmarks-publicos.md](benchmarks-publicos.md) | FLEURS, CORAA, telefônico — com comando de reprodução |

## O que continua não medido

- **RNF-04** (estabilidade térmica): nenhuma corrida chegou a 30 min
- **RNF-05** (carga concorrente): nenhuma teve softphone ativo
- WER em 8 kHz e em fala espontânea de call center
- Equivalência batch↔streaming
- Piso da frota BYOD (Q-01)
