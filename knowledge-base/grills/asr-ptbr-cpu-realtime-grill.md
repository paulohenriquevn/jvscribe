---
slug: asr-ptbr-cpu-realtime
date: 2026-07-24
questions_asked: 15
decisions_resolved: 15
verdict: NEEDS_SPLIT
---

# Grill: ASR PT-BR real-time em CPU (macaw-transcribe / Macaw Voice)

## Veredito: `NEEDS_SPLIT`

As 15 perguntas convergiram, mas **o escopo real só foi revelado na Q13**: não é uma
ferramenta pessoal de transcrição de reunião — é **deployment em milhares de
atendentes de call center, em notebooks pessoais (BYOD), com transcrições enviadas
para um data lake e classificação de intenção downstream**.

Isso invalida a premissa sob a qual as decisões Q3, Q4, Q12 e Q13 foram tomadas, e
revela pelo menos quatro sub-projetos distintos. Ver § Split recomendado.

---

## Decision tree resolvida

| # | Decisão | Resolução | Status |
|---|---|---|---|
| 1 | Superfície de deploy | **Dispositivo do usuário** (não servidor) | ✅ firme |
| 2 | Classe de dispositivo | **Desktop/notebook** (celular fora do v1) | ✅ firme |
| 3 | Hardware-alvo | Medido: i7-1355U | ⚠️ **revisar** — BYOD heterogêneo |
| 4 | Domínio de áudio | Reunião multi-pessoa → **call center** | ⚠️ **revisado na Q13** |
| 5 | Captura | **Mic + system loopback, 2 streams**; 1 ASR sobre o mix; VAD por stream como prior de diarização | ✅ firme |
| 6 | Idioma | **PT-BR only**; code-switching lexical PT/EN de 1ª classe; **hotwords** requeridas | ✅ firme |
| 7 | Falantes | **Máx. 3, geralmente 2** | ✅ firme |
| 8 | Real-time | **5 critérios formais** (ver abaixo) | ✅ firme |
| 9 | Stack de inferência | **Rust**; `ort` primeiro, kernels custom guiados por profiler | ✅ firme |
| 10 | Obtenção do modelo | **Treinar do zero**, monolíngue PT-BR | ✅ firme |
| 11 | Nemotron 3.5 | **Fora do produto**; mantido como teacher / baseline / voz de concordância | ✅ firme |
| 12 | Coleta de dados | Opt-in com correções priorizadas | ⚠️ **revisar** — transcrições vão para lake |
| 13 | Definição de v1 | Dogfood pessoal | ⚠️ **revisar** — piloto com atendentes |
| 14 | Corpus | **TAGARELA permanece principal**; gravações internas em fase posterior | ✅ firme |
| 15 | Banda do áudio | **8 kHz narrowband, G.711 a-law** (padrão call center BR) | ✅ firme |

### Critério de aceite de "real-time verdadeiro" (Q8 — LOCKED)

| # | Critério | Valor |
|---|---|---|
| 1 | RTFx sustentado do pipeline completo | **≥ 3×** |
| 2 | Latência p99 (fim da fala → texto) | **≤ 500 ms** |
| 3 | Backlog de chunks | **= 0 em 99,9% das amostras** |
| 4 | Estabilidade térmica (RTFx min. 30 ÷ min. 1) | **≥ 80%** |
| 5 | Medido com carga concorrente real na máquina | obrigatório |

### Arquitetura resultante

```
Zipformer streaming + CTC, monolíngue PT-BR, ~80M params, nativo 8 kHz
  ├─ treinado do zero (não pruning do Nemotron — poda preserva diluição multilíngue)
  ├─ um encoder serve streaming E batch (arXiv:2506.14434)
  ├─ CTC → timestamps por palavra de graça
  ├─ BPE PT-BR dedicado (~500-1000 tokens, cobrindo termos técnicos em inglês)
  └─ runtime Rust: decoder CTC + FLToP + word spotter de hotwords
```

