# Plan-Confidence — m5-scale-model-wer

**Date:** 2026-07-28 · **Verdict:** SHIPPABLE (weighted_avg 97,6; hard_caps: []; nenhum check incompleto)

Plan: `knowledge-base/plans/m5-scale-model-wer-plan.md`. Coverage Matrix 100%, 4 ADRs (D1-D4) com
alternativas, Baseline Context completo (4 subsections), Drawbacks (5), Unresolved (4), Failure
scenarios (3), Dependencies (sem dep Python nova). deps-audit: trivial (M5 reusa lhotse/torchaudio/
icefall; `unrar` é tool de sistema, não pacote Python → sem CVE de supply-chain).

MUST-FIX EC-P1 absorvido (augmentação exige `--on-the-fly-feats`; feats pré-computadas anulariam a
augmentação). Liberado para `/implement`. Implementação Fases 1-3 (patches offline) pode avançar já;
Fase 4 (treino) gated pelo train CORAA (prep em background).
