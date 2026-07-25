# Blueprint: M3 — Pipeline de corpus (pseudo-labeling + manifests Lhotse)

**Verdict:** SHIPPABLE (99,1 — `/discover-confidence`, zero hard caps)
**Slug:** `m3-corpus` · **Data:** 2026-07-25 · **Plano:** `knowledge-base/discoveries/plans/m3-corpus-plan.md` (SHIPPABLE 99,7)
**Executado por:** `speech-data-scientist` (Q3/Q5/Q7) · `audio-dsp-engineer` (Q1/Q2) · `general-purpose` (Q4/Q6/Q8) — 3 agentes em paralelo, disciplina de evidência `asr-evidence-discipline.md`.

## Context

M3 é o **risco dominante do projeto** (`ROADMAP.md` § M3; `CLAUDE.md` § "Contexto"): 8.972 h contra as 15.000–94.000 h que a receita de referência usa para modelos pequenos treinados do zero. O DoD exige quatro entregáveis: Q-09 (acesso ao Cem Mil Podcasts), pipeline de pseudo-labeling com filtro por concordância, manifests Lhotse com augmentação telefônica on-the-fly, e volume + licença de cada fonte com veredito comercial. Esta discovery investigou como construí-lo reusando o que já existe (parsimony rung 4) e expôs os riscos técnicos/legais antes de qualquer código.

**Decisão do dono do projeto (2026-07-25, registrada por Paulo):** o risco de licença dos datasets/repos — incluindo o **TAGARELA `CC-BY-NC-SA-4.0`** e a contradição TAGARELA-NC vs modelo-CC-BY — é **assumido explicitamente pelo dono**. Consequência: as 8.972 h de TAGARELA e o professor parakeet-TAGARELA ficam **liberados** como fonte/professor por decisão de negócio. O **fato** (TAGARELA é NC-SA) permanece registrado abaixo (`[LITERATURA]`) por honestidade e para o audit trail — o que muda é a postura de risco, não a proveniência do fato.

## Objective

Permitir **decidir o desenho do pipeline de corpus de M3** — como gerar pseudo-labels filtrados por concordância e servir augmentação telefônica on-the-fly via manifests — com viabilidade de dependências resolvida e licenças mapeadas. Sucesso: `/discover-confidence` ≥ SHIPPABLE_WITH_CAVEATS, cada corner com ≥ 1 proposta de decisão concreta.

## Coverage Corner 1 — Integration Tests

**Q8 — como o lhotse testa cuts/augmentação on-the-fly (padrão a replicar em M3):**

Padrão `[FONTE-REPO]` (`knowledge-base/references/lhotse/test/dataset/test_cut_transforms.py`, `test/augmentation/test_clipping.py`):
- **Fixture determinística:** `DummyManifest(CutSet, ..., with_data=True)` (nível cut) ou sinal analítico numpy — `mono_sine_wave`: seno 1000 Hz/16k (`test_clipping.py:7-13`) — para testar a cadeia DSP em isolamento.
- **Determinismo (`testing.md § 3`):** RNG sempre injetado e semeado — `random.Random(42)`/`seed=0` (`test_cut_transforms.py:30,53,79,282`), nunca RNG global. `TestTransformStateDictRoundTrip` (`:362-395`) é o gabarito para reprodutibilidade de estado (RNG round-trip bit-a-bit).
- **Asserção on-the-fly (EC-4):** replicar `test_lowpass_using_resampling` (`:277-298`) — assertar que o transform foi **anexado a `cut.recording.transforms`** (registro lazy, sem materializar) e só materializa em `cut.load_audio()`.
- **Oráculo por invariante DSP (não golden file):** duração preservada; energia acima de ~3400 Hz cai após downsample 8k; a-law idempotente sobre silêncio — com tolerância explícita (`isclose(..., abs_tol=...)`), robusto a versão de sox/scipy.

**Proposta M3:** testar o `TelephoneChannel` transform com (a) unit sobre seno analítico (invariantes DSP com tolerância) + (b) integração sobre `DummyManifest with_data=True` provando laziness via `recording.transforms`. RNG semeado onde houver aleatoriedade.

## Coverage Corner 2 — Dependencies