---

## Q&A log

### Q1 — Superfície de deploy prioritária
**Recomendado**: servidor primeiro (Nemotron pronto resolve em semanas), edge na fase 2.
**Decisão do usuário**: **dispositivo do usuário**, foco total em transcrição real-time.
**Consequência**: destilação/treino próprio obrigatório; Nemotron rebaixado a teacher; projeto de meses, não semanas.

### Q2 — Classe de dispositivo
**Recomendado**: desktop primeiro; celular depois (celular exigiria ~30-50M + NPU).
**Decisão**: **desktop primeiro**. Mantém o alvo de ~80-120M plausível.

### Q3 — Piso de hardware e orçamento de cores
**Método**: medido diretamente, não perguntado.
**Achado**: i7-1355U — 2 P-cores @5,0 GHz + 8 E-cores @3,7 GHz; **AVX-VNNI presente**; sem AVX-512; 15 GB RAM (3,8 GB livres); load 4,4 em repouso.
**Decisão**: rodar no notebook do usuário. Orçamento realista: 2 P-cores.
**Insights**: (a) int8+VNNI provavelmente supera int4 nesta CPU — int4 não tem instrução nativa e paga unpack; (b) thread affinity nos P-cores é obrigatório, senão a latência p99 vira loteria; (c) benchmark precisa ser sustentado 10+ min — chip U de 15 W não segura turbo.
**⚠️ A REVISAR**: com BYOD de milhares de atendentes, o piso real é muito menor que este notebook.

### Q4 — Domínio de áudio
**Recomendado**: reunião/call multi-pessoa.
**Decisão**: aceita — **posteriormente refinada para call center** (Q13).

### Q5 — Captura de áudio
**Recomendado**: mic + system loopback em dois streams separados.
**Decisão**: aceita.
**Racional**: dois streams dão metade da diarização de graça — o mic é o falante local por construção. Custo: implementação por SO (PipeWire/WASAPI/ScreenCaptureKit).
**Sub-decisão**: **um único ASR sobre o mix** (dois modelos não cabem em 2 P-cores); VAD independente por stream serve de prior.

### Q6 — Idioma e code-switching
**Recomendado**: PT-BR only; code-switching lexical PT/EN como requisito de 1ª classe; reuniões 100% em inglês fora de escopo.
**Decisão**: aceita, **com requisito adicional de hotwords**.
**Achado crítico**: no sherpa-onnx, hotwords só funcionam em modelos **transducer** com `modified_beam_search` — conflita com a escolha de CTC. Solução: portar CTC-based Word Spotter (Interspeech 2024, NeMo) ou WCTC-Biasing (`arXiv:2506.01263`), ambos sem retreino.
**Armadilha registrada**: FLToP CTC poda tokens de baixa probabilidade; hotwords raras **são** de baixa probabilidade. **Boost antes da poda**, ou isentar tokens do grafo de contexto — senão quebra silenciosamente em produção.

### Q7 — Número máximo de falantes
**Recomendado**: 4 (3 remotos + local), encaixando no Sortformer 4spk.
**Decisão**: **máximo 3, geralmente 2**.
**Consequência (grande)**: no caso 1:1 — o dominante — **diarização não precisa existir**: mic = atendente, sistema = cliente. Roteamento de stream, custo zero, acurácia 100%. Sortformer entra só no caso de 3. Libera orçamento de CPU inteiro para o ASR e tira do caminho crítico o componente mais arriscado.

### Q8 — Latência e definição de real-time
**Recomendado inicialmente**: chunk de 560 ms.
**Decisão**: **"real-time verdadeiro"** — critério formal de 5 pontos (tabela acima).
**Cálculo apresentado**: ancorado no benchmark da Microsoft (Nemotron 600M int4, RTFx 6× em EPYC 32 cores @2,45 GHz) → custo de ~13,1 GHz-core Zen2 por 1× real-time. Orçamento do usuário (2 P-cores @~3,0 GHz sustentado ≈ 7,8 Zen2-equiv) → **Nemotron 600M ≈ 0,6× RTFx (reprova)**; **80M + FLToP + layer-skip ≈ 9,3× (aprova com folga)**.
**Consequência**: com folga, chunk pode cair para 320 ms. O chunk vira resultado da medição, não decisão antecipada.

