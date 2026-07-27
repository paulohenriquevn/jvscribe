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

  **Afinado pelo paper Apple (`arxiv 2409.06062`, texto completo lido 2026-07-27) — 3 correções:**
  (i) **retrieval ACÚSTICO, não semântico.** Tabela II do paper: Acoustic Neighbor Embeddings
  (ANE) recall@1 head 84,8% > T5-semântico 80,7% > BM25 53,5%. A chave de retrieval das
  entidades (nomes/protocolos) tem de capturar acústica, NÃO significado. Refuta o framing
  "MiniLM semântico". Embedding da **ortografia ≈ do fonema** (fonema dá <1%, exige G2P) →
  pode pular G2P no retrieval. (ii) **injeção IN-DECODER, não pós-hoc.** O paper corrige a
  string 1-best sem áudio e admite (§ III) que re-rodar o ASR com contexto ([15][16]) é
  melhor mas exige áudio — **nós TEMOS o áudio + posterior do CTC**, então injetamos o
  biasing no decode (context-graph/FST `B`, como o sherpa), não num corretor pós-hoc.
  (iii) **simplicidade:** all-n-grams como query (sem NER), **1 melhor match acústico** (multi
  candidato piora), adaptação mínima. O **LLM de 7B do paper NÃO transfere** (CPU), mas seu
  valor é o retrieval — a injeção é FST, sem LLM.

  **Mapeamento ao roadmap existente (verificado nos arquivos, não é feature nova — 2026-07-27):**
  DISC-04 NÃO cria requisito; **implementa RF-08/RF-08b já escritos**. Mapa:
  - **RF-08** (`PRD.md:107`, v1.1): "aceitar lista de hotwords em runtime e favorecê-las na
    decodificação" = a lista de termos do domínio (Itaú, Nubank, Pix, boleto, nome do cliente).
  - **RF-08b** (`PRD.md:108`, v1.1): "casar hotwords em espaço fonético (pronúncia, não grafia) —
    nomes próprios raros" = a expansão fonética (G2P, Q-08 de M4) + matching ACÚSTICO (insight Apple).
  - **ROADMAP M8** (`ROADMAP.md:274`): "Hotwords em espaço fonético (nomes próprios raros, **nome
    do cliente**)" — já prevê o vocabulário por-cliente.
  - **`decoding-biasing-engineer`** (agent): dono; WFST/context-graph, FLToP, WCTC-Biasing, word
    spotter, contextual biasing SEM retreino, streaming. Modo "discover agora, implementar pós-M2"
    (destravado — CTC decidido).
  - **`PRD.md:250`**: Zipformer+CTC tem "FLToP aplicável (10,5×); **hotwords via WCTC-Biasing**" —
    o mecanismo é vantagem da família que escolhemos.

  **Timing honesto:** é **v1.1 / M8**, NÃO v1/agora. O runtime v0 atual é **greedy SEM** isso —
  FLToP/word-spotter/context-graph são requisito documentado, ainda **não implementados**.

  **Delta que os papers adicionam ALÉM do roadmap (o que registrar de novo):**
  (a) matching **acústico, não semântico** (Apple Tab II) — refina o "espaço fonético" do RF-08b;
  (b) injeção **só na inferência** (RASR) = privacidade + zero re-treino por cliente — justificativa
  nova p/ RF-08 (LGPD, PRD § 3.2); (c) **lista bounded → sem RAG/grafo** (MiniRAG resolve QA sobre
  docs, tarefa diferente — não se aplica ao reforço de palavra, que é autômato/FST);
  (d) **arquitetura de DUAS transcrições** (delta NÃO presente no roadmap): **biasing no vivo**
  (RF-08, real-time, no beam streaming, sem 2ª passada) para a legenda ao vivo, **+ correção pesada
  pós-chamada** (LM rescoring / corretor pequeno / GER) para o transcrito arquivado/pesquisável,
  onde a latência não conta. Dois orçamentos de latência, duas técnicas — serve os dois sem quebrar
  o real-time. Exemplo canônico: "Itaú/Nubank" no vivo = boost de hotword no beam; garbling residual
  no arquivo = correção. Caveat: boosting agressivo → falso-positivo ("Nubank" quando disseram
  "nublado"); medir recall de nome próprio **e** taxa de falso-positivo (já exigido no agent).

- **EXP-02 — fusão de LM (neural + n-gram) no beam do decode: o maior ganho barato.** PRIORIDADE
  e pré-requisito de DISC-04. Hoje decodamos **greedy, sem LM**. O paper Apple (`arxiv 2409.06062`
  § IV-A) mostra que até o CTC deles usa **DOIS LMs externos** (neural + 4-gram) — fusão de LM é
  table-stakes. Ataca a classe **real-word 36%** (medida em `analyze_error_composition.py`) que o
  léxico NÃO pega ("estruturas→torturas"). icefall/sherpa já suportam LM rescoring sobre CTC
  (Regra 9). **Fazer:** treinar um n-gram PT-BR (ou reusar) + beam + shallow fusion; medir a
  queda de WER. Barato, independente de biasing, e destrava o beam que DISC-04 também precisa.
  Pré-req: finalista de M4 + beam no runtime. `[LITERATURA/MEDIDO]`.
