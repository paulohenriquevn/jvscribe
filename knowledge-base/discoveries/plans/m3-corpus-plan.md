# Discovery Plan: M3 — Pipeline de corpus (pseudo-labeling + manifests Lhotse)

> **Version 1.1** (absorveu EC-1..EC-6 de `knowledge-base/reviews/m3-corpus-edge-cases-2026-07-25.md`) — Investiga como construir o pipeline de corpus de M3 sem re-inventar: (1) como o **lhotse** aplica augmentação **on-the-fly** sem materializar em disco e se roda **sem torch**, (2) como implementar o **filtro por concordância** entre dois transcritores (receita Granary), (3) como rodar os **dois transcritores** já em cache (faster-whisper + parakeet-TAGARELA) e construir manifests, e (4) a **licença de cada fonte de corpus** PT-BR com veredito comercial + resposta honesta a **Q-09** (acesso ao Cem Mil Podcasts). Blueprint esperado: o desenho do pipeline com trade-offs medidos/lidos e a tabela de licenças.

**Slug:** `m3-corpus`
**Owner:** `speech-data-scientist` (lidera) · `audio-dsp-engineer` (augmentação) · `technical-program-lead` (Q-09)
**Created:** 2026-07-25
**Time budget:** 8h (breakdown em ADR D1)

## Context

M3 é o **risco dominante do projeto** (`ROADMAP.md` § M3; `CLAUDE.md` § "Contexto que evita erros repetidos"): 8.972 h disponíveis contra as 15.000–94.000 h que a receita de referência usa para modelos pequenos monolíngues treinados do zero. O DoD de M3 (`ROADMAP.md`) exige quatro entregáveis: (1) Q-09 respondida (acesso ao Cem Mil Podcasts, ~76k h), (2) pipeline de pseudo-labeling com **filtro por concordância** (receita Granary — "dados processados rendem performance equivalente com ~50% do volume"), (3) manifests Lhotse com augmentação telefônica **on-the-fly** (nunca em disco), (4) volume final + **licença de cada fonte mapeada** com veredito comercial.

O reconhecimento inicial já expôs dois riscos técnicos que esta discovery deve resolver antes de qualquer plano de implementação:

- **`lhotse` 1.33 está instalado mas não importa** — `lhotse/setup.py:160` lista `torch` como dep core e `lhotse/lhotse/audio/backend.py:15` faz `import torch` no topo; o torch foi removido do ambiente (memória de baseline). O item 3 do DoD depende de resolver isto.
- **A augmentação telefônica de M1 já roda em `sox` sem torch/lhotse** (`scripts/telephone_augment.sh` — 16k→8k + banda 300-3400 + G.711 a-law). A questão é como integrá-la ao lhotse como transform on-the-fly sem materializar em disco.

