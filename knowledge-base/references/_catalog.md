---
generated_by: roadmap-init
generated_on: 2026-07-24
slug: macaw-voice-asr-ptbr
peer_count_cloned: 8
peer_count_skipped: 0
---

# References catalog

State-of-the-art peer projects gathered at project inception by `/roadmap-init`.
This file is the contract `/discover-plan` reads when investigating a peer.

> **Lifecycle:** every peer below has lifecycle `cloned` (folder present under this directory) or `skipped` (rejected at license gate, kept here for the record).

Total on disk at clone time: **743 MB** (all shallow, blob-filtered).

---

## moonshine

- **Folder:** `knowledge-base/references/moonshine/`
- **Lifecycle:** cloned
- **Repo:** https://github.com/moonshine-ai/moonshine
- **License:** `NOASSERTION` — GitHub não identificou automaticamente; o README declara **MIT** para o core e o módulo G2P. Licença dos **pesos** no HuggingFace **não confirmada**
- **License-gate decision:** clone-anyway-study-only
- **Last commit at clone time:** 2026-07-24 (`fc45890`)
- **Stars at clone time:** 10.377

### Why this peer is here

É o **candidato de arquitetura com a melhor evidência para o nosso caso** e o único
com benchmarks publicados em CPU x86 desktop — 69 ms (34M), 165 ms (123M), 269 ms
(245M) em Linux x86, contra 16.919 ms do Whisper Large v3. Roda em Raspberry Pi 5,
o que reduz materialmente o risco de hardware BYOD fraco.

O paper que o acompanha (*Flavors of Moonshine*) **valida empiricamente a tese
central deste projeto** — modelos monolíngues pequenos superam multilíngues
maiores. Com 27,1M parâmetros, têm 48% menos erro que o Whisper Tiny de tamanho
equivalente e superam o Whisper Small, 9× maior.

**Português não está entre as 8 línguas de STT que eles publicam.** É exatamente a
lacuna que este projeto ocupa.

### What to study in it

- Arquitetura encoder-decoder com RoPE (dim 288, 6+6 camadas, 8 cabeças, SwiGLU no decoder) e o custo proporcional à duração real do áudio
- Runtime: core em C++, formato `.ort`, cache de encoding e de estado do decoder
- Módulo **G2P** — candidato para a supervisão fonética auxiliar e hotwords fonéticas
- Exemplos de deploy em Raspberry Pi, iOS e Android

### Supports ROADMAP milestone(s)

- M2 — *because:* um dos dois candidatos prováveis à decisão de arquitetura
- M4 — *because:* provável braço do piloto comparativo
- M6 — *because:* o runtime C++ é referência de otimização para CPU

### Clone command used

```bash
git clone --depth 1 --filter=blob:none https://github.com/moonshine-ai/moonshine knowledge-base/references/moonshine/
```

---

## icefall

- **Folder:** `knowledge-base/references/icefall/`
- **Lifecycle:** cloned
- **Repo:** https://github.com/k2-fsa/icefall
- **License:** `Apache-2.0`
- **License-gate decision:** auto-approved-permissive
- **Last commit at clone time:** 2026-07-16 (`3f848bb`)
- **Stars at clone time:** 1.462

### Why this peer is here

Contém as recipes de treino **do zero** para Zipformer — o candidato rival ao
Moonshine. Como este projeto decidiu treinar sem herdar inicialização de checkpoint
multilíngue, uma recipe madura de treino from-scratch é o insumo mais valioso que
existe.

Zipformer entrega ~2× menos GFLOPs que Conformer com acurácia igual ou superior, e
o mesmo encoder treinado serve streaming e batch apenas reconfigurando máscaras de
atenção — atendendo o requisito de dois modos com um artefato.

### What to study in it

- Recipe Zipformer-CTC streaming: chunk, contexto limitado, cache-aware
- Estrutura de treino: schedulers, pruned transducer loss, seleção de checkpoint por validação
- Como as recipes tratam corpora grandes (GigaSpeech, WenetSpeech) — referência de escala
- Configuração de BPE e vocabulário

### Supports ROADMAP milestone(s)

- M2 — *because:* candidato à decisão de arquitetura
- M4 — *because:* provável braço do piloto comparativo
- M5 — *because:* a recipe de treino em escala vem daqui

### Clone command used

```bash
git clone --depth 1 --filter=blob:none https://github.com/k2-fsa/icefall knowledge-base/references/icefall/
```

---

## sherpa-onnx

- **Folder:** `knowledge-base/references/sherpa-onnx/`
- **Lifecycle:** cloned
- **Repo:** https://github.com/k2-fsa/sherpa-onnx
- **License:** `Apache-2.0`
- **License-gate decision:** auto-approved-permissive
- **Last commit at clone time:** 2026-07-24 (`546df6f`)
- **Stars at clone time:** 13.767

### Why this peer is here

Runtime de referência para ASR em CPU: VAD, reconhecimento streaming e diarização
integrados na mesma stack, com bindings para 12 linguagens e suporte a embarcados.
Resolve, com código testado, boa parte do plumbing que o M0 precisa.