**Q4 — lhotse exige torch? `[FONTE-REPO]`: sim, para `import lhotse`.** `setup.py:160` lista `"torch"` em `install_requires` sem guarda; `lhotse/audio/backend.py:15` e `lhotse/cut/set.py:31` fazem `import torch` no topo, ambos na cadeia disparada por `lhotse/__init__.py:1,22`. Não há subconjunto importável sem torch. Caminhos (ADR D4 do plano): **(a) torch CPU-only** (~170-200 MB, `download.pytorch.org/whl/cpu`, sem CUDA) `[LITERATURA]` — reusa lhotse integralmente; **(b) manifests JSONL próprios** (schema `supervision.py:212-216`: `recording_id/start/duration/text`) + augmentação callable, sem lhotse (rung 6, só se (a) inviável).

**Q5 — licença de cada fonte + Q-09:**

| Fonte | Licença | Comercial | Rótulo |
|---|---|---|---|
| **FLEURS** (pt_br) | CC-BY-4.0 | **Sim** (atribuição) | `[FONTE-REPO]` card local `datasets--google--fleurs/.../README.md:113,17129` |
| **MLS-PT** (~161 h) | CC-BY-4.0 | **Sim** | `[LITERATURA]` HF card |
| **Common Voice (pt)** | CC0-1.0 | **Sim** — migrou p/ Mozilla Data Collective (out/2025), re-verificar | `[LITERATURA]` |
| **parakeet-TAGARELA (modelo)** | CC-BY-4.0 (card) | card diz sim | `[LITERATURA]` |
| **TAGARELA (dataset, 8.972 h)** | **CC-BY-NC-SA-4.0** | **NÃO — non-commercial** | `[LITERATURA]` `huggingface.co/datasets/freds0/TAGARELA` |
| **Cem Mil Podcasts** (Spotify, 76k h) | research-only (sem licença comercial pública) | **NÃO confirmável** | `[DESCONHECIDO]` (Q-09) |

**Fato registrado (§ 1 honestidade):** o dataset TAGARELA é NC-SA; um modelo fine-tuned nele pode ser obra derivada NC-SA, apesar de o card do modelo declarar CC-BY-4.0. **Postura de risco (decisão do dono, § Context):** risco **assumido** — TAGARELA e parakeet-TAGARELA liberados. O rótulo NC permanece no registro; a decisão é de negócio, não de engenharia.

**Q-09 (`[DESCONHECIDO]`):** Cem Mil Podcasts (Spotify Research, arXiv:2209.11871) = 123.054 episódios / >76.000 h PT, "released for academic research purposes"; a página não detalha licença comercial nem processo de acesso. Falta negociação humana (`technical-program-lead`): contatar Spotify Research, obter o data license agreement. **Acesso ao bruto não confirmável autonomamente**; a fatia pública (TAGARELA, 8.972 h ≈ 12%) está disponível e, com o risco assumido, utilizável.

## Coverage Corner 3 — Tools

**Q6 — lhotse constrói manifests de um diretório `[FONTE-REPO]`:**
```
RecordingSet.from_dir("/data/wavs", pattern="*.wav", num_jobs=4)   # recording_set.py:110 (rglob + Recording.from_file)
SupervisionSet.from_segments(                                       # supervision.py:539
    SupervisionSegment(id=..., recording_id=r.id, start=0.0,        # :212-214
                       duration=r.duration, text=pseudo_label[r.id])# :216 <- transcrição
    for r in recs)
CutSet.from_manifests(recordings=recs, supervisions=sups)           # cut/set.py:378 (docstring :116-121)
```
O texto do pseudo-label entra **exclusivamente** em `SupervisionSegment.text`. CLI equivalente existe (`setup.py:225`). Caveat: exige `import lhotse` → torch (Q4).

