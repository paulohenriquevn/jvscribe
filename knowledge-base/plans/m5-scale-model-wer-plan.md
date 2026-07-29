---
slug: m5-scale-model-wer
milestone_id: M5
created_at: 2026-07-28
goal: Fine-tunar o Zipformer-CTC medium+fonema em CORAA com augmentação telefônica e medir o WER de fala espontânea no test CORAA (wideband + telefônico-simulado) com IC bootstrap pareado vs o baseline M4.
---

# Plan: M5 — Fine-tune para WER em fala espontânea PT-BR

## Goal

Fine-tunar o Zipformer-CTC medium+fonema (M4) no CORAA com augmentação `Reverb→Ruído→Telefone`
on-the-fly e **medir o WER de fala espontânea** no test CORAA (wideband + telefônico-simulado), com IC
bootstrap pareado vs o baseline M4 — **métrica observável: WER% no test CORAA + IC do delta** (arquivo
de recogs + `bootstrap_wer_ci.py`).

## Context

M4 fechou o finalista **Zipformer-CTC medium (64M) + fonema** (27,46% WER CPU, **wideband FLEURS = fala
LIDA** `[MEDIDO]`). M5 (`ROADMAP.md:220-238`) exige treino em escala + **fine-tune em label HUMANA** (o
único estágio que supera o teto do professor) + **WER ≤25% em call center 8 kHz** + quantizar/exportar.
O gap dominante é **READ→ESPONTÂNEO**. Corpus de fine-tune (D4, dono 2026-07-28): **mux único CORAA-v1.1
(~273h humano) + TAGARELA (~500h pseudo-Whisper), pesado ~1:1** via `--use-mux` — um run, otimizando GPU;
o dono assume o risco de licença e trouxe evidência de que TAGARELA gera modelo espontâneo forte
(Parakeet-TDT+TAGARELA: 10-21% WER espontâneo humano). **Test sempre no CORAA humano** (pseudo nunca no
test). O **como técnico** foi travado pelo blueprint `m5-scale-model-wer-blueprint.md`
(`/discover-confidence` SHIPPABLE): fine-tune por `do_finetune` (não resume) + `--use-mux`, augmentação
por lista `cut_transforms`. Este plano executa esse recipe.

**Honestidade sobre a DoD #3 (WER ≤25% call center 8 kHz REAL):** não há test set de call center 8 kHz
real (depende de dado do dono — `PRD.md` Q-01/§7.1). O proxy honesto e mensurável **hoje** é
**CORAA-espontâneo (wideband) + o mesmo CORAA passado pelo canal telefônico simulado de M3**. A meta
≤25% é aferida contra o proxy; o número em 8 kHz real fica como dependência de dado externo, marcada em
`## Unresolved Questions`. Não travar/ocultar essa distinção é a Regra 3 + falácia §3 #6 do
`asr-evidence-discipline.md`.

## Baseline Context

### Files that will be touched

| Arquivo | LoC | git sha | Papel hoje |
|---|---|---|---|
| `training/prep_phoneme_head.py` | 481 | 6c06c83 | Patch determinístico que injeta a cabeça de fonema em `zipformer.py`/`model.py`/`train.py` do icefall (assert count==1). **Molde** para o patch `do_finetune`. |
| `scripts/corpus/telephone_channel.py` | — | 19139cb | Canal telefônico M3 (banda 300-3400 Hz + G.711) — callable a empilhar em `cut_transforms`. |
| `training/make_telephone_test.py` | — | 535184b | Builder do test telefônico-simulado (usado em M4). **Molde** para o test CORAA telefônico. |
| `training/scripts/cer_from_recogs.py` | 91 | 535184b | WER+CER a partir de recogs. Reusar. |
| `training/scripts/bootstrap_wer_ci.py` | 109 | 535184b | IC bootstrap pareado (seed=42, B=10000). Reusar. |
| `training/scripts/eval_runtime_wer.py` | 127 | 535184b | Eval do runtime int8 em CPU. Reusar p/ o modelo M5. |
| `training/prep_finetune.py` | (NEW) | — | Patch que porta `add_finetune_arguments`+`load_model_params`+bloco `do_finetune` para o `zipformer/train.py` do icefall. |
| `training/prep_augment_datamodule.py` | (NEW) | — | Patch que anexa `[Reverb, telephone_channel]` à lista `cut_transforms` do `asr_datamodule.py`. |
| `training/make_telephone_test.py` | 76 | 535184b | **REUSADO** p/ o test telefônico do CORAA (lê `cv-pt_cuts_{split}`, preserva IDs) — Task 3.1 não cria script novo (YAGNI). |

### Current callers / dependents

