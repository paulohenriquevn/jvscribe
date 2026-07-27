# Backlog — experimentos e discovers pendentes

Itens de investigação registrados para não se perderem. Cada um vira um ciclo
`/discover-*` ou um experimento medido quando priorizado. Não são decisões.

## Experimentos de runtime / quantização (M6 "runtime otimizado")

- **EXP-01 — int8 vs fp32 WER (quantização mista, lição T-Mimi).** Hoje quantizamos
  o modelo inteiro em int8 (post-training, cego). A literatura (T-Mimi, `hf 2601.20094`)
  mostra que camadas sensíveis à saída deveriam ficar FP32 e o resto int8 (quantização
  mista + QAT). **Ação:** exportar o finalista em fp32 E int8, rodar ambos pela mesma
  régua (`training/scripts/eval_runtime_wer.py`, já dá WER+CER) e medir a perda do int8.
  Se material, testar mixed-precision. **Pré-req:** fp32 export (fazer quando o large/
  finalista exportar). Já era pendente em `training/results/m6-realtime-current-model.md`.
  Motivação teórica nova: quantização mista. `[LITERATURA]`.

## Discovers pós-M5 (correção / rescoring dentro do orçamento de CPU)

- **DISC-01 — correção/rescoring pós-CTC no orçamento de CPU.** Motivado pela pergunta
  do Paulo sobre "transformer para corrigir a transcrição" (2026-07-26). GER com LLM é
  offline+grande — não cabe no nosso RNF (≤2 P-cores, RTFx≥6×, p99≤500ms). Investigar a
  família LEVE, em ordem de parcimônia: (1) **beam search + LM pequeno** (hoje usamos
  greedy) — fixa erros de fronteira/grafia barato; (2) **lexicon/hotword biasing** (já
  planejado — word spotter); (3) **corretor minúsculo não-LLM** (seq2seq de dezenas de M)
  treinado nos NOSSOS erros. **Fazer DEPOIS de M5** (consertar o modelo-base com dados é
  mais alavancado que bolt-on). Fontes: GER `arxiv 2505.17410` (rare-words+fonética,
  reduz CER), FlanEC `arxiv 2501.12979`, challenge `arxiv 2409.09785`, survey
  `arxiv 2508.07285`. Nosso perfil de erro (CER 11% ≪ WER 28% = deslizes de 1-2 chars)
  favorece rescoring barato sobre correção generativa. `[LITERATURA]`.

- **DISC-02 — streaming causal: referência SAT.** Ao projetar o Zipformer causal
  (RNF-02 latência p99), estudar SAT (`RicherMans/SAT` + `arxiv 2305.17834`): transformer
  streaming em chunks ≤2s carregando estado, real-time em CPU a 20MB/0.5 GFlops. Código
  aberto. Prova que streaming transformer roda em CPU no nosso footprint. `[LITERATURA]`.

- **DISC-03 — sinal de confiança / detecção de alucinação (compliance call center).**
  NPUsper (`arxiv 2607.01108`) detecta saída não-ancorada via alinhamento de atenção.
  Para call center + compliance, ter um sinal "esta transcrição é incerta" (em vez de
  emitir lixo confiante) é valioso. Adaptar a ideia ao nosso CTC (confiança por posterior).
  `[LITERATURA]`.

- **DISC-04 — léxico + biasing contextual sobre CTC (a ideia do Paulo, versão rigorosa).**
  Ideia (Paulo, 2026-07-26): "conhecemos todas as palavras PT-BR → se a palavra existe,
  não mexe; se não, corrige via retrieval/biasing". **Instinto certo — é a restrição de
  léxico que decoders WFST embutem no grafo** (`L`∘`G`∘`B`: léxico ∘ LM ∘ biasing). 3
  refinamentos obrigatórios (análise de PhD): (a) hashmap sozinho tem **recall baixo** —
  erros real-word ("acidente→ocidente", ambas palavras) PASSAM no filtro; (b) **corrompe
  nomes corretos** — nome de cliente/protocolo ∉ dicionário → discriminador tem de ser
  `∈ (dicionário ∪ lista de biasing)`; (c) non-word é correção **fonética+LM**, não
  semântica (MiniLM não leva "logares"→"lugares"). **Arquitetura certa: trocar greedy por
  BEAM + FST de (léxico PT-BR ∪ hotwords) + LM leve** — usa o posterior do CTC (que o
  pós-hoc joga fora), previne non-word por construção, reusa o **sherpa-onnx** (Regra 9,
  já clonado). Fontes: CB-RAG `arxiv 2509.19567`, ED-CEC `arxiv 2310.05129`, entity-RAG
  `arxiv 2409.06062`. **Pré-req:** beam no runtime + finalista de M4. **Evidência que
  decide o teto:** `training/scripts/analyze_error_composition.py` mede a fração de erro
  atacável por léxico vs real-word (inatacável) vs rare-ref (biasing) vs false-flag
  (corrupção). Líder: `decoding-biasing-engineer` (destravado com CTC decidido). `[LITERATURA]`.