**Q7 — os 2 transcritores:**
- **#1 faster-whisper — VIÁVEL `[MEDIDO]`/`[FONTE-REPO]`:** `faster-whisper 1.2.1` (MIT), em cache (tiny..large-v3), provado em M1. Comando em `scripts/baseline_fleurs_ptbr.py:81,84,86` (`WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=1)` + `del model` sequencial — atende EC-3 RAM).
- **#2 parakeet-TAGARELA via sherpa-onnx — bloqueio TÉCNICO (não legal):** (1) cache só tem `encoder-model.onnx.data` de 2,4 GB `[FONTE-REPO]`, faltam grafo/decoder/joiner/tokens que `from_transducer` exige (`offline_recognizer.py:104-133`); (2) export p/ `onnx-asr`, não a tríade sherpa `[LITERATURA]`; (3) 2,4 GB não cabem em 566 MiB livres + swap cheio → OOM `[ESTIMATIVA]`. Habilitar = download completo + `onnx-asr`/tríade int8 + RAM. Com a licença liberada (§ Context), resta só o trabalho técnico.

## Coverage Corner 4 — Techniques

**Q1 — augmentação on-the-fly do lhotse (lazy de verdade?):** dois pilares `[FONTE-REPO]`. **`Recording.transforms`** — anexado lazily (`recording.py:701-724`), executado só em `load_audio()` (`recording.py:451,469-471`); base em `augmentation/transform.py:9-16`. **`cut_transforms`** — callables `CutSet→CutSet` por batch (`speech_recognition.py:108-109`), sob `CutSet.map` que preserva laziness (`cut/set.py:1084-1092`). **Restrição EC-4:** o default `input_strategy=PrecomputedFeatures()` (`speech_recognition.py:61-67`) lê features de disco e **derrota** a perturbação (`cut/data.py:815-821`) — M3 DEVE usar `AudioSamples()`/`OnTheFlyFeatures()` (`input_strategies.py:208-299,351+`).

**Q2 — cadeia telefônica como transform on-the-fly:** o `Narrowband` nativo NÃO serve `[FONTE-REPO]` (`torchaudio.py:331-378`) — sem A-law (só µ-law/lpc10), depende de torchaudio, sem banda 300-3400. A cadeia sox-CLI de M1 (`scripts/telephone_augment.sh:45-49`) usa tempfile por batch (viola "nunca em disco"). **Proposta (rung 4):** reimplementar em memória como `input_transform` — `scipy.signal.resample_poly(x,1,2)` (16k→8k, mesmo padrão do fallback lhotse `torchaudio.py:129-139`) + `scipy.signal.butter([300,3400],'band',fs=8000)`+`sosfilt` (banda) + `audioop.lin2alaw`/`alaw2lin` (A-law, stdlib, `[MEDIDO]` resolve em 3.10). Caveat: `audioop` deprecado PEP 594 → import guardado fail-fast + `audioop-lts` se o interpretador subir.

**Q3 — filtro por concordância entre 2 transcritores:** mecânica `[FONTE-REPO]` = predicado `Cut→bool` via `CutSet.filter(...)` (idêntico a `icefall/egs/librispeech/ASR/local/filter_cuts.py:64-124`). Métrica `[ESTIMATIVA]`: **CER par-a-par** entre hyp#1 e hyp#2 (menos sensível a fronteira de palavra que WER). Threshold τ — **NÃO inventar** `[FONTE-REPO]` (`filter_cuts.py:76-78` instrui calibrar pela distribuição empírica); τ `[DESCONHECIDO]` até medir num piloto. Granary threshold `[DESCONHECIDO]` (allowlist web vazio, EC-1); "≈50% do volume" (ROADMAP) é hipótese a testar (ΔWER com/sem filtro), não premissa. **Invariante § 3 #10:** filtro só no pool treino/val, nunca no test set.

## Cross-cutting Comparison

| Dimensão | lhotse | icefall | faster-whisper | parakeet-TAGARELA |
|---|---|---|---|---|
| Papel em M3 | manifests + augmentação on-the-fly | padrão de filtro (`filter_cuts`) | transcritor #1 (viável) | transcritor #2 (bloqueio técnico) |
| Dep pesada | **torch obrigatório** (Q4) | — (lhotse) | MIT, em cache | 2,4 GB, export onnx-asr |
| Cobre a cadeia telefônica? | Narrowband **não** (sem A-law/banda) | — | — | — |
| Licença | Apache-2.0 | Apache-2.0 | MIT | CC-BY-4.0 (dataset NC-SA — risco assumido) |
| Viabilidade RAM | leitura (não roda) | leitura | ✅ sequencial | ❌ OOM (2,4 GB) |

