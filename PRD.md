# PRD — Macaw Voice: ASR PT-BR real-time em CPU

| | |
|---|---|
| **Versão** | 1.0 |
| **Data** | 2026-07-24 |
| **Escopo** | Modelo ASR + runtime de inferência |
| **Fora de escopo** | Plataforma de frota, compliance LGPD, produto/UI |
| **Fontes** | `knowledge-base/grills/asr-ptbr-cpu-realtime-grill.md` (15 decisões), `deep-research-asr-ptbr-cpu-realtime.md`, `sota-techniques-asr-ptbr-cpu.md` |
| **Execução** | Agents em `.claude/agents/` · roteamento em `CLAUDE.md` · milestones em `ROADMAP.md` |
| **Contrato de evidência** | `.claude/rules/asr-evidence-discipline.md` — rotulagem de números, separação hipótese/evidência/conclusão, 12 falácias que invalidam artefato |

---

## 1. Resumo executivo

Construir um **modelo ASR de português brasileiro** e o **motor de inferência** que
o executa em **tempo real sobre CPU**, no notebook de atendentes de call center,
sem GPU e sem chamada de rede por transcrição.

A tese não é acurácia superior a generalistas. É **especialização**: um modelo que
só faz PT-BR telefônico e, por isso, cabe na ordem de dezenas de milhões de
parâmetros e roda em 2 núcleos — onde um multilíngue de 600M não fecha real-time.

> **Estado da arquitetura: pendente.** Encoder, decoder e tamanho são output de um
> `cycle-discover` + piloto medido (§ 8.1). O que está decidido são os invariantes:
> monolíngue PT-BR, treino do zero, 8 kHz nativo, streaming e batch.

---

## 2. Problema e justificativa econômica

Transcrição de atendimento em escala via API é proibitivamente cara:

| | |
|---|---|
| Volume estimado | 1.000 atendentes × 6 h/dia × 22 dias = **132.000 h/mês** |
| Custo em API (~$0,36/h) | **~$47.500/mês** (~$570k/ano) |
| Custo marginal de compute local | **$0** — hardware do atendente, já pago e ocioso |
| Investimento estimado em treino | **$5.000-8.000** (one-time) |

O investimento se paga na primeira semana de operação. Essa é a justificativa
primária do projeto; privacidade, independência de fornecedor e ausência de
latência de rede são benefícios secundários reais mas não determinantes.

---

## 3. Escopo

### 3.1 Dentro

| Componente | Descrição |
|---|---|
| **A — Modelo** | Encoder streaming + CTC, monolíngue PT-BR, nativo 8 kHz, ~80M params, treinado do zero |
| **A — Corpus e augmentação** | TAGARELA + cadeia de augmentação telefônica; BPE PT-BR dedicado |
| **A — Avaliação** | Protocolo de medição de WER contra suite pública + test set de call center próprio |
| **B — Runtime** | Motor de inferência em **Rust**: captura, VAD, encoder, decoder CTC, hotwords |
| **B — Otimização** | Quantização, thread affinity, poda de decodificação, medição sustentada |

### 3.2 Fora — dependências externas rastreadas

| Item | Por que fora | Risco se ignorado |
|---|---|---|
| **Plataforma de frota** (distribuição BYOD, versionamento, telemetria, monitoramento de WER em produção) | Sub-projeto C; depende de A+B prontos | Alto — sem isso não há operação, mas não bloqueia A/B |
| **Compliance LGPD / PII** | Sub-projeto D; jurídico, não engenharia de ASR | **Crítico** — pode exigir mascaramento de PII *no dispositivo*, consumindo orçamento de CPU que este PRD já considera apertado |
| **Classificação de intenção** | Consumidor downstream do texto | Médio — define ponderação de WER (§ 7.2) |
| **UI / produto** | Não é ASR | Baixo |

> **D é a única dependência externa que pode invalidar decisões deste PRD.** Se a
> conclusão jurídica exigir NER de PII rodando no edge, o orçamento de CPU da § 6
> muda e o tamanho-alvo do modelo cai. Levantar em paralelo, antes do treino final.

---

## 4. Contexto de uso

| Dimensão | Valor | Origem |
|---|---|---|
| Usuário | Atendente de call center | Grill Q13 |
| Escala | Milhares de instalações | Grill Q13 |
| Hardware | **Notebook pessoal (BYOD)** — heterogêneo, não controlado | Grill Q13 |
| Máquina de referência | Intel i7-1355U: 2 P-cores @5,0 GHz + 8 E-cores @3,7 GHz, AVX-VNNI, sem AVX-512, 15 GB RAM | **Medido** |
| Áudio | **8 kHz banda estreita, G.711 a-law**, filtro 300-3400 Hz | Grill Q15 |
| Captura | **2 streams**: microfone (atendente) + loopback do sistema (cliente) | Grill Q5 |
| Falantes | **Máx. 3, tipicamente 2** | Grill Q7 |
| Idioma | **PT-BR exclusivo**, com code-switching lexical PT/EN | Grill Q6 |
| Modo | Streaming ao vivo **e** batch | Grill Q1 |

> ⚠ **Risco aberto R1:** a máquina de referência é o *notebook do autor*, não o piso
> da frota. Em BYOD real o piso é provavelmente um i3/Celeron sem AVX-VNNI. Todo
> dimensionamento deste PRD assume o i7-1355U e **precisa ser revalidado** contra o
> piso real. Ver § 10.

---

## 5. Requisitos funcionais

