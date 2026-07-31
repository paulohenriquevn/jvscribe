# jvscribe — ASR PT-BR em tempo real, sobre CPU

Transcritor de português brasileiro que roda **ao vivo no notebook do atendente** — sem GPU,
sem chamada de rede, sem custo por hora transcrita. A aposta é **especialização**: um modelo
que só faz PT-BR telefônico cabe em dezenas de milhões de parâmetros onde um multilíngue de
600M não fecha real-time em CPU.

Escopo do repositório: **o modelo** e **o motor de inferência**. Plataforma de frota,
compliance LGPD e UI ficam fora (`PRD.md` § 3.2).

---

## Estado

`M0–M4 [x] · M5 [~] 2/3 DoDs · M9 [x] · M6 em medição · M7, M8 pendentes`

**O entregável é `jvscribe-ptbr-zipformer-ctc-64m`**, publicado em `paulohenriquevn/jvscribe`
(HuggingFace, privado). `[MEDIDO]` FLEURS pt_br `test[0:100]`, greedy CTC, máquina ociosa:

| WER | CER | RTFx |
|---|---|---|
| **15,99%** | **7,30%** | **40,0×** |

Reproduzido **a partir do download do HF**, não dos arquivos locais: sha256 e
`vocab_fingerprint` conferem, e o checkpoint publicado carrega, codifica PT-BR e treina
(`jvscribe/results/reproducibility-2026-07-30.md`).

---

## O modelo — o que é verdade sobre ele

**Zipformer-CTC, 64,29M parâmetros, int8**, com cabeça de fonema auxiliar que sai do grafo de
inferência. Detalhe completo em `docs/ARCHITECTURE.md`.

| módulo | params | **custo** |
|---|---|---|
| `encoder` (6 stacks, o 3 concentra 48%) | 98,6% | 75,6% |
| `encoder_embed` (Conv2dSubsampling) | **1,0%** | **22,0%** |
| `ctc_output` | 0,4% | **0,3%** |

Três fatos que mudam decisões e que a intuição erra:

**1. O modelo NÃO é streaming.** É **não-causal** — a atenção enxerga o contexto inteiro nos
dois sentidos. Confirmado por três fontes: o metadado do artefato diz
`comment: "non-streaming zipformer2 CTC"`, o grafo não tem tensor de estado, e o treino nunca
passou `--causal`. O que `jvscribe/realtime/` faz é **simular** streaming com janela deslizante
+ LocalAgreement-2 (técnica do Whisper-Streaming). Custo medido: **121 ms para reprocessar 6 s
contra 11 ms de processar só os 0,5 s novos — 10,6× de retrabalho por hop.** É o piso de
latência do desenho, e só sai com treino causal.

**2. O matmul quantizado é só 24,4% do custo.** Mais de 40% é elementwise. `Log` e `Exp` com
exatamente 84 nós cada em `/encoder_embed/conv/{3,6,9}/` são a ativação **Swoosh** que o export
ONNX expande em composto em vez de fundir. Otimizar "o int8" ataca um quarto do problema.

**3. O par (modelo, vocabulário) não é intercambiável.** Dois artefatos deste projeto têm 500
tokens emitíveis e **492 dos 500 ids mapeiam para tokens diferentes**. Trocar o `tokens.txt`
produz português plausível e errado, sem erro nenhum. Valide pelo `vocab_fingerprint` do
`model_card.json`, **nunca** pela contagem.

---

## Motor de inferência

Dois caminhos, mesmo núcleo, sem GPU. Detalhe em `docs/ARCHITECTURE.md`.

- **Lote** (`jvscribe/batch/`): ffmpeg → VAD de energia → fbank → ordena por comprimento →
  ONNX em batch → CTC greedy.
- **Tempo real** (`jvscribe/realtime/`): `DualCapture` (dois `parec`) → `FeatureCache` →
  `StreamingCTC` por canal → LocalAgreement-2 → turnos + `MetricasRNF`.

**O `model_card.json` é a AUTORIDADE sobre qual peso roda** — `jvscribe/common/artifact.py` é o
único resolvedor, e todos os entrypoints o consomem. Escolher por nome de arquivo já entregou
o modelo de 17,32% em vez do de 15,99%, em silêncio.

