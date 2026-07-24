# Blueprint: M1 — Régua de Medição ASR (harness, augmentação telefônica, test set, baseline)

> **Discovery cycle verdict:** SHIPPABLE (99.7/100 — research_coverage 100, reference_citations 100, blueprint_completeness 100, structural_risk 98; zero hard caps) — `knowledge-base/reviews/m1-measurement-harness-discover-confidence-2026-07-24.json`
> **Slug:** `m1-measurement-harness` · **Plan:** `knowledge-base/discoveries/plans/m1-measurement-harness-plan.md` · **Date:** 2026-07-24
> **Owner:** `evaluation-scientist` (lidera) · `audio-dsp-engineer` · `rust-runtime-engineer`

## Context

M1 é pré-requisito de M2 (`PRD.md` § 8.1 exige medição própria antes de travar arquitetura; `.claude/rules/asr-evidence-discipline.md` § 0 — discover contínuo). Este blueprint responde **como construir a régua** que torna a decisão de M2 defensável, investigando cinco peers clonados (`sherpa-onnx`, `parakeet-rs`, `icefall`, `lhotse`, `moonshine`) para os quatro entregáveis do DoD de M1 (`ROADMAP.md` § M1): harness dos 5 critérios de real-time, cadeia de augmentação telefônica 8 kHz, test set sem pseudo-label, e baseline de 3 modelos.

