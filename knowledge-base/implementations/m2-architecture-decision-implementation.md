# M2 — Decisão de Arquitetura: resumo de implementação

**Plano:** `knowledge-base/plans/m2-architecture-decision-plan.md` (SHIPPABLE 100)
**Promise:** IMPLEMENTATION_COMPLETE
**Data:** 2026-07-24

## O que foi entregue

| DoD de M2 (ROADMAP) | Entregável | Evidência |
|---|---|---|
| Blueprint 5 candidatos × 8 critérios | `knowledge-base/discoveries/blueprints/m2-architecture-decision-blueprint.md` (SHIPPABLE 100) | discover cycle |
| ADR com escolha + alternativas descartadas com motivo | `knowledge-base/adrs/0001-m2-architecture-finalists.md` | T1.1 |
| 2 finalistas nomeados | Zipformer+CTC e FastConformer+CTC (a-pilotar em M4) | ADR |
| PRD atualizado p/ referenciar blueprint | `PRD.md` § 8.1 (bloco "Atualização M2") + correção da alegação Moonshine | T1.2 |

## Evidência [MEDIDO] que sustentou a decisão

RTFx na mesma CPU (régua de M1 + sherpa-onnx/moonshine), n=10 com dispersão: **Zipformer transducer 20M = 15,90 ± 2,06×** vs **Moonshine tiny 27M = 7,93 ± 0,72×** — o transducer é **~2× mais rápido** em tamanho comparável, separação limpa (intervalos min–max não sobrepõem; `knowledge-base/measurements/m2-rtfx-candidates.md`). Razão arquitetural: AED custa ∝ tokens (autoregressivo), transducer/CTC ∝ frames. Isto reordenou a preferência do PRD (que favorecia Moonshine "por ter benchmark CPU" — número `[LITERATURA]` de outra CPU que não transferia). *(A medição inicial reportou 20,45× → ~2,9× sem dispersão; a re-medição N=10 na mesma clip corrigiu para ~2,0×, review F1 — a diferença é carga de CPU.)*

## Critérios de aceite (verificados por grep)

- ADR: 2 finalistas nomeados ✓ · 3 descartados com motivo ✓ · evidência `[MEDIDO]`/`[FONTE-REPO]` citada ✓ · não-travagem registrada ✓
- PRD: referencia o blueprint (grep=1) ✓ · "receita completa publicada" removida (grep=0) ✓ · 8 critérios intactos ✓

## Validação de integração

- `cargo test --workspace`: 23 suítes verdes · `cargo clippy --all-targets -D warnings`: limpo
- Zero citação fabricada no ADR (8 paths de peers resolvem em disco)
- CHANGELOG `[Unreleased]` atualizado (Regra 6)

## Achados/correções durante a implementação

1. **Teste flaky corrigido** (`server_concurrency_test`): porta fixa 7391 (colisão sob `cargo test` paralelo/TIME_WAIT) + bound de latência absoluto (1s, sensível a carga). Fix: porta efêmera via novo `app::run_with_listener` + asserção relativa (`/metrics` < duração do `/fixture`, load-independent). Não é regressão de M2 (M2 não toca Rust de produto), mas quebrava o workspace test — `testing.md` § 3 (flaky = bug). 4/4 verdes.
2. **Correção ao PRD (Regra 6):** o agente `asr-chief-scientist` achou que `PRD.md` § 8.1 alegava "receita completa publicada" para o Moonshine — refutado pela leitura do código (`moonshine/micro/stt-training/stt_training/train.py:1-12` é WordCNN de MCU, não recipe ASR). Corrigido.
3. **Tooling seeded:** removida entrada malformada do `code-quality-allowlist.txt` (4 campos vs 6 que o parser exige). plan-confidence rodado com `--no-code-quality` (sancionado p/ plano só-documento) — a cascata cq gerava finding fantasma `dead_code unknown` que clippy+cargo+vulture refutam.

## Decisões de escopo honestas

- **M2 nomeia finalistas, não vencedor** (`asr-evidence-discipline.md` § 0). WER 8 kHz call center (crit. 2) e equivalência batch≡streaming (crit. 3) só se medem no piloto de M4 — são `[LITERATURA]`/experimento futuro, honestamente registrados no ADR.
- **RTFx de Paraformer/FastConformer não medido** (tempo/download) — `[LITERATURA]`; FastConformer é família transducer/CTC (RTFx esperado próximo do Zipformer, a medir em M4).

## Follow-ups (M4 — o piloto)

Treinar/pilotar Zipformer-CTC e FastConformer-CTC (~30-80M) + Moonshine como controle; medir WER 8 kHz + RTFx sob RNF-04/05 + equivalência batch≡incremental. A régua de M1 está pronta.