- `prep_phoneme_head.py` é chamado no runbook de treino da instância (não importado por outro módulo do
  repo — é um script CLI). `grep -rl prep_phoneme_head --include=*.py` → só docs/runbooks.
- `telephone_channel.py`: importado por `scripts/corpus/run_pipeline.py` e testado por
  `scripts/tests/test_corpus_telephone.py`.
- `bootstrap_wer_ci.py`/`cer_from_recogs.py`: scripts CLI, sem importadores (chamados na reprodução).

### Domain glossary

- **do_finetune** — mecanismo icefall: carrega só pesos selecionados do base ckpt (`init_modules`) +
  otimizador fresco com LR baixo. ≠ resume (que restaura otimizador/scheduler).
- **cut_transforms** — lista de callables `CutSet→CutSet` aplicada on-the-fly no datamodule, em ordem.
- **CORAA** — corpus PT-BR ~290h de fala espontânea humana-validada (ALIP, NURC, SP2010, TEDx…).
- **proxy telefônico** — CORAA wideband passado por `telephone_channel.py` (8 kHz + G.711) como stand-in
  do call center real.

### Architecture boundaries affected

O treino roda na **instância vast.ai** com o `icefall` clonado (o `zipformer/train.py` e o
`asr_datamodule.py` NÃO estão neste repo — são material de referência read-only em
`knowledge-base/references/`). O código in-repo são **patches determinísticos** (estilo
`prep_phoneme_head.py`) aplicados ao icefall na instância + scripts de eval. `architecture.md` Regra 9:
reusar o mecanismo do icefall (não reimplementar treino).

## Dependencies

Nenhuma dependência Python NOVA — M5 reusa a stack já presente (Regra 9):

| Dependência | Versão | Papel | Nova? |
|---|---|---|---|
| `lhotse` | já instalada (instância + `scripts/corpus`) | `CutMix`/`ReverbWithImpulseResponse`/manifests | não |
| `torchaudio` | já instalada | convolução do RIR (`cut.reverb_rir`) | não |
| `icefall` (clone na instância) | já presente | `zipformer/train.py` + `asr_datamodule.py` | não |
| `unrar` / `unar` | sistema (instância) | extrair o RAR multipart do train CORAA | tool de sistema, não pacote Python — sem CVE de supply-chain Python |

Sem CVE a auditar em pacote Python novo. `unrar` é ferramenta de sistema instalada na instância de
treino (não entra no runtime de produção `macaw-*`).

## Prior Art & Related Work

- **Blueprint** `knowledge-base/discoveries/blueprints/m5-scale-model-wer-blueprint.md` (SHIPPABLE) — a
  fonte primária: mecanismo `do_finetune`, `load_model_params`/`init_modules`, ordem de augmentação,
  datasets MUSAN/RIR, invariantes de teste. ADR D1 (fine-tune≠resume) e D2 (ordem física) deste plano
  derivam dele.
- **`training/prep_phoneme_head.py`** (M4) — o padrão de patch determinístico com teste de fixture que
  espelhamos em `prep_finetune.py`.
- **`training/make_telephone_test.py`** (M4) — o builder de test telefônico que espelhamos p/ CORAA.
- **icefall** `egs/wenetspeech/KWS/zipformer/finetune.py` (zipformer+CTC, `use_ctc`) — o recipe fonte.
- Memória `m4-icefall-training-gotchas` (OMP=1 no fbank, avg degenera não-convergido, lang-dir completo)
  e `vastai-disk-full-kills-training` (poda proativa de checkpoints).
- **Evidência do dono (D4)** `[LITERATURA]` — `alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA` (HF): um
  Parakeet-TDT 0.6B adaptado com TAGARELA mede **10,4-21,3% WER em fala espontânea humana** (SP2010
  10,4% · MuPe 12,0% · C-ORAL 13,7% · NURC-Recife 13,8% · NURC-SP 16,0% · ALIP 21,3%). Prova que o alvo
  ≤25% é alcançável e que TAGARELA é dado espontâneo útil — porém em **600M** (9× o nosso 64M), logo
  limite superior, não o número do nosso tamanho. `training/prep_coraa.py` + `test_prep_coraa.py` +
  `coraa_speaker_overlap.py` (M5, entregues 2026-07-28) — prep do CORAA reusando `normalize_ptbr`+`Fbank`.

## ADRs

### D1 — Fine-tune por `do_finetune` (otimizador fresco + LR baixo), não resume

