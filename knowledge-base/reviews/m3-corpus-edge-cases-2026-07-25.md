# Discover Edge Case Review — m3-corpus

Date: 2026-07-25
Discovery plan analyzed: knowledge-base/discoveries/plans/m3-corpus-plan.md
Research questions analyzed: 8
Edge cases found: 6 (MUST FIX: 2, SHOULD TEST: 2, DOCUMENT: 2)

## MUST FIX

### EC-1: `discover-web-allowlist.txt` está vazio — WebFetch da receita Granary pode falhar
- **Affected question:** Q3
- **Family:** Method
- **Scenario:** Q3 declara "WebFetch do paper/model-card Granary". O allowlist de web do projeto está **vazio** (verificado); o WebFetch pode ser bloqueado ou não haver domínio autoritativo declarado. O execute trava tentando uma fonte inacessível.
- **Impact:** Q3 fica sem a parte `[LITERATURA]` e o filtro por concordância fica sem threshold citável.
- **Suggested fix:** Q3 declara fonte **primária local** (padrão de descarte do icefall `filter_cuts.py`) e trata a receita Granary como `[LITERATURA]` **best-effort** — se o WebFetch falhar, a métrica de concordância é derivada do padrão do peer + rotulada honestamente, nunca inventada.

### EC-2: Card do Cem Mil Podcasts pode não estar em cache; licenças via web dependem do allowlist vazio
- **Affected question:** Q5
- **Family:** Method / Citation
- **Scenario:** Q5 mapeia licenças de 5 fontes; algumas (Cem Mil Podcasts, MLS) podem não ter card em cache HF local, e a web (para completar) esbarra no allowlist vazio. Q-09 (acesso ao bruto) é negociação humana, não consultável.
- **Impact:** Tabela de licenças incompleta ou, pior, veredito comercial fabricado.
- **Suggested fix:** Q5 prioriza `LICENSE`/cards **locais** (FLEURS, parakeet-TAGARELA, o que estiver em cache); o que não for local vira `[DESCONHECIDO]` com "o que falta consultar/negociar" — nunca um veredito sem fonte (D3 já autoriza; o checkpoint torna obrigatório).

## SHOULD TEST

### EC-3: RAM apertada (709 MiB livres, swap quase cheio) — OOM se os 2 transcritores rodarem juntos
- **Affected question:** Q7
- **Suggested halt-loop checkpoint:** antes de afirmar viabilidade em Q7, validar que o fluxo carrega **um transcritor por vez** (parakeet 2,3 G *ou* faster-whisper), libera o modelo antes do próximo, e mede a RAM de pico — nunca os dois residentes simultaneamente.

### EC-4: "on-the-fly" pode exigir features pré-computadas em alguns caminhos do lhotse
- **Affected question:** Q1, Q2
- **Suggested halt-loop checkpoint:** ao responder Q1/Q2, confirmar que o caminho citado é **lazy de verdade** (transform aplicado no `__getitem__`/dataloader sobre samples de áudio, sem `compute_and_store_features`) — se o único caminho lazy exigir features materializadas, registrar isso como restrição, não como "on-the-fly puro".

## DOCUMENT

### EC-5: Se Q4 concluir "torch obrigatório", o item 3 do DoD precisa de um fallback declarado
- **Accepted risk:** Q4 existe justamente para descobrir isto. Se torch for obrigatório, há dois caminhos, a decidir no execute com a evidência: (a) instalar **torch CPU-only** (leve, sem CUDA) — reusa lhotse integralmente; (b) manifests em **JSON próprio** + augmentação `sox` on-the-fly via callable, sem lhotse — parsimony rung 6, só se (a) for inviável na máquina. O blueprint registra ambos; a escolha é do plano de implementação. Não bloqueia a discovery.

### EC-6: Q1/Q2/Q6/Q8 são respondidas por LEITURA do lhotse clonado, não por execução
- **Accepted risk:** a discovery LÊ o código dos peers (não roda). Portanto Q1/Q2/Q6/Q8 (como o lhotse faz X) **não dependem** de o lhotse importar no ambiente — só de o código clonado existir (existe). A viabilidade de *rodar* (Q4) é uma questão separada que informa a implementação. Ordem recomendada: Q4 cedo (informa o fallback EC-5), mas sem bloquear as demais.

## Summary

| Question | Edges found | MUST FIX | SHOULD TEST | DOCUMENT |
|----------|-------------|----------|-------------|----------|
| Q1 | 1 | 0 | 1 (EC-4) | 0 |
| Q2 | 1 | 0 | 1 (EC-4) | 0 |
| Q3 | 1 | 1 (EC-1) | 0 | 0 |
| Q4 | 1 | 0 | 0 | 1 (EC-5) |
| Q5 | 1 | 1 (EC-2) | 0 | 0 |
| Q7 | 1 | 0 | 1 (EC-3) | 0 |
| (transversal) | 1 | 0 | 0 | 1 (EC-6) |

**Verdict:** DISCOVERY PLAN NEEDS ADJUSTMENT — absorver EC-1 e EC-2 (fallback de fonte factual) no plano (v1.0 → v1.1); EC-3/EC-4 como checkpoints; EC-5/EC-6 como ADR/nota.
