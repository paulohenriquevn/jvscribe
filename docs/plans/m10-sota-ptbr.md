# M10 — ASR PT-BR streaming em nível SOTA

> Decomposição do milestone M10. Fonte da verdade dos milestones continua sendo o `ROADMAP.md`.
> Revisão de 2026-09-14 (noite), após T1, T1b e T2 executados.

---

## Goal

Um modelo ASR **PT-BR monolíngue, streaming causal**, que bata o melhor streaming aberto em
português — `nvidia/nemotron-3.5-asr-streaming-0.6b`, **5,80% FLEURS pt** e **10,70% MLS pt** —
medido na **régua pública do Open ASR Leaderboard**, rodando em CPU dentro do envelope do RNF.

**Não-objetivo:** bater sistemas proprietários de datacenter (Azure 2,08%, Scribe v2 2,60%).
Fora do alcance sob restrição de CPU, e fora do argumento econômico do projeto.

---

## O que as três primeiras tarefas estabeleceram

| | resultado | onde |
|---|---|---|
| **T1** | Nemotron 600M reprova o RNF-01 em 2 P-cores: 1,22× por canal. Entra como professor, não como produto | [`m10-t1`](../../wiki/medicoes/m10-t1-teto-de-cpu.md) |
| **T1b** | 53% do custo do encoder é pago **por invocação**. O teto é função da latência | [`m10-t1b`](../../wiki/medicoes/m10-t1b-latencia-e-teto.md) |
| **T2** | Régua pública implementada e travada por 11 testes. Offset de artefato: +0,26 p.p. | [`m10-t2`](../../wiki/medicoes/m10-t2-regua-publica.md) |

**Decisão do dono (2026-09-14):** orçamento de latência fixado em **1120 ms de chunk**.
RNF-02 revisado de 500 ms para **1,6 s** no `ROADMAP.md`.

### O modelo de custo que governa o dimensionamento

```
tempo(T, P) [ms por segundo de áudio] = (7,69 + 0,19509·P)/T + (29,53 + 0,17218·P)
```

`T` em segundos, `P` em milhões de parâmetros. Erro de previsão ≤ 1,4% sobre 5 pontos medidos.

**Teto a 1120 ms: 294M parâmetros** no regime sustentado (376M em rajada curta — o sustentado é o
que dimensiona). Faixa-alvo revisada para **250–280M**, 4,4× o modelo atual
([`m10-q14`](../../wiki/medicoes/m10-q14-soak-sustentado.md)).

---

## Baseline corrigido

| métrica | valor | fonte |
|---|---|---|
| WER FLEURS pt | 14,83% canônica · **12,75% estrita** | `e9` |
| WER CORAA espontâneo | 23,31% · CER 11,28% | `m5-modelo-final` |
| **WER call center REAL 8 kHz** | **40,13%** | `m5-modelo-final` |
| WER NURC-SP high / low | 32,63% / 49,22% | `e11` |
| **Horas que o modelo VIU no treino** | **~1.413 h** | `e13` |
| Horas baixáveis (TAGARELA, 1.764 shards) | 8.972 h | `treino/corpus.md` |
| Composição do erro | S 68,6% · I 18,5% · D 12,9% | `e8` |
| Ganho de beam + LM | 4,7% relativo, **saturado** | `e6-beam-lm` |
| Banda como causa do gap de domínio | **~1/6** (6,07 de ~34 p.p.) | `e11` |

> ⚠️ **Correção de 2026-09-14.** A primeira versão deste plano citava 8.972 h como o corpus de
> treino. `e13` mediu do log que o modelo entregue viu **~1.413 h** — os 8.972 h são o que existe
> **baixável**, não o que entrou. O salto até 25.000 h é portanto de **17,7×**, não de 2,8×, e o
> custo de T5 foi subestimado na mesma proporção.

**Diagnóstico vigente:** o fine-tune de M5 faz **overfitting**, não underfitting. A capacidade do
encoder não era o gargalo — dado era. Com o teto agora em 294M, a capacidade deixa de ser
restrição e o gargalo volta inteiro para o corpus.

---

## Coverage Matrix