**Decisão:** patch `prep_finetune.py` porta `add_finetune_arguments`+`load_model_params`+bloco
`do_finetune` para `zipformer/train.py`; fine-tunar com `--init-modules "encoder,ctc_output"`,
`--base-lr 1e-4`, schedule achatado.
**Alternativa rejeitada:** resume via `--start-epoch` — restaura otimizador/scheduler (continua a curva
de LR do treino original), semântica errada para corpus novo (blueprint Q2, caminho B).
**Rationale:** Regra 9 (reusar o mecanismo maduro do icefall); o `KWS/zipformer/finetune.py` já casa
zipformer+CTC. Patch determinístico e testável (molde `prep_phoneme_head.py`).

### D2 — Augmentação como lista `cut_transforms` na ordem Reverb→Ruído→Telefone

**Decisão:** patch `prep_augment_datamodule.py` anexa `[ReverbWithImpulseResponse(rir), CutMix(musan,
snr=(10,20)), telephone_channel]` à lista `cut_transforms`, com `p<1` por transform.
**Alternativa rejeitada:** filtro telefônico primeiro (fisicamente incorreto — ruído/reverb
band-limitados); augmentação offline (perde variabilidade + infla disco — `vastai-disk-full-kills`).
**Rationale:** cadeia de sinal física (sala→ruído→codec); blueprint D2.
**Restrição crítica (EC-P1):** a augmentação de canal modifica **áudio**, então o fine-tune augmentado
**exige `--on-the-fly-feats True`** (`OnTheFlyFeatures(Fbank(...))`, `asr_datamodule.py:299`) sobre cuts
CORAA-train que **retêm o `Recording` (wav)** — as `feats_train/` pré-computadas produzem fbank limpo e
anulam a augmentação (só servem a um baseline sem-aug).

### D4 — Fine-tune por mux único CORAA (humano) + TAGARELA (pseudo), pesado ~1:1