**Divergência registrada (valor, não dissolver):** `general-purpose` (leitura) sugeriu `Recording.narrowband` nativo como "bônus — transform telefônico lazy" (`recording.py:766`); `audio-dsp-engineer` (análise DSP) provou que **não** cobre o requisito de M1 — sem A-law, sem banda, exige torchaudio (`torchaudio.py:331-356`). **A análise DSP profunda vence** → D1 usa scipy+audioop. A leitura superficial teria levado a reuso incorreto.

## ADRs

### D1 — Augmentação telefônica on-the-fly via `input_transform` scipy+audioop

**Decisão:** implementar a cadeia (16k→8k + banda 300-3400 + A-law) em memória com `scipy.signal` + `audioop`, como `input_transform` do `K2SpeechRecognitionDataset` com `input_strategy=AudioSamples()`.

**Rationale:** o `Narrowband` nativo não tem A-law/banda e exige torchaudio (Q2 `[FONTE-REPO]`); a cadeia sox-CLI usa tempfile por batch. scipy/audioop já disponíveis e o lhotse os usa no fallback (rung 4). **Alternativas descartadas:** Narrowband nativo (não cobre A-law/banda); sox pipe subprocess (spawn por batch); sox-CLI-com-arquivo (materializa em disco).

**Consequências:** `audioop` deprecado → import guardado fail-fast + `audioop-lts`. `input_strategy` ≠ default `PrecomputedFeatures`.

### D2 — Filtro por concordância = predicado `CutSet.filter` com CER par-a-par, threshold empírico

**Decisão:** predicado `Cut→bool` (padrão `filter_cuts.py:124`) que descarta cuts com CER(hyp1,hyp2) > τ; τ calibrado pela distribuição empírica de CER num piloto, não a priori.

**Rationale:** o peer icefall instrui calibrar threshold pela distribuição (`filter_cuts.py:76-78` `[FONTE-REPO]`); inventar τ violaria `asr-evidence-discipline § 1`. **Alternativa descartada:** threshold Granary hardcoded (`[DESCONHECIDO]`, e o peer desaconselha hardcode).

**Consequências:** M3 mede a distribuição de CER par-a-par (dado real) antes de fixar τ; "50% do volume" vira hipótese. Invariante § 3 #10: só no pool de treino.

### D3 — Dois whisper distintos como transcritores (parakeet-TAGARELA diferido por RAM)

**Decisão:** o filtro usa dois modelos whisper de tamanhos/decodificações distintas (ex.: `small` + `medium`), carregados **sequencialmente** (EC-3 RAM). Habilitar parakeet-TAGARELA (arquitetura distinta, melhor sinal) é backlog técnico.

**Rationale:** parakeet não roda hoje (Q7, bloqueio técnico `[FONTE-REPO]` — cache/export/RAM; a licença já não é obstáculo por decisão do dono); faster-whisper é MIT/em-cache/provado. **Caveat honesto:** whispers parentes correlacionam erros → a concordância superestima confiança; arquitetura distinta melhora o sinal quando habilitada. **Alternativa descartada:** bloquear M3 até habilitar parakeet (desperdiça o caminho viável; RAM não comporta 2,4 GB).

**Consequências:** concordância real medível hoje; qualidade do sinal melhora quando o parakeet (ou outro modelo de arquitetura distinta em int8) for habilitado.

### D4 — Corpus utilizável (com risco de licença assumido pelo dono)

**Decisão:** o corpus de M3 usa as fontes disponíveis — FLEURS (CC-BY) + MLS-PT (CC-BY) + Common Voice (CC0, re-verificar) + **TAGARELA 8.972 h (NC-SA, risco assumido pelo dono, § Context)**. Volume final e tabela de licenças declarados com o rótulo de cada fonte preservado.

**Rationale:** `asr-evidence-discipline § 1` exige que o rótulo NC de TAGARELA apareça no registro mesmo com o risco assumido — o fato não muda, a postura sim. A decisão de assumir o risco é do dono (registrada), não uma inferência de engenharia. **Alternativa descartada:** excluir TAGARELA e ficar só com fontes CC — foi rejeitada pela decisão do dono, que prioriza o volume (o risco dominante do projeto é justamente falta de dados).