| ID | Requisito | Prioridade |
|---|---|---|
| RF-01 | Transcrever PT-BR falado em streaming, com saída incremental | **v1** |
| RF-02 | Transcrever em modo batch (arquivo), com o mesmo modelo | **v1** |
| RF-03 | Operar sobre áudio 8 kHz G.711 a-law sem degradação além do alvo | **v1** |
| RF-04 | Capturar microfone e áudio do sistema em streams independentes | **v1** |
| RF-05 | Atribuir falante no caso 1:1 por **roteamento de stream** (sem modelo) | **v1** |
| RF-06 | Emitir **timestamps por palavra** | **v1** |
| RF-07 | Transcrever corretamente termos técnicos em inglês em contexto PT | **v1** |
| RF-08 | Aceitar lista de **hotwords** em runtime e favorecê-las na decodificação | v1.1 |
| RF-08b | Casar hotwords em **espaço fonético** (por pronúncia, não por grafia) — nomes próprios raros | v1.1 |
| RF-09 | Pontuação e capitalização | v1.1 |
| RF-10 | ITN — números, CPF, protocolo, valores, datas | v1.1 |
| RF-11 | Diarizar até 3 falantes (2 remotos) quando o roteamento não basta | v1.2 |

**Racional RF-05:** com captura em dois streams, o microfone é o atendente por
construção. No caso 1:1 — o dominante — a diarização é resolvida por roteamento,
com custo zero de modelo e acurácia 100%. O modelo de diarização (RF-11) só é
necessário no caso de 3 falantes.

**Racional RF-06:** decodificação CTC produz alinhamento por frame nativamente.
Este é um dos motivos de escolher CTC sobre transducer — ver § 8.2.

---

## 6. Requisitos não-funcionais — "real-time verdadeiro"

Critério de aceite travado no grill (Q8). **Todos os cinco devem passar
simultaneamente.**

| ID | Critério | Alvo |
|---|---|---|
| RNF-01 | **RTFx sustentado** do pipeline completo | **≥ 3×** |
| RNF-02 | **Latência p99** (fim da fala → texto disponível) | **≤ 500 ms** |
| RNF-03 | **Backlog** de chunks não processados | **= 0 em 99,9% das amostras** |
| RNF-04 | **Estabilidade térmica**: RTFx no minuto 30 ÷ minuto 1 | **≥ 80%** |
| RNF-05 | Medição com **carga concorrente real** (softphone/Zoom ativo) | obrigatório |
| RNF-06 | Orçamento de CPU do pipeline completo | **≤ 2 P-cores** |
| RNF-07 | RTFx do ASR isolado (para o pipeline fechar RNF-01) | **≥ 6×** |
| RNF-08 | Footprint em disco do bundle completo | a definir (§ 10) |

**Racional RNF-07 — o orçamento é do pipeline, não do modelo.** Tempos somam, logo
taxas somam pelo inverso:

$$\text{RTFx}_{\text{pipeline}} = \left(\sum_i \frac{1}{\text{RTFx}_i}\right)^{-1}$$

ASR a 3× somado a diarização a 3× resulta em **1,5×**, não 3×. Dimensionar o modelo
acústico isoladamente é o erro mais caro possível neste projeto.

**Racional RNF-04.** O i7-1355U é um chip **U de 15 W**. Não sustenta 5,0 GHz sob
carga contínua, e ASR real-time é carga contínua de horas. Um benchmark de 30
segundos mede o turbo e mente.

---

## 7. Métricas de qualidade

### 7.1 Alvos de WER

Telefonia 8 kHz descarta a energia acima de 4 kHz, onde vivem as fricativas
(`/s/`, `/f/`, `/ʃ/`) que em português distinguem plural de singular. A literatura
mostra fator 2-3× entre benchmarks de banda larga e telefônicos.

| Contexto | Alvo | Âncora |
|---|---|---|
| Fala espontânea PT-BR, banda larga | ≤ 16% | `alefiury/...-TAGARELA` faz **14,3%** com 600M |
| **Call center PT-BR, 8 kHz** | **15-25%** | Sem âncora pública — a construir |
| Δ vs modelo de 600M no mesmo test set | ≤ +5 p.p. absolutos | critério de "equivalente na prática" |
| Recortes por sotaque regional | não pior que a média em > 2 p.p. | suite NURC/ALIP/C-ORAL |

### 7.2 WER não é a métrica final

Há classificação de intenção downstream. Errar "**cancelamento**" custa muito mais
que errar "**então**". O protocolo de avaliação deve incluir **WER ponderado por
palavras portadoras de intenção**, com a lista derivada do taxonomia de intenções
do sub-projeto C.

> ⚠ **Dependência aberta:** a lista de intenções ainda não existe. Até lá, usar WER
> puro e registrar que a métrica está incompleta.

### 7.3 Suite de avaliação

| Corpus | Recorte | Verificar licença |
|---|---|---|
| NURC-Recife | Nordeste | sim |
| NURC-SP, SP2010 | Sudeste urbano | sim |
| ALIP | Interior de SP | sim |
| C-ORAL Brasil I | Minas Gerais | sim |
| MuPe | Histórias de vida | sim |
| CETUC | Leitura controlada | sim |
| Common Voice 21.0 | Leitura crowdsourced | CC0 |
| MLS-PT | Audiobook | CC-BY-4.0 |
| **Test set de call center 8 kHz** | **A construir** | próprio |

Adotar esta suite dá **comparabilidade direta** com `alefiury/...-TAGARELA`, que
publica resultados nela. O test set de call center é o único ativo exclusivo — e o
único que mede o domínio real.

**Invariante:** o test set NUNCA contém pseudo-labels. Medir contra label de
máquina mede concordância com o professor, não acurácia.

---

## 8. Arquitetura

### 8.1 Modelo

#### ✅ Decidido — invariantes da arquitetura

