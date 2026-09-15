# M10 — plano de treino na vast.ai

> Complementa [`m10-sota-ptbr.md`](m10-sota-ptbr.md) com a execução em GPU alugada.
> Escrito em 2026-09-14, depois de T1, T1b, T2 e do inventário de T3.

---

## O que já está decidido, e não se rediscute aqui

| decisão | valor | origem |
|---|---|---|
| Orçamento de latência | **chunk 1120 ms**, RNF-02 p99 ≤ 1,6 s | decisão do dono, `ROADMAP.md` |
| Teto de parâmetros | **230M** a 1120 ms (sustentado + softphone) | [`m10-rnf05`](../../wiki/medicoes/m10-rnf05-carga-concorrente.md) |
| Faixa-alvo do encoder | **180–220M** | ADR-001 + o teto acima |
| Corpus principal | **TAGARELA**, risco `NC/SA` aceito | [ADR-0006](../../wiki/decisoes/0006-tagarela-como-corpus-principal.md) |
| Corpus disponível | **~15.600 h de pt-BR** | [`m10-t3`](../../wiki/medicoes/m10-t3-quanto-corpus-pt-existe.md) |
| Régua de avaliação | `normalize_for_leaderboard` | [`m10-t2`](../../wiki/medicoes/m10-t2-regua-publica.md) |

---

## O problema que a vast.ai resolve, e que a máquina local não resolve

O corpus medido ocupa **52,0 MB por hora** de áudio (FLAC 16 kHz, medido em shard real):

| horas | disco | shards |
|---|---|---|
| 1.000 | 52 GB | 104 |
| 2.000 | 104 GB | 208 |
| 5.000 | 260 GB | 520 |
| 8.000 | 416 GB | 832 |
| 15.600 | 811 GB | 1.622 |

A máquina local tem **69 GB livres**. Ela não comporta nem o subset que o M5 já usou (224 shards
≈ 112 GB). Baixar, preparar e treinar localmente está fora de questão — e transferir 400 GB para a
instância a cada run é desperdício de banda e de tempo de GPU pago.

**A solução é um volume persistente na vast.ai**, onde o corpus é preparado uma vez e reusado por
todos os runs. O custo de storage passa a ser contínuo, mas o de preparação é pago uma só vez.

---

## Arquitetura de dados

```
volume vast.ai  (persistente entre instâncias)
├── raw/              shards TAGARELA baixados do HF (FLAC 16 kHz)
├── manifests/        Lhotse: cutset + supervisions, com licença e proveniência POR SHARD
├── labels/           pseudo-rótulos dos 3 professores + veredito do filtro de concordância
├── fbank/            features pré-computadas (o que o treino realmente lê)
├── lang_bpe_XXX/     tokenizer, bpe.model, tokens.txt — o artefato que M5 perdeu
└── exp/              checkpoints, tensorboard, logs
```

**Por que `fbank/` separado de `raw/`:** o treino lê features, não áudio. Com as features
materializadas, um run que caia reinicia sem refazer a extração — que é a parte lenta e serial.

**Por que `lang_bpe_XXX/` no volume:** o `bpe.model` do M4 se perdeu e custou retrabalho
(registrado nas armadilhas de M5). No volume ele sobrevive à morte da instância.

**Invariante:** nada em `raw/` ou `labels/` é apagado durante o treino. A poda proativa age apenas
em `exp/` — ver Fase 4.

---

## As quatro fases, com custo

### Fase 0 — provisionar e validar (custo: ~$2)

1. Criar volume. **Dimensionar pela fase 2**, não pela 1 — expandir volume depois costuma exigir
   recriar.
2. Instância barata (qualquer GPU) só para montar o volume e baixar um shard.
3. **Smoke antes de escalar:** baixar 2 shards, extrair fbank, rodar `bench/finetune_smoke.py`
   equivalente. Prova que a cadeia funciona antes de pagar por 800.

**Gate:** se o smoke não fechar, nada da fase 1 começa.

### Fase 1 — corpus (custo estimado: **$15–40**)

| etapa | recurso | estimativa |
|---|---|---|
| Baixar 520–832 shards do HF | rede da instância | 260–416 GB, horas de download |
| Pseudo-rotular com 3 professores | GPU | **~$1 por professor** a cada 8.000 h (Parakeet RTFx 3257) |
| Filtro de concordância + manifesto | CPU | barato |
| Extrair fbank | CPU da instância | ver armadilha `OMP_NUM_THREADS=1` |

**A rotulação é barata e o download é caro em tempo, não em dinheiro.** Rotular 15.600 h com três
professores custa da ordem de **$6 de GPU** — o gargalo é a banda, não o compute.

**Ordem obrigatória (ADR-003):** adaptar cada professor a PT-BR **antes** de rotular. Rotular com
professor genérico é o que produziu o overfitting de M5.

**Braço de controle (ADR-004):** manter também a rotulação sem filtro de concordância, para que a
decisão possa ser refutada em T5.

**Braço de licença limpa (ADR-0006, mitigação 2):** marcar no manifesto o subconjunto sem TAGARELA,
para que "retreinar sem ele" seja mudar um filtro, não refazer a fase.

### Fase 2 — bake-off (custo estimado: **$150–400**)

Duas trilhas, protocolo idêntico, subset controlado (~1.500 h, 3 sementes):

- **Trilha A** — Nemotron-3.5 0.6B com full-parameter fine-tune monolíngue PT-BR, preservando
  cache-aware e prompt conditioning. Receita publicada em `arXiv:2607.18912`.