**Consequências:** as 8.972 h ficam utilizáveis; o risco dominante do corpus é atacado com o maior volume disponível. Q-09 (Cem Mil Podcasts) segue como upside a negociar. PRD/ROADMAP a atualizar para registrar tanto o rótulo NC quanto a decisão de risco assumido.

## Recommendations

Para o `/to-plan` de M3 (uma proposta concreta por questão):

1. **Manifests (Q4/Q6):** instalar **torch CPU-only** (~170-200 MB) e reusar lhotse integralmente (rung 4) — evita reimplementar RecordingSet/SupervisionSet/CutSet. Fallback JSONL próprio só se a instalação falhar.
2. **Augmentação (Q1/Q2):** `TelephoneChannel` como `input_transform` (scipy resample+butter + audioop a-law), com `input_strategy=AudioSamples()`; import guardado fail-fast para `audioop`/`audioop-lts`.
3. **Pseudo-labeling (Q3/Q7):** dois whisper distintos (small+medium), sequenciais; predicado `CutSet.filter` com CER par-a-par; **medir a distribuição de CER** num piloto real antes de fixar τ.
4. **Licenças/volume (Q5):** declarar a tabela de licenças com rótulos + a decisão de risco assumido; re-verificar Common Voice (Data Collective); registrar Q-09 como upside negociável.
5. **Testes (Q8):** unit sobre seno analítico (invariantes DSP com tolerância) + integração provando laziness via `recording.transforms`; RNG semeado.

## Blocked / pendências abertas (semente da implementação)

- **τ do filtro de concordância** — `[DESCONHECIDO]` até medir a distribuição de CER num piloto (D2).
- **Threshold/receita Granary** — `[DESCONHECIDO]`, allowlist web vazio (EC-1).
- **Common Voice pt na Mozilla Data Collective** — termos a re-verificar.
- **Q-09 acesso ao Cem Mil Podcasts bruto** — negociação humana (`technical-program-lead`), upside.
- **`audioop` deprecação** — confirmar `audioop-lts`/versão de remoção antes de travar a dep.
- **parakeet-TAGARELA como 2º transcritor de arquitetura distinta** — backlog técnico (download completo + int8 + RAM); licença já não é obstáculo.

## Referências (todas resolvem em disco / URL)

- Plano: `knowledge-base/discoveries/plans/m3-corpus-plan.md`
- lhotse on-the-fly: `knowledge-base/references/lhotse/lhotse/audio/recording.py:451,469-471,701-724`; `lhotse/lhotse/dataset/speech_recognition.py:108-109,130-134`; `lhotse/lhotse/cut/set.py:1084-1092`
- lhotse Narrowband/Resample: `knowledge-base/references/lhotse/lhotse/augmentation/torchaudio.py:129-139,331-378`
- lhotse manifests: `knowledge-base/references/lhotse/lhotse/audio/recording_set.py:110`; `lhotse/lhotse/supervision.py:212-216,539`; `lhotse/lhotse/cut/set.py:378`
- lhotse torch dep: `knowledge-base/references/lhotse/setup.py:160`; `lhotse/lhotse/audio/backend.py:15`
- lhotse tests: `knowledge-base/references/lhotse/test/dataset/test_cut_transforms.py:277-298,362-395`; `lhotse/test/augmentation/test_clipping.py:7-13`
- filtro (icefall): `knowledge-base/references/icefall/egs/librispeech/ASR/local/filter_cuts.py:64-124`
- sherpa API: `knowledge-base/references/sherpa-onnx/sherpa-onnx/python/sherpa_onnx/offline_recognizer.py:104-133`
- faster-whisper (M1): `scripts/baseline_fleurs_ptbr.py:81,84,86`
- cadeia telefônica (M1): `scripts/telephone_augment.sh:45-49`
- licenças locais: `~/.cache/huggingface/hub/datasets--google--fleurs/.../README.md:113,17129`
- Cem Mil Podcasts: arXiv:2209.11871 · TAGARELA: `huggingface.co/datasets/freds0/TAGARELA`
