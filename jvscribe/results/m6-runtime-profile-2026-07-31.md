# Otimização do runtime — profile por operador + prior art `[MEDIDO]` / `[LITERATURA]`

Data: 2026-07-31 · modelo `models/current/model.int8.onnx` · ONNX Runtime 1.22.0 · i7 12-core.

## Correção de método registrada

A primeira tentativa deste trabalho cronometrou blocos com `time.perf_counter()` e concluiu
"inferência = 78% do custo". Isso não diz **o que** otimizar. Em seguida testou hipóteses
inventadas (arena, threads, batch) e mediu *post-hoc* — busca por tentativa, não engenharia
guiada por dado. Pior: mediu com a máquina em load 8–14 e reportou número mesmo assim.

Esta rodada usa o **profiler por operador do ONNX Runtime** (`enable_profiling`), que estava
disponível o tempo todo, e vai atrás das fontes das técnicas em vez de citá-las de memória.

## Evidência 1 — onde o tempo realmente está `[MEDIDO]`

`enable_profiling=True`, janela de 6 s (600 frames), 3 runs, intra=6/inter=3, arena ligada.
Total em kernels: **91,6 ms/run**.

### Por subgrafo

| subgrafo | ms/run | % |
|---|---|---|
| `encoder` | 69,27 | **75,6%** |
| `encoder_embed` (subsampling) | 20,17 | **22,0%** |
| `ctc_output` | 0,26 | **0,3%** |

### Por operador

| operador | ms/run | % | nós | µs/nó |
|---|---|---|---|---|
| `DynamicQuantizeMatMul` | 22,40 | 24,4% | 242 | 92,6 |
| `Conv` | 12,20 | 13,3% | 38 | **321,1** |
| `Add` | 8,76 | 9,6% | 627 | 14,0 |
| `Sub` | 7,00 | 7,6% | 376 | 18,6 |
| `Where` | 6,54 | 7,1% | 140 | 46,7 |
| `Log` | 4,30 | 4,7% | 84 | 51,2 |
| `Mul` | 3,71 | 4,1% | 371 | 10,0 |
| `Transpose` | 2,92 | 3,2% | 227 | 12,8 |
| `Exp` | 2,24 | 2,4% | 84 | 26,6 |

Dois fatos que só o profile mostra:

1. **O matmul quantizado é só 24,4%.** Mais de 40% é elementwise. A intuição "otimizar int8"
   ataca um quarto do problema.
2. **`Log` e `Exp` têm exatamente 84 nós cada**, em `/encoder_embed/conv/{3,6,9}/`, ao lado de
   `Sub` e `Where`. É a ativação **Swoosh** do Zipformer: o export ONNX a expande no composto
   `logaddexp(0, x−c) − 0,08x − k` em vez de um kernel fundido.

## Evidência 2 — o modelo NÃO é streaming `[MEDIDO]`

Três confirmações independentes:

| fonte | evidência |
|---|---|
| metadado do artefato | `comment = "non-streaming zipformer2 CTC"` (carimbado pelo exportador k2-fsa) |
| grafo ONNX | entradas `x`, `x_lens`; saídas `log_probs`, `log_probs_len` — **nenhum tensor de estado** |
| scripts de treino | `jvscribe/finetune/run_ft_*.sh` nunca passam `--causal`; o default do icefall é `False` |

O encoder é **não-causal**: a atenção enxerga o contexto inteiro nos dois sentidos. O que
`jvscribe/realtime/` faz é **simular** streaming com janela deslizante + LocalAgreement-2
(técnica do Whisper-Streaming) sobre um modelo offline — cada hop reprocessa a janela toda.

### O custo dessa redundância `[MEDIDO]`

Forward por tamanho de entrada, mediana de 11 execuções após aquecimento:

| entrada | frames | ms | ms/frame |
|---|---|---|---|
| 0,5 s | 50 | 11,4 | 0,229 |
| 1,0 s | 100 | 16,4 | 0,164 |
| 2,0 s | 200 | 46,0 | 0,230 |
| 6,0 s | 600 | 121,1 | 0,202 |