**No caso 1:1 não existe diarização.** O mic **é** o atendente e o loopback **é** o cliente,
por construção da captura: custo zero, acurácia 100%. Diarização só entra no caso de 3
falantes (M7). `sounddevice` não serve — expõe zero monitor sources; daí o `parec` com
`--device=`.

---

## Otimização — o que está medido

**O que é portável entre CPUs** (correções algorítmicas): cache incremental de fbank, dreno do
`read()` da captura, backpressure, teto do estado do motor.

**O que precisa ser remedido ao trocar de hardware**: contagem de threads (sai da topologia) e
janela de decode (sai da ocupação de CPU). Procedimento em `docs/CALIBRATION.md`; ferramenta em
`jvscribe/tools/calibrate.py`.

| alavanca | ganho | estado |
|---|---|---|
| **Treino causal + export com estado** | **~10,6×** de encoder por hop | não feito — é trabalho de GPU |
| Sessão ONNX (arena ON + `inter_op`) | −17,1% IC95% [−36,9; −17,8] ms | ✅ |
| Cache incremental de fbank | elimina 21,6% de retrabalho | ✅ |
| Fusão da ativação Swoosh | até ~15% | não tentado |
| **FLToP CTC** (`arXiv:2510.09085`) | **~0%** | ❌ mede contra **beam search beam=1000**; o paper diz que não vale para greedy. Nosso decode é greedy e custa 0,3% |
| **Blank layer-skipping** (`arXiv:2305.11558`) | **~0%** | ❌ acelera o **joiner do transducer**; somos CTC puro |

> O DoD do M6 no `ROADMAP.md` ainda lista FLToP e blank-skip. **Os dois não se aplicam a este
> pipeline** — evidência em `jvscribe/results/m6-runtime-profile-2026-07-31.md`. A alavanca real
> é treino causal, e `arXiv:2506.14434` mostra que ela **não custa acurácia** (−7,9% de WER
> relativo com chunked attention masking).

**Afinidade de CPU foi tentada, medida e revertida.** Dava 25% isolado; ao vivo derrubou o RTFx
de 4,60× para 2,33×, porque `sched_setaffinity` **é herdado pelos processos filhos** e os
`parec` da captura passavam a disputar os mesmos P-cores. Há teste de regressão.

---

## Treino e finetuning

