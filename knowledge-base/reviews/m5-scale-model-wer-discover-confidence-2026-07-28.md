# Discover-Confidence — m5-scale-model-wer (blueprint)

**Date:** 2026-07-28
**Verdict:** SHIPPABLE (weighted_avg 100.0, hard_caps: [], soft_caps: [])

Blueprint: `knowledge-base/discoveries/blueprints/m5-scale-model-wer-blueprint.md`.
6 questions respondidas com `arquivo:linha` que resolve em `knowledge-base/references/{icefall,lhotse}`.
4 coverage corners populados, Cross-cutting Comparison + Recommendations presentes, 2 ADRs (D1 fine-tune
por do_finetune; D2 ordem de augmentação Reverb→Ruído→Telefone).

**Caveat honesto (tooling):** `check_reference_citations.py` só casa o prefixo
`.claude/knowledge-base/references/`; este projeto usa `knowledge-base/references/` (regra 4). As
citações do blueprint usam o path real (resolve em disco e foi lido) — a densidade medida pelo scorer é
artefato do mismatch de prefixo, não ausência de evidência. Verdict SHIPPABLE não foi afetado.

**Fase DISCOVER de M5: COMPLETA.** Downstream: `/to-plan` do recipe de fine-tune (bloqueado pela chegada
do corpus CORAA, em prep na instância vast.ai).
