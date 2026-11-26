# Deep Research — Arquiteturas Alternativas e Prior Art

> 2026-07-24 · Companion de `sota-techniques-asr-ptbr-cpu.md`
> Escopo: arquiteturas fora do eixo Conformer/Zipformer, runtimes CPU, modelos edge,
> e o problema de escala de dados.

---

## Sumário — o que muda nos requisitos

| # | Achado | Impacto |
|---|---|---|
| **1** | **A tese monolíngue está publicada e validada** — e com **27M**, não 80M | 🟢 Confirma a estratégia; o alvo de tamanho pode cair 3× |
| **2** | **O corpus é pequeno demais** — a receita de referência usa 15-94k h/língua; temos 8,9k | 🔴 **Risco maior que qualquer outro registrado** |
| **3** | **SSM/Mamba bate Conformer em WER *e* RTF, com inferência de tempo constante** | 🟡 Superior no papel, **bloqueado no ONNX** — destravado pelo runtime próprio |
| **4** | Mamba suporta 739 min de áudio contínuo vs 5 min do Conformer | 🟡 Relevante para chamadas longas |
| **5** | `tract` (Rust puro, Sonos) tem gestão de streaming embutida | 🟢 Alternativa ao `ort` que não estava no radar |
| **6** | Paraformer-v2 (NAR + CTC) — robustez a ruído explícita | 🟡 Terceira via entre CTC e transducer |

---

## 1. Moonshine — a tese do projeto, publicada

