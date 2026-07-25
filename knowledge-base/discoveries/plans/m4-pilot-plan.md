# Discovery Plan: M4 — Piloto comparativo (treino dos finalistas + G2P + custo)

> **Version 1.1** (absorveu EC-1..EC-5 de `knowledge-base/reviews/m4-pilot-edge-cases-2026-07-25.md`) — Investiga o que M4 precisa para decidir arquitetura/tamanho/supervisão fonética com dado próprio por fração do custo: (1) como treinar **Zipformer-CTC** do zero na recipe icefall (config, tamanho, épocas, data prep), (2) como a **supervisão fonética auxiliar** é implementada (cabeça CTC de fonemas, multi-task), (3) a qualidade do **G2P PT-BR** (phonemizer+espeak-ng) e como medir sua taxa de erro (Q-08), (4) o **ambiente de treino reprodutível** (k2+icefall+GPU, compatibilidade, custo) e como **estimar GPU-horas/custo**. Blueprint: o desenho do piloto + a estimativa de custo que decide a infraestrutura de M5.

**Slug:** `m4-pilot`
**Owner:** `asr-chief-scientist` (lidera) · `ml-infra-engineer` (treino reprodutível/custo) · `ptbr-phonetics-scientist` (G2P/ablação) · `evaluation-scientist` (significância)
**Created:** 2026-07-25
**Time budget:** 8h (breakdown em ADR D1)

## Context

M4 é o **primeiro milestone que testa a tese central do projeto** (especialização cabe onde multilíngue não cabe) — decidir arquitetura, tamanho e supervisão fonética com dado próprio por uma fração do custo do treino completo (`ROADMAP.md § M4`). Depende de M2 (2 finalistas: Zipformer+CTC, FastConformer+CTC — `knowledge-base/adrs/0001-m2-architecture-finalists.md`) e M3 (pipeline de corpus — `scripts/corpus/`), ambos concluídos (v0.3.0, v0.4.0).

O reconhecimento inicial já expôs a fronteira de viabilidade que esta discovery deve quantificar:

- **G2P PT-BR é factível AGORA em CPU** — `phonemize('bom dia, tudo bem?', language='pt-br', backend='espeak')` → `'boŋ dʒiæ tudʊ beɪŋ'` (`phonemizer 3.3.2` + `espeak-ng`). A taxa de erro (Q-08) é medível sem GPU.
- **O treino EXIGE GPU + k2 compatível** — `import k2` reclama do `torch 2.13.0+cpu` instalado (k2 é compilado contra versão/CUDA específica). Treinar Zipformer-CTC do zero em 500 h é dias de GPU, não roda nesta máquina (i7-1355U, sem GPU). Este é o muro que a discovery quantifica em GPU-horas/custo para a decisão de infraestrutura.