| # | Gap | Task | Estado |
|---|---|---|---|
| G1 | Quanto modelo cabe em 2 P-cores | T1 · T1b | ✅ fechado |
| G2 | "SOTA" não afirmável na régua interna | T2 | ✅ fechado |
| G3 | Corpus de 1.413 h contra 15–94 k da receita | **T3** | 🔶 inventário fechado, ingestão pendente |
| G4 | Overfitting ao ruído de pseudo-rótulo genérico | T3 · T4 | ⏳ |
| G5 | Arquitetura não-causal; RNF-02 não fecha por construção | T4 · T5 | ⏳ |
| G6 | Modelo preso em 64M | T4 · T5 | ✅ desbloqueado (teto 294M sustentado) |
| G7 | Call center a 40,13%; augmentação alcança 1/6 | T6 | ⏳ |
| G8 | Motor assume janela deslizante | T7 | ⏳ |
| G9 | Nenhuma afirmação verificável por terceiro | T8 | ⏳ |
| G10 | Decode saturado | — | declarado fora de escopo (`e6`) |

**10/10 mapeados.**

---

## ADRs

### ADR-001 — O alvo de inferência continua CPU; o crescimento é financiado pela latência
**Status: confirmado por medição.** T1b mostrou que o crescimento não vem de "otimizar o motor",
e sim de aceitar latência: 53% do custo do encoder é pago por invocação. A 1120 ms o teto é **294M**
no regime sustentado (`m10-q14`).
**Alternativas rejeitadas:** abandonar CPU (destrói o argumento econômico do `ROADMAP.md` §
Problem); travar em 64M (o diagnóstico de overfitting era sobre 1.413 h, não sobre 25.000).

### ADR-002 — A arquitetura é decidida por bake-off medido
Duas trilhas sob protocolo idêntico em T4: **A** — Nemotron-3.5 com full-parameter fine-tune
monolíngue PT-BR, preservando cache-aware e prompt conditioning; **B** — Zipformer2 causal
escalado a ~270M, com CR-CTC.
**Alternativas rejeitadas:** só A (descarta o domínio de icefall de M4/M5); só B (descarta um
backbone que já entrega 5,80% em pt); decidir por benchmark de terceiros (`disciplina/o-que-nao-transfere`).

### ADR-003 — Nemotron-3.5 como professor, sob OpenMDW-1.1
A licença concede uso "without restriction, including modification" e declara que **não impõe
restrição alguma sobre os outputs**. Pseudo-rótulos são outputs, logo livres. A obrigação é reter
o texto da licença ao distribuir pesos derivados.
**Alternativas rejeitadas:** Whisper-v3 como professor único (é o modelo cujo ruído causou o
overfitting de M5); nenhum professor externo (G3 não fecha).

### ADR-004 — Filtro por concordância entre famílias, não por autoconfiança
StreamHear mede que top-K por log-likelihood nunca ajuda, mas o sinal testado lá é
**autoconfiança**, mal calibrada. Concordância entre sistemas independentes mede erro
descorrelacionado — outro sinal, que o paper não testou.
**Alternativa rejeitada:** adotar top-K=100% direto. Fica como **braço de controle** em T3, para
que ADR-004 possa ser refutado por medição em T5.

### ADR-005 — Sintético só entra acima de limiar declarado antes
Conforme `arXiv:2505.16972`. **Alternativa rejeitada:** misturar e medir o WER final — confunde
qualidade do sintético com razão de mistura.

### ADR-006 — Latência de 1120 ms, decidida pelo dono
**Ganho:** teto de 294M sustentado (376M em rajada) e WER de referência 5,48% contra 5,65% a 560 ms.
**Perda declarada:** 1,6 s é latência de **texto confirmado**. Se M8 mostrar que o atendente
precisa de retorno mais rápido, a saída é exibir hipótese instável antes de confirmar — não
encolher o chunk, que custaria capacidade.
**Alternativas rejeitadas:** 560 ms (teto de 182M sustentado); 2240 ms (extrapolação sem artefato medível).

---

## Tasks restantes

### T3 — Corpus em escala, com professor adaptado antes de rotular

#### Why this step
`e13` mediu que o modelo viu ~1.413 h. A receita de referência usa 15–94 mil. Com o teto agora em
294M, capacidade deixou de ser a restrição e o corpus é o gargalo inteiro. Mas mais pseudo-rótulo
do mesmo tipo reproduz o overfitting de M5 — a correção de ordem vem do StreamHear: **adaptar o
professor ao domínio antes de rotular**.

#### Passos
1. ~~Medir Q-12~~ — ✅ **feito**: o pt-BR disponível é **~15.600 h**, quase todo no TAGARELA
   ([`m10-t3`](../../wiki/medicoes/m10-t3-quanto-corpus-pt-existe.md)). YODAS pt tem 262 h, não
   15–25 mil; VoxPopuli é 3,8% brasileiro.