**[Flavors of Moonshine: Tiny Specialized ASR Models for Edge Devices](https://arxiv.org/pdf/2509.02523)** — King, Sabra, Kudlur, Wang, Warden (Moonshine AI), set/2025.

O abstract é literalmente a tese deste projeto:

> *"Prevailing wisdom suggests that multilingual ASR models outperform monolingual
> counterparts by exploiting cross-lingual phonetic similarities. **We challenge this
> assumption**, showing that for sufficiently small models (27M parameters), training
> monolingual systems on a carefully balanced mix of high-quality human-labeled,
> pseudo-labeled, and synthetic data yields substantially superior performance."*

### Resultados

| Comparação | Resultado |
|---|---|
| vs Whisper Tiny (tamanho equivalente) | **−48% de erro**, em média |
| vs Whisper Small (**9× maior**) | **supera em todos os casos** |
| vs Whisper Medium (**28× maior**) | **iguala ou supera na maioria** |
| Velocidade on-device | **5×-15× mais rápido que Whisper** |
| Licença | permissiva, open-source |

### Arquitetura (Moonshine Tiny)

| | Moonshine | Whisper Tiny |
|---|---|---|
| Dimensão | 288 | 384 |
| Camadas encoder | **6** | 4 |
| Camadas decoder | **6** | 4 |
| Cabeças de atenção | 8 | 6 |
| Ativação FFN decoder | **SwiGLU** | GELU |
| **Parâmetros** | **27,1M** | 37,8M |
| **FLOPs vs Whisper Tiny** | **0,7×** | 1,0× |

Encoder-decoder transformer com **RoPE** no encoder e no decoder. A vantagem de
edge não é só tamanho: **o custo de inferência escala com a duração real do áudio**,
enquanto o Whisper padda tudo para 30 s independentemente do conteúdo.

**Línguas liberadas:** árabe, chinês, japonês, coreano, ucraniano, vietnamita.
**Português não está na lista** — é exatamente a lacuna que este projeto ocuparia.

### 🟢 O repositório — [`moonshine-ai/moonshine`](https://github.com/moonshine-ai/moonshine)

**Código sob licença MIT.** Contém o runtime de inferência (core em C++ com
bindings), modelos ONNX quantizados pré-construídos (formato `.ort`), módulo G2P e
exemplos para iOS, Android, Python, C++, Windows, macOS e Raspberry Pi.

**Não contém código de treino nem ferramentas de export ONNX** — os modelos são
distribuídos prontos. Reproduzir a arquitetura exige reimplementá-la a partir do
paper (dim 288, 6+6 camadas, 8 cabeças, RoPE, SwiGLU no decoder).

#### Modelos de streaming (inglês)

| Variante | Params | WER |
|---|---|---|
| Tiny | 26M | 12,66% |
| **Tiny Streaming** | **34M** | 12,00% |
| Base | 58M | 10,07% |
| **Small Streaming** | **123M** | 7,84% |
| **Medium Streaming** | **245M** | **6,65%** |

Medium Streaming, com **245M**, supera o **Whisper Large v3 (1,5B, 7,44% WER)** —
6× menos parâmetros e WER menor.

#### 🔴 Latência de transcrição ao vivo — o dado que faltava

| Modelo | Params | MacBook | **Linux x86** | Raspberry Pi 5 |
|---|---|---|---|---|
| Medium Streaming | 245M | 107 ms | **269 ms** | 802 ms |
| Small Streaming | 123M | 73 ms | **165 ms** | 527 ms |
| Tiny Streaming | 34M | 34 ms | **69 ms** | 237 ms |
| Whisper Large v3 | 1,5B | 11.286 ms | 16.919 ms | inviável |

**Isto reescreve a análise de viabilidade dos requisitos.** Até aqui, todo o
dimensionamento dependia de uma extrapolação a partir de um benchmark em servidor
EPYC de 32 núcleos. Agora existe medição em **CPU x86 desktop**:

- **123M entrega 165 ms em Linux x86** — dentro do orçamento de latência (RNF-02, p99 ≤ 500 ms)
- **245M entrega 269 ms** — também cabe, com WER de 6,65%
- **Whisper Large v3 é 105× mais lento** que o Medium no mesmo hardware

**Consequências diretas:**

1. **O teto de tamanho é maior do que assumimos.** Os requisitos fixaram ~80M com base numa
   estimativa pessimista. A evidência sugere que **123-245M cabem** num desktop x86
   — e mais parâmetros compram WER.
2. **O risco R1 (BYOD fraco) encolhe muito.** Tiny Streaming roda em **Raspberry Pi 5
   a 237 ms** — hardware muito inferior a qualquer notebook de atendente. Se roda no
   Pi, roda no i3 de 2018.
3. Confirma que o gargalo do Whisper não é tamanho, é arquitetura: janela fixa de
   30 s e ausência de cache.

⚠ "Latência de transcrição ao vivo" **não é RTFx** — é o tempo até o texto aparecer.
São métricas complementares; o projeto precisa das duas. A do requisito (RNF-01) continua
a ser medida.

#### Capacidades — todos os requisitos atendidos

| Requisito | Moonshine |
|---|---|
| RF-01 streaming | ✅ *"incremental addition of audio over time"*, com cache do encoding e de parte do estado do decoder |
| RF-06 timestamps por palavra | ✅ suportado |
| Diarização | ✅ *speaker IDs* na CLI |
| Deploy edge | ✅ Linux, macOS, Windows, iOS, Android, RPi, IoT, microcontroladores, DSPs; modelos de **1 MB** |
| Bindings | Python, Swift, Java/Kotlin, C++, C — **sem Rust** (o core em C é ponte viável via FFI) |
| **Português (STT)** | ❌ **ausente** — 8 línguas: inglês, espanhol, mandarim, japonês, coreano, vietnamita, ucraniano, árabe |

Português existe apenas no lado **TTS** (16 línguas). A lacuna de STT é exatamente
o espaço deste projeto.

⚠ **A licença dos modelos não foi confirmada** — o repo declara MIT para o código, e
os pesos vivem no HuggingFace possivelmente sob termos distintos. Verificar antes de
qualquer uso derivado.

### Receita de treino (reprodutível)

Estratégia em três estágios por língua:

1. Agregar datasets públicos existentes (baseline)
2. **Coletar e pseudo-rotular áudio bruto público** — podcasts e streams de rádio
3. **Sintetizar via TTS** a partir de datasets text-only, quando o áudio bruto é insuficiente

Hiperparâmetros: AdamW schedule-free, lr `2e-5`, **8 épocas**, batch 32, DDP em
**8× H100**. Pseudo-labeling com **WhisperX** em framework distribuído próprio.

### 🔴 O problema — o volume de dados

| Língua | Público | Interno | Sintético | **Total (mil h)** |
|---|---|---|---|---|
| Árabe | 4,6 | 10,0 | 0,9 | **15,5** |
| Ucraniano | 1,7 | 12,9 | 5,1 | **19,6** |
| Japonês | 36,9 | 17,0 | 0 | **53,9** |
| Chinês | 50,9 | 19,0 | 0 | **69,8** |
| Coreano | 27,6 | 44,4 | 0 | **72,0** |
| Vietnamita | 8,4 | 85,8 | 0 | **94,2** |
| **Este projeto (TAGARELA)** | 8,9 | 0 | 0 | **8,9** ⚠ |

**Estamos abaixo do menor caso deles — e por 43%.** Pior, o paper afirma que a
literatura indica **10⁴ a 10⁵ horas** como faixa mínima para resultado usável, e
justifica o volume com uma razão que nos atinge diretamente:

> *"(1) monolingual models **do not benefit from transfer learning**, and thus need
> larger datasets"*

Ou seja: **a decisão de treinar do zero (sem inicialização) é exatamente a que
aumenta a necessidade de dados** — e é a que tomamos com 8,9k h disponíveis.

### A saída — e ela está mais perto do que parece

O TAGARELA deriva do corpus **Cem Mil Podcasts: ~76.000 horas** de áudio em
português. O TAGARELA publicou **8.972 h processadas** — cerca de **12% da fonte**.

**Se o pipeline de pseudo-labeling for rodado sobre o corpus bruto, o volume
disponível salta para a faixa do Moonshine.** Isso transforma o maior risco do
projeto em trabalho de engenharia de dados — que é caro, mas tratável, e
tem receita publicada (Granary + Moonshine).

Fontes adicionais mapeadas, todas modestas isoladamente mas somáveis:

| Corpus | Horas | Nota |
|---|---|---|
| NURC-SP Audio Corpus | 239,3 h | 401 falantes (204 F / 197 M) |
| CORAA | 290,8 h | ALIP + C-ORAL Brasil I + NURC-Recife + SP2010 + TEDx — **CC-BY-NC-ND, inutilizável** |
| MLS-PT | 284 h | 55 audiobooks, 62 falantes, CC-BY-4.0 |
| [ASR-BPCSC](https://magichub.com/datasets/brazilian-portuguese-conversational-speech-corpus/) | ? | **Conversacional** PT-BR — verificar licença e volume |
| [Brazilian Radio Corpus 1980s-90s](https://aclanthology.org/2026.propor-1.81.pdf) | ? | PROPOR 2026; feito para TTS, avaliar para ASR |

---

## 2. SSM / Mamba — superior no papel, bloqueado na prática (e destravado pelo runtime próprio)

**[Attention-Free Dual-Mode ASR with Latency-Controlled Selective State Spaces](https://www.isca-archive.org/interspeech_2025/moriya25_interspeech.pdf)**
— Moriya, Mimura, Matsui, Sato, Matsuura (**NTT, Japão**), Interspeech 2025.

Propõe **LC-BiMamba** (latency-controlled bidirectional Mamba): processamento
chunk-wise em streaming **com acesso a contexto futuro**, comportando-se como
BiMamba padrão em modo offline. **Um modelo, dois modos** — exatamente RF-01 + RF-02.

### Resultados — LibriSpeech, dual-mode (parâmetros equalizados com Conformer)

| Encoder | WER offline (clean/other) | WER streaming (clean/other) | **RTF** |
|---|---|---|---|
| Conformer | 3,0 / 7,2 | 3,9 / 9,4 | 0,58 |
| UniConMamba (wide) | 3,2 / 7,8 | 4,3 / 10,2 | 0,92 |
| LC-BiConMamba (wide) | 3,1 / 7,3 | 3,8 / 9,1 | **0,50** |
| **LC-BiConMamba (deep)** | **3,0 / 7,1** | **3,7 / 8,9** | 0,51 |

**Bate o Conformer em WER nos dois modos e em RTF** (~14% mais rápido). Em TEDLIUM-v2
dual-mode: 6,9/7,9 contra 7,1/8,4 do Conformer, RTF 0,40 vs 0,49.

E dispensa duas coisas: *"required neither positional embedding nor history contexts"*.

### O número mais dramático

> Conformer, com complexidade quadrática, processou no máximo **5 minutos** de áudio.
> LC-BiConMamba, com **inferência de tempo constante**, suportou **739 minutos**.

**148× mais.** Para call center — chamadas longas, sessões contínuas de horas — a
diferença entre estado recorrente compacto e cache de atenção que cresce é
estrutural, não incremental.

### 🔴 A barreira — e por que ela não te atinge

Buscando viabilidade de deploy, o quadro é ruim:

- O scan seletivo é implementado em **Triton (CUDA)**; a versão recorrente para inferência não exporta para ONNX de forma direta
- [`microsoft/onnxruntime#27796`](https://github.com/microsoft/onnxruntime/issues/27796): *"ONNX Loop op makes Mamba (SSM) models **unusable on CPU** and WebGPU"* — o interpretador do op `Loop` tem overhead proibitivo
- Decompor o scan em ~40-70 ops ONNX produz resultado numericamente correto mas **materializa tensores intermediários a cada passo**
- Consenso nas issues: SSMs estão *"effectively locked to Python plus CUDA"*

**Mas o bloqueio é do ONNX, não da matemática.**

Em inferência streaming, o scan de Mamba é uma **recorrência passo a passo: O(1) por
frame, estado de tamanho fixo**. Implementar isso à mão em Rust é direto — o que é
difícil é expressá-lo no grafo estático do ONNX.

> **Consequência estratégica:** a decisão de escrever motor de inferência próprio em
> Rust deixa de ser apenas otimização de performance. Ela **destrava uma
> classe inteira de arquiteturas que o ecossistema ONNX bloqueia** — e essa classe é
> justamente a que tem inferência de tempo constante, ideal para streaming em CPU.
>
> Isso inverte a ordem recomendada nos requisitos: se o alvo for SSM, o `ort` **não** é o
> caminho de menor esforço para o encoder — ele é um beco sem saída.

**Ressalva honesta:** todos os RTFs acima foram medidos em **GPU** (RTX 6000 Ada).
Mamba em CPU é território não medido publicamente. O scan sequencial não paraleliza
como matmul — em treino e batch isso pesa; em streaming (um passo por vez) você já
está sequencial e a desvantagem desaparece. **Nenhum benchmark de Mamba-ASR em CPU
foi localizado.** É risco de pesquisa, não de engenharia.

### Trabalhos relacionados
- [Samba-ASR — `arXiv:2501.02832`](https://arxiv.org/abs/2501.02832) — Mamba como encoder **e** decoder; reivindica SOTA em GigaSpeech, LibriSpeech, SPGISpeech
- [DuplexMamba — `arXiv:2502.11123`](https://arxiv.org/html/2502.11123v1) — streaming e duplex
- [SSMs in Whispered and Multi-dialect Speech — `arXiv:2506.16969`](https://arxiv.org/pdf/2506.16969) — **multi-dialeto**, relevante para sotaque
- [Mamba for Streaming ASR with Unimodal Aggregation](https://ieeexplore.ieee.org/abstract/document/10887599) — ICASSP

---

## 3. Paraformer-v2 — a terceira via entre CTC e transducer

**[Paraformer-v2 — `arXiv:2409.17746`](https://arxiv.org/pdf/2409.17746)** — An, Li, Gao, Zhang (**Speech Lab, Alibaba**), set/2024.

Non-autoregressive de passo único. A v2 substitui o módulo *continuous
integrate-and-fire* da v1 por um **módulo CTC para extrair token embeddings** —
mais simples e mais estável. Ganhos: **>14% de WER em inglês** sobre a v1, e
**robustez a ruído** explicitamente melhorada.

**Por que importa aqui:** robustez a ruído é requisito direto de call center
(crosstalk de atendentes vizinhos, linha telefônica). E o ecossistema **FunASR** é o
mais maduro em deploy CPU que localizamos:

| Achado | Fonte |
|---|---|
| SenseVoiceSmall (234M): **5× mais rápido que Whisper-Small, 15× que Whisper-Large**, real-time em CPU | FunASR docs |
| Paraformer-Large (220M): 92 s de áudio em ~9 s num i7 → **RTFx ~10× em CPU** | FunASR docs |
| Quantização q8 ≈ **250 MB** | FunASR docs |
| **4 vCPU / 8 GB suportam 16 streams concorrentes** (2-pass streaming, validado em produção pela Alibaba) | FunASR docs |
| Paraformer suporta **timestamps e hotwords** nativamente | FunASR docs |

O último ponto merece atenção: **16 streams concorrentes em 4 vCPU** é a evidência
mais forte que encontramos de que ASR real-time em CPU comum funciona em escala de
produção. E o **2-pass streaming** (passe rápido em streaming + refinamento) é um
padrão arquitetural que os requisitos não consideram.

⚠ Números do FunASR vêm de documentação do projeto, não de paper revisado por pares.
Tratar como indicativo até reproduzir.

---

## 4. Runtimes Rust — `ort` não é a única opção

| Runtime | Natureza | Pontos fortes | Adequação |
|---|---|---|---|
| **[`tract`](https://github.com/sonos/tract)** (Sonos) | **Rust puro**, sem deps externas | ONNX + NNEF + TFLite; otimização de grafo embutida; **gestão automatizada de streaming**; abstração simbólica para dimensões dinâmicas; cross-compila para ARM | 🟢 **Forte candidato** — feito para embedded, e "streaming management" é o nosso caso |
| **[`burn`](https://github.com/tracel-ai/burn)** | Framework completo | Converte ONNX em **código Rust nativo**; **fusão automática de kernels**; backends CPU/GPU/WASM | 🟡 Interessante para kernels custom |
| **[`candle`](https://github.com/huggingface/candle)** (HuggingFace) | Tensor lib minimalista | Caso relatado: detecção em tempo real em 100+ Raspberry Pi 4, **−35% de latência vs PyTorch** | 🟡 Bom para protótipo |
| **`ort`** | Bindings ONNX Runtime (C++) | Maduro, VNNI, amplo suporte de ops | 🟢 Baseline — **mas bloqueia SSM** |

**`tract` é a descoberta desta seção.** Rust puro (sem toolchain C++), projetado
para inferência embarcada, com gestão de streaming como recurso de primeira classe —
e uma apresentação no FOSDEM 2026. É a opção que mais se aproxima de "runtime
próprio" sem escrever tudo do zero.

---

## 5. Recomendações revisadas

### 5.1 Elevar o risco de dados a bloqueante nível 1

Os requisitos listam R1 (hardware BYOD) como risco principal. **Com a evidência do Moonshine,
o volume de corpus passa à frente.** 8,9k h contra 15-94k h da receita de referência,
num regime sem transfer learning que a própria fonte identifica como o que *mais*
precisa de dados.

**Ação:** investigar acesso ao corpus bruto **Cem Mil Podcasts (~76k h)** e montar
pipeline próprio de pseudo-labeling (receita Granary + WhisperX à la Moonshine).
Isso move o projeto de "abaixo do mínimo" para "dentro da faixa" — e é a diferença
entre um modelo utilizável e um que decepciona.

### 5.2 Abrir a faixa de tamanho — para baixo **e para cima**

Os requisitos fixaram ~80M a partir de uma estimativa pessimista extrapolada de servidor. Os
benchmarks do repositório Moonshine, em **CPU x86 desktop**, mostram que a faixa
viável é bem mais larga do que supúnhamos:

| Alvo | Evidência | Trade-off |
|---|---|---|
| **~27-34M** | 69 ms em Linux x86; 237 ms em RPi 5 | Máxima folga de CPU; WER mais alto (12% en) |
| **~123M** | **165 ms em Linux x86** | Bom equilíbrio; WER 7,84% (en) |
| **~245M** | **269 ms em Linux x86**; supera Whisper Large v3 | Melhor WER (6,65% en); ainda dentro do RNF-02 |

**Ação:** o piloto da Fase 2 deve varrer **três pontos — ~30M, ~80M e ~123M** — em
vez de fixar um. A curva WER × RTFx medida no hardware-alvo é o que decide, e ela
custa pouco para levantar num piloto de 500 h.

**Correção de análise:** eu havia recomendado descer para 27M. Com os benchmarks em
mãos, isso é conservador demais — sacrificaria WER sem necessidade. E o R1 (BYOD
fraco) deixa de ser ameaça existencial por outra razão: **Tiny Streaming roda a
237 ms num Raspberry Pi 5**, hardware muito inferior a qualquer notebook de
atendente.

### 5.3 Adicionar um braço SSM ao piloto — com ressalva explícita

LC-BiConMamba bate Conformer em WER *e* RTF, resolve dual-mode nativamente, e suporta
sessões 148× mais longas. Se o runtime é próprio em Rust, a barreira do ONNX não se
aplica.

**Ação:** braço exploratório no piloto, com **gate explícito** — se o scan em CPU
não render em Rust, descartar cedo. Não é caminho principal; é opção de alto retorno
com risco contido.

### 5.4 Reordenar a decisão de runtime

Os requisitos recomendam `ort` primeiro. **Isso vale para Zipformer/Conformer, não para SSM.**
Avaliar `tract` em paralelo: Rust puro, streaming embutido, e liberdade para
implementar operadores que o ONNX não expressa.

### 5.5 Considerar arquitetura 2-pass

O padrão validado pela Alibaba — passe streaming rápido para feedback imediato +
refinamento posterior — casa com o produto: o atendente vê o texto na hora, e o lake
recebe a versão refinada. Duas qualidades, dois custos, uma captura.

---

## 6. Referências desta rodada

### Lidas integralmente (PDF extraído e analisado)

| Referência | Fatos-chave |
|---|---|
| [`moonshine-ai/moonshine`](https://github.com/moonshine-ai/moonshine) | **Código MIT**; runtime C++ com bindings Python/Swift/Java/C++/C (sem Rust); modelos ONNX quantizados `.ort`; **sem código de treino**; streaming com cache de encoding e estado do decoder; **word timestamps + speaker IDs**; **latência Linux x86: 69 ms (34M) / 165 ms (123M) / 269 ms (245M)** vs Whisper Large v3 16.919 ms; RPi 5: 237/527/802 ms; Medium Streaming 245M @ 6,65% WER supera Whisper Large v3 (1,5B @ 7,44%); **STT sem português**; ⚠ licença dos pesos não confirmada |
| [Flavors of Moonshine — `arXiv:2509.02523`](https://arxiv.org/pdf/2509.02523) | Moonshine AI; 27,1M params; dim 288, 6+6 camadas, 8 cabeças, RoPE, SwiGLU no decoder; 0,7× FLOPs do Whisper Tiny; −48% erro vs Whisper Tiny; supera Whisper Small (9×) e iguala Medium (28×); 5-15× mais rápido on-device; dados 15,5-94,2 mil h/língua; AdamW schedule-free, lr 2e-5, 8 épocas, batch 32, 8× H100; WhisperX para pseudo-label; licença permissiva; **sem português** |
| [Attention-Free Dual-Mode ASR — Interspeech 2025](https://www.isca-archive.org/interspeech_2025/moriya25_interspeech.pdf) | NTT Japão; LC-BiMamba; LibriSpeech dual-mode: 3,0/7,1 offline, 3,7/8,9 streaming, RTF 0,51 vs Conformer 3,0/7,2, 3,9/9,4, RTF 0,58; TEDLIUM-v2: 6,9/7,9 RTF 0,40 vs 7,1/8,4 RTF 0,49; chunk Lc=15 → 300 ms de latência algorítmica; **739 min vs 5 min** de duração máxima; dispensa positional embedding e history context |
| [Paraformer-v2 — `arXiv:2409.17746`](https://arxiv.org/pdf/2409.17746) | Speech Lab, Alibaba; NAR de passo único; CTC substitui CIF para extrair token embeddings; >14% de melhoria de WER em inglês sobre v1; robustez a ruído melhorada |
| [Moonshine v2 — `arXiv:2602.12241`](https://arxiv.org/pdf/2602.12241) | Kudlur, King, Wang, Warden; "ergodic streaming encoder" para aplicações latency-critical; ⚠ tabelas não extraídas do PDF — reler |

### Identificadas em busca

| Referência | Relevância |
|---|---|
| [Samba-ASR — `arXiv:2501.02832`](https://arxiv.org/abs/2501.02832) | Mamba como encoder e decoder; SOTA reivindicado em GigaSpeech/LibriSpeech/SPGISpeech |
| [DuplexMamba — `arXiv:2502.11123`](https://arxiv.org/html/2502.11123v1) | Streaming + duplex com Mamba |
| [SSMs em fala sussurrada e multi-dialeto — `arXiv:2506.16969`](https://arxiv.org/pdf/2506.16969) | Multi-dialeto — relevante para sotaque regional |
| [Mamba streaming ASR + Unimodal Aggregation](https://ieeexplore.ieee.org/abstract/document/10887599) | ICASSP |
| [`onnxruntime#27796`](https://github.com/microsoft/onnxruntime/issues/27796) | **SSM inutilizável em CPU via ONNX** — bloqueio documentado |
| [`onnx/onnx#7689`](https://github.com/onnx/onnx/issues/7689) | Proposta de operadores para atenção linear / atualização recorrente de estado |
| [`tract`](https://github.com/sonos/tract) · [FOSDEM 2026](https://fosdem.org/2026/schedule/event/YJJQTD-tract-and-torch-to-nnef/) | Runtime Rust puro com gestão de streaming |
| [`burn`](https://github.com/tracel-ai/burn) | ONNX → código Rust nativo, fusão de kernels |
| [`candle`](https://github.com/huggingface/candle) | Tensor lib Rust; −35% latência vs PyTorch em Raspberry Pi |
| [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) · [FunASR](https://github.com/modelscope/FunASR) | NAR; 16 streams em 4 vCPU; q8 ≈ 250 MB; hotwords e timestamps |
| [Paraformer — `arXiv:2206.08317`](https://arxiv.org/pdf/2206.08317) | Paper original |
| [FunASR toolkit — `arXiv:2305.11013`](https://arxiv.org/pdf/2305.11013) | Toolkit |
| [NURC-SP Audio Corpus](https://dl.acm.org/doi/10.1007/978-3-031-79029-4_3) | 239,3 h, 401 falantes, sotaque de São Paulo |
| [ASR-BPCSC](https://magichub.com/datasets/brazilian-portuguese-conversational-speech-corpus/) | Corpus **conversacional** PT-BR — verificar licença |
| [Brazilian Radio Corpus 1980s-90s — PROPOR 2026](https://aclanthology.org/2026.propor-1.81.pdf) | Rádio; feito para TTS |
| [Wav2Vec2 PT-BR — `arXiv:2107.11414`](https://arxiv.org/pdf/2107.11414) · [`lgris/wav2vec2-large-xlsr-open-brazilian-portuguese-v2`](https://huggingface.co/lgris/wav2vec2-large-xlsr-open-brazilian-portuguese-v2) | 600+ h; baseline PT-BR |
