# Arsenal Técnico — ASR PT-BR Real-Time em CPU

> Levantamento SOTA · 2026-07-24
> Companion de `deep-research-asr-ptbr-cpu-realtime.md` (v4.0)
> Escopo: técnicas, papers e artefatos aplicáveis ao objetivo da § 1 daquele documento.

---

## 0. A descoberta que reorganiza o projeto

**`nvidia/nemotron-3.5-asr-streaming-0.6b`** existe e é quase exatamente o produto:

| Propriedade | Valor | Impacto |
|---|---|---|
| Arquitetura | Cache-Aware FastConformer (24 camadas) + RNNT | **Streaming nativo** — resolve o problema #13 da v4.0 |
| **Licença** | **OpenMDW-1.1 — "ready for commercial use"** | ✅ Comercial, sem passivo |
| **pt-BR** | Tier **transcription-ready** (o mais alto) | ✅ Não é PT europeu como o parakeet |
| **WER pt-BR/pt-PT** | **5,48 @ chunk 1,12 s** · **6,29 @ chunk 80 ms** | Melhor que qualquer âncora publicada que tínhamos |
| P&C | **Nativo** | ✅ Elimina um componente inteiro do escopo |
| Chunks | 80 / 160 / 320 / 560 / 1120 ms configuráveis | ✅ Trade-off latência↔WER ajustável em runtime |
| Params | 600 M | ⚠ Grande para edge |
| **Word timestamps** | **Não suporta** | ❌ Requisito seu não atendido |
| Artefatos | ONNX int4 (comunidade), GGUF, MLX | ✅ Caminho de deploy já trilhado |

**Consequência imediata: a pergunta do projeto mudou.** Não é mais "qual arquitetura treinar" — é **"em que exatamente treinar um modelo ainda agrega valor sobre pegar este e otimizar?"**

Resposta preliminar: agrega em **três eixos**, e só neles — tamanho para edge, timestamps por palavra, e sotaque regional brasileiro.

---

## 1. Papers fornecidos — leitura e aplicabilidade

| Paper | O que é | Aplicabilidade | Prioridade |
|---|---|---|---|
| **FLToP CTC** `arXiv:2510.09085` | Poda de tokens por frame com limiar relativo no decoder CTC | **10,5× speedup, 2,78× menos memória, sem retreino.** O paper afirma que decoders CTC consomem *até 90% do tempo de processamento* | 🔴 **ALTA — plug-and-play** |
| **VibeVoice-ASR-BitNet** `arXiv:2607.21075` | Quantização heterogênea: INT8 no tokenizer (activation-bound) + BitNet ternário no decoder (weight-bound) + kernels SIMD ARM/x86 | 4,62 → 1,58 GB (2,9×); RTF < 1 com **3 threads**; 1,6-2,3× mais rápido que Whisper.cpp. Código: `microsoft/VibeASR.cpp`, CC-BY-4.0 | 🟡 **MÉDIA — técnica de quantização aproveitável, modelo não** |
| **Nemotron 3.5 → línguas quenianas** `arXiv:2607.18912` | Adaptação data-centric do Nemotron 3.5 Streaming 0.6B para Kikuyu/Dholuo/Kalenjin, preservando cache-aware + streaming decoder | **É literalmente o playbook do seu projeto.** Técnicas: corpus auditing, normalização Unicode, split checks, duration filtering, low-rate continuation, checkpoint selection por validação, **true-streaming evaluation** | 🔴 **ALTA — receita direta** |
| **PINT** `arXiv:2607.19033` | Tokenização invariante — remove locutor/prosódia/canal, preserva conteúdo. −98,7% em speaker probe, −42% ABX | Relevante para **robustez a sotaque**, mas indireto (opera no tokenizer SSL, não no CTC). Risco: sotaque tem componente fonético; invariância demais pode apagar sinal útil | 🟢 **BAIXA-MÉDIA — pesquisa, não caminho crítico** |
| **StepAudio 2.5** `arXiv:2605.23463` | Modelo unificado audio-language com RLHF, 3 modos operacionais num backbone | Escala e paradigma incompatíveis com edge CPU. Sinaliza tendência do campo | 🟢 **BAIXA — contexto, não aplicação** |

---

## 2. Papers e artefatos encontrados na expansão

### 2.0 O teacher que já existe — e a âncora de WER que faltava