2. Baixar 520–832 shards do TAGARELA via volume vast.ai
   ([plano de treino](m10-treino-vastai.md)). Somar `ytc` (927 h) e YODAS (250 h) como braço de
   licença limpa.
3. Adaptar cada professor do ensemble a PT-BR espontâneo **antes** de gerar pseudo-rótulo.
4. Estender `corpus/pseudo_label.py` para ensemble e `corpus/agreement_filter.py` para
   concordância tripla.
5. Rodar o braço de controle sem filtro (ADR-004).

#### Acceptance criteria
- [x] Q-12 respondida com número medido, não estimado
- [ ] Manifesto com **5.000–8.000 h** (a meta de 25.000 h foi refutada: não existe tanto pt-BR
      aberto), cada shard com licença e proveniência de rótulo
- [ ] Auditoria de vazamento: nenhuma utterance dos test sets no treino
- [ ] Invariante travada por teste: pseudo-rótulo nunca entra no test set
- [ ] Braço de controle preparado

#### Concurrency tests
- [ ] Escrita de manifesto atômica por shard; falha parcial não produz manifesto truncado

---

### T4 — Bake-off arquitetural

#### Why this step
O ADR 0003 travou a arquitetura sob restrições que mudaram: sem streaming aberto em pt, sem
orçamento, corpus 17× menor, teto de capacidade desconhecido. Reabrir é obrigatório; reabrir sem
protocolo seria trocar uma convicção por outra.

#### Acceptance criteria
- [ ] Vencedor com IC95% pareado do delta **não cruzando zero** (`common/stats.py`)
- [ ] BSF medido por trilha; BSF > 1,3 desqualifica
- [ ] RTFx do vencedor dentro do teto de **294M** a 1120 ms, medido em 2 P-cores **no regime
      sustentado** (30 min), não em rajada
- [ ] ADR de superseção do `wiki/decisoes/0003-finalista-medium.md`

#### Concurrency tests
- [ ] WER de validação com 1 GPU e com N GPUs difere ≤ 0,3 p.p. no mesmo número de amostras vistas

---

### T5 — Treino de escala

#### Why this step
O bake-off decide a forma; a escala move o número, porque o gargalo é dado.

#### Acceptance criteria
- [ ] **WER FLEURS pt ≤ 5,80%** na régua do leaderboard, streaming, IC95% do delta sem cruzar zero
- [ ] **WER MLS pt ≤ 10,70%**
- [ ] RTFx sustentado ≥ 3× por canal com dois canais e softphone ativo
- [ ] WER de call center medido e reportado **por canal**
- [ ] ADR-004 resolvido por medição

---

### T6 — Dado sintético para o domínio

#### Why this step
Não há áudio real de call center PT-BR. `e11` mede que a banda — a única coisa que augmentação de
canal simula — explica **1/6** do gap. Os outros cinco sextos são conteúdo, espontaneidade e
estrutura de diálogo, que só síntese de fala alcança.

#### Acceptance criteria
- [ ] Limiar de inteligibilidade declarado **antes** da geração em massa
- [ ] Varredura de razão de mistura com ≥ 3 pontos
- [ ] **WER call center 8 kHz ≤ 25%**, com IC95%
- [ ] WER reportado **por canal** (mic e loopback separados)
- [ ] FLEURS pt não piora mais que 0,3 p.p. absoluto

---

### T7 — Motor com estado

#### Why this step
`common/streaming.py` implementa janela deslizante + LocalAgreement-2 porque o modelo é
não-causal. Com modelo causal essa camada some, e o retrabalho de 10,6× junto.

#### Acceptance criteria
- [ ] `tests/test_streaming_features.py` continua verde (equivalência a 9,5×10⁻⁷ é contrato)
- [ ] Quantização comparada em ≥ 3 variantes; `ConvInteger`/`MatMulInteger` medido e rejeitado se
      reproduzir a degradação de +1,94 p.p. de `arXiv:2604.14493`
- [ ] Latência p99 ao vivo **≤ 1,6 s** (RNF-02 revisado)
- [ ] `bench/stress_test.py` por 30 min com softphone: sem backlog, térmica ≥ 80%
- [ ] Validação de par modelo↔vocabulário por fingerprint ativa

#### Concurrency tests
- [ ] Caches de estado **isolados por canal** — vazamento não aparece no WER
- [ ] Backpressure sob consumidor lento preserva a cauda

---

### T8 — Verificação independente

