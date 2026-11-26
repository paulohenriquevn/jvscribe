---
type: Medição
title: T3 — a cadeia fecha até o fbank, e o codec de storage vale 4,3×
description: >-
  CutSet → fbank → load_features validado com o código do próprio repo. Fbank a 1.638× tempo real.
  Features em lilcom custam 27 MB/h — metade do áudio; em numpy, 115 MB/h.
tags: [medicao, m10, t3, lhotse, fbank, storage, lilcom, pipeline]
timestamp: 2026-09-20T15:00:00Z
---

# T3 — fbank, CutSet e o custo de storage `[MEDIDO]`

Data: 2026-09-20 · i7-1355U · `lhotse` 1.33.0, `kaldi_native_fbank` 1.22.3 · 60 wavs do FLEURS pt
(12,9 min), usando `corpus/build_manifest.build_cutset` do próprio repositório.

## Por que este teste

O smoke anterior provou ler, decodificar, comparar e emitir manifesto, mas **parou antes do que o
treino realmente consome**. Se a cadeia do repo estivesse quebrada, era melhor descobrir antes de
alugar GPU.

## Resultado 1 — a cadeia fecha

```
build_cutset()           60 cuts, 12,9 min
compute_and_store_features()  fbank 80-dim, frame_shift 0,01 s
CutSet.to_file()         cuts_smoke.jsonl.gz, 9 KB
CutSet.from_file()       relido
load_features()          (1188, 80) float32
```

**Fbank a 1.638× tempo real** com `num_jobs=1`. Extrair 8.000 h levaria **~4,9 h de CPU** num
único job — e o `prep_icefall.py` já aceita paralelismo.

O código do repositório funcionou sem modificação. `build_cutset` monta `RecordingSet` +
`SupervisionSet` e faz fail-fast quando falta rótulo, como documentado.

## Resultado 2 — o codec de storage vale 4,3× em disco

Escrevendo o mesmo array de features com os dois writers do lhotse:

| writer | tamanho | por hora de áudio |
|---|---|---|
| `LilcomChunkyWriter` | 5,8 MB | **27 MB/h** |
| `NumpyFilesWriter` | 24,8 MB | **115 MB/h** |

E comparado ao áudio de origem:

| o que guardar | por hora | 8.000 h |
|---|---|---|
| features em **lilcom** | **27 MB** | **216 GB** |
| áudio FLAC 16 kHz (medido no TAGARELA) | 52 MB | 416 GB |
| features em numpy | 115 MB | 920 GB |

**Com lilcom, guardar features custa metade do que guardar o áudio.** Isso inverte a intuição do
[plano de treino](../../docs/plans/m10-treino-vastai.md), que tratava `fbank/` como custo
adicional sobre `raw/`: materializar features e **descartar o áudio** é a configuração mais barata
de volume, não a mais cara.

⚠️ **Lilcom é compressão com perda.** É o padrão de facto do icefall/k2 e do próprio lhotse, mas o
efeito no WER final não foi medido por este projeto.

## O gotcha que custou duas execuções

`CutSet.compute_and_store_features(..., storage_type=LilcomChunkyWriter)` aceitou o parâmetro e
**gravou em `numpy_files` mesmo assim** — verificado lendo `storage_type` do `cuts.jsonl.gz`. O
lhotse não reclamou.

Consequência prática: **conferir `storage_type` no manifesto gerado** em vez de confiar no
parâmetro. A diferença entre acertar e errar isto, em 8.000 h, é de **700 GB**.

## Um defeito de ambiente, corrigido

A primeira execução quebrou em
`AttributeError: module 'lib' has no attribute 'GEN_EMAIL'`, vindo de
`lhotse → smart_open → botocore → urllib3.contrib.pyopenssl → OpenSSL`. Causa: **pyOpenSSL 25.1.0
contra cryptography 49.0.0**, incompatíveis.

`pip install -U pyopenssl` (25.1.0 → 26.4.0) resolveu. Fica registrado porque qualquer uso de
lhotse neste ambiente esbarraria nisso, e o erro não aponta para a causa.

## Limitações

1. **60 wavs de FLEURS**, não TAGARELA — os shards foram removidos para liberar disco. A cadeia é
   a mesma; o conteúdo não.
2. **A augmentação telefônica não foi exercitada.** `build_manifest` traz `load_telephone_audio`
   para aplicação on-the-fly, e ela não entrou neste teste.
3. **O efeito do lilcom no WER não foi medido.** A escolha é herdada do icefall, não validada aqui.
4. **`num_jobs=1`.** O tempo de extração em paralelo, que é o que vale no volume da vast.ai, não
   foi medido.
5. **Nenhum treino consumiu estes cuts.** O formato é o que o icefall espera, mas isso está
   verificado por inspeção, não por execução.
