---
type: Log
title: Histórico do projeto
description: Ordem cronológica das decisões e medições que produziram o estado atual.
tags: [log, historico]
timestamp: 2026-08-01T00:00:00Z
---

# Histórico

Ordem cronológica. Detalhe de cada item no conceito linkado.

## 2026-09-14 (noite) — ADR-0006: TAGARELA é o corpus principal, risco de licença aceito

- **Decisão do dono**: usar o TAGARELA (8.130 h de pt-BR) apesar do `CC-BY-NC-SA-4.0`. A
  alternativa limpa soma ~1.180 h — **menos do que o modelo atual já viu** —, então não moveria o
  gargalo — [ADR-0006](decisoes/0006-tagarela-como-corpus-principal.md).
- **O que se aceita está dimensionado**: NC bloqueia uso comercial, SA contaminaria a distribuição
  do peso, e a pergunta "modelo treinado é derivado do corpus?" não tem consenso na indústria.
- **A pendência bloqueia M8, não M10.** Registrada no `ROADMAP.md` § Constraints com o milestone
  que ela trava.
- **Quatro mitigações entram como parte da decisão**: proveniência por shard, braço de corpus
  limpo mantido em paralelo, cópia local preservada, e o contraste dos dois braços medido em T5 —
  se o limpo ficar a menos de 2 p.p., o risco não estava sendo pago.

## 2026-09-14 (noite) — T3/Q-12: o corpus aberto em PT é menor e do domínio errado

- **YODAS-Granary pt tem 262 h**, não as 15–25 mil que o plano estimava. Medido por duas vias
  independentes que concordam em 1%; o card do dataset erra por ~8× —
  [m10-t3-quanto-corpus-pt-existe](medicoes/m10-t3-quanto-corpus-pt-existe.md).
- **91% do volume de Granary pt está no VoxPopuli** — parlamento europeu, fala preparada — e é a
  única fonte cujo `duration` não existe (`'None'` em 2,28M linhas), logo `[ESTIMATIVA]`.
- **Só ~1.200 h são medidas E de domínio razoável** (ytc 959 h + YODAS 262 h), e o YODAS tem
  mediana de 0,98 s por segmento — quase palavra isolada, de baixa utilidade para chunk de 1120 ms.
- **Q-13 respondida por medição de texto**: o gerúndio brasileiro contra o `a + infinitivo`
  europeu separa os corpora sem ambiguidade. **VoxPopuli é 3,8% pt-BR**; ytc, YODAS e TAGARELA
  ficam em 95–97%.
- **A maior fonte pt-BR é o TAGARELA — 8.972 h, 84% de todo o pt-BR disponível — e o projeto usou
  13% dela.** A expansão de T3 não depende de achar corpus novo, e sim de escalar o que M3 já
  escolheu, re-rotulando com professor adaptado.
- **Escala e licença estão em lados opostos**: o TAGARELA é `CC-BY-NC-SA-4.0`. Só com licença
  comercialmente limpa, o pt-BR cai de ~10.200 h para ~1.660 h.
- **Q-09 respondida, e fecha uma porta.** O *Cem Mil Podcasts* é o **Spotify Podcast Dataset em
  português** (mesmos autores do "100,000 Podcasts", COLING 2020) e o canal de distribuição saiu do
  ar. Ir à fonte bruta não afrouxa a licença — aperta. **O TAGARELA é o acesso mais permissivo que
  existe àquele áudio**, e já está em casa. Q-09 deixa de ser risco dominante e vira restrição
  conhecida no `ROADMAP.md`.
- **A meta de 25.000 h não se sustenta** com fontes abertas em pt-BR. O teto realista é ~10.200 h,
  dos quais 8.130 h dependem de aceitar `CC-BY-NC-SA-4.0`.

## 2026-09-14 (noite) — RNF-02 revisado: 500 ms → 1,6 s, e o modelo pode ir a 376M

O dono fixou o orçamento de latência em **1120 ms de chunk** depois de ver a curva medida. A
revisão está registrada no `ROADMAP.md` § Success criteria, com o que se ganha e o que se perde.

- **Ganho**: teto de parâmetros sobe de 237M para **376M** (5,9× os 64M atuais) e o WER de
  referência cai de 5,65% para 5,48%.
- **Perda declarada**: 1,6 s é latência de **texto confirmado**. Se M8 mostrar que o atendente
  precisa de retorno mais rápido, a saída é exibir hipótese instável antes de confirmar — não
  encolher o chunk, que custaria capacidade do modelo.
- **Consequência para M10**: T4 e T5 passam a dimensionar o encoder na faixa de 250–350M, com
  chunk de 1120 ms, em vez dos 120–150M que o plano assumia.

## 2026-09-14 (tarde) — M10/T1b e T2: latência compra capacidade, e a régua pública entra

- **53% do custo do encoder é pago POR INVOCAÇÃO** e some quando o chunk cresce. Dobrar a
  latência de 560 ms para 1,12 s dá **+50% de RTFx** (2,77× → 4,15× agregado, IC95% conclusivo)
  **e** melhora o WER — não é trade-off, é Pareto —
  [m10-t1b-latencia-e-teto](medicoes/m10-t1b-latencia-e-teto.md).
- **O teto de parâmetros é função da latência**: 145M a 320 ms, **237M a 560 ms**, **376M a
  1,12 s**. O modelo pode crescer 3,7× a 5,9× sobre os 64M atuais, conforme o orçamento escolhido.
- **O teto de 174M de T1 estava errado** — aquele ajuste comparou dois modelos com chunks
  diferentes e atribuiu toda a diferença ao tamanho. Corrigido para 237M a 560 ms.
- **A régua do Open ASR Leaderboard entra como terceira régua** (`normalize_for_leaderboard`):
  preserva acento e converte dígito para forma falada, ao contrário das duas internas —
  [m10-t2-regua-publica](medicoes/m10-t2-regua-publica.md).
- **T2 mede 6,06% contra os 5,80% publicados.** O critério de ±0,15 p.p. era inalcançável por
  construção: exportar para ONNX custa mais WER que isso. O offset é de artefato e fica declarado.
- **A escolha da coluna de referência do FLEURS vale 2,19 p.p.** — `transcription` contra
  `raw_transcription`, quase toda a diferença em inserção.

## 2026-09-14 — M10/T1: o teto de CPU medido, e o Nemotron vira professor

- **O teto de parâmetros é ~174M**, não linear: há **68 ms por segundo de áudio** de custo fixo
  que nenhum modelo menor remove, o que limita o RTFx agregado a 14,7× nesta máquina mesmo com
  encoder de tamanho zero — [m10-t1-teto-de-cpu](medicoes/m10-t1-teto-de-cpu.md).
- **`nemotron-3.5-asr-streaming-0.6b` reprova o RNF-01** em 2 P-cores: 1,22× por canal com dois
  canais, contra o alvo de 3×. Entra no M10 como professor e régua, não como produto.
- **Um FastConformer de ~115M passa**: 3,75× por canal. A faixa de 120–150M é a que sustenta o
  crescimento do modelo que o M10 assume.
- **Dois canais não custam overhead** — o agregado é indistinguível do de um canal nos dois
  modelos (IC95% cruza zero). O número a vigiar é sempre o por-canal.
- **`num_threads=4` é metade de `num_threads=2`** em 2 P-cores, com IC95% [−1,147; −0,987].
  Confirma por medição a heurística de `common/cpu.py`.

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