**Decisão (revisada 2026-07-28 por evidência do dono):** o fine-tune de M5 usa um **mux único** de
**CORAA-v1.1 full (~273h train, humano)** + **TAGARELA (~500h podcasts, pseudo-rotulado Whisper)**,
via `--use-mux` do icefall, **pesado ~1:1** (upsample do CORAA para o pseudo não afogar o sinal humano
que quebra o teto — DoD #2). Um run só, otimizando GPU. Licença: **o dono assume o risco**
(CC-BY-NC-ND do CORAA + o que se aplicar ao TAGARELA).
**Guarda-corpo não-negociável:** o **test é SEMPRE o CORAA humano** (pseudo-label NUNCA entra no test —
invariante §7.3 / falácia §3 #10); augmentação telefônica por cima (alvo 8 kHz); WER rotulado `[MEDIDO]`.

**Números medidos (2026-07-28) — o desbalanço é maior que o plano assumia:** CORAA train =
**171,45h** (306.613 cuts, humano); TAGARELA train = **1110,62h** (429.885 cuts, pseudo). Razão real
**6,5:1 pseudo:humano** (não 1,8:1). Config do mux **(B) 3:1 pseudo:humano — escolha do dono 2026-07-28** ("TAGARELA é um ótimo dataset",
lastro na evidência Parakeet+TAGARELA 10-21% espontâneo): `CutSet.mux([coraa, tagarela],
weights=[0.25, 0.75])` — cada batch ~25% humano / 75% pseudo. Aposta forte no TAGARELA no TREINO,
mantendo 25% de sinal humano. **Guarda-corpo científico inegociável:** o **test permanece 100% CORAA
humano** — o WER mede generalização a fala humana e, se o TAGARELA-pesado ganhar, valida a aposta por
DADO. `[MEDIDO]` `resume_tagarela_feats.py` (reconstruiu do wav existente, `assert kept==429885` passou;
OMP=1 destravou o deadlock de fbank — lição m4-icefall-training-gotchas). Proporção natural (6,5:1,
`weights=[0.13, 0.87]`) fica como ablação se (B) render bem.
**Por que o mux (não CORAA-only nem 2 estágios):** o dono priorizou **tempo de GPU** (um run) e trouxe
evidência `[LITERATURA]` de que TAGARELA produz modelo espontâneo forte —
`alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA` mede **10,4-21,3% WER** em benchmark espontâneo humano
(SP2010 10,4% · NURC-Recife 13,8% · ALIP 21,3%), dando margem confortável ao alvo ≤25% e a **melhor
evidência até agora de que o alvo é alcançável**.
**Alternativa rejeitada — CORAA-only:** ~2× menos GPU/época, mas `[DESCONHECIDO]` se 273h humanas bastam
ao alvo; o dono optou por incluir o dado provado num run só. Fica como fallback se o mux regredir.
**Alternativa rejeitada — 2 estágios (TAGARELA→CORAA):** custo de GPU comparável ao mux mas 2 runs;
o dono priorizou 1 run.
**Caveats honestos (§2):** (1) a evidência do Parakeet é **600M** (9× o nosso 64M) — modelo grande
absorve ruído de pseudo-label melhor; no nosso 64M o risco de diluição é maior, então a pesagem 1:1
protege o sinal humano; (2) TAGARELA é podcast **wideband** (canal errado) — só a augmentação telefônica
aproxima do alvo; (3) os 10-21% do Parakeet são **limite superior encorajador**, não o que o 64M obterá.
`[LITERATURA]` CORAA 290,77h (arXiv:2110.15731), TAGARELA ~500h (arXiv:2603.15326); dev 5,91h / test
11,24h CORAA `[MEDIDO]` (speech-data-scientist, 2026-07-28).

### D3 — Proxy telefônico-simulado como test de aceitação da DoD #3 (com a limitação declarada)

**Decisão:** aferir a DoD "WER ≤25% em 8 kHz" contra **CORAA passado por `telephone_channel.py`**;
reportar também o WER wideband. O número em 8 kHz **real** fica pendente de dado do dono.
**Alternativa rejeitada:** declarar a DoD #3 cumprida com o número wideband (falácia §3 #6 — WER público
≠ call center 8 kHz); ou travar M5 até o dono fornecer o test real (bloqueia todo o milestone por um dado
externo, quando o proxy já mede a direção).
**Rationale:** Regra 3 + evidence-discipline §3 #6. O proxy mede honestamente a penalidade telefônica.

## Dependency Graph

```
Fase 0 (corpus+datasets)  ──┐
                            ├──> Fase 1 (patch do_finetune) ──┐
Fase 0 ─────────────────────┘                                 ├──> Fase 4 (treino+decode+eval)
Fase 0 ──> Fase 2 (patch augmentação) ────────────────────────┘         │
Fase 0 ──> Fase 3 (test CORAA builder) ───────────────────────────────> Fase 4
                                                              Fase 4 ──> Fase 5 (quantiza+export+CPU eval)
                                                              Fase 5 ──> Fase 6 (Integration Validation)
```
Fases 1, 2, 3 paralelizáveis após a Fase 0. Fase 4 é o gargalo (GPU, horas).

## Phase 0 — Corpus + datasets de augmentação

### Task 0.1 — CORAA prep (dev/test manifests Lhotse) — ✅ dev/test FEITO; train BLOQUEADO por disco

#### Files to edit
`training/prep_coraa.py` (ENTREGUE — reusa `normalize_ptbr`+`Fbank` 80-bin, Regra 9),
`training/tests/test_prep_coraa.py` (ENTREGUE — 6 testes de contrato passando, incl. guarda que proíbe
filtro de voto em dev/test), `training/scripts/coraa_speaker_overlap.py` (ENTREGUE — prova disjunção de
locutor, exit 0). **Estado (`speech-data-scientist`, 2026-07-28):** dev=5,91h/7522 cuts e
test=11,24h/12676 cuts prontos na instância (100% com features, 0 texto vazio, disjunção provada em
CORAL/NURC/TEDx = 78% das horas; ALIP+SP2010 não-verificável por falta de speaker_id no metadado —
caveat honesto). **train (273h) BLOQUEADO por disco** (49GB RAR não cabe nos 33GB livres — precisa volume
maior, pré-autorizado).

#### TDD
`test_coraa_manifest_nonempty` — dado o dir de prep do CORAA, o manifest `coraa_cuts_{dev,test}.jsonl.gz`
existe, tem >0 cuts, e nenhum cut do split de treino aparece no test (invariante de vazamento; falácia
§3 #10). GWT: given prep concluído, when carrega os manifests, then `len(test)>0 and set(train_ids) ∩
set(test_ids) == ∅`.

#### Why this step
Ação: garantir o corpus humano espontâneo pronto como CutSet Lhotse. Raciocínio: é a entrada do
fine-tune (blueprint Q2) e o único dado com label humana (DoD #2); sem vazamento treino/test (regra
inviolável 5).

#### Acceptance criteria / DoD
Manifests dev/test não-vazios; zero sobreposição de IDs treino/test; `[MEDIDO]` nº de horas por split.

### Task 0.2 — Download MUSAN (SLR17) + RIR (SLR28) e prep de `musan_cuts.jsonl.gz`

#### Files to edit
Runbook na instância (`lhotse download musan` + `download_rir_noise`). Sem código in-repo novo.

#### TDD
`test_musan_cuts_loadable` — `load_manifest("musan_cuts.jsonl.gz")` retorna CutSet com >0 cuts e cada
cut carrega áudio sem erro (smoke). (blueprint Q4/Q6)

#### Why this step
Ação: baixar os datasets de ruído/RIR. Raciocínio: `CutMix`/`Reverb` exigem esses manifests (blueprint
Q4); o datamodule espera `musan_cuts.jsonl.gz` (`asr_datamodule.py:231`).

#### Acceptance criteria / DoD
Manifests carregam; disco monitorado (poda — `vastai-disk-full-kills-training`); ~11 GB MUSAN
documentado.

### Task 0.3 — Prep do TAGARELA (~500h podcasts, pseudo-Whisper) para o mux (D4)

#### Files to edit
`training/prep_tagarela.py` (NEW, molde `prep_coraa.py` — reusa `normalize_ptbr`+`Fbank`, Regra 9).
Runbook de download na instância.

#### TDD
`test_tagarela_manifest_and_no_test_leak` — o manifest `tagarela_cuts_train.jsonl.gz` tem >0 cuts, cada
cut carrega áudio, e **nenhum utterance do TAGARELA vaza para o test CORAA** (o test é 100% humano;
pseudo-label nunca no test — falácia §3 #10). Determinismo do `normalize_ptbr` idêntico ao CORAA (mesma
convenção de texto).

#### Deep file dependency analysis
Espelha `prep_coraa.py` (entregue). Só entra no split de **train** do mux; o test permanece CORAA humano.
O `--use-mux` do icefall (blueprint Q1) combina `tagarela_cuts_train` + `cv-pt_cuts_train` (CORAA)
pesados ~1:1.

#### Why this step
Ação: preparar o TAGARELA como CutSet Lhotse para o mux. Raciocínio: D4 — o dono priorizou 1 run de GPU e
trouxe evidência (`[LITERATURA]` Parakeet+TAGARELA 10-21% espontâneo) de que o dado ajuda; a pesagem 1:1
protege o sinal humano (DoD #2); o guarda-corpo é o test humano.

#### Acceptance criteria / DoD
Manifest train não-vazio; `[MEDIDO]` horas efetivas; **zero vazamento para o test CORAA**; disco
monitorado (TAGARELA ~500h + CORAA train juntos pressionam o disco — coordenar com o agente `ml-infra`).

## Phase 1 — Patch `do_finetune` no `zipformer/train.py`

### Task 1.1 — `prep_finetune.py`: portar o mecanismo de fine-tune

#### Files to edit
`training/prep_finetune.py` (NEW, orçamento ≤500 LoC, molde `prep_phoneme_head.py`).

#### TDD
`test_prep_finetune_injects_once` (fixture) — dado um `train.py` fixture do icefall, o patch injeta
`add_finetune_arguments`, `load_model_params` e o bloco `if params.do_finetune:` **exatamente uma vez**
(`assert count==1`, idempotente), e `python -c "import ast; ast.parse(patched)"` valida sintaxe. Negativo:
aplicar 2× não duplica (assert já-presente → no-op).

#### Deep file dependency analysis
Espelha `prep_phoneme_head.py` (481 LoC, sha 6c06c83): localiza âncoras por regex, insere blocos,
assert de unicidade. O `load_model_params` vem de `KWS/zipformer/finetune.py:208` (use_ctc-compatível).

#### Why this step
Ação: adicionar o fluxo `--do-finetune/--finetune-ckpt/--init-modules` ao nosso train.py. Raciocínio:
D1 — fine-tune≠resume; o patch determinístico é o padrão do projeto (Regra 9), testável offline sem
GPU.

#### Acceptance criteria / DoD
Patch idempotente (count==1); AST válido; teste de fixture verde; nenhuma âncora ausente falha silenciosa
(fail-fast, `error-handling.md`, EC-P3 — testar contra o `train.py` REAL da instância).
**Halt-loop checkpoint (EC-P2):** antes do run longo, smoke de 1 step confirma que o base ckpt M4
carrega os prefixos `encoder,ctc_output` sem erro no `assert set(src_keys)==set(dst_keys)`
(`finetune.py:507`); mismatch da cabeça de fonema pego em segundos, não após horas de GPU.

## Phase 2 — Patch da augmentação no `asr_datamodule.py`

### Task 2.1 — `prep_augment_datamodule.py`: anexar Reverb + telephone à lista `cut_transforms` — ✅ FEITO (audio-dsp-engineer, 2026-07-28; 15 testes verdes; adapter `telephone_channel_transform.py` via `AudioTransform`; on-the-fly no treino)

#### Files to edit
`training/prep_augment_datamodule.py` (NEW, ≤500 LoC).

#### TDD
`test_augment_compose_order_and_invariants` (contrato) — dado um CutSet fixture pequeno, a composição
`[Reverb, CutMix(musan), telephone_channel]` produz cuts com: (a) `aug.duration==in.duration`
(pad_to_longest), (b) `np.isfinite(samples).all()` (sem NaN/Inf), (c) determinismo com seed=42 (2 runs
idênticos), (d) ordem = ordem da lista (telephone aplicado por último). (blueprint Q6, EC-2)

#### Deep file dependency analysis
**Achado (2026-07-28):** `telephone_channel.py` (M3) expõe `apply_telephone_channel(samples, sr) ->
(samples, sr)` — **função numpy, NÃO um transform `CutSet→CutSet` do lhotse**. Logo NÃO dá "append"
direto: precisa de um **adapter** fino (reusa a função, Regra 9) que aplique o canal ao áudio do cut
on-the-fly (ou, como o codec é **determinístico** — ao contrário de ruído/RIR — avaliar aplicá-lo offline
com rationale). `CutMix(MUSAN)` já está no datamodule (`asr_datamodule.py:232`, p=0.5, snr=(10,20));
`ReverbWithImpulseResponse` é importável de `lhotse.dataset`. `--on-the-fly-feats` **já existe** como flag
(satisfaz EC-P1). Ordem D2 = [Reverb, CutMix, telephone]. **Delegado ao `audio-dsp-engineer`** (domínio
DSP+lhotse; investigar o mecanismo lhotse correto de augmentação de áudio customizada).

#### Why this step
Ação: empilhar a degradação de canal on-the-fly. Raciocínio: D2 — a ordem física
(sala→ruído→telefone) é o que aproxima READ→ESPONTÂNEO+telefônico; teste de contrato replica os
invariantes do lhotse (Q6) porque o transform telefônico é código nosso (`testing.md`).

#### Acceptance criteria / DoD
Teste de contrato verde (4 invariantes); patch idempotente; áudio degradado audível/plotável em 1 cut de
smoke (evidência); **`--on-the-fly-feats True` fixado no runbook de fine-tune** (EC-P1) — os cut
transforms operam sobre áudio antes do fbank.

## Phase 3 — Builder do test CORAA (wideband + telefônico) — ✅ COBERTO POR REUSO (YAGNI)

### Task 3.1 — REUSAR `make_telephone_test.py` (sem script novo — parsimony rung 1)

**Decisão (2026-07-28):** NÃO criar `make_coraa_test.py`. O `training/make_telephone_test.py` (M4, 76 LoC,
4 testes verdes) **já** lê `cv-pt_cuts_{split}.jsonl.gz` — o naming exato que o prep do CORAA produziu —
preserva `cut.id` (linhas 51-54: pareamento wideband↔telefônico), preserva o texto (refs idênticas) e
reusa `apply_telephone_channel` (Regra 9). O par de aceitação é: **wideband = o test CORAA humano
original** (já existe) **+ telefônico = output do `make_telephone_test.py --split test --in <dir CORAA>`**.

#### Files to edit
Nenhum (reuso). Runbook na instância: `python3 make_telephone_test.py --in data/coraa --out
data/coraa_tel --split test`.

#### TDD
Já coberto por `training/tests/test_make_telephone_test.py` (4 testes: resample, reuso sem duplicar DSP).
O pareamento de IDs é garantia estrutural do script (`recording_id=cid`, `cid=cut.id`).

#### Why this step
Ação: reusar o builder de test telefônico de M4 sobre o CORAA. Raciocínio: parsimony rung 1 — o script
já existe e cobre o requisito; escrever `make_coraa_test.py` seria duplicação (o naming e a lógica batem).
D3 — o proxy telefônico afere a DoD #3; IDs pareados habilitam `bootstrap_wer_ci.py`.

#### Acceptance criteria / DoD
Dois manifests (test CORAA original + telefônico) com IDs pareados e refs consistentes; test 100% humano
(pseudo nunca entra — só o canal determinístico é aplicado); sem vazamento com o treino (regra 5).

## Phase 4 — Fine-tune + decode + eval (GPU, instância)

### Task 4.1 — Rodar o fine-tune e medir o WER espontâneo

#### Files to edit
Runbook na instância (usa os patches das Fases 1-2). Recogs → `training/results/m5-finetune-coraa/`.

#### TDD
Não é código unitário — é **run de medição**. Gate de evidência (não green de suite): (a) `[MEDIDO]`
WER no test CORAA wideband **e** telefônico, com comando/hardware/avg; (b) `bootstrap_wer_ci.py`
pareado **M5 vs baseline M4** no MESMO test → Δ + IC95%; (c) hipótese escrita ANTES (§2): "o fine-tune
em CORAA reduz o WER espontâneo vs o M4 (treinado só em fala lida)".

#### Why this step
Ação: executar o recipe. Raciocínio: é o núcleo do milestone (DoD #1/#2); o número só vale com IC
(falácia §3 #12) e rótulo `[MEDIDO]`.

#### Acceptance criteria / DoD
WER espontâneo `[MEDIDO]` com IC; comparação pareada vs M4; hipótese/evidência/conclusão separadas
(§2). Custo do run dentro do orçamento (risco ROADMAP #1).

## Phase 5 — Quantizar + exportar + eval CPU

### Task 5.1 — Export int8 ONNX do modelo M5 + WER runtime CPU

#### Files to edit
Runbook de export (molde M4) + `training/scripts/eval_runtime_wer.py` (reuso). Modelo →
`models/m5-final/`.

#### TDD
`test_onnx_graph_clean` — o grafo ONNX exportado NÃO contém nós da cabeça de fonema (custo zero em prod,
como M4); SHA do modelo registrado. Eval: WER runtime int8 CPU ≈ WER decode (int8 lossless, como M4).

#### Why this step
Ação: entregar o modelo no runtime alvo (DoD #4). Raciocínio: o produto roda int8 CPU; o número que
importa é o do runtime (cobrança do dono em M4 — `Voce deve calcular o WER/CER na CPU`).

#### Acceptance criteria / DoD
int8 exportado; grafo limpo de fonema; WER CPU `[MEDIDO]` ≈ decode; RTFx ≥6× (RNF-07) reaferido.

## Phase 6 — Integration Validation

### Task 6.1 — Validar DoDs de M5 e reportar com honestidade

#### Files to edit
`training/results/m5-scale-model-wer-results.md` (NEW — deliverable), `CHANGELOG.md` (`[Unreleased]`).

#### TDD / gate
Checklist DoD: (1) treino escala ✓/✗; (2) fine-tune humano ✓/✗; (3) WER ≤25% no **proxy telefônico**
`[MEDIDO]` + nota da limitação 8 kHz-real; (4) int8 exportado ✓/✗. Todos os números com rótulo e IC.
Rodar a suite de testes dos patches (`pytest training/tests/ scripts/tests/`) verde.

#### Why this step
Ação: fechar o milestone com evidência. Raciocínio: a meta "NAO ACEITO ENTREGA SEM EVIDÊNCIAS 100%
FUNCIONAL" (dono) + Regra 3 — reportar ≤25% no proxy e a pendência do 8 kHz real, não overclaim.

#### Acceptance criteria / DoD
Deliverable com hipótese/evidência/conclusão; CHANGELOG atualizado; DoD #3 aferida no proxy com a
limitação declarada; suite de patches verde.

## Coverage Matrix

| Requisito / DoD | Task(s) |
|---|---|
| DoD#1 treino escala (arch/tamanho M4) | 0.1, 0.3, 4.1 |
| DoD#2 fine-tune label humana (CORAA) + mux TAGARELA pesado 1:1 (D4) | 0.1, 0.3, 1.1, 4.1 |
| DoD#3 WER ≤25% call center 8 kHz (proxy) | 3.1, 4.1, 6.1 (+ Unresolved: 8 kHz real) |
| DoD#4 quantizado+exportado runtime | 5.1 |
| Augmentação telefônica (gap READ→ESPONTÂNEO) | 0.2, 2.1 |
| Sem vazamento treino/test | 0.1, 3.1 |
| Evidência com IC + rótulo | 4.1, 5.1, 6.1 |

## Drawbacks & Risks

| Risco | Sev | Mitigação | Owner |
|---|---|---|---|
| WER estaciona acima de 25% (corpus insuficiente, ROADMAP risco #2) | Alta | proxy telefônico mede a direção; varredura de SNR/LR; mais dados (Q-09) se preciso | asr-chief-scientist |
| Custo GPU acima do orçamento (ROADMAP #1) | Média | run curto (~12 épocas), start de avg-model, poda de checkpoints (`vastai-disk-full-kills`); mux é 1 run (não 2) | ml-infra-engineer |
| Mux dilui o sinal humano (500h pseudo-Whisper vs 273h CORAA) → WER pior que CORAA-only | Média | pesagem ~1:1 via `--use-mux` (upsample CORAA); test humano; fallback CORAA-only se regredir | asr-chief-scientist |
| Disco insuficiente p/ CORAA train (49GB) + TAGARELA (~500h) juntos | Alta | volume maior (pré-autorizado) OU arquivar exp de M4 (~70GB); agente `ml-infra` coordena; poda proativa >90% | ml-infra-engineer |
| Patch `do_finetune` quebra em versão diferente do icefall na instância | Média | teste de fixture + assert de âncora fail-fast (não silencioso) | — |
| DoD #3 literal (8 kHz real) não aferível sem dado do dono | Alta | D3: proxy + pendência declarada, não overclaim | asr-chief-scientist |
| Vazamento CORAA treino→test infla acurácia | Alta | invariante de ID disjunto (Task 0.1/3.1), regra inviolável 5 | speech-data-scientist |
| Vazamento **cross-corpus** (locutor do TAGARELA-podcast = TEDx no test CORAA) — F2 da revisão | Média (rebaixado) | **[MEDIDO 2026-07-28] cross-check TEDx: exit 0 — 81 videoIDs, nenhum casa path do TAGARELA (sem vazamento demonstrável)**. Residual NURC/ALIP/SP2010 (sem chave pública) NÃO-VERIFICÁVEL → declarado como caveat no deliverable | speech-data-scientist |
| Mux ignora TAGARELA silenciosamente (naming `tagarela_cuts_train` ≠ glob `cv-pt_cuts_train`) → vira CORAA-only sem avisar — F9 (lição B-1) | Alta | Fase 4: `--use-mux` aponta EXPLÍCITO ao arquivo + smoke confirma horas do mux (não só CORAA) | asr-chief-scientist |
| Alucinação de pseudo-label do Whisper no TAGARELA polui o fine-tune — F3 | Média | filtro determinístico (repetição n-grama + char/s) na prep; medir impacto em WER | speech-data-scientist |

## Unresolved Questions

- LICENÇA CORAA — RESOLVIDA (dono assume o risco, 2026-07-28). CORAA é CC-BY-NC-ND 4.0 (agrega
  TEDx + acadêmicos); a premissa "comercial-limpo" era falsa, mas o **dono assumiu explicitamente o risco
  de licença** e escolheu o dataset mais apropriado ao alvo técnico → **CORAA full** (D4). O modelo M5
  é rotulado nesse contexto; a limpeza comercial do dado fica como responsabilidade assumida do dono, não
  claim do projeto.
- BLOQUEIO DE DISCO (train CORAA). train = 49,4 GB RAR → ~50 GB extraído (RAR multipart,
  não-streamável); instância tem 33 GB livres. Precisa volume maior na vast.ai (pré-autorizado pelo
  dono) OU arquivar dados de M4 (~70 GB). dev/test já prontos.
- Common Voice PT (CV17) gated — precisa sessão HF autenticada + aceite dos termos Mozilla; licença
  CC0 (a mais limpa). Baixar via `datasets.load_dataset(...,"pt",token=...)` após aceite.
- Test set de call center 8 kHz REAL (DoD #3 literal): depende de dado do dono (`PRD.md` Q-01). Até
  lá, a DoD é aferida no proxy telefônico-simulado (D3). Pergunta aberta ao dono: fornecer áudio real?
- **Cabeça de fonema no fine-tune:** manter (com `gen_phonemes.py` no CORAA) vs desligar
  (`init-modules` sem `phoneme`)? Decisão no início da Fase 1 — o mecanismo suporta ambos (blueprint EC-4).
- **SNR/`p`/LR ótimos:** hiperparâmetros a varrer na Fase 4 (não travados).

## Failure scenarios

O plano toca I/O externo (download de datasets, leitura de manifests na instância, export ONNX):

| Dependência | Modo de falha | Como o teste reproduz | Comportamento esperado |
|---|---|---|---|
| Download MUSAN/RIR (SLR17/28) | rede cai / zip corrompido | checksum do tar / smoke `load_manifest` | fail-fast com erro claro, não manifest vazio silencioso |
| Manifest CORAA na instância | arquivo ausente / vazio | `test_coraa_manifest_nonempty` | erro tipado "manifest ausente", não treino com 0 cuts |
| Export ONNX | nó de fonema vaza no grafo | `test_onnx_graph_clean` | falha o export, não modelo com custo extra em prod |

## Global Definition of Done

- Todos os patches com teste (fixture/contrato) verde: `pytest training/tests/ scripts/tests/`.
- Nenhum arquivo novo >500 LoC (`architecture.md`).
- Todo número com rótulo de proveniência + IC onde sustenta decisão (`asr-evidence-discipline.md`).
- CHANGELOG `[Unreleased]` atualizado (Regra 6).
- Deliverable de resultados de M5 (criado na Fase 6, sob `training/results/`) com hipótese/evidência/conclusão separadas.
- DoD #3 aferida no proxy telefônico com a limitação 8 kHz-real declarada (não overclaim).
- Integration Validation (Fase 6) passa.