Regras que qualquer padrão emprestado deve respeitar: `asr-evidence-discipline.md` (§ 1 rótulos; § 3 #6 WER público ≠ call center 8 kHz; § 3 #1 GPU≠CPU; § 3 #12 IC), `testing.md`, `parsimony-ladder.md` (rung 4 — reusar icefall/phonemizer, não reimplementar).

## Objective

O blueprint deve permitir **decidir o desenho do piloto de M4 e a infraestrutura de treino**, com a estimativa de GPU-horas/custo que fecha o orçamento de M5.

- [ ] Todas as research questions respondidas com citação a `knowledge-base/references/` (ou fonte factual/medição declarada)
- [ ] Tabela comparativa do fluxo de treino (icefall Zipformer) + G2P + ambiente
- [ ] ≥ 1 proposta de decisão concreta por research question, incluindo a estimativa de custo
- [ ] `/discover-confidence` verdict ≥ SHIPPABLE_WITH_CAVEATS

## In-Scope / Out-of-Scope

### In-Scope (por reference project)

| Project | In-scope subdirectories | Reason |
|---|---|---|
| `knowledge-base/references/icefall/` | `egs/librispeech/ASR/zipformer/` (`train.py`, `model.py`, `ctc_decode.py`, `scaling.py`, `finetune.py`) | A recipe de treino Zipformer-CTC — o "como treinar" (DoD 1, 2, 4) |
| `knowledge-base/references/parakeet-rs/` | `README.md` (FastConformer/TDT) | O 2º finalista (FastConformer) — viabilidade de treino/recipe |

### Out-of-Scope (explícito)

| Project / Subdir | Why excluded |
|---|---|
| Treino real dos modelos (GPU) | É a execução de M4, não a discovery; a discovery entrega o desenho + estimativa |
| `knowledge-base/references/{lhotse,funasr,moonshine,sherpa-onnx,tract,vibeasr-cpp}/` | Não são recipes de treino Zipformer/FastConformer |
| NeMo (FastConformer recipe) | Não clonado (`_catalog.md` — descartado por tamanho); FastConformer via `[LITERATURA]`/parakeet-rs |

## ADRs

### D1 — Time budget + stop conditions

**Decision:** icefall 4h (recipe de treino, 3 questões), G2P/phonemizer 2h (medição Q-08), infra/custo 2h (estimativa GPU-horas).

**Rationale:** icefall concentra o "como treinar" (o núcleo do piloto); G2P é medição CPU factível agora; a estimativa de custo é cálculo que decide a infraestrutura.

**Stop condition — per question:** Fase A vazia após 3 variações → BLOCKED "Fase A exhausted", seguir. NUNCA preencher com hotspots de outra questão.

**Stop condition — per project:** budget esgotado → questões restantes BLOCKED "budget exhausted". Todas `done`/`blocked` → `<promise>BLUEPRINT_BLOCKED</promise>` com relatório honesto.

**Anti-pattern:** NUNCA fabricar número de treino/custo sem cálculo explícito (Regra 3; `asr-evidence-discipline § 6`).

### D2 — Investigation depth

**Decision:** Ler end-to-end os pontos-chave do `train.py`/`model.py` do icefall (config de tamanho, CTC head, aux loss); para G2P, **medir** de verdade (phonemizer sobre um conjunto PT-BR); para custo, estimativa com fórmula explícita.

**Rationale:** o desenho do piloto exige entender a recipe, não grep superficial; Q-08 exige medição (§ 1 `[MEDIDO]`); custo exige fórmula (`[ESTIMATIVA]`).

### D3 — GPU-horas/custo é `[ESTIMATIVA]` com fórmula, não `[MEDIDO]`

**Decision:** a estimativa de GPU-horas por época (DoD 5) é `[ESTIMATIVA]` derivada por fórmula (params × tokens × FLOPs/token ÷ throughput de GPU de referência), com premissas explícitas — não um treino medido.

**Rationale:** treinar para medir é o próprio M4-execução (GPU); a discovery entrega a estimativa que decide se vale investir. `asr-evidence-discipline § 1`: `[ESTIMATIVA]` que sustenta decisão bloqueante deve virar `[MEDIDO]` antes de travar — aqui a decisão (investir GPU) é do dono, informada pela estimativa.

**Consequences:** o blueprint entrega uma faixa de custo com premissas; o número exato vem do primeiro run real de treino (execução de M4, gated pela decisão de infra).

## Research Questions

| # | Question | Corner | Reference/fonte | Fase A (broad) | Fase B (deep) | Expected answer shape |
|---|---|---|---|---|---|---|
| Q1 | Como treinar **Zipformer-CTC do zero** na recipe icefall? Config de tamanho (~30/80/123M), data prep (manifests Lhotse de M3), nº de épocas, otimizador? | techniques | `knowledge-base/references/icefall/egs/librispeech/ASR/zipformer/` | `grep -nE "num_encoder_layers|encoder_dim|def get_params|world_size|num_epochs|ScaledAdam" icefall/.../zipformer/train.py` | Ler `train.py` (config de tamanho, loop de treino) + `scaling.py` (ScaledAdam) | Passo-a-passo de treino + como parametrizar os 3 tamanhos + `arquivo:linha` |
| Q2 | Como a **supervisão fonética auxiliar** (cabeça CTC de fonemas) é implementada? Multi-task loss (transducer + CTC aux)? Peso? | techniques | `knowledge-base/references/icefall/egs/librispeech/ASR/zipformer/` | `grep -nE "use_ctc|ctc_loss|aux|attention_decoder|--ctc-loss-scale" icefall/.../zipformer/model.py icefall/.../zipformer/train.py` | Ler `model.py` (forward multi-task) + os flags de CTC/aux em `train.py` | Mecanismo da cabeça auxiliar + como fazer a ablação (com/sem) + citações |
| Q3 | **G2P PT-BR (Q-08):** qual a qualidade do phonemizer+espeak-ng em PT-BR? Cobertura, determinismo, concordância, falhas em casos difíceis? | techniques | `phonemizer 3.3.2` + `espeak-ng` (medição) | rodar `phonemize(...)` sobre um conjunto PT-BR de palavras/frases | medir cobertura (% sem OOV/falha), determinismo, concordância entre variantes, inspeção de casos difíceis (EC-1) | **`[MEDIDO]`**: cobertura + determinismo + concordância + inventário de falhas. **EC-1:** PER absoluto exige gold fonético humano (inexistente localmente) → `[DESCONHECIDO]` com "precisa de anotador"; NÃO fabricar taxa de erro |
| Q4 | **Ambiente de treino** (k2+icefall+torch): compatibilidade de versão, GPU obrigatória, o que roda em CPU? | deps | `knowledge-base/references/icefall/` + ambiente | `python3 -c "import k2"` (já falha c/ torch 2.13 cpu); `grep -rn "torch\|k2\|cuda" icefall/egs/librispeech/ASR/zipformer/train.py` | Ler os requisitos de import/CUDA do train.py + a mensagem de erro do k2 | Veredito: k2 exige torch/CUDA específico; treino é GPU-only; caminho de setup reprodutível |
| Q5 | **G2P deps** (phonemizer, espeak-ng): licença, cobertura PT-BR, determinismo? | deps | `phonemizer`/`espeak-ng` | `pip show phonemizer`; `espeak-ng --version` | ler licença + testar determinismo (mesma entrada → mesma saída) | Licenças + veredito de uso comercial + determinismo |
| Q6 | **Ambiente reprodutível barato** (vast.ai/Droplet GPU): checkpoint/resume, custo/hora de GPU, tempo por run? | tools | `PRD.md` § 9 + `[LITERATURA]` | ler `PRD.md` § plano de fases (orçamento GPU) | web/literatura de preço de GPU preemptível (best-effort) | Opções de infra + $/hora + esboço de checkpoint/resume |
| Q7 | **Estimativa de GPU-horas por época** (DoD 5): fórmula que fecha o orçamento de M5? | tools | cálculo `[ESTIMATIVA]` | derivar FLOPs ≈ 6·params·tokens; tokens de 500 h; throughput de GPU de referência `[LITERATURA]` | montar a fórmula + faixa de custo | GPU-horas/época + custo estimado por tamanho + premissas explícitas |
| Q8 | Como a recipe icefall **valida o treino** (test set, WER, decodificação CTC)? | tests | `knowledge-base/references/icefall/egs/librispeech/ASR/zipformer/` | `grep -nE "def decode|wer|ctc_decode|compute_loss|greedy" icefall/.../zipformer/ctc_decode.py` | Ler `ctc_decode.py` (protocolo de avaliação) | Protocolo WER + como medir WER×RTFx no piloto + citações |

## Coverage Matrix

| Corner | Questions mapped | Status |
|---|---|---|
| Integration tests | Q8 | Covered |
| Dependencies | Q4, Q5 | Covered |
| Tools | Q6, Q7 | Covered |
| Techniques | Q1, Q2, Q3 | Covered |

**Coverage: 4/4 corners covered (100%)**

## Halt-loop Checkpoints

| Checkpoint | Assertion | Action if fails |
|---|---|---|
| Before answering Qx | O path `knowledge-base/references/{...}` declarado existe | Marcar Qx BLOCKED "path not found", seguir |
| Q3 medição (Q-08) | G2P rodado de verdade antes de afirmar qualquer número; sem gold PT-BR, medir cobertura/determinismo/concordância e rotular; PER absoluto = `[DESCONHECIDO]` (EC-1) | Não inventar taxa de erro; `[DESCONHECIDO]` com "precisa de anotador" |
| Q1 tamanhos (EC-3) | Confirmar se os 3 tamanhos (30/80/123M) vêm de configs prontas OU de escalar `num_encoder_layers`/`encoder_dim` | Se só há 1 config, registrar que os outros 2 são derivados por escala, não "3 recipes prontas" |
| Q6/Q7 custo (EC-2) | Números de $/GPU-hora e throughput rotulados `[LITERATURA]` (ordem de grandeza, não cotação); fórmula de Q7 explícita | Sem fonte → faixa `[LITERATURA]` com ressalva; nunca cotação firme |
| Q7 custo | Fórmula explícita + premissas antes de qualquer número de GPU-hora | Sem fórmula → `[DESCONHECIDO]`, não chute |
| Q4 GPU | Afirmar "treino é GPU-only" só com a evidência do erro k2 + requisito CUDA lido | Registrar honestamente o que foi verificado vs assumido |
| Before promising complete | Os 4 corners com seção preenchida | Recusar promise, continuar |

## Acceptance Criteria

- [ ] Todas as research questions respondidas OU marcadas BLOCKED com razão
- [ ] Os quatro corners com seção preenchida no blueprint
- [ ] Cada citação de código aponta para um `knowledge-base/references/{...}` real; G2P Q-08 tem número `[MEDIDO]`; custo tem fórmula `[ESTIMATIVA]`
- [ ] ≥ 1 ADR no blueprint sintetiza o desenho do piloto + a decisão de infra
- [ ] `/discover-confidence` verdict ≥ SHIPPABLE_WITH_CAVEATS
- [ ] Blueprint salvo em `knowledge-base/discoveries/blueprints/m4-pilot-blueprint.md`

## Global Definition of Done

- [ ] Todas as fases (plan → edge-cases → plan-confidence → execute → confidence)
- [ ] Verdict final no header do blueprint
- [ ] Zero citação fabricada; G2P medido; custo com fórmula
- [ ] Coverage Matrix 100%
- [ ] ADRs referenciam ≥ 1 regra (`asr-evidence-discipline § 1/§ 3`, `parsimony-ladder` rung 4)
