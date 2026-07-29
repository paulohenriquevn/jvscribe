# Edge Case Review (plan) — m5-scale-model-wer

Date: 2026-07-28
Plan analyzed: knowledge-base/plans/m5-scale-model-wer-plan.md
Tasks analyzed: 0.1, 0.2, 1.1, 2.1, 3.1, 4.1, 5.1, 6.1
Edge cases found: 4 (MUST FIX: 1, SHOULD TEST: 2, DOCUMENT: 1)

## MUST FIX

### EC-P1: augmentação on-the-fly exige `OnTheFlyFeatures` (áudio→augment→fbank); features pré-computadas do CORAA não podem ser augmentadas
- **Affected task:** 2.1, 0.1, 4.1 (ADR-2)
- **Family:** Interpretation / Dependency
- **Scenario:** o prep do CORAA (`prep_coraa.py`) computou fbank estático (`feats_{dev,test,train}/`). Mas os `cut_transforms` (Reverb/CutMix/telephone) modificam **áudio** e só têm efeito se aplicados **antes** do fbank. Com `PrecomputedFeatures` (feats estáticas), a augmentação de canal **não surte efeito** — o modelo treinaria em fbank limpo, anulando ADR-2 e o gap READ→ESPONTÂNEO+telefônico. `asr_datamodule.py:299` mostra o caminho correto: `input_strategy=OnTheFlyFeatures(Fbank(...))` sobre cuts que retêm o `Recording` (áudio).
- **Impact:** o recipe de M5 falharia silenciosamente no objetivo — WER espontâneo medido sem a augmentação que ele promete.
- **Suggested fix:** o fine-tune augmentado usa **`--on-the-fly-feats True`** (OnTheFlyFeatures) sobre cuts CORAA-train que **retêm o áudio** (Recording), não as feats pré-computadas. As `feats_train/` só servem a um baseline SEM augmentação. Task 0.1 deve garantir que os train cuts mantêm referência ao wav; Task 2.1/4.1 fixam `--on-the-fly-feats`.

## SHOULD TEST

### EC-P2: `load_model_params` com `--init-modules` pode falhar no `assert set(src_keys)==set(dst_keys)` se o modelo instanciado divergir do base ckpt
- **Affected task:** 1.1, 4.1
- **Suggested halt-loop checkpoint:** antes do run longo, um **smoke de 1 step** que confirma que o base ckpt M4 (medium+fonema) carrega os prefixos `encoder,ctc_output` sem erro (`finetune.py:507` exige que os módulos batam). Se mantivermos a cabeça de fonema, `init_modules` deve incluí-la OU o modelo instanciar sem ela; o smoke pega o mismatch em segundos, não após horas de GPU.

### EC-P3: o `zipformer/train.py` da instância pode divergir da versão de referência que embasa o patch
- **Affected task:** 1.1
- **Suggested halt-loop checkpoint:** o `prep_finetune.py` deve **falhar-alto** (não silencioso) se qualquer âncora de regex não casar exatamente 1×, e o teste de fixture deve rodar contra o `train.py` REAL da instância (copiar/verificar), não só o de referência.

## DOCUMENT

### EC-P4: filtro de voto de qualidade no TRAIN (permitido) vs proibido em dev/test
- **Accepted risk:** o guarda de `test_prep_coraa.py` proíbe filtro em dev/test (anchor comparável). No train, filtrar por votos negativos/hesitação é permitido e desejável, mas **muda a contagem de horas efetivas** — documentar se filtrou e quantas horas sobraram (`[MEDIDO]`), para o número de "treino em escala" ser honesto. Delegado ao agente `ml-infra-engineer` (reporta se filtrou).

## Summary

| Task | Edges | MUST FIX | SHOULD TEST | DOCUMENT |
|---|---|---|---|---|
| 0.1 | 1 | (EC-P1 compart.) | 0 | 1 (EC-P4) |
| 1.1 | 2 | 0 | 2 (EC-P2, EC-P3) | 0 |
| 2.1 | 1 | 1 (EC-P1) | 0 | 0 |
| 4.1 | 1 | (EC-P1 compart.) | 0 | 0 |

**Verdict:** PLAN NEEDS ADJUSTMENT (1 MUST FIX — EC-P1 on-the-fly features; absorvido no plano v1.1).