```
monolíngue PT-BR · treinado do zero · nativo 8 kHz · streaming + batch
  ├── BPE PT-BR dedicado (~500-1000 tokens, cobrindo termos técnicos em inglês)
  ├── supervisão fonética auxiliar em camada intermediária (agnóstica ao decoder)
  ├── timestamps por palavra (RF-06 — requisito, não escolha de design)
  └── cache-aware / contexto limitado desde o treino
```

**Por que treinar do zero e não podar um multilíngue.** Pruning remove capacidade
de forma aproximadamente uniforme, mas o conhecimento de 40 idiomas está
entrelaçado nos pesos — não há como podar "as outras 39". Um modelo podado
preserva a diluição. Treinar do zero coloca 100% da capacidade em PT-BR.

#### ⏸ PENDENTE — encoder, decoder e tamanho

> **A escolha de arquitetura NÃO está tomada.** Ela é output de um ciclo
> `cycle-discover` (blueprint + ADR) seguido de piloto medido, **não deste PRD**.

> **Atualização M2 (2026-07-24).** O ciclo de descoberta produziu o blueprint
> `knowledge-base/discoveries/blueprints/m2-architecture-decision-blueprint.md`
> (SHIPPABLE 100) e o ADR `knowledge-base/adrs/0001-m2-architecture-finalists.md`,
> que nomeiam **2 finalistas a pilotar em M4** — **Zipformer+CTC** e
> **FastConformer+CTC** — com Moonshine-AED como braço de controle. A decisão foi
> por evidência: RTFx `[MEDIDO]` na CPU (Zipformer transducer 20M = 15,90 ± 2,06× vs
> Moonshine tiny 27M = 7,93 ± 0,72×, n=10, ~2× com separação limpa;
> `knowledge-base/measurements/m2-rtfx-candidates.md`).
> **O vencedor NÃO está travado** — WER 8 kHz e equivalência batch≡streaming são
> medidos no piloto de M4. A tabela abaixo permanece como registro dos trade-offs
> conhecidos; a avaliação completa 5×8 está no blueprint.

**Por que está pendente.** A decisão oscilou três vezes durante o levantamento —
FastConformer (para herdar inicialização) → Zipformer (ao decidir treinar do zero)
→ Moonshine (ao surgirem benchmarks em CPU x86). Uma decisão que oscila assim não
tem maturidade para ser travada. Pior: versões anteriores deste PRD fixavam
Zipformer **usando benchmarks do Moonshine como evidência** — extrapolação entre
arquiteturas sem parentesco (Moonshine é AED com RoPE; Zipformer é encoder U-Net
com CTC). É o mesmo erro de método que invalidou os números da pesquisa original.

**Candidatos e trade-offs conhecidos:**

| Candidato | A favor | Contra |
|---|---|---|
| **Moonshine-like (AED)** | Benchmark CPU x86 publicado (`[LITERATURA]`, outra CPU); valida a tese monolíngue; código MIT | FLToP e blank layer-skip **não se aplicam**; hotwords fracos no ASR (`[FONTE-REPO]`: sem biasing no repo); **sem recipe ASR from-scratch** (`[FONTE-REPO]`, M2: o `train.py` do repo é WordCNN de MCU, não ASR); RTFx ~2× pior que transducer `[MEDIDO]` (M2, n=10) |
| **Zipformer + CTC** | Recipe de treino aberta (icefall); FLToP aplicável (10,5×); hotwords via WCTC-Biasing; timestamps nativos; um encoder serve os dois modos [`arXiv:2506.14434`] | Sem benchmark publicado em CPU x86 nesta faixa |
| **FastConformer + CTC** | Maduro; cache-aware validado; ecossistema NeMo | Sem vantagem clara sobre os dois acima quando se treina do zero |
| **Paraformer / NAR** | Robustez a ruído explícita; hotwords e timestamps nativos; FunASR reporta **16 streams em 4 vCPU** | Números vêm de documentação de projeto, não de paper revisado |
| **LC-BiMamba (SSM)** | Bate Conformer em WER **e** RTF; **inferência de tempo constante** (739 min vs 5 min); dual-mode nativo | **Inviável via ONNX** (`onnxruntime#27796`); exige runtime próprio; nenhum benchmark de CPU publicado |

**Correção de análise registrada:** este PRD rejeitava decoder autorregressivo com
base no Whisper. **A generalização era indevida** — o Whisper é lento por janela
fixa de 30 s e 1,5B parâmetros, não por ser AED. Moonshine é AED e faz 165 ms com
123M. A objeção não sobrevive à evidência.

**Critérios de decisão — fixados antes da medição, para não racionalizar depois:**

| # | Critério | Peso |
|---|---|---|
| 1 | RTFx medido no hardware-alvo (RNF-07) | Bloqueante |
| 2 | WER no test set de call center 8 kHz | Bloqueante |
| 3 | Streaming nativo com cache | Bloqueante |
| 4 | Timestamps por palavra (RF-06) | Bloqueante |
| 5 | Viabilidade de hotwords (RF-08/08b) | Alto |
| 6 | Exportabilidade para o runtime alvo | Alto |
| 7 | Maturidade da recipe de treino | Médio |
| 8 | Licença de código e pesos | Médio |

**Faixa de tamanho a varrer:** ~30M / ~80M / ~123M. A curva WER × RTFx medida
decide — não uma estimativa. Evidência disponível: 34M → 69 ms, 123M → 165 ms,
245M → 269 ms em Linux x86 (arquitetura Moonshine).

**Por que 8 kHz nativo.** Match de domínio — o modelo não gasta capacidade
modelando banda inexistente em produção, e a tarefa mais simples permite modelo
menor para a mesma qualidade. **O ganho direto de compute é modesto (~5-10%)**: a
taxa de frames do encoder depende do hop (10 ms → 100 fps), não do sample rate;
apenas o frontend encolhe.