**[`alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx`](https://huggingface.co/alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx)**

Alguém já executou o Estágio 1 que este documento propunha — fine-tune de um
multilíngue de 600M em PT-BR **usando o TAGARELA** — e publicou com ONNX pronto.

| Propriedade | Valor |
|---|---|
| Base | `alexandreacff/parakeet-tdt-0.6b-v3-ptBR-plus` (← NVIDIA parakeet-tdt-0.6b-v3) |
| Fine-tune | **TAGARELA** |
| **Licença** | **CC-BY-4.0** ✅ comercial |
| **WER fala preparada** | **7,5%** (média) |
| **WER fala espontânea** | **14,3%** (média) |
| Test sets | CETUC, Common Voice 21.0, MLS-PT, MTEDx-PT, **ALIP**, **C-ORAL Brasil I**, **NURC-Recife**, **SP2010**, **NURC-SP**, **MuPe** |
| Deploy | via `onnx-asr` |
| Autores | alefiury + Alexandre Costa Ferro Filho |

**Três coisas que isso resolve:**

1. **A âncora de WER em fala espontânea PT-BR que este documento vinha dizendo não
   existir.** 14,3% em espontâneo, com um modelo de 600M em banda larga. Em 8 kHz
   telefônico, espere degradação — o alvo de **15-25% para call center** que
   fixamos está corretamente calibrado.
2. **Prova empírica de que o TAGARELA funciona como corpus de fine-tune.** Deixa de
   ser aposta.
3. **É provavelmente o melhor teacher disponível** — PT-BR especializado, treinado
   no mesmo corpus, com WER medido em fala espontânea, licença comercial. Supera o
   Nemotron genérico nesse papel e **dispensa o Estágio 1** do desenho da § 3.

**Precedente de licença** (observação, não aconselhamento jurídico): o modelo é
publicado sob **CC-BY-4.0** apesar de treinado em dado **CC-BY-NC-SA**. É a posição
de que pesos não herdam a licença dos dados de treino — exatamente a questão em
aberto discutida em `deep-research § 4`. Há prática estabelecida na direção que o
projeto escolheu; isso não a torna juridicamente segura.

> ⚠ **Não verificado nesta leitura:** quantização do ONNX, sample rate esperado,
> se é streaming ou offline (o parakeet-tdt-0.6b-v3 base é **offline**), suporte a
> P&C, e o número de horas do TAGARELA usadas. A model card não declara. Verificar
> antes de adotar como teacher — se for offline, o desalinhamento de spike timing
> volta a existir e o **Delayed-KD** (§ 2.1) passa a ser necessário.

### 2.1 Destilação — o caminho para o modelo pequeno

| Recurso | Achado |
|---|---|
| **Delayed-KD** `arXiv:2505.22069` | Temporal Alignment Buffer resolve o **desalinhamento de spike timing** entre teacher não-streaming e student streaming — o problema clássico de destilar CTC. **−9,4% CER relativo vs U2++ a 40 ms de latência**; CER 5,42% em AISHELL-1 |
| Factorized/progressive KD para CTC | Destilação em estágios para modelos CTC |
| KD label-free em dados não transcritos | Seleção cuidadosa de frames blank permite treino puramente por KL **sem transcrição** |

> **Insight de arquitetura:** se o teacher for o **Nemotron 3.5 (já streaming)**, o desalinhamento temporal que o Delayed-KD existe para resolver **desaparece por construção**. Teacher streaming → student streaming é alinhamento nativo. Isso torna a destilação substancialmente mais simples do que a literatura assume.
>
> **E mais:** KD label-free significa que você **não precisa das transcrições do TAGARELA** — só do áudio. As labels passariam a vir do Nemotron (comercial, 5,48 WER) em vez do Whisper. Remove a dependência do ToS da ElevenLabs. **Não resolve o `NC` do áudio**, mas elimina uma das duas camadas de passivo.

### 2.2 Aceleração de inferência — o arsenal que fecha o orçamento de CPU

Somáveis entre si. É aqui que o RTFx ≥ 6× da § 3 do documento principal se torna alcançável.

| Técnica | Ganho | Fonte |
|---|---|---|
| **FLToP CTC** — poda de token por frame | **10,5× no decoder**, 2,78× memória | `arXiv:2510.09085` |
| **Blank-regularized CTC** — frame skipping | **4× na inferência do transducer, sem perda** | `arXiv:2305.11558` |
| **CTC Blank-Triggered Dynamic Layer-Skipping** | **29%** — pula camadas finais do encoder em frames com alta prob. de blank | Interspeech 2024 |
| **Spike Window Decoding** | Reduz drasticamente frames envolvidos na decodificação | `arXiv:2501.03257` |
| **Multi-blank Transducers** | Big-blank tokens pulam múltiplos frames; ganho de velocidade **e** leve ganho de acurácia | NVIDIA |
| **int4 k-quant** (calibration-free PTQ) | **73%** de redução de tamanho, degradação de WER ~0,17-0,92 p.p. | `arXiv:2604.14493` |
| **Decomposição em 3 grafos** (encoder/decoder/joiner ONNX separados) | Quantização por componente; só o encoder quantizado (decoder+joiner = 35 MB em FP32) | idem |
| **Cache stateful zero-copy** + mel nativo em ring-buffer | Elimina materialização de tensores intermediários | idem |
| **Fusão de operadores** (MHA em kernel único) + SIMD ARM/x86 | idem / `arXiv:2607.21075` |

### 2.3 ⚠ A armadilha do RTFx — leia antes de acreditar em qualquer número

O paper da Microsoft (`arXiv:2604.14493`) reporta **RTFx > 6×** para o Nemotron 600M int4.

**Hardware: AMD EPYC 7V12, fixado em 32 cores a 2,45 GHz, batch 1.**

**São 32 cores.** Isso não é edge — é servidor. A v1.0 deste projeto quase caiu na mesma armadilha com o "RTFx 4,5 single-core". Escalonamento de threads é sublinear, mas mesmo sendo generoso, **600 M em um dispositivo de 4 cores não fecha real-time com margem**.

> **Conclusão dura:** o Nemotron 3.5 resolve o **servidor**. Ele **não** resolve o **edge**. Se o edge é requisito real, destilar para ~100 M é obrigatório — não é otimização, é viabilidade.

### 2.4 Qualidade de dados — o multiplicador mais subestimado

| Recurso | Achado |
|---|---|
| **Granary** `arXiv:2505.13404` | Pipeline NVIDIA de pseudo-labeling: segmentação → **inferência ASR em duas passadas** → verificação de language-ID → filtragem de texto → **filtro de alucinação** → restauração de P&C. Produziu ~1 M h em 25 línguas |
| **O número que importa** | Modelos treinados nos dados **processados** atingem performance similar com **~50% menos dados** |
| **Pseudo2Real** `arXiv:2510.08047` | Task arithmetic: treina dois modelos do mesmo init (um em ground-truth, outro em pseudo-label), a diferença de pesos é um **vetor de correção de viés** aplicável ao modelo alvo. Até **−35% WER relativo** (Whisper tiny em AfriSpeech-200). Artefatos sob CC-BY-NC-SA-4.0 |
| **Which Data Matter?** `arXiv:2603.05819` | Seleção de dados por embedding para ASR |
| Confidence filtering / Noisy Student | Filtro por confiança em nível de enunciado, N-best agreement, relaxamento gradual de limiar, concordância entre múltiplos transcritores fracos |

> **Aplicação direta:** o TAGARELA declara filtro de qualidade, mas não sabemos o quão rigoroso. Rodar um pipeline estilo Granary por cima pode valer **metade do corpus** — ou seja, ~4.500 h bem filtradas ≈ 8.972 h cruas. Isso corta tempo de treino pela metade e provavelmente melhora o WER.

### 2.5 Streaming + batch com um modelo só

**`arXiv:2506.14434` — Unifying Streaming and Non-streaming Zipformer-based ASR**

> O mesmo encoder Zipformer treinado serve online (streaming) **e** batch (full-context) **sem retreino** — bastando reconfigurar as máscaras de atenção por chunk.

Isso atende diretamente o requisito "ambos" que você marcou, com **um único artefato**. O Nemotron cache-aware oferece algo equivalente via `att_context_size` configurável.

### 2.6 Zipformer × FastConformer — a comparação honesta

| | Zipformer | FastConformer |
|---|---|---|
| Mecanismo de eficiência | U-Net com **frame rates variáveis** (multi-resolução) | **Subsampling agressivo 8×** no frontend |
| Ganho sobre Conformer | Zipformer-M: **~2×** (metade dos GFLOPs/memória) com acurácia ≥ | **2-3×** (e 7-10× vs Whisper large-v3 em sistema completo) |
| Streaming | Nativo; mesmo encoder serve os dois modos | Cache-aware nativo (Nemotron) |

> **Honestidade:** **não existe comparação head-to-head publicada** entre os dois, muito menos na faixa de ~100 M. Ambos reportam ganhos contra o mesmo baseline (Conformer) por caminhos diferentes. Qualquer afirmação de que um vence o outro é opinião, não evidência. **Isso se decide no seu piloto, não na literatura.**

### 2.7 Diarização streaming — deixou de ser fronteira

| Recurso | Achado |
|---|---|
| **Streaming Sortformer** `arXiv:2507.18446` | Arrival-Order Speaker Cache (AOSC) — embeddings acústicos por ordem de chegada, encoder Transformer por chunks, seleção por score preservando ordem de chegada. Autores NVIDIA (Medennikov, Park, Wang et al.) |
| Latência | Competitivo mesmo a **0,32 s** |
| Modelo pronto | `nvidia/diar_streaming_sortformer_4spk-v2` — **CC-BY-4.0** ✅ |
| Limite | **4 falantes** |
| Benchmarks | DIHARD, CALLHOME, AMI/ICSI, AISHELL-4, VoxConverse, DiPCo, AliMeeting |
| Implementação de referência | `github.com/altunenes/parakeet-rs` — STT + diarização + streaming **em CPU**, em Rust |

> Corrige a avaliação da v4.0 (§ 3), que classificava diarização streaming como "problema de fronteira". **Existe modelo pronto, comercialmente licenciado, com latência de 0,32 s.** O limite de 4 falantes é a restrição real a validar contra o caso de uso.

### 2.8 Sotaque PT-BR — o único eixo onde superar é plausível

| Recurso | Relevância |
|---|---|
| **BIPA** — PROPOR 2026 (`aclanthology.org/2026.propor-1.47`) | **Dataset fonético PT-BR com variações dialetais por região.** Candidato direto a componente do test set de sotaque |
| **`arXiv:2605.30457`** | Extração de features de sotaque em PT-BR falado **sem labels sociolinguísticos** |
| **PROPOR 2026** (`2026.propor-1.83`) — confirmado | Real + sintético (TTS) para adaptação ASR PT-BR; testado com Whisper, Wav2Vec 2.0 e Conformer |
| **Accent-Invariant ASR** `arXiv:2510.09528` | Mascaramento de espectrograma guiado por saliência |
| **CAMÕES** `arXiv:2508.19721` | Treino multi-varietal PT-BR + PT-EU + PT-AF atinge SOTA em todas — sugere **não descartar** as 842 h de PT-PT do TAGARELA |
| **PINT** `arXiv:2607.19033` | Invariância a locutor/canal preservando conteúdo — com a ressalva da § 1 |

---

## 3. A arquitetura que emerge do levantamento

```
                    ┌─ TEACHER ────────────────────────────┐
                    │  Nemotron 3.5 Streaming 0.6B          │
                    │  cache-aware · pt-BR 5,48 WER         │
                    │  OpenMDW-1.1 (comercial) · P&C nativo │
                    └───────────────┬──────────────────────┘
                                    │  KD label-free
   ┌────────────────┐               │  (só áudio — dispensa
   │ TAGARELA       │──── áudio ────┤   as labels do Whisper)
   │ 8.972 h        │               │  teacher streaming →
   │ filtro Granary │               │  student streaming =
   │ → ~4.500 h ✓   │               │  alinhamento nativo
   └────────────────┘               ▼
                    ┌─ STUDENT ────────────────────────────┐
                    │  Zipformer streaming + CTC ~80-120M   │
                    │  BPE PT-BR dedicado                   │
                    │  + word timestamps (grátis no CTC)    │
                    │  + streaming E batch (mesma rede)     │
                    └───────────────┬──────────────────────┘
                                    │  fine-tune final supervisionado
                    ┌───────────────┴──────────────────────┐
                    │  MLS + Common Voice + projeto-sotaque │
                    │  + BIPA  ·  Pseudo2Real correction    │
                    └───────────────┬──────────────────────┘
                                    ▼
   ┌─ INFERÊNCIA CPU ──────────────────────────────────────────────┐
   │  FLToP CTC (10,5×) + blank layer-skip (29%) + int4 k-quant     │
   │  + 3-graph ONNX + cache zero-copy + SIMD ARM/x86               │
   │  ── paralelo ──►  Streaming Sortformer 4spk (CC-BY-4.0)        │
   └───────────────────────────────────────────────────────────────┘
```

**O que o student ganha que o teacher não tem:** timestamps por palavra (CTC), tamanho de edge, e — via fine-tune final — sotaque regional brasileiro.

---

## 4. As três perguntas que o levantamento não responde

1. **O Nemotron 3.5 já resolve o servidor?** Se sim, treinar modelo próprio só se justifica pelo edge + timestamps + sotaque. Isso reduz o escopo drasticamente — e é uma boa notícia, não uma derrota.
2. **Qual o teto real de hardware no edge?** RTFx > 6× foi com 32 cores. O número no seu dispositivo-alvo decide se ~100 M basta ou se precisa descer para ~50 M.
3. **4 falantes bastam?** É o limite do Sortformer streaming. Se o caso de uso tiver reuniões de 6+ pessoas, a solução pronta não serve.

---

## 5. Referências completas

### Fornecidas pelo usuário
- [FLToP CTC — arXiv:2510.09085](https://arxiv.org/abs/2510.09085)
- [StepAudio 2.5 — arXiv:2605.23463](https://arxiv.org/abs/2605.23463)
- [Nemotron 3.5 → Kenyan Languages — arXiv:2607.18912](https://arxiv.org/abs/2607.18912)
- [PINT: Content is What Remains — arXiv:2607.19033](https://arxiv.org/abs/2607.19033)
- [VibeVoice-ASR-BitNet — arXiv:2607.21075](https://arxiv.org/html/2607.21075v1)

### Encontradas
- [alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx](https://huggingface.co/alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx) — **CC-BY-4.0**; parakeet v3 fine-tuned em TAGARELA; **WER 7,5% preparada / 14,3% espontânea**; suite de test sets espontâneos PT-BR
- [nvidia/nemotron-3.5-asr-streaming-0.6b](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b) — OpenMDW-1.1, pt-BR, WER 5,48
- [onnx-community/nemotron-3.5-asr-streaming-0.6b-onnx-int4](https://huggingface.co/onnx-community/nemotron-3.5-asr-streaming-0.6b-onnx-int4)
- [Pushing the Limits of On-Device Streaming ASR — arXiv:2604.14493](https://arxiv.org/html/2604.14493v2) — Microsoft CoreAI; RTFx > 6× em **32 cores**
- [Delayed-KD — arXiv:2505.22069](https://arxiv.org/html/2505.22069)
- [Granary — arXiv:2505.13404](https://arxiv.org/abs/2505.13404) · [dataset](https://huggingface.co/datasets/nvidia/Granary)
- [Pseudo2Real — arXiv:2510.08047](https://arxiv.org/html/2510.08047v2)
- [Which Data Matter? — arXiv:2603.05819](https://arxiv.org/pdf/2603.05819)
- [Blank-regularized CTC — arXiv:2305.11558](https://arxiv.org/abs/2305.11558)
- [Spike Window Decoding — arXiv:2501.03257](https://arxiv.org/pdf/2501.03257)
- [Unifying Streaming and Non-streaming Zipformer — arXiv:2506.14434](https://arxiv.org/html/2506.14434)
- [Streaming Sortformer — arXiv:2507.18446](https://arxiv.org/pdf/2507.18446) · [modelo](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2)
- [parakeet-rs](https://github.com/altunenes/parakeet-rs) — STT + diarização + streaming em CPU, Rust
- [BIPA — PROPOR 2026](https://aclanthology.org/2026.propor-1.47.pdf) — dataset dialetal PT-BR
- [Accent features PT-BR — arXiv:2605.30457](https://arxiv.org/abs/2605.30457)
- [Real + Synthetic PT-BR — PROPOR 2026](https://aclanthology.org/2026.propor-1.83.pdf)
- [Accent-Invariant ASR — arXiv:2510.09528](https://arxiv.org/html/2510.09528)
- [Zipformer — arXiv:2310.11230](https://arxiv.org/html/2310.11230v4)
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)
- [VibeASR.cpp](https://github.com/microsoft/VibeASR.cpp)
