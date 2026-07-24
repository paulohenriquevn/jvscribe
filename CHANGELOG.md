# Changelog

Todas as mudanças relevantes deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o versionamento segue [Semantic Versioning](https://semver.org/lang/pt-BR/).

> **Nota sobre referências.** A Regra 6 exige que toda entrada cite o ticket/issue/PR
> de origem. O repositório ainda não está sob controle de versão nem tem tracker
> configurado — as entradas abaixo referenciam os artefatos em disco que as
> originaram. As referências `(#N)` passam a ser obrigatórias assim que o tracker
> existir; nenhum número foi inventado retroativamente.

## [Unreleased]

### Added

- App web local de teste (`macaw-cli serve` + `scripts/app.sh`): dashboard no navegador que mostra ao vivo o roteamento de falante (você/cliente), saúde do sink, backlog e deriva, com botão para rodar o forward pass do encoder — servidor HTTP mínimo em `std::net`, sem dependência nova (`crates/macaw-cli/src/app.rs`, `dashboard.html`)
- Teste de regressão do servidor do app: sobe o servidor numa thread e prova que um endpoint lento (`/fixture`) não bloqueia os polls de `/metrics` (`crates/macaw-cli/tests/server_concurrency_test.rs`)

### Fixed

- VAD de energia não disparava em áudio real de sistema: o ganho estava calibrado para o tom sintético da fixture (RMS ≈ 0,35) e exigia RMS ≈ 0,25, mas áudio real via loopback fica muito mais baixo (medido: vídeo do YouTube pelo monitor do sink → RMS ≈ 0,065), então era classificado como silêncio e o roteamento de falante não acendia o "Sistema". Ganho recalibrado de 2,0 para 15,0 (dispara em RMS ≈ 0,033) — heurística de M0, robustez real vem do Silero em M1 (`crates/macaw-audio/src/vad.rs`)
- App de teste congelava ao rodar o forward pass do encoder: o servidor HTTP era single-threaded e bloqueante, então carregar o encoder de 2,3 GB travava os polls de métricas e a UI inteira. Corrigido com thread por conexão, guard de single-flight no teste do modelo e cache do engine carregado (`crates/macaw-cli/src/app.rs`)

## [0.1.0] - 2026-07-24

### Added

- Walking skeleton de M0 implementado: workspace Rust de três crates (`macaw-audio`, `macaw-asr`, `macaw-cli`) com captura dual mic+loopback, VAD por stream, roteamento de falante, extração log-mel zero-alocação e forward pass do encoder ONNX de 600M sobre features reais — 34 testes passando, clippy limpo (`knowledge-base/implementations/m0-walking-skeleton-implementation.md`)
- Blueprint e plano de M0 aprovados com verdict SHIPPABLE nos gates de descoberta e de confiança de plano (`knowledge-base/discoveries/blueprints/m0-walking-skeleton-blueprint.md`, `knowledge-base/plans/m0-walking-skeleton-plan.md`)
- Evidência experimental de captura e de sincronia entre streams: loopback provado via libpulse, drift em regime medido como ≈ 0 com offset de partida constante de 1,44s (`knowledge-base/discoveries/m0-capture-probe-evidence.md`, `m0-drift-evidence.md`)
- Custo do VAD medido e resolvido de desconhecido: 3,32 µs média, 3,66 µs p99, 17,94 µs max no i7-1355U — 1784× real-time no pior caso (`crates/macaw-audio/tests/vad_cost_test.rs`)
- Escopo do projeto definido em `PRD.md`: modelo ASR PT-BR e motor de inferência em CPU, com 11 requisitos funcionais e 8 não-funcionais (`PRD.md`)
- Critério de aceite de "real-time verdadeiro" com cinco condições simultâneas — RTFx sustentado ≥ 3×, latência p99 ≤ 500 ms, backlog zero, estabilidade térmica ≥ 80% em 30 min, medição sob carga concorrente (`PRD.md` § 6)
- Arquitetura-alvo definida: encoder Zipformer streaming com decodificação CTC, monolíngue PT-BR, ~80M parâmetros, nativo em 8 kHz (`PRD.md` § 8.1)
- Suite de avaliação de fala espontânea PT-BR com recorte regional adotada como referência — NURC-Recife, NURC-SP, SP2010, ALIP, C-ORAL Brasil I, MuPe, CETUC (`PRD.md` § 7.3)
- Levantamento do estado da arte com 30+ referências classificadas por nível de verificação (`sota-techniques-asr-ptbr-cpu.md`)
- Registro das 15 decisões arquiteturais com racional e alternativas descartadas (`knowledge-base/grills/asr-ptbr-cpu-realtime-grill.md`)
- Plano de execução em cinco fases, começando por validação de premissa a custo zero (`PRD.md` § 9)
- Registro de riscos com oito itens rastreados e sete questões em aberto (`PRD.md` § 10, § 11)
- Pesquisa de arquiteturas alternativas ao eixo Conformer/Zipformer, runtimes Rust nativos e modelos de referência para edge (`deep-research-arquiteturas-alternativas.md`)

- Roadmap macro do projeto com 9 milestones (M0-M8), do walking skeleton ao piloto com atendentes reais (`ROADMAP.md`)
- Critério de ship do V1 definido: WER ≤ 25% no test set de call center 8 kHz, com os cinco critérios de real-time atendidos, sustentado por ~20 atendentes durante 4 semanas sem intervenção manual (`ROADMAP.md`)
- Métrica north-star definida: horas de áudio transcritas localmente por mês, com taxa de correção por minuto como guarda de qualidade (`ROADMAP.md`)
- Catálogo de 8 projetos de referência clonados para estudo, com licença, decisão de gate e mapeamento para milestones (`knowledge-base/references/_catalog.md`)
- Supervisão fonética auxiliar no treino, descartada na inferência: cabeça CTC de fonemas em camada intermediária, com custo zero em produção e ganho esperado de 10-20% relativo em WER (`PRD.md` § 8.1)
- Casamento de hotwords em espaço fonético para nomes próprios raros, requisito RF-08b (`PRD.md` § 8.2)

- Documento de entrada do projeto com roteamento de tarefa para agent e para skill de ciclo, estado travado da arquitetura e as regras invioláveis locais (`CLAUDE.md`)
- Responsáveis declarados por milestone: cada um dos nove milestones passa a nomear seus agents e, quando aplicável, a skill de ciclo que o conduz (`ROADMAP.md`)
- Time de doze agents especialistas cobrindo pesquisa ASR, dados e linguística PT-BR, inferência em CPU, sistemas/áudio/Rust, avaliação experimental e coordenação técnica (`.claude/agents/`)
- Disciplina de evidência como contrato compartilhado por todos os agents: rotulagem obrigatória de proveniência de cada número, separação entre hipótese, evidência e conclusão, e doze falácias que invalidam um artefato (`.claude/rules/asr-evidence-discipline.md`)
- Estado "discover contínuo" registrado como regra travada: nenhum agent escolhe encoder, decoder ou tamanho fora do ADR de M2, e o trabalho independente de arquitetura fica explicitamente liberado (`.claude/rules/asr-evidence-discipline.md` § 0)

### Changed

- Risco de volume de corpus promovido a bloqueante de nível 1: a receita de referência para modelos monolíngues pequenos usa 15.000-94.000 h por idioma, contra as 8.972 h atualmente disponíveis (`deep-research-arquiteturas-alternativas.md` § 1)
- Faixa de tamanho do modelo abandona o alvo fixo de ~80M e passa a ser varredura de três pontos (~30M / ~80M / ~123M) decidida por curva WER × RTFx medida, após benchmarks em CPU x86 mostrarem 165 ms para 123M (`deep-research-arquiteturas-alternativas.md` § 5.2)
- Arquitetura do modelo marcada como **pendente**: encoder, decoder e tamanho passam a ser resultado de um ciclo de descoberta seguido de piloto comparativo, com cinco candidatos e oito critérios de decisão fixados previamente (`PRD.md` § 8.1)
- Decoder e word spotter removidos da fase de trabalho independente de arquitetura — ambos dependem da escolha de decodificação (CTC, autorregressivo ou recorrente) e aguardam a decisão (`PRD.md` § 8.2, § 9)
- DoD de M0 corrigido: o critério de transcrição real-time de 5 minutos foi movido para M5/M6, por ser estruturalmente impossível com o modelo emprestado de 600M offline — impossibilidade que é a própria premissa do projeto; M0 prova o encanamento features→modelo (`ROADMAP.md` M0, `knowledge-base/discoveries/m0-borrowed-model-dod-analysis.md`)
- Claude Code passa a operar sem prompts de permissão neste repositório: `defaultMode` vira `bypassPermissions` e as listas `deny`/`ask` foram removidas a pedido do dono do projeto; os hooks de segurança (git-safety, boundary-check, stop-validation) seguem ativos e continuam sendo a única barreira automática (`.claude/settings.json`)

### Fixed

- Corrigida extrapolação indevida que sustentava a escolha de Zipformer com benchmarks de CPU medidos em arquitetura Moonshine — modelos sem parentesco arquitetural (`PRD.md` § 8.1)
- Corrigida rejeição de decoder autorregressivo baseada no desempenho do Whisper: a lentidão decorre da janela fixa de 30 s e de 1,5B parâmetros, não da arquitetura encoder-decoder (`PRD.md` § 8.1)

### Changed

- Corpus de treino definido como TAGARELA (8.972 h, 91% PT-BR), substituindo o conjunto CORAA + MLS + Common Voice previsto na pesquisa inicial (`PRD.md` § 8.3)
- Domínio de áudio fixado no padrão de call center brasileiro — 8 kHz banda estreita, G.711 a-law, filtro 300-3400 Hz — substituindo a premissa inicial de banda larga 16 kHz (`PRD.md` § 4)
- Alvos de WER recalibrados para 15-25% em call center 8 kHz, substituindo o alvo inicial de < 10% que comparava benchmarks não equivalentes (`PRD.md` § 7.1)
- Decisão de treinar o modelo do zero em vez de comprimir um checkpoint multilíngue existente, por preservação de capacidade dedicada ao PT-BR (`PRD.md` § 8.1)

### Fixed

- Correções do review pré-merge de M0 (dois BLOCKERs + quatro HIGH): caminho absoluto no `.cargo/config.toml` trocado por relativo (build reprodutível); detecção de sink mudo e medidor de deriva ganharam caller de produção no CLI, com teste de integração provando o caminho; RTF do encoder remedido com aquecimento e n=10; histórico de métricas limitado a janela deslizante para não crescer sem limite em chamada longa (`knowledge-base/reviews/m0-walking-skeleton-review-2026-07-24.md`)

### Removed

- Módulo `ring::SampleRing` removido: código morto apontado no review — construído e testado isolado, nunca integrado ao pipeline, que usa canal mpsc (`knowledge-base/reviews/m0-walking-skeleton-review-2026-07-24.md`)
- Três exports públicos órfãos removidos na auditoria de code-quality de M0, por YAGNI: `AsrEngine::with_vocab`, `AsrEngine::vocab_len` (vocabulário é decode, bloqueado por M2) e `DriftMeter::latest_drift_ms` (redundante com `record` + `history`) (`knowledge-base/audits/m0-walking-skeleton-code-quality.md`)
- CORAA excluído do plano de dados: a licença CC-BY-NC-ND proíbe obras derivadas, o que inviabiliza treino (`PRD.md` § 8.3)

### Security

- Risco de licença do corpus TAGARELA (CC-BY-NC-SA-4.0, não-comercial e ShareAlike) formalmente registrado e assumido em 2026-07-24, com o caminho de saída documentado (`PRD.md` § 8.3)
- Dependência de compliance LGPD registrada como risco R2: mascaramento de PII no dispositivo pode consumir orçamento de CPU já dimensionado (`PRD.md` § 10)