#### Supervisão fonética auxiliar (intermediate CTC) — custo zero em inferência

O modelo é treinado com **duas cabeças**:

| Cabeça | Onde | Alvo | Em produção |
|---|---|---|---|
| **Auxiliar** | camada intermediária do encoder | **fonemas PT-BR** | **descartada** |
| **Principal** | topo do encoder | BPE PT-BR | ativa |

A cabeça fonética existe **apenas durante o treino**. Na inferência é removida:
mesmo modelo, mesmo RTFx, mesma latência, mesmo footprint. **O custo em produção é
exatamente zero** — o ganho fica embutido nos pesos do encoder.

**Evidência:** *intermediate CTC loss* reporta **10-20% de redução relativa de
WER/CER** via multitask learning, self-conditioning e convergência melhor. Ganhos
foram observados especificamente em **fala telefônica conversacional** ao treinar um
CTC subword com *auxiliary phone loss* em camada intermediária — o domínio exato
deste projeto.

**Por que é especialmente adequado aqui:**

1. **Monolíngue** — inventário fonético único, sem conflito entre línguas no alvo auxiliar.
2. **PT-BR tem ortografia relativamente transparente** — G2P mais confiável que em inglês.
3. **Ataca o risco dominante (R9 — corpus escasso).** Supervisão fonética é injeção de conhecimento linguístico atuando como regularização; o benefício é **maior** quanto menos dados houver.
4. **8 kHz descarta as fricativas** (`/s/`, `/f/`, `/ʃ/`) — supervisão explícita dá sinal estruturado onde a informação acústica está degradada.
5. **Sotaque regional é fenômeno fonético** — forçar realizações regionais distintas a convergirem no mesmo alvo fonético é a invariância desejada.

**Rejeitado — pipeline fonema → léxico → palavra.** É a arquitetura clássica que o
end-to-end superou. Reintroduz componente com erro próprio, exige léxico + WFST
(caro em CPU), e o G2P quebra em nomes próprios, siglas e no **code-switching PT/EN
que é requisito (RF-07)**. Custaria latência e provavelmente pioraria o WER.

⚠ Os 10-20% vêm da literatura, em outras línguas e domínios. **Não são garantia** —
exigem ablação medida (§ 9, Fase 2).

### 8.2 Runtime de inferência (Rust)

```
[mic]────┐
         ├──VAD por stream──► prior de falante (RF-05)
[loop]───┘         │
                   ▼
              mix ──► log-mel (ring buffer) ──► encoder (int8/VNNI)
                                                    │
                                                    ▼
                            decoder CTC greedy + FLToP + word spotter
                                                    │
                                                    ▼
                                    texto + timestamps por palavra
```

| Componente | Decisão | Depende da arquitetura? |
|---|---|---|
| Pipeline de áudio: 2 streams, ring buffers, VAD, mix, roteamento de falante | **Rust, escrever já** | ❌ Não |
| Thread affinity nos P-cores | **Rust, escrever já** | ❌ Não |
| Log-mel em ring buffer | **Rust, escrever já** | ❌ Não (config muda, forma não) |
| Harness de medição dos RNF-01..05 | **Escrever já** | ❌ Não |
| **Decoder** (CTC greedy + FLToP, ou AED, ou NAR) | **⏸ AGUARDAR discover** | ✅ **Sim** |
| Word spotter de hotwords | ⏸ aguardar | ✅ Sim |
| Encoder — `ort` / `tract` / runtime próprio | ⏸ aguardar | ✅ Sim |

> **⟲ Correção.** Versões anteriores deste PRD afirmavam que o decoder "não depende
> do modelo" e podia ser escrito imediatamente. **Errado.** O decoder é a peça que
> **mais** depende da arquitetura: CTC greedy + FLToP para Zipformer/CTC; decoder
> autorregressivo sem FLToP para AED; scan recorrente custom para SSM. Escrevê-lo
> antes do discover é construir para uma arquitetura que pode não ser escolhida.
>
> A escolha de runtime também depende: **SSM inviabiliza ONNX** — se LC-BiMamba
> vencer, `ort` sai de cena e o runtime próprio deixa de ser otimização para virar
> pré-requisito.

**Quantização: int8, não int4.** O i7-1355U tem **AVX-VNNI** (`VPDPBUSD`,
dot-product int8 com acumulação int32). int4 não tem instrução nativa e paga
unpack. A escolha de int4 no benchmark de referência otimizava *tamanho*; aqui o
objetivo é *velocidade*. **Medir ambos.**

**Hotwords (RF-08) — restrição conhecida.** No sherpa-onnx, hotwords funcionam
apenas em modelos **transducer** com `modified_beam_search`. Com CTC, é necessário
portar CTC-based Word Spotter ou WCTC-Biasing — ambos sem retreino, rodando em
paralelo ao decoder, fora do caminho crítico.

**Hotwords em espaço fonético (RF-08b).** O word spotter casa candidatos pela
**pronúncia**, não pela grafia. Motivação direta: ASR end-to-end tem **baixo recall
em nomes próprios raros**, e nome de cliente é o erro mais frequente e mais visível
num call center — o modelo nunca viu "Wanderleia" no treino, mas a sequência
fonética é reconhecível.

| | |
|---|---|
| Evidência | WCTC-Biasing (wildcard CTC, tolerante a match ambíguo): **+29% de F1 em palavras desconhecidas** |
| Custo | Confinado ao spotter, que já roda em paralelo — **caminho crítico intacto** |
| Sinergia | Reaproveita o mesmo G2P da supervisão auxiliar (§ 8.1) |

