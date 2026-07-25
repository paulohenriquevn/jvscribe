# Macaw Voice — transcrição PT-BR em tempo real, sobre CPU

Transcreva atendimento em português brasileiro **ao vivo, no notebook do próprio
atendente** — sem GPU, sem enviar áudio para a nuvem, sem custo por hora transcrita.

A aposta é **especialização**: um modelo que só faz PT-BR telefônico cabe em dezenas
de milhões de parâmetros onde um multilíngue de 600M não fecha tempo real em CPU.

Escopo deste repositório: **o modelo** e **o motor de inferência**. Plataforma de
frota, compliance LGPD e UI ficam fora (`PRD.md` § 3.2).

---

## Estado do projeto

Projeto em **discover contínuo, orientado por evidência**: a arquitetura não é
escolhida por convicção, é medida. Progresso por milestones (`ROADMAP.md`, M0–M8).

| Milestone | Estado |
|---|---|
| M0 — Fundação do runtime | ✅ concluído |
| M1 — Instrumentação e régua de medição | ✅ concluído (v0.2.1) |
| **M2 — Decisão de arquitetura** | ✅ **concluído (v0.3.0)** |
| M3 — Corpus (paralelo) · M4 — Piloto comparativo | ⏳ próximos |

### O que M2 concluiu

Dos 5 candidatos avaliados contra 8 critérios, a família **CTC/transducer** venceu o
critério de velocidade em CPU. M2 nomeia **2 finalistas a pilotar em M4** —
**Zipformer+CTC** e **FastConformer+CTC** — com **Moonshine-AED** como braço de
controle. **O vencedor não está travado**: WER em 8 kHz de call center, RTFx sob carga
e equivalência batch≡streaming são medidos no piloto de M4.

**Achado que sustentou a decisão** `[MEDIDO]`: em CPU, na mesma máquina e na mesma
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
| [`ROADMAP.md`](ROADMAP.md) | Milestones M0–M8 com Definition of Done |
| [`CHANGELOG.md`](CHANGELOG.md) | Toda mudança relevante |
| [`knowledge-base/adrs/`](knowledge-base/adrs/) | Decisões de arquitetura com racional |
| [`knowledge-base/discoveries/blueprints/`](knowledge-base/discoveries/blueprints/) | Blueprints de investigação (prior art) |
| [`.claude/rules/asr-evidence-discipline.md`](.claude/rules/asr-evidence-discipline.md) | Contrato de evidência — todo número carrega rótulo de proveniência |

## Disciplina de evidência

Todo número neste projeto carrega um rótulo: `[MEDIDO]` (rodamos o experimento),
`[LITERATURA]` (reportado por terceiro), `[FONTE-REPO]` (fato lido no código de um
peer clonado), `[ESTIMATIVA]` (derivado por cálculo) ou `[DESCONHECIDO]`. Sem rótulo,
o número não existe. É a vacina contra decidir por benchmark que não transfere.
