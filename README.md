# jvscribe — transcrição PT-BR em tempo real, sobre CPU

Transcreva atendimento em português brasileiro **ao vivo, no notebook do próprio
atendente** — sem GPU, sem enviar áudio para a nuvem, sem custo por hora transcrita.

A aposta é **especialização**: um modelo que só faz PT-BR telefônico cabe em dezenas
de milhões de parâmetros onde um multilíngue de 600M não fecha tempo real em CPU.

Escopo deste repositório: **o modelo** e **o motor de inferência**. Plataforma de
frota, compliance LGPD e UI ficam fora (`PRD.md` § 3.2).

---

## Estado do projeto

Projeto em **discover contínuo, orientado por evidência**: a arquitetura não é
escolhida por convicção, é medida. Progresso por milestones (`ROADMAP.md`, M0–M9).

| Milestone | Estado |
|---|---|
| M0 — Fundação do runtime · M1 — Instrumentação | ✅ concluídos |
| M2 — Decisão de arquitetura · M3 — Corpus | ✅ concluídos |
| M4 — Piloto comparativo | ✅ concluído |
| M5 — Modelo em escala | ⚠️ 2/3 DoDs — o telefônico ficou **deferido** por limite de dado ([evidência](jvscribe/results/m5-final-results.md)) |
| M6 — Runtime otimizado · M7 — Escopo de produto · M8 — Piloto | ⏳ próximos |
| M9 — Governança de artefato e reprodutibilidade | ⏳ próximo |

> A tabela reflete o `ROADMAP.md`, que é a fonte da verdade. Um teste
> ([`test_readme_links.py`](jvscribe/tests/test_readme_links.py)) garante que todo link interno
> daqui resolve — em 2026-07-30, 5 de 5 apontavam para arquivos removidos por engano.

### A arquitetura, decidida por medição

Dos 5 candidatos avaliados contra 8 critérios, a família **CTC/transducer** venceu o critério
de velocidade em CPU (M2). O piloto comparativo de M4 então **travou o finalista**:
**Zipformer-CTC `medium` (64M), int8, com cabeça de fonema auxiliar** —
[ADR 0003](knowledge-base/adrs/0003-m4-finalist-medium.md), que supersede o eixo de tamanho do
[ADR 0002](knowledge-base/adrs/0002-m4-architecture-finalist.md) após medição de soak e carga.

`[MEDIDO]` head-to-head com parâmetros equivalentes: Zipformer domina Conformer nos dois eixos
de acurácia (WER 28,86% vs 31,57%, IC95% do delta excluindo 0). A cabeça de fonema levou o
medium a **27,49% WER** ([evidência](jvscribe/results/m4-medium-phoneme-ablation-results.md)).

**O achado de M2 que orientou a escolha da família** `[MEDIDO]`: em CPU, na mesma máquina e na mesma
clip de 12 s, o transducer é **~2× mais rápido** que o AED em tamanho comparável —
Zipformer 20M = 15,90 ± 2,06× tempo real vs Moonshine tiny 27M = 7,93 ± 0,72×
(n=10, separação estatística limpa;
[medição completa](knowledge-base/measurements/m2-rtfx-candidates.md)). A razão é
arquitetural: o AED é autoregressivo (custo cresce com os tokens gerados), o
transducer/CTC faz um passe (custo fixo pelos frames de áudio).

> Nota de honestidade: esses números são medidos numa **máquina de dev, não no piso
> da frota BYOD** (ainda `[DESCONHECIDO]`) — o que transfere é a *razão entre
> arquiteturas*, não o valor absoluto. A magnitude "~2×" precisa de confirmação sob
> soak com carga concorrente em M4; reportar dispersão já baixou uma estimativa
> anterior de "~3×" (a diferença era carga de CPU).

---

## Como navegar

| Documento | Papel |
|---|---|
| [`PRD.md`](PRD.md) | Requisitos (RF/RNF), arquitetura, pendências, riscos, questões abertas |
| [`ROADMAP.md`](ROADMAP.md) | Milestones M0–M9 com Definition of Done |
| [`CHANGELOG.md`](CHANGELOG.md) | Toda mudança relevante |
| [`knowledge-base/adrs/`](knowledge-base/adrs/) | Decisões de arquitetura com racional |
| [`knowledge-base/discoveries/blueprints/`](knowledge-base/discoveries/blueprints/) | Blueprints de investigação (prior art) |
| [`.claude/rules/asr-evidence-discipline.md`](.claude/rules/asr-evidence-discipline.md) | Contrato de evidência — todo número carrega rótulo de proveniência |

## Disciplina de evidência

Todo número neste projeto carrega um rótulo: `[MEDIDO]` (rodamos o experimento),
`[LITERATURA]` (reportado por terceiro), `[FONTE-REPO]` (fato lido no código de um
peer clonado), `[ESTIMATIVA]` (derivado por cálculo) ou `[DESCONHECIDO]`. Sem rótulo,
o número não existe. É a vacina contra decidir por benchmark que não transfere.
