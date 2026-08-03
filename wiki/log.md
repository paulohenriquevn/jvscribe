---
type: Log
title: Histórico do projeto
description: Ordem cronológica das decisões e medições que produziram o estado atual.
tags: [log, historico]
timestamp: 2026-08-01T00:00:00Z
---

# Histórico

Ordem cronológica. Detalhe de cada item no conceito linkado; mudanças de código no
`CHANGELOG.md` do repositório.

## 2026-08-01 — a régua estava errada, e isso moveu tudo

O dia começou perseguindo 10% de WER e terminou descobrindo que **o instrumento mentia nos dois
sentidos**. Nada no modelo mudou; o que mudou foi o que sabemos sobre ele.

- **A régua contava acerto do modelo como erro.** 187 das 919 referências do FLEURS trazem
  **dígito** e o modelo emite forma falada — ele acerta, a régua reprova. Custo: **2,29 p.p.**
  E ela **premia** 0,31 p.p. no eixo oposto, ao apagar acento (que em português **funde palavras
  distintas**: `e`/`é`, `pais`/`país`). O padrão da área tem o mesmo defeito, **e só em não-inglês** —
  [e9](medicoes/e9-vies-do-normalizador-contra-modelos-de-forma-falada.md).
- **O `test[0:100]` foi aposentado.** É amostra alta: o test completo dá 14,83% contra os 15,99%
  publicados, e duas amostras honestas de 100 variam de 12,4% a 17,5%.
- **Beam + LM entrega 4,7%, não 10–20%** — e a citação herdada vinha de CTC nível-caractere e de
  modelos treinados em minutos de áudio. Corpus, ordem do n-grama e largura de beam **saturaram**.
  O LM comprava ganho **apagando palavras**; o ponto de operação foi corrigido —
  [e6](medicoes/e6-beam-lm.md).
- **O split S/D/I foi medido pela primeira vez.** Os "três terços" nunca foram terços do erro — são
  terços das substituições (68,6%). **Inserção é 18,5%** e ninguém tinha olhado — [e8](medicoes/e8-composicao-do-erro-na-regua-corrigida.md).
- **Seis técnicas de pré-processamento, seis pioras.** Banda sintética é pior que banda ausente: o
  reconhecedor lida melhor com informação **faltando** do que com informação **inventada** —
  [e12](medicoes/e12-realce-de-audio-antes-do-asr-piora.md).
- **NURC-SP entra como conjunto de dificuldade** — 36,9% (49,2% no recorte ruim), licença **MIT**,
  e sobreviveu à auditoria de convenção que poderia tê-lo derrubado —
  [e10](medicoes/e10-busca-por-conjunto-desafiador-ptbr.md), [e13](medicoes/e13-duas-verificacoes-antes-da-gpu.md).
- **O corpus de treino é ~1.413 h, não ~870.** A documentação erra por 1,6×, e com isso **toda
  projeção de escala usou o denominador errado** — [e13](medicoes/e13-duas-verificacoes-antes-da-gpu.md).

## 2026-07-31 — M6 em medição

- **Profile por operador** substituiu o cronômetro de blocos. Revelou que o matmul quantizado é
  só 24,4% do custo e que `ctc_output` custa 0,3% —
  [m6-profile-por-operador](medicoes/m6-profile-por-operador.md).
- **FLToP e blank-skipping não se aplicam** a este pipeline, com a fonte de cada um —
  [o-que-nao-se-aplica](otimizacao/o-que-nao-se-aplica.md).
- **Confirmado que o modelo não é streaming**, por três fontes independentes. É a restrição
  dominante — [nao-e-streaming](modelo/nao-e-streaming.md).
- **Afinidade de CPU revertida**: 25% melhor isolada, 46% pior no sistema, porque
  `sched_setaffinity` é herdado pelos filhos — [afinidade-de-cpu](otimizacao/afinidade-de-cpu.md).
- **`stats.comparar_pareado()`** criado depois de três conclusões erradas de corrida única —
  [nunca-concluir-de-uma-corrida](disciplina/nunca-concluir-de-uma-corrida.md).
- **Calibração por máquina**: a janela deixa de ser constante — [calibracao](motor/calibracao.md).

## 2026-07-30 — M9 concluído, modelo publicado

- **O modelo oficial mudou por medição**: dos dois candidatos M5, o averaged vence com IC95% do
  delta [−2,25; −0,43] pp — [entregavel](modelo/entregavel.md).
- **Publicado** em `paulohenriquevn/jvscribe`, e a reprodutibilidade verificada a partir do
  download — [reprodutibilidade](medicoes/reprodutibilidade.md).
- **Checkpoint corrompido recuperado**: o `.pt` do modelo oficial chegou truncado a 80 MB de
  257 MB — [retomar-o-treino](treino/retomar-o-treino.md).
- **Runtime Rust removido** — não por performance ([ADR 0004](decisoes/0004-remocao-do-runtime-rust.md)).
- **Governança de artefato (M9)**: o `model_card.json` vira autoridade, e o vocabulário passa a
  ser validado por fingerprint — [vocabulario](modelo/vocabulario.md).

## Antes — M0 a M5

- **M5**: modelo em escala, 2/3 DoDs; o telefônico ficou deferido por limite de dado —
  [m5-modelo-final](medicoes/m5-modelo-final.md).
- **M4**: piloto comparativo travou o finalista `medium` (64M) por soak e carga —
  [ADR 0003](decisoes/0003-finalista-medium.md). A cabeça de fonema entregou −4,74% relativo —
  [cabeca-de-fonema](modelo/cabeca-de-fonema.md).
- **M3**: corpus — pseudo-labeling com filtro por concordância.
- **M2**: decisão de família. Transducer/CTC ~2× mais rápido que AED em CPU —
  [m2-rtfx-candidatos](medicoes/m2-rtfx-candidatos.md).
- **M1**: instrumentação e régua — [m1-harness](medicoes/m1-harness.md).
- **M0**: walking skeleton.
