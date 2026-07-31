---
slug: portao-de-confianca
created_at: 2026-07-31
goal: Descobrir, por experimento falseável e em loop, quanto do erro de transcrição é recuperável sem GPU — e parar cedo quando não for.
---

# Portão de confiança e correção pós-decode — protocolo experimental

## Goal

Determinar **por medição, não por analogia com a literatura**, quanto do erro de transcrição do
`jvscribe-ptbr-zipformer-ctc-64m` é recuperável por pós-processamento em CPU, e **abandonar cada
caminho no ponto em que o número diz que ele não paga**.

Este documento é um **protocolo experimental**, não um plano de construção. A entrega de cada
fase é um **número com intervalo de confiança** e um aprendizado registrado — inclusive quando o
resultado é nulo. Código só é promovido a `common/` depois que o número autoriza.

## Context

Cinco artigos foram lidos e mapeados (`wiki/medicoes/composicao-do-erro-e-o-que-cada-remedio-alcanca.md`).
Três deles convergem no mesmo achado — o conhecimento externo faz o trabalho, o LLM é embalagem
cara — e nenhum se aplica diretamente: somos CTC greedy, 64M, sem entrada de contexto, com
orçamento de RTFx ≥ 6× em CPU (`PRD.md` § 6, RNF-07).

Quatro medições próprias mudaram o desenho **depois** de eu ter proposto outra coisa:

1. O erro se divide em **três terços** (`non_word_hyp` 31,5% · `real_word_hyp` 36,6% ·
   `rare_ref` 31,9%). Nenhuma intervenção isolada alcança mais que um.
2. Existe um **portão de confiança gratuito**: margem top-1 sobre top-2 por palavra. A τ=1,0
   sinaliza 10,3% das palavras, contém 49,8% dos erros, precisão 49,4% — **4,8×** a taxa base.
3. O portão e o LM são **anticorrelacionados**: ele pega 69% de `non_word_hyp` mas só 32% de
   `real_word_hyp`, onde o modelo está *confiantemente* errado.
4. O **teto** do caminho de correção é baixo: 63% (substituições) × 50% (sinalizados) × 26%
   (alcançáveis) ≈ **8% dos erros**, com corretor perfeito.

O item 4 é o motivo de este documento existir como protocolo e não como plano de implementação:
**um teto de 8% não justifica construir antes de medir.**

## Baseline Context (deep review of current state)

Estado em `git 9a30c66`, `develop`, 501 testes verdes, ruff `F,E9,B` limpo.

### Files that will be touched

| arquivo | LoC hoje | papel hoje | mudança prevista |
|---|---|---|---|
| `jvscribe/common/ctc.py` | 57 | colapso greedy: `collapse`, `greedy_ids`, `detok_pieces`, `greedy_text` | ✅ **E0** — `+ greedy_palavras`, `+ Palavra`, `+ detok_pieces_bruto`. `greedy_text` **NÃO** tocada (ver revisão abaixo) |
| `jvscribe/tests/test_ctc_equivalence.py` | — | guarda a equivalência do colapso | **+** RED de que texto novo == texto antigo em toda fixture |
| `jvscribe/probes/portao_correcao_probe.py` | — | **novo** | o experimento das fases E2/E3 |
| `jvscribe/tests/test_portao_confianca.py` | — | **novo** | RED do portão e do corretor (lógica pura) |

Nada em `common/` é promovido antes da fase que o autoriza (D2).

### Current callers / dependents

`ctc.greedy_text` tem **6** chamadores de produção — `common/engine.py:27`,
`batch/batch_transcribe.py:55`, `batch/decode_onnx_local.py:47`, `eval/measure_callcenter.py:77`,
`eval/measure_realcodec.py`, `probes/tta_feature_align_probe.py:68` — mais os testes
`test_decode_onnx_local.py:49` e `test_ctc_equivalence.py:55`. **Nenhum pode mudar de assinatura**;
por isso `greedy_palavras` é adição, não substituição.

`ctc.BLANK` é importado por `common/streaming.py:24`, `realtime/mic_transcribe.py:44`,
`probes/blank_penalty_probe.py:29` e `bench/finetune_smoke.py:53`.

### Domain glossary