A ordem **boost → poda** continua obrigatória (ver armadilha do FLToP acima), e vale
igualmente para o casamento fonético.

> ⚠ **Armadilha de composição:** FLToP CTC poda tokens de baixa probabilidade;
> hotwords raras **são** tokens de baixa probabilidade. A poda aplicada antes do
> boost eliminaria exatamente as palavras a favorecer. **Ordem obrigatória: boost
> → poda**, ou isentar tokens do grafo de contexto. Falha silenciosa se invertida.

### 8.3 Dados

| Estágio | Corpus | Papel |
|---|---|---|
| Pré-treino | **TAGARELA** — 8.972 h (91% PT-BR) | Aprende PT-BR amplo, sotaque, fala espontânea |
| Fine-tune final | MLS-PT + Common Voice + `projeto-sotaque` + correções de usuário | Único estágio capaz de superar o teto do professor |

**Augmentação telefônica — on-the-fly, obrigatória.** O TAGARELA é podcast de
estúdio a 16 kHz; a produção é call center a 8 kHz. A cadeia
`16k→8k → filtro 300-3400 Hz → G.711 a-law round-trip → babble/crosstalk → AGC`
roda no dataloader, **não materializada em disco** — cada época deve ver o mesmo
áudio com degradação diferente. Congelar uma versão 8 kHz destruiria a variação
que é o propósito da augmentação.

**Licença — decisão de risco registrada.** TAGARELA é `CC-BY-NC-SA-4.0`:
não-comercial e ShareAlike viral. Não há contraparte capaz de licenciar
comercialmente — o áudio vem de ~76.000 h de podcasts de terceiros. **Decisão
(2026-07-24, Paulo): prosseguir assumindo o risco.** Risco dominante não é ação
judicial, é due diligence em venda enterprise ou auditoria de investidor. Existe
precedente de prática — `alefiury/...-TAGARELA` publica sob CC-BY-4.0 um modelo
treinado nesse corpus — mas precedente não é segurança jurídica.

**Filtro de qualidade por concordância.** As labels do TAGARELA são de máquina
(ElevenLabs Scribe → Whisper large-v3 fine-tuned). Rodar um segundo transcritor e
manter apenas os segmentos concordantes segue o pipeline do Granary, que reporta
performance equivalente com ~50% dos dados. **Implementado em M3** (`scripts/corpus/`,
blueprint `knowledge-base/discoveries/blueprints/m3-corpus-blueprint.md`): filtro por
concordância CER par-a-par com τ calibrado empiricamente + manifests Lhotse com
augmentação telefônica on-the-fly; licenças mapeadas em `knowledge-base/corpus/m3-licenses.md`.
A alegação Granary "~50% dos dados" fica como hipótese a testar em M4, não premissa.

---

## 9. Plano de fases

### Fase 0 — Validação do cálculo (custo $0, dias)

| # | Entrega | Critério |
|---|---|---|
| 0.1 | Benchmark de `alefiury/...-TAGARELA-onnx` (600M) no i7-1355U | RTFx sustentado 10+ min, P-cores fixos, carga concorrente |
| 0.2 | Baseline dos candidatos a teacher na suite § 7.3 | WER por corpus |

> **Esta fase pode inverter a estratégia.** O dimensionamento inteiro assume que
> 600M rende ~0,6× RTFx nesta máquina — extrapolação de um benchmark em servidor de
> 32 núcleos, **não uma medição**. Se render ~3×, o caminho passa a ser quantizar um
> modelo existente, e o treino é desnecessário. Executar antes de alugar GPU.

### Fase 0.5 — Discover de arquitetura (bloqueia a Fase 2)

Ciclo `cycle-discover` completo sobre os cinco candidatos da § 8.1, com os oito
critérios já fixados. Saída: blueprint em
`knowledge-base/discoveries/blueprints/` + ADR, com **dois finalistas** para o
piloto. Este PRD passa a referenciar o blueprint em vez de fixar arquitetura.

### Fase 1 — Runtime independente de arquitetura (paralelo às Fases 0 e 0.5)

| # | Entrega |
|---|---|
| 1.1 | Captura de 2 streams + ring buffers + VAD por stream + roteamento de falante (Rust) |
| 1.2 | Log-mel 8 kHz em ring buffer (Rust) |
| 1.3 | Thread affinity nos P-cores |
| 1.4 | Harness de medição dos RNF-01..05 (sustentado, com carga concorrente) |
| 1.5 | Cadeia de augmentação telefônica (sox): 16k→8k, 300-3400 Hz, G.711 a-law, babble, AGC |

> Decoder e word spotter **saíram desta fase** — dependem da arquitetura (§ 8.2).

### Fase 2 — Piloto comparativo de dois braços (~$100-200)

Os **dois finalistas** do discover, treinados no mesmo subset, avaliados no mesmo
test set, com o mesmo protocolo. A curva WER × RTFx decide — não o paper.

| # | Entrega |
|---|---|
| 2.1 | Subset de ~500 h, manifests Lhotse, augmentação telefônica on-the-fly |
| 2.2 | BPE PT-BR (~500-1000 tokens) |
| 2.2b | **G2P PT-BR avaliado** — taxa de erro medida em amostra anotada, antes de gerar alvos fonéticos |
| 2.2c | Alvos fonéticos gerados para o subset |
| 2.6 | **Ablação da supervisão fonética** — mesmo modelo, mesmo dado, mesmo test set, com e sem cabeça auxiliar. Critério: manter apenas se o ganho de WER for ≥ 3% relativo |
| 2.3 | Zipformer-CTC 8 kHz, treino curto, export ONNX |
| 2.4 | RTFx medido + WER na suite § 7.3 |
| 2.5 | Estimativa de GPU-horas/época para orçar a Fase 3 |

