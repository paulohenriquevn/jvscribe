# M2 — RTFx dos candidatos na CPU-alvo (evidência [MEDIDO])

**Data:** 2026-07-24
**Hardware:** máquina de referência do dev (12 cores, `OMP_NUM_THREADS=2`) — **NÃO** o i7-1355U do PRD nem o piso da frota BYOD (Q-01). Os valores absolutos não transferem para "a frota"; o que transfere é a **razão entre arquiteturas** medidas no mesmo silício.
**Áudio:** 12,0 s de fala PT-BR (FLEURS pt_br concatenado, 16 kHz) — mesma clip para todos, para comparação justa.
**Metodologia:** régua de M1 — 8 execuções, 2 de warmup descartadas, mediana. RTFx = duração_áudio ÷ tempo_de_parede (maior = mais rápido).
**Rótulo:** `[MEDIDO — arquitetura, não produto]` — modelos de referência (inglês) medindo a **velocidade da arquitetura+tamanho**; RTFx é agnóstico a idioma (o encoder faz o mesmo compute), WER **não** é e fica `[LITERATURA]`/M4 (ADR D4 do plano).

## Resultado

| Arquitetura | Família | Params | RTFx `[MEDIDO]` | Mediana | Nota de método |
|---|---|---|---|---|---|
| Moonshine tiny | AED (encoder-decoder) | ~27M | **7,09×** | 1692 ms | gerou 193 tokens — custo AED ∝ tokens |
| Moonshine base | AED | ~62M | **11,49×** | 1044 ms | gerou 49 tokens (transcrição mais curta → menos passos) — mostra a **content-dependência do AED** |
| Zipformer (transducer streaming) | transducer/CTC-family | ~20M | **20,45×** | 587 ms | custo fixo pelos frames, não pelos tokens |

Comandos:
- Moonshine: `moonshine_onnx.MoonshineOnnxModel(model_name).generate(audio)` (`useful-moonshine-onnx==20251121`), 8 runs.
- Zipformer: `sherpa_onnx.OnlineRecognizer.from_transducer(...)` sobre `sherpa-onnx-streaming-zipformer-en-20M-2023-02-17` (encoder/decoder/joiner fp32, num_threads=2), 8 runs.

## Leitura honesta (o que a evidência sustenta)

1. **O Zipformer 20M é ~3× mais rápido que o Moonshine tiny 27M na mesma CPU** — em faixa de tamanho comparável (ADR D4). É `[MEDIDO]`, não extrapolado.
2. **A razão é arquitetural, não de implementação:** AED (Moonshine) tem decoder **autoregressivo** — custo cresce com o nº de tokens de saída (tiny: 193 tokens/1692ms; base: 49 tokens/1044ms — a própria variância mostra a dependência do conteúdo). Transducer/CTC (Zipformer) faz **um passe** — custo fixo pelos frames de áudio, independente do texto. Para áudio longo de call center, a diferença **amplia** a favor do CTC/transducer.
3. **Isto corrige o viés do PRD** que favorecia Moonshine "por ser o único com benchmark CPU publicado" (`_catalog.md`). O benchmark publicado (69ms/34M) é `[LITERATURA]` de outra CPU, em clips curtos — não capturava a content-dependência nem transferia para o i7-1355U (falácia §3 #1/#4). Medindo na mesma CPU, o transducer ganha o critério 1.

## Limites (§ 4)

- **Não é o i7-1355U** — o piso da frota é `[DESCONHECIDO]` (Q-01). A razão entre arquiteturas é o achado transferível, não os 20,45×.
- **Não é sob os RNF-04/05** (soak ≥10 min + carga) — é medição de arquitetura em janela curta; o soak sob carga do finalista é experimento de M4.
- **Paraformer/NAR e FastConformer não foram medidos** neste ambiente (tempo/download) — `[LITERATURA]`: FunASR reporta 16 streams em 4 vCPU (documentação de projeto, não paper); FastConformer é da mesma família transducer/CTC do Zipformer, RTFx esperado próximo (a medir em M4). **LC-BiMamba não roda em ONNX** (`onnxruntime#27796`) — `[DESCONHECIDO]` por impossibilidade, o que já o exclui pelo critério 6.
- **Modelos de referência são inglês** — mede arquitetura, não o modelo PT-BR (que só existe em M3+). WER é `[LITERATURA]`/M4.