Também documenta a restrição que descobrimos sobre hotwords: funcionam apenas em
modelos **transducer** com `modified_beam_search`, o que condiciona a escolha de
decodificação em M2.

### What to study in it

- Pipeline de streaming: gestão de chunks, cache de estado, endpointing
- **ContextGraph / Aho-Corasick** para hotwords — e por que só funciona com transducer
- Integração de VAD (Silero) e de diarização (Sortformer)
- Estratégia de bindings e empacotamento multi-plataforma

### Supports ROADMAP milestone(s)

- M0 — *because:* referência direta para o walking skeleton
- M6 — *because:* padrões de otimização de runtime em CPU
- M7 — *because:* integração de diarização e hotwords

### Clone command used

```bash
git clone --depth 1 --filter=blob:none https://github.com/k2-fsa/sherpa-onnx knowledge-base/references/sherpa-onnx/
```

---

## lhotse

- **Folder:** `knowledge-base/references/lhotse/`
- **Lifecycle:** cloned
- **Repo:** https://github.com/lhotse-speech/lhotse
- **License:** `Apache-2.0`
- **License-gate decision:** auto-approved-permissive
- **Last commit at clone time:** 2026-06-22 (`cfc429b`)
- **Stars at clone time:** 1.143

### Why this peer is here

Ferramenta de preparação de dados que o projeto vai usar. Duas capacidades são
decisivas: **augmentação on-the-fly** no dataloader — obrigatória, porque cada época
precisa ver o mesmo áudio com degradação telefônica diferente, e materializar em
disco destruiria essa variação — e o formato **Shar**, para streaming de object
storage quando o corpus escalar para terabytes.

### What to study in it

- Cuts e CutSet: compor augmentação em cadeia sem materializar
- Transformações disponíveis: resample, filtros, codec, ruído aditivo
- Formato Shar e integração com object storage
- Como manifests com milhões de segmentos são manipulados sem estourar memória

### Supports ROADMAP milestone(s)

- M1 — *because:* a cadeia de augmentação telefônica é construída aqui
- M3 — *because:* manifests e pipeline de corpus
- M4 — *because:* dataloader do piloto

### Clone command used

```bash
git clone --depth 1 --filter=blob:none https://github.com/lhotse-speech/lhotse knowledge-base/references/lhotse/
```

---

## parakeet-rs

- **Folder:** `knowledge-base/references/parakeet-rs/`
- **Lifecycle:** cloned
- **Repo:** https://github.com/altunenes/parakeet-rs
- **License:** `MIT`
- **License-gate decision:** auto-approved-permissive
- **Last commit at clone time:** 2026-07-14 (`d317e75`)
- **Stars at clone time:** 374

### Why this peer is here

O peer **arquiteturalmente mais próximo do que vamos construir**: ASR com diarização
e streaming, em CPU, escrito em **Rust**. Menor repositório da lista (1,3 MB), e
provavelmente o de maior densidade de utilidade por linha lida — resolve o plumbing
que M0 e M6 precisariam descobrir sozinhos.

### What to study in it

- Captura de áudio e ring buffers em Rust
- Integração com ONNX Runtime via bindings Rust (`ort`)
- Gestão de threads e estado em streaming
- Como a diarização é encaixada sem estourar o orçamento de CPU

### Supports ROADMAP milestone(s)

- M0 — *because:* modelo de referência para o pipeline de captura
- M6 — *because:* padrões de runtime Rust para ASR em CPU

### Clone command used

```bash
git clone --depth 1 --filter=blob:none https://github.com/altunenes/parakeet-rs knowledge-base/references/parakeet-rs/
```

---

## tract

- **Folder:** `knowledge-base/references/tract/`
- **Lifecycle:** cloned
- **Repo:** https://github.com/sonos/tract
- **License:** `NOASSERTION` — não identificada automaticamente; projetos Rust da Sonos costumam ser dual MIT/Apache-2.0. **Verificar o arquivo LICENSE antes de copiar qualquer código**
- **License-gate decision:** clone-anyway-study-only
- **Last commit at clone time:** 2026-07-24 (`352b383`)
- **Stars at clone time:** 3.008

### Why this peer is here

Runtime de inferência em **Rust puro**, sem toolchain C++, projetado para inferência
embarcada — com **gestão de streaming como recurso de primeira classe** e abstração
simbólica para dimensões dinâmicas. É a alternativa ao ONNX Runtime que mais se
aproxima de "runtime próprio" sem escrever tudo do zero.

Ganha relevância adicional se M2 apontar para modelos de espaço de estados: **SSMs
são inviáveis via ONNX Runtime** (o operador `Loop` torna a execução em CPU
proibitiva), o que transformaria o runtime próprio de otimização em pré-requisito.

### What to study in it

- Otimização de grafo embutida e fusão de operadores
- Gestão automatizada de streaming
- Cross-compilação para ARM e footprint em alvos embarcados
- Como operadores não expressos no ONNX podem ser implementados