O custo é **linear nos frames** (~0,2 ms/frame) — não há explosão quadrática de atenção
nestes comprimentos. Logo o desperdício é puro retrabalho:

> **121 ms** para reprocessar 6 s, contra **11 ms** que custaria processar só os 0,5 s novos
> → **10,6× de trabalho redundante por hop**.

Ressalva honesta: a razão real seria menor que 10,6×, porque entradas pequenas pagam overhead
fixo por chamada — note que 1,0 s custa 0,164 ms/frame contra 0,229 ms/frame de 0,5 s.

## Evidência 3 — as técnicas que o ROADMAP nomeia não se aplicam `[LITERATURA]`

O DoD do M6 lista *"FLToP e blank layer-skipping se CTC"*. Fui às fontes:

### FLToP CTC — `arXiv:2510.09085`

Reporta **10,5× de speedup e 2,78× menos memória**. Mas:

- o baseline é **beam search com beam=1000** (`Algorithm 1: Beam Search FLToP CTC Decoding`);
- o paper afirma que **não se aplica a greedy argmax** — "greedy decoding selects only the
  single highest-probability token per frame, making token pruning unnecessary";
- ele reduz a **busca do decoder**, não o forward do encoder. A premissa do paper é um regime
  em que "CTC decoding can account for as much as 90% of the processing time" — encoder em
  GPU, beam search em CPU.

**Nosso `ctc_output` custa 0,3%** e o decode é greedy (`argmax` do numpy). Por Amdahl, speedup
infinito de 0,3% rende ~0. **FLToP só passa a valer se migrarmos para beam search + LM** —
que é uma alavanca de WER listada no `CLAUDE.md`, não de latência.

### Blank layer-skipping — `arXiv:2305.11558` + recipe do icefall

O mecanismo, na descrição do recipe `zipformer_ctc_blankskip`: a saída do encoder calcula a
posterior CTC e, **para cada frame de saída**, descarta-se o frame se a posterior de blank
passar de um limiar. Isso acelera o que roda **depois** do encoder — o joiner do transducer,
que é executado por frame. O ganho reportado (4× vs transducer padrão) é nesse componente.

**Somos CTC puro** (`--use-transducer 0`): não há joiner. Descartar frames após o encoder não
devolve tempo de encoder, que já rodou.

Só o **Skipformer** (`arXiv:2403.08258`) economiza encoder de verdade — usa uma saída CTC
intermediária para dividir frames em cruciais/pulados/ignorados, e só os cruciais seguem para
os blocos seguintes. Reduz a sequência em 22× no LibriSpeech. Mas é **mudança de arquitetura
com retreino**, não otimização de runtime.

## Evidência 4 — o que foi aplicado e mediu ganho `[MEDIDO]`

Bootstrap **pareado** (round-robin entre configurações na mesma rodada, para a flutuação de
carga entrar igual nos dois lados), 25 repetições:

| mudança | delta pareado (IC95%) | veredito |
|---|---|---|
| arena ON + `inter_op=4` + `intra=8` | **−17,1%** [−36,9; −17,8] ms | conclusivo |
| arena ON sozinha | −6,7% [−18,3; −3,9] ms | conclusivo |
| batch dos 2 canais numa `run()` | −15,5% | **não soma** sobre o item 1 |
| `graph_optimization_level = BASIC` | **+6,6%** [+0,2; +20,8] ms | **piora** |

A varredura **sem** pareamento dava tudo inconclusivo (IQRs sobrepostos) e a primeira
varredura, com uma corrida por configuração, chegou a reportar 158,8 ms e 169,1 ms para duas
configurações **idênticas** — ruído de 35 ms, maior que vários dos efeitos.

Aplicado também o **cache incremental de fbank** (`FeatureCache`), que elimina reextrair a
janela toda a cada hop — 21,6% do custo de decode era esse retrabalho.

