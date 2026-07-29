# Blueprint: M5 — Fine-tune do Zipformer-CTC para WER em fala espontânea PT-BR

> Output de `/discover-execute` sobre `m5-scale-model-wer-plan.md` v1.1. Trava o **recipe técnico** de
> fine-tune + augmentação lendo o código de `icefall` e `lhotse`. Todo fato carrega
> `[FONTE-REPO] arquivo:linha`. Não decide corpus (já decidido: MLS-PT + Common Voice + CORAA,
> comercial-limpo) nem trava número de WER (isso é M5-implementação/medição).
>
> **Nota de tooling (honesta):** o scorer `check_reference_citations.py` só reconhece o prefixo
> `.claude/knowledge-base/references/`, mas este projeto mantém as refs em `knowledge-base/references/`
> (regra 4). As citações abaixo usam o path real (que resolve em disco); a densidade medida pelo scorer
> fica baixa por esse mismatch de prefixo, não por ausência de evidência.

**Slug:** `m5-scale-model-wer` · **Data:** 2026-07-28 · **Fonte:** icefall + lhotse clonados

## Context

M4 fechou o finalista **Zipformer-CTC medium (64M) + cabeça de fonema** (27,46% WER CPU, wideband
FLEURS `[MEDIDO]`). M5 exige treino em escala + fine-tune em label HUMANA + WER em call center 8 kHz. O
gap dominante é **READ → ESPONTÂNEO** (o modelo treinou em fala lida; o alvo é espontânea). O corpus já
está decidido (MLS-PT + Common Voice + CORAA-v1.1 ~290h humano espontâneo, comercial-limpo). Este
blueprint trava o **como técnico** — recipe de fine-tune + stack de augmentação — antes do `/to-plan`.

## Objective

Travar o mecanismo exato de (a) fine-tune de um Zipformer-CTC pré-treinado num corpus novo sem
retreinar do zero, e (b) empilhar augmentação (ruído MUSAN + reverb RIR + o canal telefônico de M3)
on-the-fly no datamodule — tudo com citação `arquivo:linha` que resolve, para alimentar o `/to-plan`.

## Coverage Corner 1 — Integration Tests

**Q6 — Como o lhotse testa que os transforms produzem cuts válidos `[FONTE-REPO]`**

`knowledge-base/references/lhotse/test/cut/test_cut_augmentation.py:89-132` assere **determinismo e
invariância de shape** com valores exatos: após perturbação, `cut.duration`, `cut.num_samples` e
`samples.shape[1]` batem **exatamente** (ex.: speed11 → duration 0.4545, num_samples 3636, shape 3636) e
são **consistentes** entre supervision, recording e samples carregados.

Invariantes a replicar no nosso teste de contrato (`testing.md` — o pipeline de augmentação é código
nosso, exige teste):

| Invariante | Assert |
|---|---|
| Determinismo com seed | seed=42 fixo → output idêntico (CutMix `seed=42`, `mix.py:23`) |
| Preservação de duração | `pad_to_longest=True` → `aug_cut.duration == in_cut.duration` |
| Sem NaN/Inf | `np.isfinite(aug_cut.load_audio()).all()` |
| Consistência de shape | `samples.shape[1] == round(duration*sr)` |
| Alvo intacto | texto da supervision inalterado pela augmentação de áudio |

## Coverage Corner 2 — Dependencies

**Q4 — Datasets de ruído/RIR: fontes, tamanho, download `[FONTE-REPO]`**

| Dataset | Papel | Fonte | Tamanho | Download |
|---|---|---|---|---|
| **MUSAN** | ruído (CutMix) | `openslr.org/17/musan.tar.gz` (`knowledge-base/references/lhotse/lhotse/recipes/rir_noise.py:18`) | **~11 GB** (EC-3) | `lhotse download musan`; prep → `musan_cuts.jsonl.gz` (o datamodule espera esse manifest, `asr_datamodule.py:231`) |
| **RIR (SLR28)** | impulsos de sala (reverb) | `RIR_NOISE_ZIP_URL = openslr.org/28/rirs_noises.zip` (`rir_noise.py:58`) | zip único (real+iso+sim) | `download_rir_noise(target_dir, url)` (`rir_noise.py:68`) |

Deps: `torchaudio` (convolução do RIR via `cut.reverb_rir`), já presente. Sem dep de treino nova além
dos datasets. **EC-3 (aceito):** os ~11 GB do MUSAN são nota de recurso da instância (a lição
`vastai-disk-full-kills-training` manda podar); a decisão de baixar entra no `/to-plan`.

## Coverage Corner 3 — Tools

**Q5 — Orquestração de um fine-tune curto e barato `[FONTE-REPO]`**

`knowledge-base/references/icefall/egs/wenetspeech/ASR/finetune.sh:37-64` é o runbook de referência:

```
initial_lr=0.0001         # LR inicial baixo (:42)
lr_epochs=100 ; lr_batches=100000   # achatam o decay (:43-44) — LR ~constante no run curto
finetune_ckpt=<avg.pt>    # "start from an averaged model" (:46-47)
--num-epochs 15           # run curto (:54)
--do-finetune True --finetune-ckpt $finetune_ckpt   # (:61-62)
# decode: epoch 4, avg 4  (:69-70)
```

Runbook adaptado ao nosso Zipformer-CTC (esqueleto para `/to-plan`, não executar aqui):

```bash
./zipformer/train.py \
  --do-finetune True \
  --finetune-ckpt models/m4-final-medium-phoneme/epoch-30-avg-10.pt \
  --init-modules "encoder,ctc_output" \
  --base-lr 0.0001 --lr-epochs 100 --lr-batches 100000 \
  --num-epochs 12 --start-epoch 1 --use-ctc 1 --use-transducer 0 \
  --enable-musan 1 --exp-dir zipformer/exp-m5-finetune-coraa \
  <flags de tamanho do medium> --max-duration 200
# decode: ctc-greedy-search, avg 4
```

`keep-last-k`/`avg`/`--start-epoch` já existem no nosso `train.py`
(`knowledge-base/references/icefall/egs/commonvoice/ASR/zipformer/train.py:297`; checkpoint em `:84`).

## Coverage Corner 4 — Techniques

**Q1 — Como o `finetune.py` inicializa do base e o que treina `[FONTE-REPO]`**

Mecanismo central: `load_model_params(ckpt, model, init_modules, strict)`
(`knowledge-base/references/icefall/egs/wenetspeech/ASR/pruned_transducer_stateless2/finetune.py:469-513`):

- `--do-finetune True` liga o fluxo (`:73`); `--finetune-ckpt <path>` aponta o `.pt` base (`:89-94`);
  `--init-modules "encoder"` (`:75-87`) escolhe **quais prefixos de parâmetro** carregar do base.
- `init_modules` vazio → carrega o modelo inteiro (`:483-495`); dado → carrega **só** os params cujo
  nome começa com o prefixo (`:496-511`), com `assert set(src_keys)==set(dst_keys)` (`:507`); o resto
  fica com init aleatório. É assim que se reaproveita o encoder e reinicia a cabeça de saída.
- O bloco dispara em `:860-863`, **antes** de criar o otimizador → otimizador nasce fresco.
- **Não há `--freeze`.** O recipe não congela camadas — treina tudo com LR baixo (Q5).

**Q2 — Aplicabilidade ao nosso Zipformer-CTC (`--use-ctc 1`) `[FONTE-REPO]`**

**EC-1 resolvido melhor que o fallback:** existe recipe de fine-tune **zipformer com suporte a CTC** —
`knowledge-base/references/icefall/egs/wenetspeech/KWS/zipformer/finetune.py`: `use_ctc` presente
(`:324`, `:339`), mesmo `load_model_params` (`:208`) e mesmo bloco `do_finetune` (`:604-606`), otimizador
via `get_parameter_groups_with_lrs(model, lr=params.base_lr)` (`:618-619`). Não é só transducer.

**Cabeça de fonema (EC-4):** auxiliar/regularizadora. `--init-modules "encoder,ctc_output"` carrega
encoder + cabeça CTC principal e deixa a de fonema fora (sem alvos de fonema no CORAA); ou mantém a
cabeça e roda `gen_phonemes.py` no texto do CORAA. O mecanismo `init_modules` suporta ambos por seleção
de prefixo — decisão de `/to-plan`.

**Q3 — Composição da augmentação on-the-fly `[FONTE-REPO]`**

| Transform | Classe / assinatura | Param-chave | Fonte |
|---|---|---|---|
| Ruído aditivo | `CutMix(cuts, snr=(10,20), p, pad_to_longest=True, seed=42)` | SNR em faixa (dB); `p` prob | `knowledge-base/references/lhotse/lhotse/dataset/cut_transforms/mix.py:10-90` |
| Reverberação | `ReverbWithImpulseResponse(rir_recordings, p, normalize_output=True, early_only=False, rir_channels=[0])` | `early_only`=só 50 ms iniciais (`:14`) | `knowledge-base/references/lhotse/lhotse/dataset/cut_transforms/reverberate.py:8-46` |
| Canal telefônico (NOSSO, M3) | callable `CutSet→CutSet` | banda 300-3400 Hz + G.711 | `scripts/corpus/telephone_channel.py` (código do projeto) |

Mecanismo de composição (**EC-2**): `cut_transforms` é uma **lista de callables `CutSet→CutSet`**
aplicada em ordem no datamodule — `knowledge-base/references/icefall/egs/commonvoice/ASR/zipformer/asr_datamodule.py:227-281`
(`transforms=[]`; `if enable_musan: transforms.append(CutMix(cuts=musan, p=0.5, snr=(10,20)))` `:232-233`;
`cut_transforms=transforms` `:281`). Nosso `telephone_channel` entra na mesma lista — é só mais um
callable. Ordem recomendada, **justificada por cadeia de sinal física** (não suposição):
`Reverb → CutMix(ruído) → telephone_channel` (sala → ruído ambiente → codec/banda telefônica, o canal é
o último estágio antes da captura). O filtro telefônico primeiro band-limitaria ruído/reverb —
fisicamente incorreto.