### Supports ROADMAP milestone(s)

- M6 — *because:* candidato a runtime do encoder, e caminho obrigatório se SSM vencer M2

### Clone command used

```bash
git clone --depth 1 --filter=blob:none https://github.com/sonos/tract knowledge-base/references/tract/
```

---

## funasr

- **Folder:** `knowledge-base/references/funasr/`
- **Lifecycle:** cloned
- **Repo:** https://github.com/modelscope/FunASR
- **License:** `MIT`
- **License-gate decision:** auto-approved-permissive
- **Last commit at clone time:** 2026-07-24 (`a28ee6b`)
- **Stars at clone time:** 19.459

### Why this peer is here

Traz o terceiro candidato de arquitetura — **Paraformer, não-autorregressivo de
passo único**, cuja v2 substituiu o módulo CIF por CTC para extrair token embeddings
e ganhou robustez a ruído explicitamente, requisito direto de call center.

E traz a evidência mais forte que localizamos de que ASR real-time em CPU funciona
em escala de produção: a documentação reporta **16 streams concorrentes em 4 vCPU**
com o modo 2-pass streaming, e quantização q8 em torno de 250 MB. Esses números vêm
de documentação de projeto, não de paper revisado — indicativos até reproduzir.

### What to study in it

- Paraformer-v2: predição não-autorregressiva e o uso de CTC para token embeddings
- Arquitetura **2-pass streaming** — passe rápido para feedback imediato, refinamento posterior; encaixa no produto (atendente vê na hora, lake recebe refinado)
- Implementação de hotwords e timestamps em modelo NAR
- Estratégia de quantização e serving concorrente em CPU

### Supports ROADMAP milestone(s)

- M2 — *because:* candidato à decisão de arquitetura
- M6 — *because:* referência de serving concorrente em CPU
- M7 — *because:* hotwords e timestamps em modelo não-autorregressivo

### Clone command used

```bash
git clone --depth 1 --filter=blob:none https://github.com/modelscope/FunASR knowledge-base/references/funasr/
```

---

## vibeasr-cpp

- **Folder:** `knowledge-base/references/vibeasr-cpp/`
- **Lifecycle:** cloned
- **Repo:** https://github.com/microsoft/VibeASR.cpp
- **License:** `MIT`
- **License-gate decision:** auto-approved-permissive
- **Last commit at clone time:** 2026-07-24 (`2d09198`)
- **Stars at clone time:** 9

### Why this peer is here

Implementação de referência do paper VibeVoice-ASR-BitNet (Microsoft Research):
**quantização heterogênea** — INT8 no tokenizer dominado por ativações, pesos
ternários BitNet no decoder dominado por pesos — com kernels SIMD escritos à mão
para ARM e x86, unificados num pipeline `maddubs`. Reporta 2,9× de compressão e
RTF < 1 com apenas 3 threads de CPU.

Adoção baixa (9 stars) porque é recente; a procedência e o paper compensam. É o peer
mais diretamente útil para o motor de inferência próprio.

### What to study in it

- Kernels SIMD para multiplicação quantizada em x86 (AVX-VNNI) e ARM
- Quantização por componente, em vez de uniforme no modelo inteiro
- Fusão de operadores eliminando materialização de tensores intermediários
- Treino com quantização progressiva por alpha-blending

### Supports ROADMAP milestone(s)

- M6 — *because:* referência central para quantização e kernels do runtime próprio

### Clone command used

```bash
git clone --depth 1 --filter=blob:none https://github.com/microsoft/VibeASR.cpp knowledge-base/references/vibeasr-cpp/
```

---

## Skipped peers (license gate)

> Peers identified during SOTA discovery but rejected at the license gate.
> Listed here so the decision is auditable and not repeated next time.

| Peer | Repo | License | Reason for skip |
|---|---|---|---|
| *(nenhum)* | — | — | Todos os 8 peers aprovados foram clonados com sucesso; nenhuma rejeição no license gate e nenhuma falha de clone |

**Considerado e não incluído na shortlist** (curadoria, não license gate):

| Peer | Repo | Motivo |
|---|---|---|
| NVIDIA/NeMo | https://github.com/NVIDIA/NeMo | Repositório muito grande; os checkpoints NVIDIA já foram descartados do produto, e as recipes de FastConformer perdem relevância com a decisão de treinar do zero. Sortformer é consumido como modelo pronto, não como código |
| huggingface/candle | https://github.com/huggingface/candle | Sobreposição com `tract` e `parakeet-rs` para o mesmo papel; incluir os três seria ruído |

---

## Cleanup protocol

- **Remove a peer:** delete its folder under this directory AND remove its entry from this catalog in the same commit.
- **Update a peer (refresh clone):** `cd knowledge-base/references/<peer>/ && git pull` — record the new commit SHA in this catalog.
- **Replace a peer with a better one:** treat as remove + add. Do NOT rename folders; symbolic continuity is meaningless when the underlying repo changed.
