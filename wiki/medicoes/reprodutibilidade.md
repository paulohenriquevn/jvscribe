---
type: Medição
title: Reprodutibilidade do artefato publicado
description: Prova de que o modelo no HuggingFace transcreve e o checkpoint treina — medido a partir do download.
tags: [medicao, reprodutibilidade, huggingface]
timestamp: 2026-07-31T00:00:00Z
---

# Reprodutibilidade do artefato publicado — 2026-07-30

Prova de que `paulohenriquevn/jvscribe` (HuggingFace, privado) contém um modelo que **transcreve**
e um checkpoint que **treina**. Motivada por dois fatos deste projeto: o peso oficial já foi
escolhido errado por nome de arquivo, e o `.pt` do oficial chegou truncado da nuvem.

## Hipóteses

| # | Hipótese | Como falha |
|---|---|---|
| H1 | O artefato renomeado serve o MESMO modelo de antes | WER muda após a renomeação |
| H2 | O checkpoint publicado encaixa na arquitetura declarada | `load_state_dict` acusa chave faltante |
| H3 | O checkpoint codifica PT-BR, não só "carrega" | CTC loss próxima à de um modelo aleatório |
| H4 | O checkpoint aceita treino | loss não cai / gradiente não flui |

## Evidência

### H1 — a renomeação preserva o modelo `[MEDIDO]`

FLEURS pt_br `test[0:100]`, 2.552 palavras, greedy CTC, 4 threads, load average < 1.

| | antes (`m5_avg.int8.onnx`) | depois (`model.int8.onnx`) |
|---|---|---|
| WER | 15,99% | **15,99%** |
| CER | 7,30% | **7,30%** |
| sha256 | `1ac8bc5d…` | `1ac8bc5d…` |

RTFx medido em 40,0× (1.367,8 s de áudio em 34,2 s). O piso do RNF-07 é 6×.

### H2, H3, H4 — o checkpoint é finetunável `[MEDIDO]`

`jvscribe/bench/finetune_smoke.py` sobre `finetune/avg-124k-112k.pt`, 6 utterances reais do
FLEURS com transcrição humana, tokenizadas pelo `bpe.model` publicado. CPU, venv limpo.

```
lote: 6 utterances, 8250 frames, 428 tokens BPE
load_state_dict: faltando=0  sobrando=2
CTC loss  treinado=0.8618   aleatorio=21.9610
  passo 00  loss=0.8599  |grad|=16.450
  passo 09  loss=0.1252  |grad|=0.585
OK — loss 0.8599 -> 0.1252 (85.4% de queda em 10 passos)
```

- **H2 confirmada** — `faltando=0`. As 2 chaves "sobrando" são `phoneme_output.1.weight/bias`,
  a cabeça de fonema auxiliar, ausente do harness CTC-only por construção. Nada foi descartado
  em silêncio; verificado listando as chaves.
- **H3 confirmada** — 0,86 contra 21,96 no MESMO lote: **25× menor** que um modelo de mesma
  arquitetura com pesos aleatórios. Um `.pt` corrompido ou mal-carregado produziria loss da
  ordem do aleatório.
- **H4 confirmada** — queda monotônica com a norma do gradiente decrescendo de 16,4 para 0,59.

Isto **fecha a lacuna** deixada pela reconstrução do checkpoint (ver
`models/current/finetune/README.md § Incidente`): o `avg-124k-112k.pt` regenerado não era
verificado além de "abre e tem o tamanho certo". Agora está medido que ele treina.

### H1–H4 revalidadas a partir do HuggingFace `[MEDIDO]`

O teste acima ainda rodava sobre os arquivos locais. Repetido sobre um **download limpo** de
`paulohenriquevn/jvscribe` num diretório vazio — que é o que um terceiro receberia:

| verificação | resultado |
|---|---|
| `model_sha256` do card vs arquivo baixado | `1ac8bc5d…` = `1ac8bc5d…` **OK** |
| `vocab_fingerprint` do card vs `tokens.txt` baixado | `9fcb45e4…` = `9fcb45e4…` **OK** |
| WER / CER da inferência sobre o baixado | **15,99% / 7,30%** — idêntico ao declarado |
| RTFx | 43,4× (1.367,8 s em 31,5 s) |
| finetune sobre `finetune/avg-124k-112k.pt` baixado | `faltando=0`; loss 0,8599 → 0,1639 (−80,9% em 8 passos) |

Amostra da saída (`a007.wav`):

```
REF: o acidente ocorreu em grande altitude no terreno montanhoso e acredita-se que tenha
     sido causado por fogo inimigo
HYP: o acidente ocorreu em grande atitude no terreno montanhoso e acredita se que tenha
     sido causado por fogo inimigo
```

O erro residual se concentra em nomes próprios (`goethe` → `golte`, `fichte` → `fiste`) e em
diferenças de normalização que a régua conta como erro sem sê-lo (`20` vs `vinte`).

**Um achado durante a verificação:** `hf download --include` com seis padrões buscou apenas
cinco arquivos e **omitiu silenciosamente o `model.int8.onnx`** — sem erro, sem aviso. Baixado
sozinho, veio íntegro. Quem for reproduzir deve conferir o inventário do download contra o
repositório, não confiar no exit code.

## Conclusão

O artefato publicado transcreve com WER 15,99% e serve como ponto de partida de finetuning.
Ambas as afirmações foram medidas **a partir do download do HuggingFace**, não dos arquivos
locais — que é a única forma de a reprodutibilidade significar algo.

## Reprodução

```bash
# inferência
python3 jvscribe/batch/batch_transcribe.py --input-dir <wavs> --out-dir <saida> --threads 4

# finetuning (venv limpo; icefall clonado; stub de k2 — ver Limitações)
<venv>/bin/python jvscribe/bench/finetune_smoke.py \
  --checkpoint models/current/finetune/avg-124k-112k.pt \
  --bpe        models/current/finetune/bpe.model \
  --audio-dir <wavs> --refs <refs.tsv> \
  --icefall <clone do icefall> --k2stub <stub> --steps 10 --n-utts 6
```

## Limitações — o que este documento NÃO prova

- **Não é um treino.** São 10 passos de Adam em CPU sobre 6 utterances. Não valida o
  datamodule, a augmentação, o `ScaledAdam` nem o scheduler da receita real.
- **O `k2` é um stub.** A máquina tem `k2` compilado para PyTorch 1.13.1+cu117 contra torch
  2.13.0+cpu instalado. O `scaling.py` usa `k2` apenas para as ativações `swoosh_l`/`swoosh_r`;
  o stub as reimplementa com as **fórmulas exatas do próprio `scaling.py`** (ramo
  `torch.jit.is_scripting()`, o mesmo caminho do export ONNX) — não é aproximação, mas também
  não é o kernel compilado. Qualquer outro nome de `k2` levanta `NotImplementedError` de
  propósito, para o smoke não passar exercitando um caminho que precisaria do k2 real.
- **Não valida 8 kHz nem call center.** Continua `[DESCONHECIDO]`, como no model card.
- **A equivalência bit a bit do checkpoint regenerado com o original segue não verificada** —
  o que está provado é que ele é funcional, não que é idêntico ao que gerou o ONNX.