| termo | significado neste documento |
|---|---|
| **margem** | `log P(top-1) − log P(top-2)` num frame que emite token, em nats |
| **margem da palavra** | o **mínimo** das margens dos tokens que a compõem — o elo mais fraco |
| **portão** | sinalizar palavra cuja margem < τ |
| **τ** | limiar do portão, em nats |
| `non_word_hyp` | hyp não está no dicionário, ref está — atacável por léxico |
| `real_word_hyp` | ambas são palavras reais — nenhum filtro lexical distingue |
| `rare_ref` | ref fora do dicionário — alvo de biasing/contexto |
| **erro de prior** | acústica não discrimina; quem decide é o modelo de linguagem implícito |

### Architecture boundaries affected

`common/ctc.py` é **shared kernel**: import cross-pipeline só a partir de `common/`
(`.claude/rules/architecture.md`, guardado por `jvscribe/tests/test_dominios.py`). Adicionar
função ao kernel exige que ela seja domínio de kernel — a confiança é propriedade do **mesmo
colapso**, logo é (D1). O probe vive em `jvscribe/probes/`, cujo domínio declarado é hipótese de
pesquisa que pode dar nulo.

> **Revisão 1 (E0, 2026-07-31) — o passo 5 do loop em ação.** O plano previa `greedy_text` virar
> invólucro de `greedy_palavras`. **Refutado antes da primeira linha de código:** o `tokens.txt`
> do artefato tem o token id **7 == `'▁'`**; emitido, ele vira espaço solto e `detok_pieces`
> produz `"a  b"` enquanto uma junção por palavras produziria `"a b"`. Como invólucro,
> `greedy_text` mudaria de saída — e ela tem seis chamadores de produção (R4). O contrato passou
> a ser `[p.texto for p in greedy_palavras(x)] == greedy_text(x).split()`, que é exato nos dois
> casos e não toca em nada. Verificado contra **300 utterances reais**: 0 divergências.

## Prior Art & Related Work