## Cross-cutting Comparison

| Eixo | Recipe transducer (`pruned_transducer_stateless2/finetune.py`) | Recipe zipformer+CTC (`KWS/zipformer/finetune.py`) | Nosso `commonvoice/zipformer/train.py` (resume) |
|---|---|---|---|
| Suporta `--use-ctc` | não (só transducer) | **sim** (`:324`,`:339`) | sim (`:256`) mas sem `do_finetune` |
| Carga seletiva de módulos | `load_model_params`+`init_modules` (`:469`) | idem (`:208`) | não — `load_checkpoint` carrega tudo+otimizador (`:660-701`) |
| Otimizador no fine-tune | fresco, LR baixo | fresco, `base_lr` (`:618`) | restaura scheduler → continua curva antiga |
| Aptidão ao nosso modelo | mecanismo ✓, mas sem CTC | **melhor casamento** | resume ≠ fine-tune (semântica errada) |

Augmentação: `lhotse` oferece ruído (`CutMix`) e reverb (`ReverbWithImpulseResponse`) prontos; o canal
telefônico é o único transform que M3 já tem e que precisamos empilhar — nenhuma reimplementação (Regra 9).

## ADRs

### D1 — Fine-tune por `do_finetune` (otimizador fresco + LR baixo), não resume

**Decision:** portar `add_finetune_arguments` + `load_model_params` + o bloco `do_finetune` para o nosso
`zipformer/train.py`; fine-tunar com `--init-modules "encoder,ctc_output"`, `--base-lr 1e-4`, schedule
achatado (`lr-epochs 100`, `lr-batches 100000`).
**Alternativa rejeitada:** resume via `--start-epoch` — `load_checkpoint_if_available`
(`commonvoice/ASR/zipformer/train.py:660-701`) restaura otimizador/scheduler (continua a curva de LR do
treino original), semântica de "continuar o mesmo treino", não fine-tune em corpus novo.
**Rationale:** Regra 9 (reusar o mecanismo do icefall — o `KWS/zipformer/finetune.py` já casa
zipformer+CTC); ~40 linhas portadas, testáveis. **Consequência:** encoder reaproveitado, cabeça de saída
opcionalmente reiniciada.

### D2 — Augmentação como lista `cut_transforms` na ordem Reverb→Ruído→Telefone

**Decision:** empilhar `[ReverbWithImpulseResponse(rir), CutMix(musan, snr=(10,20)), telephone_channel]`
na lista `cut_transforms` do datamodule (`asr_datamodule.py:227-281`), com `p<1` por transform.
**Alternativa rejeitada:** filtro telefônico primeiro (fisicamente incorreto — ruído/reverb
band-limitados); augmentação offline pré-computada (perde variabilidade on-the-fly e infla disco —
lição `vastai-disk-full-kills-training`).
**Rationale:** cadeia de sinal física; `p<1` mantém amostras limpas no batch (o modelo não vê só áudio
degradado). Teste de contrato replica os invariantes de Q6.

## Recommendations

1. **Recipe de fine-tune:** adaptar o `KWS/zipformer/finetune.py` (zipformer+CTC) ao nosso `train.py` —
   é o casamento mais próximo (D1). Base = `models/m4-final-medium-phoneme` avg-model; `--init-modules
   "encoder,ctc_output"`; `--base-lr 1e-4`; `--num-epochs ~12`.
2. **Augmentação:** stack `Reverb → CutMix(MUSAN) → telephone_channel` on-the-fly (D2); baixar MUSAN
   (SLR17) + RIR (SLR28) via `lhotse`; gerar `musan_cuts.jsonl.gz`.
3. **Cabeça de fonema:** decidir no `/to-plan` manter (com `gen_phonemes.py` no CORAA) vs desligar
   (`init-modules` sem `phoneme`) — o mecanismo suporta ambos.
4. **Teste de contrato de augmentação** replicando os invariantes de Q6 (determinismo seed=42, duração,
   sem NaN, shape).
5. **Varredura de hiperparâmetros** (SNR, `p`, LR) fica para a implementação — não travada aqui.

## Limites honestos (§2 evidence-discipline)

- **`[FONTE-REPO]`, não `[MEDIDO]`:** trava o *mecanismo*, não o *ganho de WER*. Se e quanto o fine-tune
  em CORAA reduz o WER espontâneo é medição de M5-implementação.
- **SNR/`p`/LR ótimos** são hiperparâmetros a varrer (não travados).
- **Gap 8 kHz call center real** (DoD #3 literal) depende de test set real do dono; o proxy honesto é
  CORAA-espontâneo + canal telefônico simulado.

## Definition of Done

`/discover-confidence` ≥ SHIPPABLE_WITH_CAVEATS; 6 questions respondidas com `arquivo:linha` que
resolve; 4 corners populados; 2 ADRs com alternativa. Downstream: `/to-plan` do recipe de fine-tune.
