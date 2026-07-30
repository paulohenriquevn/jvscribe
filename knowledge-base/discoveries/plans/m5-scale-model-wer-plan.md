# Discovery Plan: M5 — Fine-tune para WER em fala espontânea PT-BR

> **Version 1.1** (MUST-FIX EC-1 absorvido: fallback CTC em Q2) — Investiga, no código dos peers `icefall` e `lhotse`, COMO (a) fine-tunar um
> Zipformer-CTC pré-treinado num corpus novo sem retreinar do zero, (b) empilhar a augmentação
> (ruído MUSAN + reverb RIR + o canal telefônico de M3) on-the-fly no datamodule, e (c) preparar o
> pipeline para o alvo real de M5: **WER em fala espontânea** (o gap READ→ESPONTÂNEO, maior que o do
> canal 8 kHz). Output: blueprint que trava o recipe de fine-tune + augmentação antes do `/to-plan`.

**Slug:** `m5-scale-model-wer`
**Owner:** Paulo
**Created:** 2026-07-28
**Time budget:** 4h (icefall 2,5h — recipe de fine-tune; lhotse 1,5h — augmentação)

## Context

M4 fechou o finalista **Zipformer-CTC medium (64M) + cabeça de fonema** (27,46% WER CPU, wideband
FLEURS `[MEDIDO]`, `training/results/m4-medium-phoneme-ablation-results.md`). M5 (`ROADMAP.md § M5`)
exige treino em escala + **fine-tune supervisionado em label HUMANA** (o único estágio que supera o
teto do professor) + **WER ≤25% em call center 8 kHz**. O gap dominante é **READ → ESPONTÂNEO**: o
modelo treinou em fala LIDA (MLS-PT audiobooks), o alvo é ESPONTÂNEA (call center). Decisão de
corpus (dono, 2026-07-28): recipe **comercial-limpo** — MLS-PT 161h + Common Voice PT + **CORAA-v1.1
(~290h humano, espontâneo)** — sem TAGARELA (CC-BY-NC-SA). Este discover trava o **como técnico**
(fine-tune + augmentação) antes de implementar; a decisão de corpus já está tomada.