| fonte | o que dá | o que NÃO dá |
|---|---|---|
| `wiki/medicoes/composicao-do-erro-e-o-que-cada-remedio-alcanca.md` | os três terços, o portão, o teto — tudo `[MEDIDO]` aqui | nada sobre fala espontânea |
| [`arXiv:2409.06062`](https://arxiv.org/abs/2409.06062) | ASR também CTC; ganho é o **retrieval**, não o LLM; ortografia ≈ fonema | usa OpenLLaMA 7B; entidades musicais em consultas curtas |
| [`arXiv:2509.19567`](https://arxiv.org/abs/2509.19567) | teto por contexto oráculo (24,1% rel.); retrieval barato bate LLM a 1/5 do custo | exige ASR que **aceita** lista de contexto |
| [`arXiv:2505.17410`](https://arxiv.org/abs/2505.17410) | dados sintéticos carregam ~90% do ganho; **IPA piorou** o CER (14,2→27,3) | GER com LLM de 70B |
| [`arXiv:2501.06713`](https://arxiv.org/abs/2501.06713) | estrutura bate semântica, e a vantagem cresce quando o modelo encolhe | outra tarefa; exige SLM de 1,5–4B |
| [`arXiv:2502.15264`](https://arxiv.org/abs/2502.15264) | — | não se aplica: exige decoder autoregressivo |
| `CLAUDE.md` § Otimização | beam + LM listado como alavanca não explorada, 10–20% relativo `[LITERATURA]` | número não medido aqui |

## Objective

Ao fim do protocolo, cada uma destas perguntas tem **um número com IC95%**, ou uma razão
documentada de por que a pergunta foi abandonada:

1. A margem por palavra separa certo de errado fora de FLEURS?
2. Correção pós-decode com portão reduz o WER? Em quanto, e quebrando quanto?
3. Beam + LM cabe no RNF-07? Reduz o WER em quanto?
4. Qual dos dois caminhos vale mais por unidade de custo?

## ADRs

### D1 — A confiança entra no kernel; o corretor, não

**Decisão.** `greedy_palavras` vai para `common/ctc.py` na fase E0. O corretor fica em
`probes/` até que a fase E2 o autorize.

**Alternativas consideradas.**
- *(a) Tudo em `probes/`.* Rejeitada: a margem sai do **mesmo colapso** que o texto; reimplementá-la
  no probe recria a duplicação que este repositório já pagou sete vezes com o colapso CTC
  (`CLAUDE.md`, `tests/test_dominios.py::test_um_so_parser_de_tokens_txt` é o análogo).
- *(b) Tudo em `common/`.* Rejeitada: promover o corretor antes da medição presume o resultado, e
  o teto medido (~8%) diz que ele pode não sobreviver.
- **(c) Confiança no kernel, corretor no probe.** Escolhida: a confiança é gratuita e tem uso
  independente do corretor (marcar palavra incerta no relatório ao vivo já vale sem corrigir nada).

### D2 — Predição pré-registrada e critério de morte, antes de rodar

**Decisão.** Cada fase declara, **antes da execução**, a predição numérica e o valor que a mata.
Alterar qualquer um dos dois depois de ver o resultado é defeito de severidade máxima.

**Alternativas.** *(a) Medir e depois interpretar* — rejeitada: é exatamente como este projeto
declarou vencedor de corrida única três vezes e errou nas três (`CLAUDE.md`). *(b) Só critério de
morte, sem predição* — rejeitada: sem predição não se aprende nada com um acerto.

### D3 — Correção sobre a string antes de re-decodificar com beam

**Decisão.** E2 corrige sobre o **texto de saída**. Re-decodificação local com beam só entra em
E3 se E2 falhar **e** a análise apontar a acústica descartada como causa.

**Alternativas.** *(a) Beam local direto* — rejeitada pela escada de parcimônia: exige mudar o
caminho de decode e não sabemos se a string basta. *(b) Só beam global* — é a fase E4, com custo
próprio a medir.

### D4 — O caminho do LM **não** é condicionado à confiança

**Decisão.** Se E4 acontecer, o beam/LM roda em toda a locução, não só nas palavras sinalizadas.

**Alternativa rejeitada:** *gatear o beam pela confiança para caber no orçamento.* Foi minha
proposta inicial e a medição a refutou: o portão pega só **32%** de `real_word_hyp`, que é
justamente a classe que o LM conserta. Gatear destruiria o benefício.

### D5 — Resultado nulo é entregável

**Decisão.** Toda fase produz um documento em `wiki/medicoes/`, com ou sem ganho. Uma fase
abandonada por critério de morte é registrada com o número que a matou.

**Alternativa rejeitada:** documentar só o que der certo — produz um repositório que parece ter
acertado sempre e não ensina onde não ir.

## Drawbacks & Risks

| # | risco | probabilidade | impacto | mitigação |
|---|---|---|---|---|
| R1 | **Todo o protocolo é FLEURS** — leitura de notícias, não conversa telefônica. Os três terços podem inverter no domínio real | alta | invalida a priorização, não as ferramentas | E1 declara isso como limite; E5 existe para refazer em áudio real |
| R2 | O teto de ~8% pode não se materializar: corretor real fica abaixo do oráculo | alta | E2 morre | critério de morte explícito; custo da fase é um probe |
| R3 | **Over-correction**: quebrar palavra correta. É o modo de falha que `arXiv:2505.17410` nomeia | média | pior que não corrigir | reportar consertou/quebrou separado; abster em empate |
| R4 | `greedy_palavras` mudar o texto de saída e alterar todo WER publicado | baixa | catastrófico | RED que exige texto idêntico ao de `greedy_text` em toda fixture, antes de qualquer outra coisa |
| R5 | Beam + LM não caber no RNF-07 | média | E4 morre | medir custo antes de medir ganho |
| R6 | Otimizar contra a régua errada por n pequeno | média | conclusão falsa | paired bootstrap com IC; `melhor=None` quando cruza zero |

## Unresolved Questions

1. **A margem é a melhor confiança disponível?** A posterior da trajetória colapsada provavelmente
   separa melhor. Não medido. E1 compara as duas se a margem ficar abaixo da predição.
2. **Merges e splits** (`não estivesse`→`naostivesse`) são 37% do erro total e **nenhum** corretor
   palavra-a-palavra os toca. Fora do escopo deste protocolo — registrado, não resolvido.
3. **De onde vem a lista de domínio** num call center real? `arXiv:2509.19567` sugere descobri-la
   da própria ligação. Não endereçado aqui.
4. **O portão vale sozinho?** Marcar palavra incerta na tela do atendente, sem corrigir, pode ter
   valor de produto independente. Não medido.

## Dependency Graph

E0 é pré-requisito de tudo — sem `greedy_palavras` não há margem para medir. E1 valida o
instrumento e pode matar o protocolo inteiro. E2 depende de E1. E3 depende de E2 **falhar** por
uma causa específica. E4 é independente de E1–E3 e pode rodar em paralelo. E5 depende de dado que
não existe e destrava a re-execução de tudo.

---

## Phase E0 — O instrumento

**Objective:** extrair a margem por palavra sem alterar uma vírgula do texto transcrito.

### T0.1 — `greedy_palavras` no kernel, com o texto provado idêntico

#### Objective
Adicionar `ctc.greedy_palavras(log_probs_row, id2tok, valid_len) -> list[Palavra]` com
`Palavra(texto: str, margem: float)`, e reescrever `greedy_text` como invólucro sobre ela.

#### Why this step
**O que faz:** move o colapso para uma função que também acumula a margem, e faz `greedy_text`
delegar — um colapso, um lugar.

**Por que agora:** a margem é o único sinal medido com valor comprovado (4,8× sobre a base) e é
gratuita. Sem ela nenhuma fase seguinte existe. E tem de vir antes porque é a única mudança do
protocolo que toca **6 chamadores de produção** (`## Baseline Context § Current callers`) — o
risco R4 é o maior do documento e precisa ser fechado primeiro.

#### Evidence
`jvscribe/common/ctc.py:1-57` tem `collapse`, `greedy_ids`, `detok_pieces`, `greedy_text`.
`jvscribe/common/engine.py:27` e `jvscribe/batch/batch_transcribe.py:55` chamam `greedy_text`
com três argumentos.

#### Files to edit
```
jvscribe/common/ctc.py                    — + greedy_palavras; greedy_text vira invólucro
jvscribe/tests/test_ctc_equivalence.py    — RED: texto novo idêntico ao antigo
```

#### TDD
```python
def test_greedy_text_continua_identico_apos_a_refatoracao():
    """R4: qualquer divergência aqui altera TODO WER publicado."""
    for fixture in FIXTURES_DE_LOGPROBS:
        assert ctc.greedy_text(fixture, ID2TOK) == "".join(
            p.texto for p in ctc.greedy_palavras(fixture, ID2TOK))

def test_margem_da_palavra_e_o_minimo_dos_tokens():
    """O elo mais fraco: uma palavra com um token duvidoso é duvidosa."""
    p = ctc.greedy_palavras(LOGPROBS_COM_UM_TOKEN_FRACO, ID2TOK)[0]
    assert p.margem == pytest.approx(MARGEM_DO_TOKEN_MAIS_FRACO)

def test_palavra_sem_token_emitido_nao_entra():
    assert ctc.greedy_palavras(SO_BLANK, ID2TOK) == []
```

#### Acceptance criteria
- [ ] `python3 -m pytest jvscribe/tests -q` verde (501+ testes)
- [ ] `python3 -m ruff check jvscribe --select F,E9,B` limpo
- [ ] `bench/bench_rtfx.py --iters 5` — RTFx dentro do IC95% do valor pré-mudança
- [ ] `batch/batch_transcribe.py` sobre `data/eval/fleurs/` produz **byte-idêntico** ao anterior

**Predição pré-registrada:** custo adicional < 2% do tempo de decode (a margem é uma subtração
sobre um `argsort` que já acontece).
**Critério de morte:** RTFx cai fora do IC95% → reverter e reavaliar o desenho.

> ✅ **E0 CONCLUÍDA — predição CONFIRMADA.** `[MEDIDO]` +0,368 ms absolutos = **+0,31%** do decode
> (< 2%). Colapso medido isolado da sessão ONNX, que tem variância de 2× nesta máquina e
> mascararia o efeito. 514 testes verdes, ruff limpo, saída do `batch_transcribe` **byte-idêntica**
> (md5 `5329b677…`). Evidência: [`wiki/medicoes/e0-instrumento-de-confianca.md`](../../wiki/medicoes/e0-instrumento-de-confianca.md).

---

## Phase E1 — O portão vale? (valida o instrumento)

**Objective:** confirmar que a separação medida não é artefato da amostra.

### T1.1 — Precisão e recall do portão com IC, e o corte de τ

#### Why this step
**O que faz:** reproduz a curva precisão/recall do portão com bootstrap sobre utterances.

**Por que agora:** os números do `## Context` vieram de **uma** passagem. A regra 3 da disciplina
de medição proíbe concluir de corrida única, e este projeto errou três vezes por isso. Se a
separação não sobreviver ao IC, todas as fases seguintes caem.

#### Evidence
`wiki/medicoes/composicao-do-erro-e-o-que-cada-remedio-alcanca.md` — τ=1,0: 10,3% sinalizado,
recall 49,8%, precisão 49,4%, base 10,3%.

#### Files to edit
```
jvscribe/probes/portao_correcao_probe.py  — novo: modo --curva
jvscribe/tests/test_portao_confianca.py   — novo: RED da lógica pura
```

#### TDD
```python
def test_portao_sinaliza_abaixo_do_limiar_e_nada_acima():
    palavras = [Palavra("a", 0.3), Palavra("b", 5.0)]
    assert [p.texto for p in sinalizadas(palavras, tau=1.0)] == ["a"]

def test_precisao_recusa_amostra_sem_erro():
    """Precisão sobre zero sinalizados é indefinida, não 100%."""
    assert precisao([], []) is None
```

#### Acceptance criteria
- [ ] Curva para τ ∈ {0,25 · 0,5 · 1 · 2 · 3} com IC95% bootstrap sobre utterances (n≥1000 reamostragens, seed fixa)
- [ ] `wiki/medicoes/e1-portao-de-confianca.md` com hipótese/evidência/conclusão separadas

**Predição pré-registrada:** a τ=1,0, precisão ≥ **35%** com o limite inferior do IC95% acima da
taxa base (~10%).
**Critério de morte:** limite inferior do IC95% da precisão **encosta na taxa base** → o portão é
ruído; o protocolo inteiro para e o aprendizado é registrado.

---

## Phase E2 — Correção pós-decode reduz o WER?

**Objective:** transformar o teto de ~8% em um ΔWER medido.

### T2.1 — Dois corretores, dois gatilhos, e o dano contabilizado

#### Why this step
**O que faz:** para cada palavra sinalizada, aplica o corretor que a classe admite —
`non_word_hyp` → dicionário; `rare_ref` → lista de domínio — e mede ΔWER pareado.

**Por que agora:** é a menor coisa que responde à pergunta 2 do `## Objective`. Corrige sobre a
**string** (D3), sem tocar o caminho de decode, então falha barato.

#### Evidence
Teto medido: 63% × 50% × 26% ≈ 8% dos erros. Precondição do corretor de dicionário é
`classificar(rw, hw, lex) == "non_word_hyp"`, já implementado em
`jvscribe/eval/analyze_error_composition.py`. Falso positivo do léxico: 0,49% das palavras corretas.

#### Files to edit
```
jvscribe/probes/portao_correcao_probe.py  — modo --corrigir
jvscribe/tests/test_portao_confianca.py   — RED do corretor
```

#### TDD
```python
def test_corrige_nao_palavra_para_o_vizinho_mais_proximo():
    assert corrigir("inncidente", LEXICO, orcamento=2) == "incidente"

def test_abstem_em_empate():
    """Dois candidatos equidistantes: não escolher é a resposta honesta."""
    assert corrigir("gata", {"gato", "gate"}, orcamento=1) is None

def test_nao_toca_palavra_que_ja_e_do_lexico():
    """`real_word_hyp` não é do escopo deste corretor — mexer nela é over-correction."""
    assert corrigir("segunda", LEXICO, orcamento=2) is None

def test_orcamento_cresce_com_o_tamanho_da_palavra():
    assert corrigir("pix", {"pinto"}, orcamento=None) is None      # 3 letras, d=1 máx
```

#### Acceptance criteria
- [ ] ΔWER com `common/metrics.paired_bootstrap` (IC95%, seed fixa)
- [ ] **consertou** e **quebrou** reportados separadamente — ΔWER nulo pode esconder 50 de cada
- [ ] varredura de τ × orçamento de distância, em round-robin
- [ ] `wiki/medicoes/e2-correcao-com-portao.md`

**Predição pré-registrada:** ΔWER entre **−0,3 e −1,3 p.p.** (partindo de 16,07%), com
`consertou / quebrou ≥ 3`.
**Critério de morte:** IC95% do ΔWER **cruza zero**, ou `quebrou ≥ consertou` → o caminho morre
aqui e E3 não acontece. Registrar como nulo (D5).

---

## Phase E3 — A acústica descartada era a causa? (condicional)

**Objective:** só existe se E2 falhar **e** a análise apontar que corrigir sobre a string joga
fora informação acústica que um beam local recuperaria.

### T3.1 — Re-decode local com beam nas palavras sinalizadas

#### Why this step
**O que faz:** nas palavras sinalizadas, re-decodifica o trecho com beam restrito ao léxico.

**Por que agora:** só depois de E2, e só se a causa da falha for a apontada. `[MEDIDO]`: o top-5
do próprio modelo satura em 21,7% de recuperação, o que **sugere** que a alternativa certa não
está nas vizinhanças — mas o teto foi medido variando no máximo 3 posições de baixa margem, e uma
busca mais larga pode achar mais.

#### Acceptance criteria
- [ ] Custo do beam local medido contra RNF-07 **antes** do ganho
- [ ] `wiki/medicoes/e3-beam-local.md`

**Predição pré-registrada:** recuperação ≥ 35% dos sinalizados (contra 21,7% do top-5 limitado).
**Critério de morte:** custo empurra o RTFx do pipeline abaixo de 6×, **ou** recuperação < 26%
(o valor do dicionário, que é mais barato).

---

## Phase E4 — Beam + LM global (independente)

**Objective:** medir a alavanca que ataca o maior terço, e que nenhuma fase anterior toca.

### T4.1 — Custo antes de ganho

#### Why this step
**O que faz:** mede primeiro quanto beam + LM custa; só depois mede quanto rende.

**Por que agora:** `real_word_hyp` é **36,6%** do erro — o maior bloco — e o portão só pega 32%
dele (D4). É a única fase cujo alvo é a classe majoritária. Ordem invertida de propósito: se não
couber no RNF-07, o ganho é irrelevante.

#### Acceptance criteria
- [ ] RTFx com beam ∈ {2, 4, 8} medido em round-robin, IC95% (`bench/runtime_bench.py`)
- [ ] ΔWER pareado, só para os beams que couberem
- [ ] `wiki/medicoes/e4-beam-lm.md`

**Predição pré-registrada:** 10–20% relativo `[LITERATURA]` (`CLAUDE.md`), ou seja WER 16,07% →
12,9–14,5%.
**Critério de morte:** nenhum beam ≥ 2 mantém RTFx ≥ 6× → registrar o custo e parar.

---

## Phase E5 — Refazer tudo em áudio do domínio (bloqueada)

**Objective:** repetir E1–E4 no áudio que decide, e comparar as duas distribuições.

**Bloqueio:** o áudio de call center é local por LGPD e não está nesta máquina. É o **mesmo**
bloqueio do WER de domínio (`CLAUDE.md`, seção "Ainda desconhecido").

**Por que está no plano mesmo bloqueada:** para que o limite de tudo acima fique explícito. Se a
distribuição dos três terços inverter no domínio real, a priorização de E2 contra E4 muda — e
ninguém deve descobrir isso depois de ter construído.

**Predição pré-registrada:** `rare_ref` **maior** que em FLEURS (jargão, produto, nome próprio) e
`real_word_hyp` **menor** (fala espontânea tem menos concordância complexa que texto lido).
**Critério de morte:** não se aplica — é a fase que valida ou refuta as outras.

---

## O loop

O protocolo não é uma fila; é um ciclo com três pontos de retorno.

```
   ┌──────────────────────────────────────────────────────┐
   │                                                      │
E0 → E1 ──(morre)──→ registra nulo, PARA                  │
   │                                                      │
   └→ E2 ──(morre por causa acústica)──→ E3 ──────────────┘
        │
        └──(morre por outra causa)──→ registra nulo
                                                          
E4 roda em paralelo, independente
E5 destrava e reexecuta E1–E4 sobre o domínio real
```

Cada volta do ciclo executa, sem exceção:

1. **Declarar** hipótese, predição e critério de morte — commitados **antes** de rodar.
2. **Medir** com IC; nunca corrida única (§ 3 regra 3); round-robin quando compara.
3. **Confrontar** o resultado com a predição. Divergência é o dado mais valioso, não um problema.
4. **Registrar** em `wiki/medicoes/`, com hipótese/evidência/conclusão em seções distintas.
5. **Revisar o plano**: predição errada muda as fases seguintes. Editar este documento faz parte
   do ciclo, e cada edição registra o número que a causou.

## Coverage Matrix

| # | Lacuna / requisito | Task(s) | Resolução |
|---|---|---|---|
| 1 | Margem por palavra não existe no código | T0.1 | `ctc.greedy_palavras` |
| 2 | Refatorar o colapso pode alterar todo WER publicado (R4) | T0.1 | RED de texto idêntico, antes de tudo |
| 3 | Portão medido em corrida única | T1.1 | curva com IC bootstrap |
| 4 | Não se sabe se corrigir reduz WER | T2.1 | ΔWER pareado + consertou/quebrou |
| 5 | Over-correction (R3) | T2.1 | abstenção em empate; precondição por classe |
| 6 | Corrigir sobre string pode descartar acústica | T3.1 | beam local, condicional |
| 7 | `real_word_hyp` (36,6%) não é tocado por E2/E3 | T4.1 | beam + LM global |
| 8 | Beam pode não caber no RNF-07 (R5) | T4.1 | custo medido antes do ganho |
| 9 | Tudo é FLEURS, não domínio (R1) | E5 | fase declarada e bloqueada, com predição |
| 10 | Resultado nulo tende a não ser registrado | D5, passo 4 do loop | documento por fase, com ou sem ganho |
| 11 | Conclusão de corrida única (R6) | T1.1, T2.1, T4.1 | IC em toda comparação |

**Coverage: 11/11 lacunas cobertas (100%)**

## Dependencies

### Existing (nenhuma nova)

| dependência | versão | uso | Regra 9 |
|---|---|---|---|
| `numpy` | ≥1.24 | argsort e margem | já declarada em `requirements-eval.txt` |
| `onnxruntime` | ≥1.16 | sessão do modelo | já declarada em `requirements-test.txt` |
| `pytest` | ≥8.0 | RED antes de GREEN | já declarada |

**Nenhuma dependência nova é introduzida por este protocolo.** O dicionário vem de
`/usr/share/dict/brazilian` (já usado por `analyze_error_composition.load_lexicon`), a distância
de edição de `common/metrics.word_edit_distance`, e o bootstrap de
`common/metrics.paired_bootstrap`. Se E4 exigir um LM, ele entra com `/deps-audit` próprio.

### Removed

Nenhuma.

## Global Definition of Done

- [ ] Toda fase executada tem documento em `wiki/medicoes/`, com hipótese/evidência/conclusão separadas
- [ ] Toda fase **abandonada** tem o número que a matou registrado
- [ ] Nenhum número publicado sem rótulo de proveniência (§ 1)
- [ ] Nenhuma comparação sem IC95%
- [ ] `python3 -m pytest jvscribe/tests -q` verde ao fim de cada fase
- [ ] `python3 -m ruff check jvscribe --select F,E9,B` limpo
- [ ] `CHANGELOG.md` atualizado por fase (Regra Inquebrável 6)
- [ ] Nada promovido a `common/` sem o número que autoriza (D1)
- [ ] Este documento revisado ao fim de cada fase, com o número que motivou cada mudança

## Followups

- Merges e splits (37% do erro) — fora de escopo, sem caminho conhecido em CPU
- Descoberta automática de contexto a partir da própria ligação (`arXiv:2509.19567`)
- Valor de produto do portão **sozinho**: marcar palavra incerta ao atendente, sem corrigir
- Dados sintéticos de termos raros no treino (`arXiv:2505.17410`) — precisa de GPU

## Related

- `wiki/medicoes/composicao-do-erro-e-o-que-cada-remedio-alcanca.md` — a medição que originou este plano
- `.claude/rules/asr-evidence-discipline.md` — o contrato de evidência que o loop implementa
- `.claude/rules/parsimony-ladder.md` — por que E2 vem antes de E3, e E3 antes de E4
- `docs/ARCHITECTURE.md` — fronteiras do kernel