#### Acceptance criteria
- [ ] WER reproduzido **a partir do download**, dentro de ±0,1 p.p.
- [ ] `vocab_fingerprint` e sha256 conferem
- [ ] PR aberto no Open ASR Leaderboard
- [ ] Distribuição carrega o texto da OpenMDW-1.1 se a Trilha A vencer

---

## Failure scenarios

| # | Cenário | Detecção | Mitigação |
|---|---|---|---|
| F1 | Download de dataset truncado (YODAS pt ~1,5 TB) | sha256 e contagem de shards | Retomada por shard; manifesto só após verificação |
| F2 | Rate limit ou 5xx do HF durante ingestão longa | status por shard | Backoff com teto; falha de um shard não invalida os demais |
| F3 | **Disco enche e corrompe checkpoint** — já aconteceu | tamanho e carregabilidade após cada escrita | Poda proativa; escrita atômica; `bench/finetune_smoke.py` |
| F4 | Instância de GPU interrompida | heartbeat por época | Retomada do último checkpoint verificado |
| F5 | Professor alucina sistematicamente num domínio | divergência anômala entre os três | Filtro de concordância descarta; shard marcado, não aceito em silêncio |
| F6 | **Processo longo perde tudo ao morrer** — aconteceu em T2 | ausência de saída parcial | Gravação incremental com `flush` e retomada; nunca gravar só no fim |

---

## Drawbacks & Risks

**D1 — A meta de 5,80% pode não ser alcançável.** O Nemotron treinou em escala que o projeto não
alcança. Se T5 platôar acima, o resultado ainda vale (o Pareto "streaming PT-BR sub-400M" está
vazio), mas a afirmação de SOTA cai — e isso precisa ser dito, não redefinido depois do fato.

**D2 — O salto de corpus é de 17,7×, não 2,8×.** A correção de `e13` reprecifica T3 e T5. O custo
de treino sobe na mesma proporção, e o orçamento precisa ser revisto antes de T5.

**D3 — Dado sintético pode ensinar o modelo a transcrever TTS.** Todos os estudos citados em T6
são fine-tune de modelos grandes, não treino de modelos de 300M do zero.

**D4 — Nenhuma alavanca de decode restou.** Beam+LM saturou em 4,7%; correção pós-decode tem teto
em 68,6% do erro e quebra token correto em até 64% das edições. Sem plano B barato na inferência.

**D5 — A migração de arquitetura invalida comparações.** Se a Trilha A vencer, as medições de
M4/M5 deixam de ser comparáveis com as novas.

**D6 — Concentração de fornecedor.** Professor, backbone candidato, runtime e corpus vêm todos da
NVIDIA. Licença permissiva, dependência técnica real.

~~**D7**~~ — **RESOLVIDO em parte.** O soak de 30 min mediu degradação de apenas 2,4% e o
**RNF-04 passa**; a queda vista em T2 era carga concorrente, não térmica. Mas o regime sustentado
custa 20,6% a mais que a rajada, e o teto caiu de 376M para **294M**
([`m10-q14`](../../wiki/medicoes/m10-q14-soak-sustentado.md)). **RNF-05 (carga concorrente) segue
não exercitado** — e é o que o pior minuto do soak (1,20× por canal) sugere ser o risco real.

---

## Unresolved Questions

**Q-11 — O tamanho final do modelo.** Faixa definida (250–350M), valor exato depende de T4.

**Q-12 — Quantas horas de pt existem no YODAS-Granary.** Primeiro passo de T3.

**Q-13 — Fração pt-BR contra pt-PT nos corpora novos.** VoxPopuli é parlamento europeu; YODAS é
YouTube misto. Um corpus majoritariamente europeu move FLEURS sem mover call center brasileiro.

~~**Q-14**~~ — **RESPONDIDA**: sim, 20,6% mais lento. O teto a 1120 ms é **294M**, não 376M. Mas
não há degradação ao longo do tempo (2,4% em 30 min) e o RNF-04 passa.

**Q-01 (herdada) — Piso de hardware da frota BYOD.** T1 mediu a máquina de referência, não o piso.

---

## Sequenciamento

```
T1 ✅ ─┬─> T4 ──> T5 ──> T6 ──> T7 ──> T8
T1b ✅ ┤          ▲
T2 ✅ ─┤          │
T3 ────┴──────────┘
```

**Gate duro:** T5 não começa antes de T3 publicar o manifesto auditado. Treinar sobre corpus não
auditado é o modo de falha que M5 já pagou.
