---
type: Peer de referência
title: sherpa-onnx — runtime CPU de referência
description: O que aprendemos lendo o código, com as citações fixadas no commit 116a44e7.
resource: https://github.com/k2-fsa/sherpa-onnx/tree/116a44e72c5b
tags: [sherpa-onnx, runtime, onnx, streaming, fonte-repo]
timestamp: 2026-07-31T00:00:00Z
---

# sherpa-onnx

| | |
|---|---|
| repositório | `k2-fsa/sherpa-onnx` |
| commit fixado | `116a44e72c5b` (2026-07-30) |
| licença | Apache-2.0 |
| papel | Runtime CPU de referência para ASR |

## O que ele fez que nós não fazíamos

### 1. Configura `inter_op` e mantém a arena de memória ligada

[`sherpa-onnx/csrc/session.cc:149,156`](https://github.com/k2-fsa/sherpa-onnx/blob/116a44e72c5b/sherpa-onnx/csrc/session.cc#L149)
`[FONTE-REPO]`

```cpp
sess_opts.SetIntraOpNumThreads(num_threads);
sess_opts.SetInterOpNumThreads(num_threads);
```

E só desliga a arena quando explicitamente pedido — o default dele é **ligada**. A nossa estava
desligada sem justificativa, e sozinha custava −6,7% [IC95% −18,3; −3,9] ms. Adotado.

### 2. Extração de features **incremental**

[`sherpa-onnx/csrc/features.h:106,117,131`](https://github.com/k2-fsa/sherpa-onnx/blob/116a44e72c5b/sherpa-onnx/csrc/features.h#L106)
`[FONTE-REPO]` — `AcceptWaveform` / `NumFramesReady` / `GetFrames(frame_index, n)`.

Features são computadas **uma vez** e recuperadas por índice de frame. Nós reextraíamos a
janela inteira a cada hop — 21,6% do custo de decode em retrabalho. Adotado como
[`FeatureCache`](../motor/fbank-incremental.md).

### 3. Encoder streaming que carrega estado

[`sherpa-onnx/csrc/online-zipformer2-transducer-model.h:32`](https://github.com/k2-fsa/sherpa-onnx/blob/116a44e72c5b/sherpa-onnx/csrc/online-zipformer2-transducer-model.h#L32)
`[FONTE-REPO]` — `GetEncoderInitStates()`, com os estados passando por toda a cadeia.

**Isto nós não temos**, e é a diferença que mais custa: o nosso grafo não tem tensor de estado,
então cada hop reprocessa a janela inteira. Ver
[../modelo/nao-e-streaming.md](../modelo/nao-e-streaming.md).

Adotá-lo exige **treinar com `--causal 1`** e reexportar — não é mudança de runtime.