- **Trilha B** — Zipformer2 causal dimensionado a ~200M, com CR-CTC.

**Gate:** vencedor com IC95% pareado que não cruze zero (`common/stats.py`), BSF ≤ 1,3, e RTFx
dentro do teto medido em 2 P-cores — **não extrapolado da GPU**.

### Fase 3 — treino de escala (custo estimado: **$600–1.500**)

A configuração vencedora sobre 5.000–8.000 h. A estimativa vem de escala relativa ao M5 (64M,
1.413 h, 10 épocas): **~4,7× em parâmetros e ~3,5–5,7× em dados ≈ 16–27× o custo daquele run**.

⚠️ **Esta é a estimativa mais frágil do plano.** O custo real do run de M5 não está registrado em
lugar nenhum — nem no `wiki/`, nem no `ROADMAP.md`. A faixa acima é derivada de proporção, não de
medição. **Medir o custo por época na Fase 2 e reprecificar a Fase 3 antes de lançá-la.**

### Fase 4 — avaliação e export (custo: ~$10)

Decode do test set completo, export ONNX decomposto em três grafos (encoder/decoder/joiner,
conforme `arXiv:2604.14493`), quantização comparada em ≥ 3 variantes.

**A avaliação de RTFx acontece na máquina local, não na instância.** O número que importa é o do
i7-1355U com dois canais, e GPU não o prediz.

---

## As armadilhas já pagas — cada uma custou um run

Estas não são recomendações; são cicatrizes registradas em
[`wiki/treino/armadilhas.md`](../../wiki/treino/armadilhas.md) e nas lições de M5.

| armadilha | o que fazer |
|---|---|
| **LR de cabeça fresca** | `0.0001` numa cabeça nova → platô em blank → WER 100%. Usar **~`0.03` na cabeça**, `0.002` no corpo |
| **fp16 colapsa sob augmentação** | `--use-fp16 0`. O `grad_scale` colapsa quando a augmentação introduz choque |
| **Full-finetune com codec-aug colapsa o greedy** | Medido 2×, greedy vai a ~98%. Congelar o encoder profundo e adaptar frontend + cabeças |
| **Disco cheio corrompe o último `.pt`** | Já aconteceu: 150 GB enchem com checkpoints, o último sai truncado **sem erro**. Poda proativa + verificar tamanho antes de confiar |
| **`OMP_NUM_THREADS=1` na extração de fbank** | Sem isso a extração serializa mal e demora múltiplos do necessário |
| **As quatro flags de arquitetura não estão no `.pt`** | `--num-encoder-layers`, `--feedforward-dim`, `--encoder-dim`, `--encoder-unmasked-dim`. Sem elas o checkpoint não carrega |
| **`bpe.model` se perde** | O do M4 se perdeu. Vive no volume, versionado junto do manifesto |
| **OOM em pre-scan** | Registrado em M5. `eager` + `workers=2` |

---

## Checkpointing e retomada

1. **Checkpoint por época**, não por batch, para limitar a superfície de corrupção.
2. **Poda proativa**: manter no máximo N checkpoints em `exp/`, apagando o mais antigo. Só `exp/`
   é podado — `raw/` e `labels/` nunca.
3. **Verificar tamanho após cada escrita.** Um modelo de 300M em fp32 ocupa ~1,2 GB; um `.pt`
   muito menor que isso está truncado.
4. **Escrita atômica** (tmp + rename), pela mesma razão.
5. **Checkpoint averaging** ao final — `[MEDIDO]` em M5 como valendo IC95% [−2,25; −0,43] pp.

O volume persistente muda a natureza da retomada: a instância pode morrer sem perder nada além do
progresso da época corrente.

---

## Riscos

**R1 — O custo da Fase 3 é estimado por proporção, não medido.** Ver o aviso na própria fase. É o
maior risco financeiro do plano e tem mitigação barata: medir na Fase 2.

**R2 — Storage persistente custa continuamente.** 400 GB parados são cobrados mesmo com a
instância desligada. Se o projeto pausar, o volume continua na fatura. **Decidir explicitamente o
que fazer com o volume entre fases.**

**R3 — Disponibilidade de GPU na vast.ai é volátil.** Instância barata pode ser interrompida. O
plano assume isso: checkpoint por época e volume persistente tornam a interrupção um atraso, não
uma perda.

**R4 — 520–832 shards de download é a etapa mais longa e a menos controlável.** Rate limit do HF,
queda de rede, shard corrompido. Baixar com verificação de integridade e retomada por shard.

**R5 — O contraste do braço limpo precisa caber no orçamento.** ADR-0006 exige medir o braço sem
TAGARELA. Se ele for tratado como "se sobrar tempo", nunca acontece — e a decisão de licença fica
sem falsificador.

---

## Pendências que bloqueiam a execução

1. **Chave de API da vast.ai.** O CLI está instalado (`~/.local/bin/vastai`) mas **não
   autenticado** — não há `~/.vast_api_key` e `vastai show user` devolve `403`. Sem isso nada da
   Fase 0 acontece.
2. **Orçamento aprovado por fase.** O `ROADMAP.md` prevê $5.000–8.000 para 3–5 runs; este plano
   estima **$800–1.950** no total, mas com a Fase 3 frágil (R1).
3. **Preço de storage da vast.ai** não verificado — depende do provedor da instância e não foi
   consultado (o CLI não autentica).