Instância vast.ai **on-demand**, disco local (~50 GB). Sem object storage — nesta
escala não precisa existir.

### Fase 3 — Treino completo (~$1.500-2.000/run)

| # | Entrega |
|---|---|
| 3.1 | Object storage (R2/B2 — egress zero) + Lhotse Shar |
| 3.2 | Treino em 8.972 h, vast.ai interruptible + checkpoint/resume testado |
| 3.3 | Fine-tune final supervisionado |
| 3.4 | Modelo final quantizado + RNF-01..08 medidos |

### Fase 4 — Escopo v1.1+

P&C, ITN, Streaming Sortformer para 3 falantes, otimização de kernels custom.

---

## 10. Riscos

| ID | Risco | Impacto | Mitigação |
|---|---|---|---|
| **R1** | **Piso de hardware BYOD muito abaixo do i7-1355U** (i3/Celeron sem AVX-VNNI) | **Alto** — derruba o alvo de 80M; pode exigir tiering | Levantar a distribuição real de hardware da frota **antes da Fase 3** |
| **R2** | LGPD exigir NER de PII no dispositivo | **Alto** — consome orçamento de CPU já apertado | Sub-projeto D em paralelo, antes do treino final |
| **R3** | Cálculo de RTFx errado (é extrapolação) | **Alto** — pode invalidar a estratégia | **Fase 0.1** — custa horas, resolve |
| **R4** | Domain gap podcast→call center maior que a augmentação corrige | Médio | Test set de call center desde a Fase 0; gravações internas em fase posterior |
| **R5** | Licença do TAGARELA questionada em due diligence | Médio | Risco aceito e registrado; caminho de saída = retreino com dado próprio |
| **R6** | Poda de 7,5× na literatura de pruning não é território documentado | Baixo | Mitigado — decisão é treinar do zero |
| **R7** | Dataloader vira gargalo com augmentação on-the-fly | Baixo | Workers suficientes; medir na Fase 2 |
| **R8** | Corpora da suite de avaliação são acadêmicos e possivelmente NC | Baixo | Verificar licença antes de uso comercial; avaliação interna é uso legítimo |
| **R9** | **Volume de corpus abaixo da receita de referência** — 8.972 h contra 15.000-94.000 h usadas para treinar modelos monolíngues pequenos comparáveis, num regime (treino do zero) que a própria fonte identifica como o que **mais** precisa de dados | **Crítico** | Investigar acesso ao corpus bruto *Cem Mil Podcasts* (~76k h; o TAGARELA usou ~12%); pipeline próprio de pseudo-labeling; supervisão fonética auxiliar como regularização (§ 8.1) |
| **R10** | **G2P PT-BR de baixa qualidade envenena a loss auxiliar** em vez de ajudar | Médio | Medir taxa de erro do G2P em amostra anotada **antes** de treinar (Fase 2.2b); ablação decide se a cabeça auxiliar fica |

---

## 11. Questões em aberto

| # | Questão | Bloqueia |
|---|---|---|
| Q-01 | Distribuição real de hardware da frota BYOD | Fase 3 |
| Q-02 | Teto de tamanho do bundle no dispositivo (RNF-08) | Fase 3 |
| Q-03 | Taxonomia de intenções para WER ponderado (§ 7.2) | Protocolo de avaliação completo |
| Q-04 | `alefiury/...-TAGARELA` é streaming ou offline? Quantização do ONNX? Sample rate? | Escolha do teacher; se offline, Delayed-KD torna-se necessário |
| Q-05 | Licença de cada corpus da suite § 7.3 | Uso comercial dos números |
| Q-06 | Existem gravações internas de atendimento? Em que volume? | Fase 4 / substituição do corpus |
| Q-07 | Definição de v1 em termos de piloto com atendentes reais | Critério de encerramento do projeto |
| Q-08 | Qual G2P PT-BR usar? Candidatos: `espeak-ng` (suporta pt-br, rápido) e o módulo G2P do repositório Moonshine (**MIT**). Qualidade para PT-BR **não verificada** em nenhum dos dois | Fase 2.2b — supervisão fonética e hotwords fonéticas |
| Q-09 | Existe acesso ao corpus bruto *Cem Mil Podcasts* (~76k h) e sob que termos? | **R9 — risco dominante do projeto** |
| Q-10 | **Qual arquitetura — encoder, decoder e tamanho?** Cinco candidatos, oito critérios fixados (§ 8.1) | **Fase 2** — decoder, word spotter e escolha de runtime aguardam |

---

## 12. Referências

### 12.1 Lidas integralmente (model cards / papers acessados)

