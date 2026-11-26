---
type: Medição
title: M2 — RTFx dos candidatos
description: Transducer/CTC ~2× mais rápido que AED em CPU, com separação estatística limpa.
tags: [medicao, m1, m2, rtfx]
timestamp: 2026-07-31T00:00:00Z
---

# M2 — RTFx dos candidatos na CPU-alvo (evidência [MEDIDO])

**Data:** 2026-07-24 (medição inicial, só mediana) · **2026-07-25** (re-medição com dispersão — este documento, review F1)
**Hardware:** máquina de referência do dev (12 cores, `OMP_NUM_THREADS=2`) — **NÃO** o i7-1355U de referência nem o piso da frota BYOD (Q-01). Os valores absolutos não transferem para "a frota"; o que transfere é a **razão entre arquiteturas** medidas no mesmo silício.
**Áudio:** 12,00 s de fala PT-BR (FLEURS pt_br `test`, primeiros exemplos concatenados, 16 kHz) — mesma clip para todos. Prova de que é a **mesma clip** da medição inicial: o Moonshine gerou contagem de tokens **idêntica** (tiny 193, base 49) nas duas execuções, isolando o ambiente como única variável entre elas.
**Metodologia:** régua de M1 — **10 execuções + 3 de warmup descartadas**, reportando **média ± desvio, min–max e mediana**. A medição inicial só reportou mediana; a disciplina de evidência exige média ± desvio para `[MEDIDO]` — corrigido aqui (review F1). RTFx = duração_áudio ÷ tempo_de_parede (maior = mais rápido).
**Rótulo:** `[MEDIDO — arquitetura, não produto]` — modelos de referência (inglês) medindo a **velocidade da arquitetura+tamanho**; RTFx é agnóstico a idioma (o encoder faz o mesmo compute), WER **não** é e fica `[LITERATURA]`/M4 (ADR D4 do plano).

## Resultado

| Arquitetura | Família | Params | RTFx `[MEDIDO]` (média ± desvio) | min–max | Mediana | Nota de método |
|---|---|---|---|---|---|---|
| Moonshine tiny | AED (encoder-decoder) | ~27M | **7,93 ± 0,72×** | 6,52–8,58× | 8,25× | 193 tokens — custo AED ∝ tokens |
| Moonshine base | AED | ~62M | **12,10 ± 3,15×** | 7,10–15,19× | 13,67× | 49 tokens (transcrição mais curta → menos passos) — **content-dependência do AED** |
| Zipformer (transducer streaming) | transducer/CTC-family | ~20M | **15,90 ± 2,06×** | 11,72–18,04× | 16,76× | custo fixo pelos frames, não pelos tokens |

n=10 por arquitetura; `OMP_NUM_THREADS=2`; CPU sob carga variável de dev (ver Limites § 4).

Comandos:
- Moonshine: `moonshine_onnx.MoonshineOnnxModel(model_name).generate(audio)` (`useful-moonshine-onnx==20251121`), 10 runs (+3 warmup).
- Zipformer: `sherpa_onnx.OnlineRecognizer.from_transducer(...)` sobre `sherpa-onnx-streaming-zipformer-en-20M-2023-02-17` (encoder/decoder/joiner fp32, num_threads=2), 10 runs (+3 warmup).
- Script reprodutível: `measure_rtfx_dispersion.py` (clip `fleurs_ptbr_12s.wav`).

## Leitura honesta (o que a evidência sustenta)

1. **O Zipformer 20M é ~2× mais rápido que o Moonshine tiny 27M na mesma CPU** — média 15,90× vs 7,93× (razão 2,01×), mediana 16,76× vs 8,25× (razão 2,03×), em faixa de tamanho comparável (ADR D4). A separação é **estatisticamente limpa**: o pior Zipformer (11,72×) ainda supera o melhor tiny (8,58×) — os intervalos min–max **não se sobrepõem**. É `[MEDIDO]`, não extrapolado.
   - **Transparência (review F1):** a medição inicial (só mediana, sem dispersão) reportou Zipformer 20,45× → razão ~2,9×. A re-medição com N=10 e a **mesma clip** (tokens idênticos 193/49) deu ~2,0×. A discrepância é **carga de CPU**: o Zipformer variou ~20% entre execuções (±2,06) com conteúdo constante — exatamente a sensibilidade a ambiente que as falácias § 3 #4/#5 preveem e que motiva o soak sob RNF-04/05 em M4. A **direção** (transducer > AED) sobrevive a ambas as execuções; a **magnitude honesta hoje é ~2×**, a confirmar sob carga controlada. Este é o valor exato de reportar dispersão: o "~3×" de antes era um artefato de amostragem num momento quieto.