Ganho combinado, medido de ponta a ponta em `StreamingCTC.update()`:
**379,3 ms → 315,1 ms**, delta pareado **−55,1 ms** IC95% [−81,1; −30,2] → **−14,5%**.

## Conclusão

| alavanca | ganho | custo |
|---|---|---|
| **Treino causal + export com estado** | **~10,6×** de encoder por hop | retreino na GPU + reexport |
| Tuning de sessão ONNX | −17% de inferência | ✅ feito |
| Cache incremental de fbank | −21% do fbank | ✅ feito |
| Fusão da ativação Swoosh | até ~15% (Log+Exp+parte de Sub/Where) | kernel custom ou ORT mais novo |
| FLToP CTC | **~0%** | — não se aplica a greedy |
| Blank layer-skipping | **~0%** | — não há joiner em CTC puro |

**A única alavanca de ordem de grandeza é treinar com `--causal 1`.** E ela não custa
acurácia: `arXiv:2506.14434` — já citado no PRD — mostra um único Zipformer servindo os dois
modos via chunked attention masking com right-context dinâmico, com **−7,9% de WER relativo**.

Isso é trabalho de treino, não de runtime. O `m6-streaming-causal-blueprint.md` já previa;
o que está errado é a **lista de otimizações do DoD do M6**, que nomeia duas técnicas
inaplicáveis a este pipeline.

## Limitações

- **Máquina não quieta.** Load average entre 3 e 14 durante as medições. O pareamento cancela
  a componente comum, mas os valores absolutos não são de máquina ociosa.
- **`perf` indisponível**: `perf_event_paranoid = 4` bloqueia contadores de hardware sem root.
  Não há dado de cache miss, IPC ou stall — a atribuição de custo é por operador, não por
  causa microarquitetural.
- **Sem flamegraph do lado Python.** `py-spy` está instalado e não foi usado nesta rodada.
- Uma máquina, uma CPU. Nada aqui se transfere para o piso da frota BYOD (Q-01).

## Reprodução

```bash
# profile por operador
python3 - <<'EOF'
import onnxruntime as ort
so = ort.SessionOptions(); so.enable_profiling = True
# ... run() ...; p = sess.end_profiling()  -> JSON no formato chrome://tracing
EOF

# varredura de configuração com bootstrap pareado
python3 jvscribe/tools/runtime_bench.py --audio <wav> --janela 6 --reps 25

# soak com o modelo real
python3 jvscribe/tools/stress_test.py --audio-dir <wavs> --minutos 30
```

## Fontes

- FLToP CTC — <https://arxiv.org/abs/2510.09085>
- Blank-regularized CTC for Frame Skipping — <https://arxiv.org/abs/2305.11558>
- Skipformer — <https://arxiv.org/abs/2403.08258>
- Unifying Streaming and Non-streaming Zipformer — <https://arxiv.org/abs/2506.14434>
- Zipformer — <https://arxiv.org/abs/2310.11230>
- Recipe blank-skip do icefall — <https://icefall.readthedocs.io/en/latest/recipes/Non-streaming-ASR/librispeech/zipformer_ctc_blankskip.html>
- `sherpa-onnx` `[FONTE-REPO]`, commit `116a44e72c5b` — as citações são permalinks fixados,
  verificáveis por qualquer pessoa (o clone local de 51 MB foi removido em favor disto):
  sessão em [`csrc/session.cc:149,156`](https://github.com/k2-fsa/sherpa-onnx/blob/116a44e72c5b/sherpa-onnx/csrc/session.cc#L149);
  features incrementais em [`csrc/features.h:106,117,131`](https://github.com/k2-fsa/sherpa-onnx/blob/116a44e72c5b/sherpa-onnx/csrc/features.h#L106);
  estado do encoder streaming em
  [`csrc/online-zipformer2-transducer-model.h:32`](https://github.com/k2-fsa/sherpa-onnx/blob/116a44e72c5b/sherpa-onnx/csrc/online-zipformer2-transducer-model.h#L32).
  Contexto em `wiki/referencias/sherpa-onnx.md`