| Referência | Fatos extraídos |
|---|---|
| [`freds0/TAGARELA`](https://huggingface.co/datasets/freds0/TAGARELA) | 8.972 h; 91% PT-BR (~8.130 h) + 9% PT-PT; 7.111.196 segmentos; FLAC 16 kHz mono; **split único, sem dev/test**; 1,21 TB download / 1,76 TB em disco; derivado de *Cem Mil Podcasts*; labels via ElevenLabs Scribe → Whisper large-v3 fine-tuned; **CC-BY-NC-SA-4.0** |
| [`alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx`](https://huggingface.co/alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx) | Base `alexandreacff/parakeet-tdt-0.6b-v3-ptBR-plus`; fine-tune em TAGARELA; **CC-BY-4.0**; **WER 7,5% preparada / 14,3% espontânea**; suite CETUC, CV 21.0, MLS-PT, MTEDx-PT, ALIP, C-ORAL Brasil I, NURC-Recife, SP2010, NURC-SP, MuPe; deploy via `onnx-asr` |
| [`nvidia/nemotron-3.5-asr-streaming-0.6b`](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b) | Cache-Aware FastConformer 24 camadas + RNNT; 600M; **OpenMDW-1.1, uso comercial permitido**; 40 language-locales, **pt-BR em tier transcription-ready**; P&C nativo; chunks 80/160/320/560/1120 ms; **WER pt-BR+pt-PT 5,48 @1,12 s / 6,29 @80 ms (FLEURS)**; **sem timestamps por palavra** |
| [`nvidia/parakeet-tdt-0.6b-v3`](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | 600M; FastConformer + TDT; CC-BY-4.0; 25 línguas; RTFx 3.332,74 (leaderboard); WER PT: Fleurs 4,76 / MLS 7,50 / CoVoST 3,96; **treinado em PT europeu**; 670 k h (660 k pseudo-rotuladas via Granary) |
| [`nvidia/parakeet-ctc-1.1b`](https://huggingface.co/nvidia/parakeet-ctc-1.1b) | 1,1 B; CTC; **English-only**; CC-BY-4.0; RTFx 2.728,52; **sem dados de CPU na card** |
| [`nvidia/stt_pt_fastconformer_hybrid_large_pc`](https://huggingface.co/nvidia/stt_pt_fastconformer_hybrid_large_pc) | 115M; **PT-BR**; CTC+Transducer; P&C; 2.200 h; **CC-BY-NC-4.0**; WER MCV16 12,03% (RNNT) / MLS 24,78% |
| [Pushing the Limits of On-Device Streaming ASR — `arXiv:2604.14493`](https://arxiv.org/html/2604.14493v2) | Microsoft CoreAI; Nemotron Speech Streaming ~600M; int4 k-quant 0,67 GB (−73%); **RTFx > 6× em AMD EPYC 7V12, 32 núcleos @2,45 GHz, batch 1**; delay algorítmico 0,56 s, efetivo 0,62-0,70 s; técnicas: decomposição em 3 grafos ONNX, cache stateful zero-copy, log-mel nativo em ring buffer, RNNT greedy, fusão de operadores |
| [FLToP CTC — `arXiv:2510.09085`](https://arxiv.org/abs/2510.09085) | Poda de token por frame com limiar relativo; **10,5× speedup de runtime, 2,78× redução de memória**, sem retreino; afirma que decoders CTC consomem **até 90% do tempo de processamento** |
| [VibeVoice-ASR-BitNet — `arXiv:2607.21075`](https://arxiv.org/html/2607.21075v1) | Microsoft Research; quantização heterogênea INT8 (tokenizer) + BitNet ternário (decoder LM); 4,62→1,58 GB (2,9×); **RTF < 1 com 3 threads**; 1,6-2,3× vs Whisper.cpp; kernels SIMD ARM/x86; código `microsoft/VibeASR.cpp`, CC-BY-4.0 |
| [Nemotron 3.5 → Kenyan Languages — `arXiv:2607.18912`](https://arxiv.org/abs/2607.18912) | Adaptação data-centric do Nemotron 3.5 Streaming 0.6B preservando cache-aware e streaming decoder; técnicas: corpus auditing, normalização Unicode, split checks, duration filtering, checkpoint selection por validação, **true-streaming evaluation**; WER Kikuyu 42,97% / Dholuo 33,98% / Kalenjin 68,74% |
| [PINT — `arXiv:2607.19033`](https://arxiv.org/abs/2607.19033) | nyra labs; tokenização invariante via alinhamento sobre enunciados paralelos; **−98,7% em speaker probe accuracy** (93,1%→1,2%), −42% ABX, −27-30% perplexidade |
| [StepAudio 2.5 — `arXiv:2605.23463`](https://arxiv.org/abs/2605.23463) | Modelo unificado audio-language; RLHF por regime operacional; sem métricas quantitativas no abstract |
| [Pseudo2Real — `arXiv:2510.08047`](https://arxiv.org/html/2510.08047v2) | Task arithmetic para correção de viés de pseudo-label; vetor de correção `θ_corrigido = θ_pseudo + λτ`; **−35% WER relativo** (Whisper tiny, AfriSpeech-200); artefatos sob CC-BY-NC-SA-4.0 |
| [Streaming Sortformer — `arXiv:2507.18446`](https://arxiv.org/pdf/2507.18446) | NVIDIA (Medennikov, Park, Wang et al.); Arrival-Order Speaker Cache; competitivo a **0,32 s de latência**; CC-BY-4.0; modelo [`nvidia/diar_streaming_sortformer_4spk-v2`](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2); **teto de 4 falantes** |
| [CORAA](https://github.com/nilc-nlp/CORAA) · [TaRSila](https://sites.google.com/view/tarsila-c4ai/coraa-versions) | ~290 h; **CC-BY-NC-ND 4.0** — `ND` proíbe derivar. **Excluído do projeto** |
| [MLS — OpenSLR 94](https://www.openslr.org/94/) | ~284 h PT; CC-BY-4.0; uso comercial permitido |

### 12.2 Identificadas em busca — não lidas integralmente

| Referência | Relevância |
|---|---|
| [Granary — `arXiv:2505.13404`](https://arxiv.org/abs/2505.13404) | Pipeline de pseudo-labeling: segmentação → ASR two-pass → verificação de language-ID → filtragem de texto → filtro de alucinação → P&C. **Dados processados atingem performance equivalente com ~50% menos dados** |
| [Unifying Streaming and Non-streaming Zipformer — `arXiv:2506.14434`](https://arxiv.org/html/2506.14434) | Mesmo encoder serve streaming e batch reconfigurando máscaras de atenção |
| [Delayed-KD — `arXiv:2505.22069`](https://arxiv.org/html/2505.22069) | Temporal Alignment Buffer resolve desalinhamento de spike timing teacher offline → student streaming; −9,4% CER relativo vs U2++ a 40 ms |
| [Blank-regularized CTC — `arXiv:2305.11558`](https://arxiv.org/abs/2305.11558) | Frame skipping; **4× aceleração de inferência do transducer sem perda** |
| [Spike Window Decoding — `arXiv:2501.03257`](https://arxiv.org/pdf/2501.03257) | Reduz frames envolvidos na decodificação CTC |
| [WCTC-Biasing — `arXiv:2506.01263`](https://arxiv.org/pdf/2506.01263) | Contextual biasing **sem retreino** via keyword spotting wildcard CTC + biasing inter-camadas |
| [CTC Word Spotting streaming — `arXiv:2605.18222`](https://arxiv.org/html/2605.18222) | Contextual biasing para streaming ASR via CTC word spotting |
| [Which Data Matter? — `arXiv:2603.05819`](https://arxiv.org/pdf/2603.05819) | Seleção de dados por embedding para ASR |
| [Hierarchical Multitask Learning for CTC — `arXiv:1807.06234`](https://arxiv.org/abs/1807.06234) | Loss auxiliar de baixo nível (fonemas) em camadas intermediárias de encoder CTC |
| [Hierarchical Conditional CTC com subwords multi-granulares — `arXiv:2110.04109`](https://arxiv.org/pdf/2110.04109) | Vocabulário cresce gradualmente da camada baixa ao topo; cada nível condicionado ao anterior |
| [Hierarchical Multi-Task CTC — Interspeech 2024](https://www.isca-archive.org/interspeech_2024/kusunoki24_interspeech.html) | Multitask CTC com operação recursiva |
| [Intermediate CTC Loss](https://www.emergentmind.com/topics/intermediate-ctc-loss) | **10-20% de redução relativa de WER/CER**; ganhos reportados em **fala telefônica conversacional** com auxiliary phone loss |
| [PAC — `arXiv:2509.12647`](https://arxiv.org/pdf/2509.12647) | Intercala anotação grafêmica e fonética para melhorar reconhecimento de keywords |
| [Massive Open-Vocabulary Keyword Spotting — `arXiv:2606.11279`](https://arxiv.org/html/2606.11279) | Keyword spotting de vocabulário aberto |
| [Zipformer — `arXiv:2310.11230`](https://arxiv.org/html/2310.11230v4) | Zipformer-M: ~2× eficiência (metade dos GFLOPs/memória) vs Conformer com acurácia ≥ |
| [Accent-Invariant ASR — `arXiv:2510.09528`](https://arxiv.org/html/2510.09528) | Mascaramento de espectrograma guiado por saliência |
| [BIPA — PROPOR 2026](https://aclanthology.org/2026.propor-1.47.pdf) | Dataset fonético PT-BR com variações dialetais por região |
| [Real + Synthetic PT-BR — PROPOR 2026](https://aclanthology.org/2026.propor-1.83.pdf) | Adaptação ASR PT-BR combinando dados reais e sintéticos |
| [Accent features PT-BR — `arXiv:2605.30457`](https://arxiv.org/abs/2605.30457) | Extração de features de sotaque PT-BR sem labels sociolinguísticos |
| [CAMÕES — `arXiv:2508.19721`](https://arxiv.org/abs/2508.19721) | Treino multi-varietal PT-BR/PT-EU/PT-AF; sugere não descartar as 842 h de PT-PT do TAGARELA |
| [`freds0/distil-whisper-large-v3-ptbr`](https://huggingface.co/freds0/distil-whisper-large-v3-ptbr) | **8,22% WER em Common Voice 16**; mesmo autor do TAGARELA |
| [Hotwords — sherpa-onnx docs](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html) | Aho-Corasick + ContextGraph; **apenas transducer**, exige `modified_beam_search` |

### 12.3 Ferramentas e implementações de referência

| Recurso | Papel |
|---|---|
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | Runtime de referência; VAD + ASR + diarização em CPU; bindings mobile/desktop |
| [icefall](https://github.com/k2-fsa/icefall) | Recipes de treino Zipformer do zero |
| [`parakeet-rs`](https://github.com/altunenes/parakeet-rs) | STT + diarização + streaming em CPU, em **Rust** — estudar antes de escrever |
| [`microsoft/VibeASR.cpp`](https://github.com/microsoft/VibeASR.cpp) | Kernels SIMD ARM/x86 para ASR quantizado |
| [Lhotse](https://github.com/lhotse-speech/lhotse) | Manifests, augmentação on-the-fly, formato Shar para object storage |

---

## 13. Rastreabilidade das decisões

Cada decisão arquitetural deste PRD tem origem registrada em
`knowledge-base/grills/asr-ptbr-cpu-realtime-grill.md`:

| Decisão | Grill |
|---|---|
| Deploy no dispositivo, não em servidor | Q1 |
| Desktop antes de mobile | Q2 |
| Máquina de referência i7-1355U (medida) | Q3 |
| Domínio call center | Q4, Q13 |
| Captura em 2 streams, 1 ASR sobre o mix | Q5 |
| PT-BR only + code-switching + hotwords | Q6 |
| Máx. 3 falantes → diarização por roteamento no caso 1:1 | Q7 |
| Critério de real-time em 5 pontos | Q8 |
| Rust; `ort` antes de kernels custom; decoder primeiro | Q9 |
| Treinar do zero, não podar multilíngue | Q10, Q11 |
| Nemotron fora do produto, mantido como teacher/baseline | Q11 |
| Coleta priorizando correções | Q12 |
| TAGARELA como corpus principal | Q14 |
| 8 kHz G.711 a-law | Q15 |
