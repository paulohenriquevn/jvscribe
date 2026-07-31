---
type: Índice
title: Disciplina de evidência
description: As regras que este projeto pagou para aprender. Cada uma nasceu de um erro concreto.
tags: [evidencia, metodo, medicao]
timestamp: 2026-07-31T00:00:00Z
---

# Disciplina de evidência

Este projeto registra no próprio PRD uma falha de método já cometida: a escolha de Zipformer foi
sustentada, inicialmente, por benchmarks medidos em arquitetura sem parentesco. As regras abaixo
são a vacina.

| conceito | a regra |
|---|---|
| [rotulos-de-proveniencia.md](rotulos-de-proveniencia.md) | Todo número carrega rótulo. Sem rótulo, o número não existe |
| [nunca-concluir-de-uma-corrida.md](nunca-concluir-de-uma-corrida.md) | Três erros documentados. Use bootstrap pareado |
| [o-que-nao-transfere.md](o-que-nao-transfere.md) | Componente ≠ sistema; isolado ≠ sob carga; uma máquina ≠ a frota |

## Hipótese, evidência e conclusão são seções distintas

Conclusão que excede a evidência é defeito de severidade máxima — **mesmo quando se prova certa
depois**.