2. **A razão é arquitetural, não de implementação:** AED (Moonshine) tem decoder **autoregressivo** — custo cresce com o nº de tokens de saída (tiny: 193 tokens/1692ms; base: 49 tokens/1044ms — a própria variância mostra a dependência do conteúdo). Transducer/CTC (Zipformer) faz **um passe** — custo fixo pelos frames de áudio, independente do texto.
   - `[ESTIMATIVA]` **Projeção para áudio longo:** para uma chamada de call center (minutos, não 12 s), a diferença *tende a ampliar* a favor do CTC/transducer. Mecanismo: o custo do AED cresce com o nº de tokens (∝ duração da fala) e a self-attention do decoder é O(n²) sobre os tokens já gerados, enquanto o transducer permanece ∝ frames. **A magnitude é a-medir em M4** — a clip de 12 s sustenta apenas o gap medido (~2,0×), não sua ampliação; se ambos escalassem linearmente com a duração, a *razão* ficaria constante. Só a direção é robusta; o "amplia" é hipótese com mecanismo, não medição.
3. **Isto corrige o viés do documento de requisitos original** que favorecia Moonshine "por ser o único com benchmark CPU publicado" (`_catalog.md`). O benchmark publicado (69ms/34M) é `[LITERATURA]` de outra CPU, em clips curtos — não capturava a content-dependência nem transferia para o i7-1355U (falácia §3 #1/#4). Medindo na mesma CPU, o transducer ganha o critério 1.

## Limites (§ 4)

- **Não é o i7-1355U** — o piso da frota é `[DESCONHECIDO]` (Q-01). A razão entre arquiteturas (~2×) é o achado transferível, não os valores absolutos (15,90×/7,93×).
- **Sensível a carga (medido, não hipótese):** o próprio RTFx do Zipformer variou 20,45× → 15,90× entre a medição inicial e a re-medição, com a clip idêntica (tokens 193/49 constantes). O desvio de ±2,06 (13% do valor) é a assinatura dessa contenção. Nenhuma decisão deve pendurar-se num único número; a régua de M1 mede sob soak em M4.
- **Não é sob os RNF-04/05** (soak ≥10 min + carga) — é medição de arquitetura em janela curta; o soak sob carga do finalista é experimento de M4.
- **Paraformer/NAR não foi medido** neste ambiente (tempo/download) — `[LITERATURA]`: FunASR reporta 16 streams em 4 vCPU (documentação de projeto, não paper).
- **FastConformer não foi medido** — o RTFx "esperado próximo do Zipformer" é `[ESTIMATIVA]`, **não** `[LITERATURA]`: é derivado por analogia de família (ambos decodificam por CTC/transducer, custo ∝ frames), não reportado por nenhuma fonte na mesma CPU. **Premissa e ressalva:** os *decoders* são da mesma família, mas os *encoders* diferem — Zipformer é U-Net/downsampling do k2/icefall; FastConformer é Conformer + subsampling 8× do NeMo — então "≈" carrega a suposição, não medida, de que a topologia de encoder não muda a ordem de grandeza. `parakeet-rs` expõe `encoder.onnx + decoder_joint.onnx` rodável no sherpa (blueprint), logo **FastConformer é mensurável agora na mesma régua** — foi diferido por tempo, não por impossibilidade. Medir antes de tratá-lo como par do Zipformer é item explícito do piloto de M4.
- **LC-BiMamba não roda em ONNX** (`onnxruntime#27796`) — `[DESCONHECIDO]` por impossibilidade, o que já o exclui pelo critério 6.
- **Modelos de referência são inglês** — mede arquitetura, não o modelo PT-BR (que só existe em M3+). WER é `[LITERATURA]`/M4.
- **Viés de idioma no AED (caveat de justeza):** o Moonshine (inglês) sobre áudio pt_br pode alucinar/repetir tokens, o que **infla** a contagem (tiny=193 tokens em 12 s é alto) e, como o custo do AED é ∝ tokens, **deprime** artificialmente seu RTFx. Parte da penalidade de 7,09× pode ser artefato de idioma, não da arquitetura. Consequência: o número robusto é a **direção** (transducer > AED), não a **magnitude** exata do gap. A direção sobrevive ao viés (um AED nativo pt_br geraria menos tokens, mas continuaria autoregressivo ∝ tokens vs o passe único do transducer); a decisão não muda, mas a honestidade metodológica exige registrar que o gap medido é um **teto** da vantagem real do transducer, não seu valor final.