Tudo para retomar está em `models/current/finetune/` — ver o `README.md` de lá. Receita
[icefall](https://github.com/k2-fsa/icefall) `zipformer` sobre `egs/commonvoice/ASR`.

**As quatro flags de arquitetura são obrigatórias e NÃO estão dentro do `.pt`:**

```
--num-encoder-layers 2,2,3,4,3,2   --encoder-dim          192,256,384,512,384,256
--feedforward-dim    512,768,1024,1536,1024,768
--encoder-unmasked-dim 192,192,256,256,256,192
```

Pontos de partida: `checkpoint-124000.pt` (com `optimizer`/`scheduler` → **retoma** o run) e
`avg-124k-112k.pt` (só pesos → finetune novo com LR reiniciado).

**Armadilhas já pagas com run inteiro:**

- **LR de cabeça fresca**: `0.0001` numa cabeça recém-inicializada quebra o treino — platô em
  blank, WER 100%. Use ~`0.03` na cabeça, `0.002` no corpo.
- **fp16 colapsa** sob choque de augmentação (`grad_scale`). Os runs usam `--use-fp16 0`.
- **Full-finetune com codec-aug colapsa o greedy para ~98%** `[MEDIDO]` 2×. Daí o
  `run_ft_freeze.sh`, que congela o encoder profundo e adapta só frontend + cabeças (~1,4%).
- **Disco cheio corromper o último `.pt`** já aconteceu: o `avg-124k-112k.pt` chegou truncado a
  80 MB de 257 MB. Foi reconstruído pela média dos dois checkpoints íntegros.
- **O melhor checkpoint do treino não está em disco.** O `wer_trajectory.log` registra
  `epoch-98.pt` com WER 22,09%, podado antes do download.

**O gargalo é dado, não arquitetura** `[MEDIDO]`. O finetune de M5 faz **overfitting**, não
underfitting: train ctc ≈ val ctc no melhor ponto de cada época, mas dentro da época a val sobe
e o WER no CORAA humano degrada. Overfitting **prova que a capacidade do encoder é suficiente**
— modelo pequeno demais faria o oposto. Não mude a arquitetura: seria retrabalho contra a
medição de M4, e 64M é o tamanho **certo dado o constraint** de RNF-07 (`large`/`XL` violariam
real-time).

**Três alavancas antes de colher dado novo (caro), todas contra o MESMO overfitting:**

1. **Augmentação LIGADA** — o run de convergência rodou com `--enable-musan 0`. Religar
   Reverb→Noise→Telephone + SpecAugment mais forte + weight decay é regularização de graça, e
   ataca também o DoD#3 (telefônico 8 kHz).
2. **Checkpoint averaging** — `[MEDIDO]`, não mais estimativa: a média de 112k+124k dá WER
   **15,99%** contra 17,32% do checkpoint único, IC95% do delta [−2,25; −0,43] pp.
3. **Beam search + LM no decode** — 10–20% relativo `[LITERATURA]`, sem tocar modelo nem dado.
   O decode de hoje é greedy, o piso. **É também o que tornaria o FLToP aplicável.**

Corpus: **8.972 h** disponíveis contra as 15.000–94.000 h que a receita de referência usa para
monolíngues pequenos treinados do zero. Q-09 (acesso às ~76k h brutas do Cem Mil Podcasts) vale
mais para o WER final que qualquer escolha de encoder.

---

## Disciplina de medição — as regras que este projeto pagou para aprender

**1. Todo número carrega rótulo de proveniência.** `[MEDIDO]` / `[LITERATURA]` / `[FONTE-REPO]`
/ `[ESTIMATIVA]` / `[DESCONHECIDO]`. Sem rótulo, o número não existe.
`.claude/rules/asr-evidence-discipline.md` § 1.

**2. Hipótese, evidência e conclusão são seções distintas.** Conclusão que excede a evidência é
defeito de severidade máxima — mesmo quando se prova certa depois.

**3. NUNCA conclua de uma corrida só.** Este projeto declarou vencedor de corrida única **três
vezes** e errou nas três:

| conclusão | o que era |
|---|---|
| "intra=8 é 30,9% melhor" | não reproduziu |
| 158,8 ms vs 169,1 ms | a **mesma** configuração — 35 ms de ruído |
| "afinidade é 25% melhor" | no sistema real piorou 46% |

Use `jvscribe/common/stats.py::comparar_pareado()` — devolve `melhor=None` quando o IC95% cruza
zero e recusa n < 3. Meça em **round-robin** para a carga entrar igual nos candidatos.

**4. Benchmark de componente não transfere para o sistema.** A afinidade provou: 25% melhor
isolada, 46% pior no pipeline com dois canais e subprocessos de captura.

**5. Máquina sob carga não mede.** Mesma config ao vivo, quatro corridas: 3,51× · 2,90× · 2,82×
· 2,50×. Confira `uptime` antes; o `calibrate.py` avisa acima de load 1,0.

**6. O harness ao vivo VALIDA, não compara.** Depende de alto-falante, microfone e timing. Para
comparar configuração use `runtime_bench.py` (pareado) ou `stress_test.py` (determinístico).

**7. Pseudo-label nunca entra no test set.** Mede concordância com o professor, não acurácia
(`PRD.md` § 7.3).

**8. `knowledge-base/references/` é read-only.** Material de estudo clonado; achados vão para
`knowledge-base/discoveries/blueprints/`. Dois hooks enforçam.

**As falácias de `asr-evidence-discipline.md` § 3 são motivo de recusa.** As que mais aparecem
aqui: benchmark de GPU para justificar CPU; generalizar entre arquiteturas sem parentesco;
média sem p99; benchmark curto em chip U; tratar WER público como equivalente a call center
8 kHz.

---

## Contexto que evita erro repetido

**O orçamento de CPU é do pipeline, não do modelo.** Taxas somam pelo inverso: ASR a 3× somado
a diarização a 3× dá 1,5×. Por isso o RNF-07 exige ASR isolado ≥ 6× (`PRD.md` § 6).

**Máquina de referência ≠ piso da frota.** Todo dimensionamento assume um i7 híbrido medido; o
parque BYOD real é `[DESCONHECIDO]` (Q-01) e provavelmente muito pior. Extrapolar daqui para
"a frota" é a falácia mais provável neste projeto.

**RNF-04 e RNF-05 nunca foram exercitados.** Nenhuma corrida chegou a 30 min; nenhuma teve
softphone ativo. Qualquer afirmação sobre estabilidade térmica ou carga concorrente é
`[DESCONHECIDO]`.

**Ainda desconhecido:** WER em 8 kHz e em fala espontânea de call center (FLEURS é leitura de
notícias); equivalência batch↔streaming; comportamento no piso da frota.

---

## Onde está o quê

| Documento | Papel |
|---|---|
| `docs/ARCHITECTURE.md` | Como o modelo e o motor funcionam — grafo, stacks, custo por operador, pipelines |
| `docs/CALIBRATION.md` | Runbook ao trocar de CPU — o que é portável e o que remedir |
| `models/current/finetune/README.md` | Retomar o treino — comandos, flags, armadilhas |
| `jvscribe/results/` | Toda medição, com hipótese, evidência e limitações separadas |
| `PRD.md` | RF/RNF, arquitetura, riscos, questões abertas |
| `ROADMAP.md` | Milestones M0–M9 com DoD |
| `CHANGELOG.md` | Toda mudança relevante (Regra Inquebrável 6) |
| `knowledge-base/adrs/` | Decisões travadas, com racional e alternativas descartadas |
| `.claude/rules/asr-evidence-discipline.md` | **Contrato de evidência** — leia antes de concluir qualquer coisa |

---

## Roteamento — qual agent

Invoque pelo nome via Task/Agent. Detalhes em `.claude/agents/README.md`.

| Se a tarefa é… | Agent |
|---|---|
| Avaliar arquitetura, desenhar piloto, redigir ADR de seleção | `asr-chief-scientist` |
| Verificar se um candidato é streaming de verdade; chunk, look-ahead, cache | `streaming-asr-scientist` |
| Auditar corpus, pseudo-labeling, filtro por concordância, vazamento treino/teste | `speech-data-scientist` |
| G2P, BPE, alvos da cabeça fonética, code-switching, erro por sotaque | `ptbr-phonetics-scientist` |
| Estimar ou medir RTFx, quantização, backend, profiling | `cpu-inference-engineer` |
| Captura, ring buffers, VAD, log-mel, afinidade de threads, soak | `rust-runtime-engineer` |
| G.711, filtro telefônico, AGC, crosstalk, simulador de canal | `audio-dsp-engineer` |
| Viabilidade de hotwords e timestamps por família de decoder | `decoding-biasing-engineer` |
| Ambiente de treino, GPU preemptível, checkpoint/resume, custo por run | `ml-infra-engineer` |
| Protocolo de medição, WER por recorte, IC, p99, curva térmica | `evaluation-scientist` |
| Piso real da frota BYOD, tiering, CPUs sem AVX-VNNI | `hardware-validation-engineer` |
| Sequenciar trabalho, arbitrar dependência, proteger decisão pendente | `technical-program-lead` |

**Divergência entre agents é resultado de valor.** Registre-a e nomeie o experimento que a
resolve — não dissolva por senioridade.

## Roteamento — qual skill

Ciclo completo em `.claude/rules/cycle-*.md`. Lista completa: `/plan-help`.

| Momento | Skill |
|---|---|
| Requisitos vagos | `/grill-me {slug}` |
| Investigar prior art antes de decidir | `/discover-plan` → `/discover-edge-cases` → `/discover-plan-confidence` → `/discover-execute` → `/discover-confidence` |
| Planejar implementação | `/to-plan` → `/edge-case-plan` → `/deps-audit` → `/plan-confidence` |
| Implementar plano aprovado | `/implement {slug}` |
| Auditar código pós-implementação | `/code-quality` |
| Revisar antes do merge | `/review {slug}` |
| Cortar release | `/release` |
| Adicionar feature ao roadmap | `/roadmap-feature` |

Decisão de arquitetura sai de ciclo `/discover-*` completo, não de conversa.