Rules que o blueprint respeita: `.claude/rules/asr-evidence-discipline.md` (§1 rótulos, §3 #6 8kHz,
#10 pseudo-label fora do test), `architecture.md` (Regra 9 — reusar a recipe, não reimplementar),
`testing.md` (o pipeline de augmentação precisa de teste de contrato).

## Objective

Produzir um blueprint que permita decidir o **recipe exato de fine-tune + augmentação** do medium+fonema
para fala espontânea. Critérios de sucesso:

- [ ] Todas as research questions respondidas com citação `knowledge-base/references/{icefall,lhotse}/...:linha`
- [ ] Tabela comparativa de augmentação (o que lhotse oferece vs o que M3 já tem)
- [ ] Ao menos 1 proposta de decisão concreta por question (flags de fine-tune, ordem de augmentação)
- [ ] `/discover-confidence` verdict ≥ SHIPPABLE_WITH_CAVEATS

## In-Scope / Out-of-Scope

### In-Scope

| Project | Subdiretórios in-scope | Razão |
|---|---|---|
| `knowledge-base/references/icefall/` | `egs/commonvoice/ASR/pruned_transducer_stateless7_streaming/finetune.py`, `egs/wenetspeech/ASR/{finetune.sh,pruned_transducer_stateless2/finetune.py}`, `egs/commonvoice/ASR/zipformer/{train.py,asr_datamodule.py}` | Recipe de fine-tune + o datamodule que estende |
| `knowledge-base/references/lhotse/` | `lhotse/dataset/cut_transforms/{mix.py,reverberate.py}`, `lhotse/recipes/{rir_noise.py,but_reverb_db.py}`, `test/cut/{test_cut_augmentation.py,test_multi_cut_augmentation.py}`, `lhotse/shar/writers/shar.py` | Augmentação on-the-fly + testes + streaming |

### Out-of-Scope (explícito)

| Item | Por quê |
|---|---|
| `knowledge-base/references/icefall/egs/*/` que não `commonvoice`/`wenetspeech` | Fora da família de recipe que usamos |
| `knowledge-base/references/{funasr,sherpa-onnx,moonshine,parakeet-rs,tract,vibeasr-cpp}/` | Não são a stack de treino (icefall+lhotse); avaliados em M2 |
| Decisão de corpus (TAGARELA vs limpo) | Já decidida pelo dono (comercial-limpo) — não é question de discover |
| Aquisição de test set de call center 8 kHz REAL | Dependência de dado externo (dono); CORAA-espontâneo+telefone é o proxy honesto |

## ADRs

### D1 — Time budget + stop conditions

**Decision:** icefall 2,5h, lhotse 1,5h.
**Rationale:** o recipe de fine-tune (icefall) é o núcleo do risco; a augmentação (lhotse) é
mais direta (M3 já tem o canal telefônico; falta empilhar ruído/reverb).
**Stop — por question:** Fase A sem matches após 3 variações → BLOCKED "Fase A exhausted".
**Stop — por projeto:** budget esgotado → questions restantes BLOCKED "budget exhausted"; se todas
`done`/`blocked`, emitir `<promise>BLUEPRINT_BLOCKED</promise>`.
**Anti-pattern:** nunca fabricar Fase B; BLOCKED honesto (Regra 3).

### D2 — Investigation depth

**Decision:** Read end-to-end os arquivos de fine-tune (poucos, densos); grep+Read pontual na augmentação.
**Rationale:** o fine-tune tem armadilhas (quais params congelar, LR, model-averaging da base) que só
a leitura completa revela; a augmentação é composição de transforms conhecidos.
**Consequences:** blueprint denso no fine-tune, conciso na augmentação.

## Research Questions

| # | Question | Corner | Ref project | Fase A (broad) | Fase B (deep Read) | Expected answer shape |
|---|---|---|---|---|---|---|
| Q1 | Como o `finetune.py` do icefall inicializa a partir de um checkpoint pré-treinado e quais params treina (freeze? LR menor? `--use-mux` mistura corpora)? | techniques | icefall | Grep `--do-finetune\|--finetune-ckpt\|--use-mux\|load_checkpoint` em `egs/commonvoice/ASR/pruned_transducer_stateless7_streaming/finetune.py` + `egs/wenetspeech/ASR/pruned_transducer_stateless2/finetune.py` | Read as funções de init + o loop de treino; capturar LR, warmup, o que carrega do base | Tabela: flag → efeito, + snippet de init com `path:linha` |
| Q2 | Como aplicar o `finetune` ao nosso Zipformer-CTC (`--use-ctc 1`, não transducer)? **Os recipes de finetune são TRANSDUCER (EC-1)** — então investigar o MECANISMO de fine-tune, não só o script. | techniques | icefall | Grep `use_ctc\|ctc_output\|use-mux\|load_checkpoint\|--start-epoch` em `egs/wenetspeech/ASR/finetune.sh` **E** `egs/commonvoice/ASR/zipformer/train.py` | Read: (a) como o `finetune.py` transducer inicializa do base + `--use-mux`; (b) **FALLBACK** — como `zipformer/train.py` carrega checkpoint (`--start-epoch`/`load_checkpoint`), pois fine-tune CTC = continuar treino do base com `--base-lr` reduzido no corpus novo | Prosa: mecanismo de fine-tune aplicável ao CTC (recipe dedicado OU train.py+base-ckpt+LR menor) + como tratar a cabeça de fonema aux + `path:linha` |
| Q3 | Como o lhotse compõe augmentação on-the-fly (CutMix de ruído MUSAN + reverb RIR) que empilharíamos sobre o `telephone_channel.py` de M3? | techniques | lhotse | Read `lhotse/dataset/cut_transforms/mix.py` + `reverberate.py` | Read as classes `CutMix`/`ReverbWithImpulseResponse`: assinatura, SNR, ordem de aplicação, custo | Tabela de transforms (nome→efeito→param) + ordem recomendada telefone∘ruído∘reverb + `path:linha` |
| Q4 | Que datasets de ruído/RIR o lhotse espera (MUSAN, BUT ReverbDB) e como baixá-los? Deps/versões? | deps | lhotse | Read `lhotse/recipes/rir_noise.py` + `but_reverb_db.py` (Fase A skip — text/recipe shape) | Read as funções de download/prep: URLs, tamanho, formato | Lista: dataset→fonte→tamanho→formato + deps (torchaudio) |
| Q5 | Como o icefall orquestra o fine-tune (start de um base ckpt, `keep-last-k`, avg) para um run curto e barato? | tools | icefall | Read `egs/wenetspeech/ASR/finetune.sh` | Read o script: como aponta o base ckpt, nº de épocas típico, decode | Runbook: comando de fine-tune + parâmetros + `path:linha` |
| Q6 | Como o lhotse TESTA que os transforms de augmentação produzem cuts válidos (shape, sem NaN, reprodutível)? | tests | lhotse | Grep `def test_` em `test/cut/test_cut_augmentation.py` + `test_multi_cut_augmentation.py` | Read 2-3 testes-chave: o que asseguram (invariância de duração? determinismo com seed?) | Tabela: teste→invariante assegurado → o que replicar no nosso teste de contrato |

## Coverage Matrix

| Corner | Questions | Coberto? |
|---|---|---|
| Integration tests | Q6 | ✅ |
| Dependencies | Q4 | ✅ |
| Tools | Q5 | ✅ |
| Techniques | Q1, Q2, Q3 | ✅ |

Todas as 4 corners ≥1 question. Sem deferral.

## Halt-loop checkpoints

- Antes de marcar Q1/Q2 `done`: a flag/mecanismo de fine-tune citado tem de resolver (`path:linha` exibe).
- Antes de Q3 `done`: a ordem de composição (telefone∘ruído∘reverb) tem de estar justificada por leitura, não suposição.
- Antes de fechar: toda citação `references/{icefall,lhotse}/...` resolve em disco.

## Acceptance Criteria

- [ ] 6 questions respondidas OU honestamente BLOCKED com razão.
- [ ] Toda citação backed por `knowledge-base/references/` path que resolve.
- [ ] Blueprint com: recipe de fine-tune (flags), stack de augmentação (ordem + deps), e o teste de contrato a replicar.
- [ ] ADR-shape: proposta de recipe (base→fine-tune CORAA→augmentação) com alternativas.

## Global Definition of Done

`/discover-confidence` ≥ SHIPPABLE_WITH_CAVEATS (`.claude/rules/discover-blueprint-golden-rule.md`).
Blueprint em `knowledge-base/discoveries/blueprints/m5-scale-model-wer-blueprint.md`.