Descoberta-chave transversal: **nenhum peer implementa o que M1 exige de fato** — todos medem RTF de um arquivo curto (não sustentado, sem p99), reportam WER agregado (sem IC), e nenhum faz a cadeia G.711 completa. A régua de M1 é, portanto, majoritariamente **construção própria informada por padrões emprestáveis**, não adoção direta. Isso é consistente com o risco 1 do ROADMAP (significância) e as falácias § 3 (#3 média sem p99, #4 benchmark curto).

## Objective

Permitir decidir a arquitetura do harness de medição de M1 — o que construir em Rust vs orquestrar em script, como montar/validar a augmentação, como curar o test set sem violar LGPD, como medir o baseline de forma comparável — com evidência citável de cada peer.

## Coverage Corner 1 — Integration Tests

### lhotse — teste determinístico de resample/augmentação (Q4)

O padrão de teste que ancora o **teste da nossa cadeia de augmentação** e o determinismo exigido por `.claude/rules/testing.md` § 3:

- **Property-based com tolerância explícita.** `knowledge-base/references/lhotse/test/audio/test_resample_randomized.py:28-47` testa `resample` sobre a matriz de taxas {8000, 16000, 48000} × {8000, 16000, 48000} gerada por `hypothesis` (`st.just(...)`), e assere a invariante numérica com **tolerância de uma amostra**: `assert isclose(rec_rs.duration, rec.duration, abs_tol=1/target_sampling_rate)` (`test_resample_randomized.py:44`), além de shape (`num_channels`, `num_samples`) e preservação de id (`rec_rs.id == rec.id`, linha 42).
- **Energia preservada sob transformação.** `knowledge-base/references/lhotse/test/augmentation/test_torchaudio.py:130` usa `assert_array_almost_equal(rvb_energy, orig_energy)` (import `from numpy.testing import assert_array_almost_equal`, linha 8) — a asserção de augmentação não é "roda sem erro", é "a energia/forma bate dentro de tolerância numérica".
- **Parametrização de casos.** `@pytest.mark.parametrize("scale", [0.125, 1.0, 2.0])` (`test_torchaudio.py:139`) e shapes exatos esperados (`assert audio_perturbed.shape == audio_volume.shape`, linha 144).

**Como aplicar ao nosso harness:** a cadeia telefônica (Corner 4/Q3) deve ter teste determinístico com **fixture versionada → transform → asserção numérica com tolerância**, não "rodou sem panic". Edge case (`.claude/rules/testing.md` § 4.1): boundary = round-trip a-law de sinal de amplitude máxima (clipping); negative = taxa de origem inválida deve dar erro tipado. O invariante anti-pseudo-label do test set (`PRD.md` § 7.3) vira um teste: o loader do test set **rejeita** qualquer manifesto marcado como pseudo-label (fail-fast, `.claude/rules/error-handling.md` § 2).

## Coverage Corner 2 — Dependencies

### moonshine — deps reais de avaliação vs pyproject (Q5)

As dependências que **de fato** rodam uma avaliação de WER end-to-end estão nos imports do script de eval, não no manifesto:

- **`knowledge-base/references/moonshine/scripts/eval-librispeech.py:54-60`** importa: `numpy`, `soundfile` (leitura de áudio), `datasets.load_dataset` (corpus), **`jiwer.process_words`** (cálculo de WER — lib estabelecida, `.claude/rules/parsimony-ladder.md` rung 4: reusar antes de reimplementar), `scipy.signal.resample_poly` (resample), e **`whisper.normalizers.EnglishTextNormalizer`** (normalização de texto).
- **`knowledge-base/references/moonshine/python/pyproject.toml`** declara apenas `numpy, sounddevice, requests, tqdm, filelock, platformdirs` — as deps de **inferência** do runtime moonshine, **não** as de avaliação. Grep de `dependencies` no manifesto mente sobre o que a régua precisa (EC-2 do edge-case review).

**Rótulos de proveniência (`.claude/rules/asr-evidence-discipline.md` § 1):**

| Modelo do baseline | Fonte da dep/execução | Rótulo |
|---|---|---|
| Moonshine | `eval-librispeech.py` (padrão emprestável) + pyproject | `[LITERATURA]` — peer clonado |
| whisper-large-v3 | model card HuggingFace (`transformers`/`openai-whisper`) — **fora dos peers** | `[LITERATURA]` — a resolver no `/to-plan` |
| `alefiury/…-TAGARELA` | model card HuggingFace — **fora dos peers** | `[LITERATURA]` — a resolver no `/to-plan` |

**Conclusão de deps:** a régua de baseline reusa `jiwer` para WER (não reinventa), mas o normalizador de texto EN **não serve** para PT-BR — é componente próprio (EC-5). whisper-large-v3 e TAGARELA são `transformers`, deps derivadas do model card, não de peer.

## Coverage Corner 3 — Tools

### sherpa-onnx — knob de threads → runtime → afinidade de P-core (Q6)

A fixação de threads que sustenta `taskset` nos P-cores (RNF-06 ≤ 2 P-cores) e a medição sob carga (RNF-05):

- **API expõe `num_threads` como parâmetro de primeira classe.** `knowledge-base/references/sherpa-onnx/python-api-examples/offline-nemo-parakeet-decode-file.py:25` passa `num_threads=1` ao construtor do recognizer, junto de `provider="cpu"`.
- **O knob propaga direto ao config do runtime.** `knowledge-base/references/sherpa-onnx/sherpa-onnx/csrc/offline-diacritization-model-config.h:17` declara `int32_t num_threads = 1;` como campo do model-config, passado ao construtor (linhas 24-30) — ou seja, o número de threads intra-op do ONNX Runtime é escolha explícita do chamador, não default oculto.

**Como aplicar (RNF-05/06):** o nosso motor (backend ONNX provável) fixa `num_threads` = nº de P-cores do orçamento (≤ 2), e o processo inteiro é preso aos P-cores físicos com `taskset -c` (verificado disponível no ambiente). Para **carga concorrente** (RNF-05) sem `stress-ng` (ausente no ambiente), a alternativa reprodutível é gerar carga com o que existe: N processos `taskset`-presos aos E-cores rodando `yes > /dev/null` ou um loop de `openssl speed`/`ffmpeg` de transcodificação (simula softphone/Zoom consumindo CPU), medido **em paralelo** ao ASR nos P-cores. O ponto é a carga ser dimensionável e registrada, não a ferramenta específica.

## Coverage Corner 4 — Techniques

### RTF/RTFx sustentado + p99 — o que emprestar e o que falta (Q1)

Dois peers medem "RTF", **com definições inversas** — a primeira armadilha da régua:

- **sherpa (batch, N runs, sem warmup).** `knowledge-base/references/sherpa-onnx/cxx-api-examples/streaming-zipformer-rtf-cxx-api.cc:94-130`: mede `elapsed = steady_clock` por run, soma sobre `num_runs`, e reporta `rtf = total_elapsed/num_runs/duration` (linha 120). Aqui **RTF = tempo/áudio** (menor = mais rápido). Inclui o primeiro run frio na média (sem warmup) e processa o arquivo inteiro de uma vez.
- **parakeet (streaming real, single run).** `knowledge-base/references/parakeet-rs/examples/streaming.rs:139-146`: loop de chunks de 2560 amostras (160 ms), e reporta `RTF: duration/elapsed` (linha 144) — aqui **"RTF" = áudio/tempo** (maior = mais rápido), que é o nosso **RTFx**. Um único run, `Instant::now()`/`elapsed()`.

**Gap analysis contra RNF-01/02/04 (`PRD.md` § 6):**

| Requisito M1 | sherpa | parakeet | Lacuna a construir |
|---|---|---|---|
| RTFx = áudio/parede, maior=melhor (RNF-01 ≥ 3×) | inverso (RTF) | ✓ (chama de RTF) | **Fixar terminologia**: harness reporta RTFx = duration/wall, explícito |
| Sustentado ≥ 10 min (RNF-04, min30÷min1 ≥ 80%) | ✗ arquivo curto | ✗ single run | **Loop de ≥ 10 min** medindo RTFx por janela + razão min30/min1 |
| Latência p99 fim-da-fala→texto (RNF-02 ≤ 500 ms) | ✗ só média | ✗ só total | **Histograma de latência por chunk**, reportar p50/p95/**p99** |
| Warmup | ✗ (run frio na média) | ✗ | **Descartar N runs de warmup** antes de medir (turbo/cache frios mentem, falácia §3 #4) |

O `BacklogCounter` de M0 (`crates/macaw-audio/src/metrics.rs:51` — já com p50/p95/p99 via `backlog_percentiles`) é a base do RNF-03 e o padrão de percentil que o harness de latência reusa (DRY, `.claude/rules/parsimony-ladder.md` rung 4).

### WER com intervalo de confiança via bootstrap (Q2)

- **Cálculo canônico emprestável.** `knowledge-base/references/icefall/icefall/utils.py:686-730` — `write_error_stats(f, test_set_name, results, ...)` onde `results: List[Tuple[cut_id, ref, hyp]]` é **por-utterance** (docstring linhas 718-720). Conta insertions/deletions/substitutions via alinhamento e retorna WER. O padrão de saída (ins/del/sub sobre N palavras de referência) é o formato comparável com o TAGARELA (`PRD.md` § 7.3).
- **IC por bootstrap (técnica própria, `[LITERATURA]`).** Nenhum peer implementa IC (verificado — risco 1 do ROADMAP). Mas a estrutura **por-utterance** de `results` habilita bootstrap direto: reamostrar a lista de utterances **com reposição** B vezes (ex.: B=1000), recomputar WER a cada reamostragem, e reportar o percentil 2,5–97,5 como IC 95%. Insumo obrigatório: preservar o WER **por-segmento** (EC-3), não só o agregado corpus-wide que tanto icefall quanto moonshine (`eval-librispeech.py:20` — "WER is aggregated corpus-wide") reportam por padrão. Sem granularidade por-utterance o IC é impossível.

Isso ataca diretamente o risco 1 (20 min de áudio têm IC largo) — a régua **reporta o IC**, não esconde a cauda (falácia §3 #12).

### Cadeia de augmentação telefônica 8 kHz — o que é sox, o que é lhotse (Q3)

- **lhotse cobre só o resample.** `knowledge-base/references/lhotse/lhotse/augmentation/resample.py:126-175` — `resample()` faz reamostragem bandlimitada por sinc (torchaudio, `sinc_interp_hann`, `rolloff=0.99`, `lowpass_filter_width=6`). É **só** o passo 16k→8k; **não** tem filtro de banda telefônica (300-3400 Hz), **não** tem G.711 a-law, **não** tem babble/AGC.
- **sox faz a cadeia inteira, nativamente.** Verificado: `sox` suporta encoding `a-law` (`sox --help` → `-e a-law`), reamostragem, e filtro `sinc`/`highpass`/`lowpass` de banda. Como sox cobre resample + filtro + a-law num pipeline sem dependência torch, a conclusão KISS/Não-Reinvente (`.claude/rules/parsimony-ladder.md` rungs 2-4) é **fazer a cadeia em sox**, não trazer torch/lhotse só para o resample.

**Cadeia proposta (a validar na implementação, comando-a-comando):**

```
# 16k→8k + banda telefônica 300-3400 Hz + G.711 a-law round-trip
sox in_16k.wav -r 8000 tmp_8k.wav             # reamostra p/ 8 kHz
sox tmp_8k.wav band_8k.wav sinc 300-3400      # filtro de banda telefônica
sox band_8k.wav -e a-law alaw.wav             # codifica G.711 a-law
sox alaw.wav -e signed-integer -b 16 out.wav  # decodifica (round-trip)
```

babble/crosstalk (mistura de fala de fundo) e AGC (`compand`) são passos adicionais de sox, aplicados on-the-fly. Cada passo é `[MEDIDO]` quando rodado; a degradação introduzida pela própria cadeia deve ser medida (não assumida) — `audio-dsp-engineer` mede o WER do baseline com e sem cada estágio para isolar o custo do canal (fator 2-3× esperado, `PRD.md` § 7.1, rótulo `[LITERATURA]` até medirmos).

## Cross-cutting Comparison

| Dimensão | sherpa-onnx | parakeet-rs | icefall | lhotse | moonshine | O que a régua de M1 herda |
|---|---|---|---|---|---|---|
| Medição de tempo | RTF=t/áudio, N runs, sem warmup (`…rtf-cxx-api.cc:120`) | RTFx=áudio/t, single run, chunks reais (`streaming.rs:144`) | — | — | — | RTFx explícito + warmup + sustentação ≥10min + p99 (construir) |
| WER | — | — | por-utterance, ins/del/sub (`utils.py:686`) | — | corpus-wide via `jiwer` (`eval-…py:57`) | cálculo por-utterance + bootstrap IC (construir sobre icefall) |
| Augmentação 8 kHz | — | — | — | só resample sinc (`resample.py:126`) | `resample_poly` | cadeia G.711 completa em sox (construir) |
| Config de threads | `num_threads` 1ª classe (`…config.h:17`) | — | — | — | — | fixar `num_threads`=P-cores + `taskset` (herdar padrão) |
| Normalização de texto | — | — | — | — | EN (`eval-…py:60`) | normalizador PT-BR próprio (construir) |

## ADRs

### D1 — A régua é construção própria informada por padrões, não adoção de um peer

**Decisão:** Construir o harness de medição em Rust/script próprio, emprestando **padrões** (fórmula de RTF do sherpa/parakeet, estrutura por-utterance do icefall, tolerância de teste do lhotse, `num_threads` do sherpa) e **libs** (`jiwer` para WER, `sox` para augmentação), mas não adotando o pipeline de nenhum peer inteiro.

**Rationale:** Nenhum peer satisfaz os RNFs de M1 (sustentação ≥10min, p99, IC, cadeia G.711) — verificado por leitura direta. Adotar um peer inteiro traria sua stack (torch, python de treino) sem entregar o que M1 exige. Emprestar padrão + lib estabelecida respeita Não-Reinvente sem herdar complexidade (`.claude/rules/parsimony-ladder.md` rungs 2-5). Alternativa descartada: portar o `decode.py` do icefall inteiro (traria k2/torch, e ainda faltaria IC e sustentação).

**Consequences:** o harness é testável e enxuto, mas o IC, a sustentação, o p99 e o normalizador PT-BR são código novo com teste próprio (não há oráculo emprestado).

### D2 — Test set 8 kHz v1 é proxy de canal sobre corpus público, rotulado honestamente

**Decisão:** O test set v1 de "call center 8 kHz" é construído aplicando a cadeia de augmentação telefônica (D-Corner4/Q3) sobre **corpus público de fala espontânea PT-BR** (`PRD.md` § 7.3 — NURC, ALIP, C-ORAL, etc.), rotulado como **proxy de canal telefônico**, não como áudio real de atendimento.

**Rationale:** Áudio real de call center exige consentimento + trilho LGPD **fora de escopo** (`PRD.md` § 3.2; `ROADMAP.md` § M1 risco 2). O DoD pede 8 kHz curado sem pseudo-label — corpus público tem transcrição humana (não pseudo-label, respeita o invariante `PRD.md` § 7.3) e a augmentação dá o canal 8 kHz. A honestidade de rótulo (`.claude/rules/asr-evidence-discipline.md` § 2, falácia #6: WER público ≠ call center) é o que impede tratar o proxy como domínio real. Alternativa descartada: adiar M1 até obter áudio real (bloqueia M2 indefinidamente por dependência fora de escopo).

**Consequences:** o baseline de M1 mede o domínio **proxy**, com caveat explícito de que o gap proxy→call-center real (R4 do PRD) é medido depois, quando/se houver áudio consentido. A escolha final do corpus é do `/to-plan`, não desta descoberta (D3 do plano).

### D3 — Terminologia de RTFx fixada para evitar a inversão dos peers

**Decisão:** O harness reporta **RTFx = duração_do_áudio / tempo_de_parede** (maior = mais rápido, alvo ≥ 3× RNF-01 / ≥ 6× RNF-07), nunca "RTF" ambíguo.

**Rationale:** sherpa e parakeet chamam "RTF" a razões inversas (`…rtf-cxx-api.cc:120` vs `streaming.rs:144`) — copiar cegamente qualquer um introduz erro de fator. Fixar RTFx alinhado ao `PRD.md` § 6 elimina a ambiguidade na origem.

**Consequences:** todo relatório do harness usa RTFx; conversão de números de peers exige inverter quando a fonte reporta RTF.

## Recommendations for the project

1. **Harness em Rust, orquestração em script.** O laço de medição sustentada (RTFx por janela, p99 de latência, razão térmica min30/min1, backlog) roda em Rust reusando `BacklogCounter`/`DriftMeter` de M0 (`crates/macaw-audio/src/metrics.rs`). A augmentação (sox) e o baseline (jiwer + modelos HF) ficam em script Python/shell — cada um na ferramenta certa (`.claude/rules/architecture.md` § 3).
2. **WER com IC desde o primeiro número.** Implementar bootstrap sobre WER por-utterance (padrão icefall) e **nunca** reportar WER sem IC 95% (ataca risco 1; falácia §3 #12). `evaluation-scientist` valida o protocolo.
3. **Cadeia telefônica em sox, testada com tolerância.** Implementar os 4 estágios (resample/banda/a-law/round-trip) em sox, com teste determinístico estilo lhotse (fixture → transform → tolerância numérica) e medição do custo de cada estágio. `audio-dsp-engineer` mede.
4. **Baseline reusa `jiwer`, normalizador PT-BR é próprio.** Emprestar o fluxo de `eval-librispeech.py` (load → transcribe → normalize → jiwer) mas trocar `EnglishTextNormalizer` por um normalizador PT-BR (números por extenso, "R$", "pra/para", pontuação, acentos).
5. **Carga concorrente reprodutível sem stress-ng.** Documentar o gerador de carga (N processos presos aos E-cores) como parte do protocolo RNF-05, com o ASR preso aos P-cores via `taskset`.
6. **Test set proxy com rótulo honesto (D2).** Não chamar o test set v1 de "call center real"; rotular como proxy de canal e registrar o gap a medir depois.

## Blocked questions (if any)

Nenhuma. As 6 research questions foram respondidas com citação verificável a `knowledge-base/references/`. As fronteiras conhecidas (whisper-large-v3/TAGARELA deps via model card; normalizador PT-BR; corpus final do test set) são `[LITERATURA]`/decisões de `/to-plan` explicitamente registradas nos ADRs D1/D2 e no edge-case review (EC-4/EC-5), não bloqueios.

## Halt-loop progress (audit trail)

| Q | Corner | Peer + citação | Status |
|---|---|---|---|
| Q1 | Techniques | `sherpa-onnx/cxx-api-examples/streaming-zipformer-rtf-cxx-api.cc:94-130`, `parakeet-rs/examples/streaming.rs:139-146` | done |
| Q2 | Techniques | `icefall/icefall/utils.py:686-730` | done |
| Q3 | Techniques | `lhotse/lhotse/augmentation/resample.py:126-175` + sox | done |
| Q4 | Tests | `lhotse/test/audio/test_resample_randomized.py:28-47`, `lhotse/test/augmentation/test_torchaudio.py:130` | done |
| Q5 | Deps | `moonshine/scripts/eval-librispeech.py:54-60`, `moonshine/python/pyproject.toml` | done |
| Q6 | Tools | `sherpa-onnx/python-api-examples/offline-nemo-parakeet-decode-file.py:25`, `sherpa-onnx/sherpa-onnx/csrc/offline-diacritization-model-config.h:17` | done |

## Related

- Plano de descoberta: `knowledge-base/discoveries/plans/m1-measurement-harness-plan.md`
- Edge cases: `knowledge-base/reviews/m1-measurement-harness-edge-cases-2026-07-24.md`
- Âncoras: `PRD.md` § 6 (RNF), § 7 (WER/avaliação), § 3.2 (escopo LGPD); `ROADMAP.md` § M1
- Disciplina de evidência: `.claude/rules/asr-evidence-discipline.md`
- Base de M0 reusada: `crates/macaw-audio/src/metrics.rs`