Regras do projeto que qualquer padrão emprestado deve respeitar: `asr-evidence-discipline.md` (§ 1 rótulos de proveniência; § 3 #10 pseudo-label nunca no test set), `testing.md` (§ 3 determinismo; pirâmide), `error-handling.md` (§ 2 fail-fast), `parsimony-ladder.md` (rung 4 — reusar lhotse/sox já presentes, não re-implementar).

## Objective

O blueprint deve permitir **decidir o desenho do pipeline de corpus de M3** — como gerar pseudo-labels filtrados por concordância e como servir augmentação telefônica on-the-fly via manifests — com viabilidade de dependências resolvida e licenças mapeadas.

- [ ] Todas as research questions respondidas com citação a `knowledge-base/references/` (ou fonte factual declarada para as questões de licença/Q-09)
- [ ] Tabela comparativa preenchida para lhotse (on-the-fly, torch) + icefall (filtro) + os 2 transcritores
- [ ] ≥ 1 proposta de decisão concreta por research question
- [ ] `/discover-confidence` verdict ≥ SHIPPABLE_WITH_CAVEATS

## In-Scope / Out-of-Scope

### In-Scope (por reference project)

| Project | In-scope subdirectories | Reason |
|---|---|---|
| `knowledge-base/references/lhotse/` | `lhotse/dataset/cut_transforms/`, `lhotse/cut/`, `lhotse/audio/`, `lhotse/bin/modes/`, `setup.py`, `test/dataset/`, `test/augmentation/` | Manifests + augmentação on-the-fly (DoD item 3) — a lib central de M3 |
| `knowledge-base/references/icefall/` | `egs/*/ASR/local/filter_cuts.py` (padrão de filtragem de cuts) | Base do filtro por concordância (DoD item 2) |
| `knowledge-base/references/sherpa-onnx/` | `python-api-examples/` (offline recognizer) | Rodar parakeet-TAGARELA para pseudo-labels (DoD item 2) |

### Out-of-Scope (explícito)

| Project / Subdir | Why excluded |
|---|---|
| `knowledge-base/references/lhotse/docs/` | Docs de marketing, não fonte de verdade |
| `knowledge-base/references/*/{build,dist,.venv,__pycache__}/` | Artefatos de build |
| `knowledge-base/references/{moonshine,funasr,parakeet-rs,tract,vibeasr-cpp}/` | Não tocam corpus/manifests/pseudo-label — irrelevantes a M3 |
| Treino/fine-tune de modelo | É M4/M5 — M3 só entrega o corpus e o pipeline |

## ADRs

### D1 — Time budget + stop conditions

**Decision:** lhotse 5h (a lib central, 4 questões), icefall 1h (1 questão de padrão), sherpa-onnx + factual/web 2h (transcritores + licenças/Q-09).

**Rationale:** lhotse concentra o risco técnico (torch, on-the-fly) e três dos quatro corners; icefall só fornece o padrão de `filter_cuts`; a parte factual (licenças, Q-09) é leitura de cards + web autoritativa, não código.

**Alternatives considered:** split igual (rejeitado — desperdiça budget no icefall), single-project lhotse (rejeitado — perde o filtro e as licenças).

**Stop condition — per question (mandatory):** quando a Fase A de uma questão retorna vazio após 3 variações de query, marcar BLOCKED com razão "Fase A exhausted" e seguir. NUNCA preencher com hotspots de outra questão.

**Stop condition — per project (mandatory):** budget esgotado com N questões pendentes → marcar as restantes BLOCKED "budget exhausted". Se todo projeto restante está `done` ou honestamente `blocked`, emitir `<promise>BLUEPRINT_BLOCKED</promise>` (não COMPLETE) com o relatório honesto.

**Anti-pattern:** NUNCA fabricar respostas da Fase B para fechar questão cuja Fase A esgotou (Regra Inquebrável 3; `asr-evidence-discipline` § 6).

**Consequences:** o halt-loop para num projeto quando o budget esgota; questões bloqueadas viram semente da próxima discovery.

### D2 — Investigation depth

**Decision:** Ler end-to-end os módulos de transform/cut do lhotse e o `filter_cuts.py` do icefall; para licenças/Q-09, ler o `LICENSE`/dataset-card e citar a linha que exibe o veredito.

**Rationale:** o mecanismo on-the-fly e o filtro por concordância são a substância do blueprint — grep-only perderia o intent. Licenças exigem a citação exata (`asr-evidence-discipline` § 1: número/fato sem rótulo não existe).

**Consequences:** mais lento por questão, mas cada afirmação do blueprint resolve em `arquivo:linha`.

### D3 — M3 estende o método de discover para investigação factual (não só código de peers)

**Decision:** As questões Q3 (receita Granary) e Q5 (licenças + Q-09) têm componente **factual/externo** que não vive nas references clonadas. Método declarado: (a) padrão de código no peer quando existir (icefall `filter_cuts` para Q3), (b) `LICENSE` + dataset-card local em cache HF, (c) WebFetch de fonte autoritativa (páginas HF de dataset, ToS) para o que não é local. O que exigir **negociação humana** (acesso efetivo ao Cem Mil Podcasts bruto) fica `[DESCONHECIDO]` honesto com "o que seria preciso para saber".

**Rationale:** o DoD de M3 é metade engenharia, metade factual/negociação (o próprio ROADMAP aloca `technical-program-lead` a Q-09 "porque é negociação, não engenharia"). Forçar tudo no molde "código de peer" produziria fabricação; honestidade (Regra 3) exige declarar o método factual.

**Consequences:** o blueprint carregará rótulos `[LITERATURA]`/`[FONTE-REPO]`/`[DESCONHECIDO]` nas questões factuais; a resposta a Q-09 pode ser "acesso não confirmável autonomamente — eis os termos publicados e o que falta negociar", que é uma resposta **válida** ao DoD.

### D4 — Fallback se o lhotse exigir torch (EC-5); discovery lê, não executa (EC-6)

**Decision:** Q4 existe para descobrir se `torch` é obrigatório. Se for, dois caminhos ficam registrados no blueprint, a decidir no plano de implementação com a evidência: (a) **torch CPU-only** (leve, sem CUDA) reusando lhotse integralmente (parsimony rung 4 — reusar); (b) **manifests JSON próprios + augmentação `sox` on-the-fly via callable**, sem lhotse (parsimony rung 6 — mínimo que funciona), só se (a) for inviável na máquina.

**Rationale:** a discovery **lê** o código clonado do lhotse (não o executa) — Q1/Q2/Q6/Q8 respondem "como o lhotse faz X" por leitura e não dependem de o lhotse importar no ambiente. A viabilidade de *rodar* (Q4) é separada e informa só a implementação; não bloqueia a discovery (EC-6).

**Consequences:** o blueprint entrega o desenho independente da resolução de torch; a escolha (a)/(b) é uma decisão explícita do `/to-plan` de M3, com a evidência de Q4 na mão.

## Research Questions

| # | Question | Corner | Reference project(s) | Fase A (broad — grep/glob map) | Fase B (deep — Read) | Expected answer shape |
|---|---|---|---|---|---|---|
| Q1 | Como o lhotse aplica augmentação/perturbação **on-the-fly** sem materializar áudio em disco? Qual o mecanismo (CutSet lazy + cut_transforms aplicados no dataloader)? | techniques | `knowledge-base/references/lhotse/` | `grep -rn "class .*Transform\|def __call__\|perturb" lhotse/lhotse/dataset/cut_transforms/` | Ler `perturb_speed.py`, `perturb_volume.py` e `lhotse/cut/set.py` (`.perturb_*`/`.map`) para capturar o contrato lazy | Descrição do mecanismo + `arquivo:linha` do transform e do ponto lazy |
| Q2 | Como integrar a **cadeia telefônica de M1** (`sox`: 8k + banda + a-law) como transform **on-the-fly** no lhotse, sem escrever em disco? | techniques | `knowledge-base/references/lhotse/`, `scripts/telephone_augment.sh` | `grep -rn "class .*Transform\|CutTransform\|def __call__" lhotse/lhotse/dataset/cut_transforms/*.py` | Ler o padrão de um transform custom + `telephone_augment.sh` para mapear a cadeia sox ao contrato | Proposta: custom transform (ou WavAugment/callable) que aplica a cadeia em memória + citações |
| Q3 | Qual a mecânica do **filtro por concordância** entre 2 transcritores (receita Granary)? Métrica (WER/CER entre hipóteses) e threshold de descarte? | techniques | `knowledge-base/references/icefall/`, web (Granary/NVIDIA) | `grep -rn "def filter\|wer\|cer\|threshold\|agree" icefall/egs/commonvoice/ASR/local/filter_cuts.py` | Ler `filter_cuts.py` (padrão de descarte por critério) como fonte **primária local**; WebFetch do Granary é **best-effort** `[LITERATURA]` (EC-1) | Definição da métrica de concordância + threshold recomendado + citação (peer `[FONTE-REPO]` + `[LITERATURA]` se acessível). **EC-1:** se o WebFetch falhar (allowlist vazio), derivar a métrica do padrão do peer e rotular honestamente — nunca inventar threshold |
| Q4 | O lhotse consegue construir manifests + aplicar augmentação on-the-fly **sem torch**, ou torch é obrigatório? Qual o custo mínimo (torch CPU-only)? | deps | `knowledge-base/references/lhotse/` | `grep -n "torch\|soundfile\|audioread\|install_requires" lhotse/setup.py lhotse/lhotse/audio/backend.py` | Ler `setup.py:150-165` + `audio/backend.py:15,127` (fallback soundfile) para o caminho mínimo | Veredito: torch obrigatório? qual subconjunto roda sem ele + citação |
| Q5 | Qual a **licença de cada fonte de corpus** PT-BR candidata (FLEURS, Common Voice, MLS, TAGARELA/parakeet, Cem Mil Podcasts) e o **veredito de uso comercial**? Q-09: há acesso ao Cem Mil Podcasts bruto e sob que termos? | deps (legal) | dataset-cards em cache HF + `LICENSE` dos peers + web autoritativa | `find ~/.cache/huggingface -iname "README*" -path "*fleurs*"`; `grep -irn "license\|commercial\|CC-BY\|non-commercial" <cards>` | Ler cada card/LICENSE **local**; WebFetch das páginas HF só para o que faltar (best-effort) | Tabela: fonte → licença → veredito comercial → rótulo. **EC-2:** priorizar fonte local; o que não for local vira `[DESCONHECIDO]` com "o que falta consultar/negociar" — nunca veredito sem fonte. Q-09 bruto = negociação humana → `[DESCONHECIDO]` honesto com os termos publicados |
| Q6 | Como o lhotse expõe **construção de manifests** (RecordingSet/SupervisionSet) a partir de um diretório de áudio — CLI (`lhotse/bin`) ou API? | tools | `knowledge-base/references/lhotse/` | `ls lhotse/lhotse/bin/modes/`; `grep -rn "def recording_set\|RecordingSet.from_dir\|from_recordings" lhotse/lhotse/audio/recording_set.py` | Ler o modo de CLI + `RecordingSet.from_dir`/`SupervisionSet` para o fluxo mínimo | Passo-a-passo (CLI + API) para gerar manifest de um dir de WAVs + citações |
| Q7 | Como rodar os **2 transcritores** para gerar hipóteses PT-BR — parakeet-TAGARELA (onnx) via sherpa-onnx e faster-whisper? Deps/licenças das libs? | tools | `knowledge-base/references/sherpa-onnx/`, cache HF | `ls ~/.cache/.../parakeet-tdt-*-TAGARELA-onnx`; `grep -rln "OfflineRecognizer\|from_transducer\|from_paraformer" sherpa-onnx/python-api-examples/` | Ler o exemplo offline do sherpa + os arquivos do modelo TAGARELA no cache | Comando/API para cada transcritor + veredito de viabilidade na RAM disponível |
| Q8 | Como o lhotse **testa** cuts/augmentação on-the-fly contra áudio real (fixtures)? Padrão de teste a replicar (determinismo)? | tests | `knowledge-base/references/lhotse/` | `ls lhotse/test/augmentation/ lhotse/test/dataset/`; `grep -rn "def test_.*perturb\|def test_.*transform" lhotse/test/dataset/test_cut_transforms.py` | Ler os testes de `test_cut_transforms.py` + `test/augmentation/` para o padrão determinístico | Padrão de teste (fixture + assert determinístico) a replicar em M3 + citações |

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
| Before answering Qx | O path `knowledge-base/references/{...}` declarado na Fase A existe | Marcar Qx BLOCKED "path not found", seguir |
| Per-question Fase A budget | Fase A retornou ≥ 1 hotspot OU 3 variações tentadas | Após 3 retries vazios, Qx BLOCKED "Fase A exhausted"; seguir |
| Q3/Q5 factual | Fonte factual (card/LICENSE/URL autoritativa) aberta antes de afirmar licença/veredito | Se inacessível, marcar o item `[DESCONHECIDO]` com "o que falta"; nunca inventar veredito |
| Q7 RAM (EC-3) | O fluxo carrega **um transcritor por vez** (parakeet *ou* faster-whisper), libera antes do próximo; RAM de pico medida | Se ambos residentes, refatorar para sequencial antes de afirmar viabilidade |
| Q1/Q2 lazy (EC-4) | O caminho on-the-fly citado é lazy de verdade (transform no dataloader, sem `compute_and_store_features`) | Se exigir features materializadas, registrar como restrição, não "on-the-fly puro" |
| After answering Qx | Seção do blueprint sob Qx tem ≥ 1 citação | Re-iterar Qx (1 retry) |
| Per-project time budget | Budget do projeto não esgotado | Ao esgotar, restantes BLOCKED "budget exhausted"; avançar |
| Before promising complete | Os 4 corners têm seção preenchida | Recusar promise, continuar |

## Acceptance Criteria

- [ ] Todas as research questions respondidas OU marcadas BLOCKED com razão
- [ ] Os quatro corners com seção preenchida no blueprint
- [ ] Cada citação de código aponta para um `knowledge-base/references/{...}` real; cada afirmação de licença aponta para card/LICENSE/URL com rótulo
- [ ] ≥ 1 ADR no blueprint sintetiza as decisões (desenho do pipeline)
- [ ] Time budget respeitado por projeto
- [ ] `/discover-confidence` verdict ≥ SHIPPABLE_WITH_CAVEATS
- [ ] Blueprint salvo em `knowledge-base/discoveries/blueprints/m3-corpus-blueprint.md`

## Global Definition of Done

- [ ] Todas as fases (plan → edge-cases → plan-confidence → execute → confidence → improve se preciso)
- [ ] Verdict final de `/discover-confidence` no header do blueprint
- [ ] Zero citação fabricada
- [ ] Coverage Matrix 100%
- [ ] ADRs referenciam ≥ 1 regra do projeto (`asr-evidence-discipline.md` § 1/§ 3, `testing.md` § 3, `parsimony-ladder.md` rung 4)