### Q9 — Stack de inferência
**Recomendado**: `ort` primeiro; kernels custom onde o profiler apontar; runtime próprio como fase 3.
**Decisão**: aceita — motor de inferência próprio em **Rust** é o destino.
**Ordem por dependência**: decoder CTC + FLToP + word spotter e pipeline de áudio **não dependem do modelo** e começam já; encoder é otimizado depois de existir. Estudar [`parakeet-rs`](https://github.com/altunenes/parakeet-rs) antes de escrever.
**Nota**: o BPE em runtime é uma lookup table — não há o que otimizar ali. O ganho de Rust está no decoder e no pipeline.

### Q10 — Como obter o modelo de ~80M
**Recomendado inicialmente**: structured pruning + distillation do Nemotron (FastConformer-CTC).
**Questionado pelo usuário** ("o Nemotron é o caminho?") → **recomendação revisada**:
- O WER 5,48 do Nemotron em pt-BR é medido em **FLEURS** — fala lida de estúdio. Não diz nada sobre call center espontâneo.
- Existe teacher PT-BR dedicado com número melhor em benchmark comparável: [`freds0/distil-whisper-large-v3-ptbr`](https://huggingface.co/freds0/distil-whisper-large-v3-ptbr) — **8,22% WER em Common Voice 16** (vs 12,03% do FastConformer PT-BR dedicado). `freds0` é o **mesmo autor do TAGARELA**.
- Pruning de 7,5× (600M→80M) é agressivo demais; a literatura opera em 2-4×.

### Q11 — Nemotron: usar ou não
**Decisão do usuário**: **criar modelo próprio; Nemotron não entra no produto.**
**Validação técnica**: a decisão é defensável e não só estratégica — **podar um multilíngue de 40 locales para 80M provavelmente rende pior que treinar 80M monolíngue do zero**, porque a poda preserva a diluição. Treinar do zero coloca 100% da capacidade em PT-BR.
**Viabilidade calculada**: 8.972 h está na faixa do GigaSpeech/WenetSpeech — escala em que se treinam modelos de referência do zero. ~900 GPU-horas/run ≈ $1.500-2.000; 3-5 runs ≈ **$5.000-8.000 de orçamento total de GPU**.
**Consequência**: **Zipformer volta a ser a escolha principal** — o único argumento pró-FastConformer era herdar inicialização do Nemotron.
**Escopo do "não usar"**: fora do produto; **mantido** como teacher para pseudo-labels, baseline de medição e segunda voz no filtro de concordância (técnica do Granary: dados processados = mesma performance com 50% menos dados).

### Q12 — Coleta de dados
**Recomendado**: opt-in explícito, desligado por padrão, priorizando **correções** em vez de áudio bruto — o par `(áudio, correção humana)` é o ativo mais escasso do projeto e vem de graça do usuário irritado.
**Decisão**: aceita.
**⚠️ A REVISAR**: na Q13 revelou-se que as transcrições vão para um data lake corporativo — o regime de consentimento é o aviso de gravação da chamada, não opt-in do atendente.

### Q13 — Definição de v1
**Recomendado**: dogfood pessoal — o usuário transcrevendo as próprias reuniões no próprio notebook, com os 5 critérios medidos.
**Resposta do usuário revelou o escopo real**: **milhares de atendentes**, notebooks **pessoais (BYOD)**, transcrições enviadas para um **data lake**, **classificação de intenção** downstream, **monitoramento de WER** em produção.
**Consequências mapeadas**:
- **Motivo do CPU é economia de escala**: ~132.000 h/mês para 1.000 atendentes ≈ **$47.500/mês** em API. Compute marginal local = zero. O treino se paga na primeira semana.
- **BYOD**: o piso real é um i3/Celeron de 2018 sem AVX-VNNI — não o i7-1355U. Provável necessidade de **tiering** de modelo.
- **LGPD entra no caminho crítico**: CPF, dados financeiros, possivelmente sensíveis. Mascaramento de PII antes do envio ao lake.
- **ITN vira crítico**: CPF, protocolo, valores, datas. WER puro deixa de ser a métrica certa — errar "cancelamento" custa mais que errar "então".
- **Ruído de call center**: crosstalk de atendentes vizinhos.

### Q14 — Gravações internas substituem o TAGARELA?
**Recomendado**: se existirem, substituem — resolvem domain gap, licença e test set de uma vez (dado próprio = licença própria; o passivo NC-SA sai do caminho crítico).
**Decisão**: **por enquanto não** — TAGARELA permanece o corpus principal.
**Consequência**: **augmentação de domínio vira caminho crítico**, não mitigação opcional.

### Q15 — Banda do áudio
**Recomendado**: assumir 8 kHz como piso, treinar robusto a ambos via augmentação de banda.
**Decisão**: **padrão de call center do Brasil** — 8 kHz narrowband, G.711 a-law, filtro 300-3400 Hz.
**Correção emitida**: afirmei que 8 kHz "corta o compute quase pela metade" — **está errado**. A taxa de frames do encoder depende do hop (10 ms → 100 fps), não do sample rate. Só o frontend encolhe (FFT 256 vs 512, ~64 vs 80 mel bins) — **ganho real ~5-10%**. O ganho verdadeiro é match de domínio, e indiretamente permite um modelo menor para a mesma qualidade.
**Consequências**:
- Storage cai pela metade: reamostrar o TAGARELA para 8 kHz na ingestão → **~880 GB** em vez de 1,76 TB.
- **Alvos de WER sobem**: telefonia perde a energia acima de 4 kHz, onde vivem as fricativas que em português distinguem plural de singular. Alvo realista: **15-25% WER** em call center PT-BR espontâneo (não ≤12%).
- Cadeia de augmentação: 16k→8k, filtro 300-3400 Hz, round-trip G.711 a-law, babble/crosstalk, AGC.

---

## Split recomendado

O tópico contém quatro sub-projetos com ciclos independentes:

| Sub-tópico | Escopo | Bloqueia? |
|---|---|---|
| **A — `asr-model-ptbr-8khz`** | Corpus, augmentação telefônica, BPE, treino Zipformer-CTC 8 kHz, avaliação | Sim — é o coração |
| **B — `asr-runtime-rust-edge`** | Captura 2 streams, VAD, ring buffers, decoder CTC + FLToP + hotwords, thread affinity, quantização | Não — paralelo a A |
| **C — `edge-fleet-platform`** | Distribuição para milhares de BYOD, versionamento de modelo, telemetria, monitoramento de WER em produção, tiering por hardware | Não — depende de A+B |
| **D — `lgpd-pii-compliance`** | Base legal, mascaramento de PII, retenção, contrato do lake | **Sim** — pode invalidar o desenho |

**Ordem sugerida**: D (levantamento, barato e pode matar premissas) ∥ A e B em paralelo → C.

## Decisões que precisam ser revisitadas antes do plano

1. **Piso de hardware BYOD** (Q3) — o i7-1355U não é o piso; é provavelmente o teto.
2. **Regime de dados** (Q12) — lake corporativo, não opt-in individual.
3. **Definição de v1** (Q13) — piloto com N atendentes reais, não dogfood pessoal.
4. **Alvos de WER** — recalibrar para telefonia 8 kHz **e** ponderar por palavras que carregam intenção.

## Próximo passo

`/grill-me asr-model-ptbr-8khz` — sub-tópico A, o caminho crítico. Em paralelo,
levantamento de D antes de qualquer treino.
