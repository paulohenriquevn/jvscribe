# ASR PT-BR em CPU Real-Time — Blueprint Técnico

> Versão: 4.0 (consolidada) · 2026-07-24
> Projeto: jvscribe / jvscribe
> Substitui as v1.0 (2026-05-09), v2.0 e v3.0. Histórico de correções na § 11.

---

## 1. Tese do projeto

> Construir o **melhor modelo ASR de português brasileiro que roda em tempo real
> sobre CPU** — pequeno o suficiente para o dispositivo do usuário, bom o suficiente
> para competir com generalistas de 10× o tamanho **em PT-BR**.

O diferencial **não** é acurácia genérica. É **especialização**: um modelo que só
faz português brasileiro, e por isso pode ser pequeno, rápido e melhor em sotaque
regional do que qualquer generalista multilíngue.

### Por que isso é tecnicamente vantajoso

Modelos multilíngues gastam capacidade em idiomas que este produto nunca usará.
Whisper large-v3 (1,5 B) cobre 99 línguas; `parakeet-tdt-0.6b-v3` (600 M) cobre 25.
Um modelo **monolíngue PT-BR de ~80-120 M** tem chance real de igualar ou superar
ambos **na única métrica que importa aqui**, porque cada parâmetro trabalha para o
português.

Ganhos que acompanham a decisão:

| Ganho | Consequência prática |
|---|---|
| Tokenizer BPE 100% português | Menos tokens/palavra, decodificação mais rápida, melhor modelagem |
| Capacidade concentrada | ~5-8× menos parâmetros para a mesma qualidade em PT-BR |
| `projeto-sotaque` vira ativo central | Sotaque regional é onde generalistas erram e onde ninguém tem dado |
| P&C e ITN em PT-BR | Deixam de ser custo e viram diferencial defensável |

### Consequência de escopo

**Um modelo, não dois.** Um monolíngue pequeno serve o edge *e* o batch em
servidor. A decisão "modelo pequeno para edge + modelo grande para servidor" seria
necessária num cenário multilíngue; a especialização a torna desnecessária.

---

## 2. Restrições de produto (fonte de todas as decisões)

| Restrição | Valor | Origem |
|---|---|---|
| Hardware de inferência | **CPU** — custo, on-premise, edge no dispositivo, independência de fornecedor | Decidido |
| Cenário mais restritivo | **Edge no dispositivo do usuário** | Define o teto de tamanho |
| Modo de operação | **Streaming ao vivo _e_ batch** | Ambos são caminhos sérios |
| Entregáveis | Texto + **pontuação/capitalização** + **diarização** + **timestamps por palavra** | Decidido |
| Idioma | **PT-BR exclusivamente** | Tese do projeto |

**Edge domina.** Dos quatro motivos para CPU, o edge é o mais restritivo: um modelo
que roda no notebook do cliente também roda barato no servidor, também é
on-premise, e também elimina o fornecedor. O inverso não vale. **O teto de tamanho
é ditado pelo edge.**

⚠ **Hardware-alvo ainda não especificado.** Preencher antes de qualquer medição —
sem isso, "CPU real-time" não é hipótese testável.

```
Arquitetura:  [ x86_64 AVX2 / AVX-512 / ARM64 / Apple Silicon ]
Cores / threads para inferência: [ N ]
RAM disponível ao processo: [ N GB ]
Piso de dispositivo suportado: [ ex.: notebook 2020, celular médio ]
```

---

## 3. Orçamento de CPU — do **pipeline**, não do modelo

O erro mais caro que este projeto pode cometer é dimensionar o modelo acústico
isoladamente. **Tempos somam; taxas somam pelo inverso.**

$$\text{RTFx}_{\text{pipeline}} = \left(\sum_i \frac{1}{\text{RTFx}_i}\right)^{-1}$$

Exemplo concreto: ASR a 3× e diarização a 3× **não** dão 3× — dão **1,5×**.

| Componente | Custo relativo | Observação |
|---|---|---|
| ASR (encoder + CTC) | dominante | Alvo individual **≥ 6-8× RTFx** |
| Diarização | alto | Segmentation + embedding + clustering. Não é barato |
| VAD | baixo | ~5% do orçamento |
| P&C | baixo-médio | Modelo de texto por segmento |
| ITN | baixo | Baseado em regras |

> **Alvo corrigido:** para o pipeline completo fechar em **≥ 2× real-time**
> confortável, o ASR isolado precisa de **6-8× RTFx** — não os 3× das versões
> anteriores deste documento. Isso empurra o modelo ainda mais para baixo e reforça
> a escolha monolíngue.

**Diarização é o componente mais difícil da lista.** Offline (arquivo pronto) é
tratável. **Em streaming, com número de falantes desconhecido, é problema de
fronteira** — produtos comerciais maduros ainda erram muito. Tratar como risco
técnico de primeira ordem, não como item de checklist.

---

## 4. Dataset

### Principal: TAGARELA (decidido)

[`freds0/TAGARELA`](https://huggingface.co/datasets/freds0/TAGARELA)

| Propriedade | Valor |
|---|---|
| Horas | **8.972 h** |
| Variedade | **~8.130 h PT-BR (91%)** + ~842 h PT-PT |
| Segmentos | 7.111.196 |
| Áudio | FLAC, 16 kHz, mono, 16-bit |
| Splits | **split único (`train`) — não há dev/test** |
| Tamanho | 1,21 TB download / **1,76 TB em disco** |
| Origem do áudio | *Cem Mil Podcasts* (~76.000 h) |
| Transcrições | ElevenLabs Scribe (bootstrap) → Whisper large-v3 fine-tuned + filtro |
| Licença | **`cc-by-nc-sa-4.0`** |

**Volume deixa de ser o gargalo.** As recipes de referência do icefall treinam
Zipformer com 960 h (LibriSpeech). 8.972 h é 9× isso — suficiente para treinar um
modelo monolíngue do zero.

**Não há split de teste.** O test set é artefato seu (§ 8) e **não pode sair do
TAGARELA**: as labels são de máquina, então medir contra elas mede concordância com
o Whisper, não acurácia.

### Licença — decisão registrada

`CC-BY-NC-SA-4.0` = atribuição + **não-comercial** + **ShareAlike** (viral).

**Não tem `ND`** — modificar é explicitamente permitido, diferente do CORAA
(`NC-ND`), onde derivar é justamente o proibido.

**Negociar licença comercial não é caminho aqui:** o áudio vem de ~76.000 h de
podcasts de terceiros; o mantenedor quase certamente não detém os direitos para
conceder. Diferente do CORAA, onde o NILC/USP detém e poderia licenciar. **Não há
contraparte capaz de dizer sim.**

Se os **pesos** de um modelo constituem obra derivada dos dados de treino é questão
jurídica **aberta e em litígio ativo**. Ninguém pode afirmar o contrário com
honestidade — nem a favor, nem contra.

> **DECISÃO (2026-07-24, Paulo):** prosseguir com TAGARELA assumindo o risco.
> Registrado para rastreabilidade. O risco prático dominante não é processo
> judicial — é **due diligence**: proveniência de dados exigida em venda
> enterprise, auditoria de investidor, exposição por concorrente. O passivo fica
> embutido nos pesos e não expira.

### Complementares — o dado humano, que agora vale mais

| Dataset | Horas | Licença | Papel |
|---|---|---|---|
| MLS Portuguese | ~284 h | CC-BY-4.0 | **Fine-tune final supervisionado** |
| Common Voice PT | ~100 h+ | CC0 (⚠ não verificado) | **Fine-tune final supervisionado** |
| `jvscribe-dataset-processed` | ? | ⚠ não verificado | ? |
| **`projeto-sotaque`** | alvo 1-10 k h | CDLA-Permissive-2.0 | **Ativo estratégico — sotaque regional** |
| ~~CORAA v1.1~~ | ~290 h | CC-BY-NC-**ND** | Excluído — `ND` proíbe derivar |

**Estratégia em dois estágios:**

1. **Adaptação em escala** — TAGARELA 8.972 h (pseudo-labels). Ensina PT-BR,
   sotaque, fala espontânea, ruído de podcast. Leva o modelo **até** o teto do
   professor.
2. **Fine-tune final supervisionado** — MLS + Common Voice + `projeto-sotaque` +
   dados próprios com label humana. Único estágio capaz de empurrar o modelo
   **acima** desse teto.

Inverter a ordem desperdiça o dado humano, que é escasso e o mais valioso do
projeto.

⚠ **ToS da ElevenLabs** quanto a treinar modelos com output do Scribe permanece
aberto e cobre TAGARELA **e** `projeto-sotaque` conjuntamente — a exposição é a
mesma, não duas separadas.

---

## 5. Arquitetura

### Comparativo, sob as restrições da § 2

| Critério | **Zipformer + CTC** | Parakeet 600M (FastConformer+TDT) | Whisper |
|---|---|---|---|
| Eficiência de encoder | **melhor disponível** | boa | fraca (janela fixa 30 s) |
| Streaming | **nativo** | exige re-treino cache-aware | limitado |
| Tamanho viável para edge | **escala a 50-120 M** | 600 M | ≥ 1,5 B |
| Timestamps por palavra | **grátis (alinhamento de frame)** | via TDT | fraco |
| Monolíngue PT-BR | **sim, por construção** | multilíngue (capacidade desperdiçada) | multilíngue |
| sherpa-onnx | **cidadão de primeira classe** + bindings mobile/desktop | export manual | não |
| Pipeline VAD + ASR + diarização | **integrado na mesma stack** | montar por conta | montar por conta |
| Ponto de partida PT-BR | do zero (mas 8.972 h disponíveis) | encoder viu PT **europeu** | viu PT |

### Recomendação — rota principal

> **Zipformer streaming + CTC, monolíngue PT-BR, treinado do zero no TAGARELA.
> Alvo: ~80-120 M parâmetros.**

Ganha em todos os eixos que as restrições da § 2 apertam. O único eixo em que
perde — ponto de partida pré-treinado — é o que o TAGARELA neutraliza.

**Detalhes de configuração:**

- **Cache-aware / contexto limitado desde o início.** Um modelo cache-aware roda
  offline também, com perda pequena. Um modelo offline **não** roda streaming de
  jeito nenhum. Treinar offline e "converter depois" não existe.
- **Tokenizer BPE PT-BR dedicado**, ~500-1000 tokens.
- **CTC, não transducer.** Não-autorregressivo, paralelo, timestamps de graça, e o
  mais barato em CPU.
- **Shallow fusion com LM n-gram PT-BR** — a melhoria de WER mais barata que existe
  para CTC, suportada nativamente no sherpa-onnx.

### Rota de controle (seguro, roda em paralelo no piloto)

**Fine-tune do `parakeet-tdt-0.6b-v3`** (CC-BY-4.0, 600 M) em PT-BR.

Justificativa honesta: o parakeet viu **670.000 h** de treino. Transfer learning
nessa escala é real, e 8.972 h não compensam isso trivialmente. **Não afirmo que o
monolíngue do zero ganha** — afirmo que é a aposta certa e que a decisão deve ser
**empírica**, não argumentativa.

O piloto (§ 8, Fase 2) roda as duas rotas no mesmo subset e compara no mesmo test
set. Custa pouco e elimina a dúvida com dado.

### Referência que não pode ser usada

`nvidia/stt_pt_fastconformer_hybrid_large_pc` — 115 M, **PT-BR**, CTC+Transducer,
com P&C, 2.200 h. Tecnicamente é quase exatamente o alvo deste projeto. É
**CC-BY-NC-4.0**: serve como **âncora de WER**, nada além disso.

---

## 6. O que NÃO fazer

| Abordagem | Por que evitar |
|---|---|
| **Dimensionar o modelo isoladamente** | O orçamento de CPU é do pipeline (§ 3). ASR 3× + diarização 3× = 1,5× |
| **Treinar offline e "converter" para streaming** | Não existe. Cache-aware é decisão de treino, não flag de export |
| **Usar modelo multilíngue** | Paga parâmetros por 24 línguas inúteis em cada dispositivo |
| **Colocar qualquer pseudo-label no test set** | Mede concordância com o professor, não acurácia. Invalida toda a avaliação |
| **Prometer WER superior ao Whisper** | As labels vêm do Whisper (§ 7). Vender isso é vender o que os dados não sustentam |
| **Treinar nas 8.972 h sem piloto em subset** | Erro de manifest/tokenizer só aparece após dias de GPU |
| **Usar CORAA** | `CC-BY-NC-ND` — o `ND` proíbe derivar, não só copiar |
| **Partir de `stt_pt_fastconformer_hybrid_large_pc`** | `CC-BY-NC-4.0`, apesar de tecnicamente ideal |
| Treinar do zero como Cohere (2 B, 500 k h) | Inviável sem datacenter próprio |

> **Pseudo-labels não estão nesta lista.** Treinar em labels de máquina em escala é
> o método SOTA atual — o parakeet v3 usou 660.000 h pseudo-rotuladas (Granary)
> contra 10.000 h humanas. O que está proibido é **avaliar** contra elas e
> **prometer** superar o professor.

---

## 7. Métricas e alvos

### A tese de acurácia, honestamente

As labels do TAGARELA foram geradas por um **Whisper large-v3 fine-tuned**. Treinar
sobre elas é **destilação**: o modelo aprende a reproduzir o professor, inclusive
onde o professor erra. Superá-lo sistematicamente no mesmo domínio é
estruturalmente improvável — o sinal de treino não contém a informação para
corrigi-lo.

O Whisper large-v3 é, portanto, o **teto de referência**, não o baseline a superar.

**A promessa vendável é:**

> Paridade de WER com o Whisper large-v3 em PT-BR, num modelo ~15× menor, rodando
> real-time em CPU, com sotaque regional brasileiro **melhor** que o generalista.

O item de sotaque é o único onde superar é plausível — e depende do
`projeto-sotaque` + fine-tune supervisionado final, não do TAGARELA.

### Âncoras publicadas

`stt_pt_fastconformer_hybrid_large_pc` (115 M, 2.200 h, PT-BR):

| Test set | WER (Transducer) | WER (CTC) | CER |
|---|---|---|---|
| Common Voice 16 PT | **12,03%** | 12,83% | 3,20% |
| MLS PT | **24,78%** | 25,70% | 5,92% |

`parakeet-tdt-0.6b-v3` (600 M, PT **europeu**): Fleurs 4,76% · MLS 7,50% ·
CoVoST 3,96%.

**A âncora que faltava — [`alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA`](https://huggingface.co/alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx)**
(600 M, parakeet v3 fine-tuned **no TAGARELA**, CC-BY-4.0):

| | WER médio |
|---|---|
| **Fala preparada** | **7,5%** |
| **Fala espontânea** | **14,3%** |

Test sets: CETUC, Common Voice 21.0, MLS-PT, MTEDx-PT, ALIP, C-ORAL Brasil I,
NURC-Recife, SP2010, NURC-SP, MuPe.

> Esta é a referência mais relevante do documento: **fala espontânea PT-BR, corpus
> TAGARELA, licença comercial.** Confirma que 14,3% é o patamar de um modelo de
> 600 M em banda larga — e valida o alvo de **15-25% para call center 8 kHz**, onde
> a perda de banda degrada. Também prova empiricamente que o TAGARELA funciona como
> corpus de fine-tune, e é provavelmente o **melhor teacher disponível** para este
> projeto.

> A distância entre 7,50% e 24,78% em MLS reflete escala de dados (670 k h vs
> 2,2 k h) e provavelmente protocolos de avaliação diferentes. **Não tire conclusão
> daqui sem rodar os dois no seu test set.**

### Alvos

| Métrica | Onde | Alvo | Justificativa |
|---|---|---|---|
| WER | Common Voice PT | ≤ 12% | Paridade com o modelo dedicado PT-BR |
| WER | MLS PT | ≤ 15% | Entre 7,50% e 24,78% dos comparáveis |
| WER | Test set interno (espontâneo + sotaque) | **≤ Whisper large-v3 no mesmo set** | Paridade é o alvo honesto |
| Δ WER | vs Whisper large-v3 | ≤ +2 p.p. absolutos | Critério de "equivalente na prática" |
| WER | Recortes por sotaque regional | **< Whisper large-v3** | Único eixo onde superar é plausível |
| **RTFx (ASR isolado)** | CPU-alvo, int8, 1 thread | **≥ 6×** | Para o pipeline fechar em ≥ 2× (§ 3) |
| RTFx (pipeline completo) | CPU-alvo | **≥ 2×** | Margem operacional real |
| Latência 1º token | CPU-alvo | < 300 ms | 160 ms é o chunk algorítmico; compute não é grátis |
| Tamanho do bundle | Edge | ⚠ definir | ASR + diarização + P&C + VAD somados |

---

## 8. Plano de execução

### Fase 0 — infraestrutura e critério de aceite

1. **Definir o hardware-alvo** (§ 2). Sem isso não existe critério de aceite e
   nenhum RTFx deste documento significa nada.
2. **Provisionar ≥ 3 TB** e baixar o TAGARELA (1,21 TB — ~27 h em link de
   100 Mbps).

| Item | Tamanho |
|---|---|
| TAGARELA — download / em disco | 1,21 TB / **1,76 TB** |
| Features fbank pré-computadas (80-dim, 10 ms, fp32) | ~1 TB adicional |
| Checkpoints + logs | ~100 GB |
| **Reservar** | **≥ 3 TB** |

> **Compute features on-the-fly** (Lhotse suporta). Pré-computar fbank para 8.972 h
> adiciona ~1 TB sem ganho proporcional. Só pré-compute se o I/O for **medido**
> como gargalo.

### Fase 1 — avaliação antes de treinar (a mais barata e a mais pulada)

3. **Test set blindado** PT-BR: espontâneo + **sotaques regionais**, curado por
   humano, sem sobreposição de locutor com o TAGARELA, **sem nenhum pseudo-label**.

   > ⟲ **CORREÇÃO (#16).** Versões anteriores afirmavam que "nenhum benchmark
   > público mede sotaque regional brasileiro bem". **Estava errado.** Existe uma
   > suite acadêmica de fala espontânea PT-BR com recorte regional, usada na
   > avaliação do `alefiury/...-TAGARELA`:
   >
   > | Corpus | Recorte |
   > |---|---|
   > | **NURC-Recife** | Nordeste |
   > | **NURC-SP** / **SP2010** | Sudeste urbano |
   > | **ALIP** | Interior de SP |
   > | **C-ORAL Brasil I** | Minas Gerais |
   > | **MuPe** | Histórias de vida |
   > | **CETUC** | Leitura controlada |
   >
   > Somados a **BIPA** (PROPOR 2026, dataset fonético dialetal PT-BR), isso é
   > cobertura regional pública substancial. **Adotar esta suite como espinha
   > dorsal da avaliação** — ela dá comparabilidade direta com um modelo publicado.
   > Verificar licença de cada corpus antes de uso comercial (vários são
   > acadêmicos e provavelmente NC).
   >
   > O que **continua** sendo ativo estratégico próprio: o test set de **call
   > center 8 kHz**, que nenhum benchmark público cobre. É esse que precisa ser
   > construído.
4. **Baseline zero-shot** no test set, sem treinar nada: `whisper-large-v3` (o
   teto), `parakeet-tdt-0.6b-v3`, `canary-1b-v2`, e — referência interna apenas —
   `stt_pt_fastconformer_hybrid_large_pc`.
5. **Medir RTFx em CPU** de um Zipformer streaming de referência (~80-120 M) em
   ONNX int8, no hardware do passo 1. **Incerteza #1:** se não atingir ≥ 6×, o
   orçamento da § 3 não fecha e é preciso descer de escala **antes** de gastar em
   treino.

### Fase 2 — piloto comparativo (~500 h de subset)

6. **Rota A** — Zipformer streaming CTC monolíngue, tokenizer BPE PT-BR, do zero.
7. **Rota B** — fine-tune do `parakeet-tdt-0.6b-v3`.

Ambas: mesmo subset, mesmo test set, mesmo protocolo. Valida o pipeline inteiro por
uma fração do custo, produz a estimativa de GPU-horas/época que fecha o orçamento,
e **decide a arquitetura com dado em vez de argumento**.

### Fase 3 — escala

8. Treino da rota vencedora no corpus completo (8.972 h).
9. **Fine-tune final supervisionado** — MLS + Common Voice + `projeto-sotaque` +
   dados próprios com label humana. Único estágio que pode superar o teto do
   professor, e onde o diferencial de sotaque é conquistado.

### Fase 4 — pipeline de produto

10. VAD + endpointing.
11. **Diarização** — tratar como risco técnico de primeira ordem (§ 3), não item de
    checklist. Streaming com número de falantes desconhecido é problema de fronteira.
12. P&C + ITN PT-BR.
13. LM n-gram shallow fusion.
14. Empacotamento edge (bindings sherpa-onnx) + medição do bundle final.

### Setup de treino

| GPU | VRAM | Preço/h aprox. | Indicação |
|---|---|---|---|
| RTX 4090 | 24 GB | $0,40-0,70 | **Adequada** — modelo de 80-120 M não precisa de mais |
| A100 80GB | 80 GB | $1,50-2,00 | Se o wall-clock em 8.972 h incomodar |
| H100 | 80 GB | $2,50-4,00 | Provavelmente desnecessário nesta escala |

> O alvo monolíngue de ~100 M barateia o treino em relação às versões anteriores
> deste documento, que assumiam 600 M.

⚠ **Custo total ainda não estimado** — só é estimável após o piloto da Fase 2, que
fornece GPU-horas/época reais.

---

## 9. Pendências abertas

| Pendência | Impacto | Status |
|---|---|---|
| Hardware-alvo não especificado | Sem critério de aceite | **Bloqueia Fase 1** |
| Tamanho máximo do bundle no edge | Define o teto real do modelo | Aberto |
| ToS da ElevenLabs (Scribe → treino) | Cobre TAGARELA + `projeto-sotaque` | Aberto, risco aceito |
| Licença do `jvscribe-dataset-processed` | Uso no fine-tune final | Não verificado |
| Proveniência do *Cem Mil Podcasts* | A montante do TAGARELA | Não verificado |
| Diarização em streaming | Componente mais difícil do escopo | Sem plano técnico ainda |
| Domínio de áudio alvo | Define vocabulário, ITN, se 8 kHz importa | Não declarado |

---

## 10. Referências

### Verificadas (2026-07-24)

- [alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx](https://huggingface.co/alefiury/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx) — **CC-BY-4.0**; parakeet v3 fine-tuned em TAGARELA; **WER 7,5% preparada / 14,3% espontânea**; suite de test sets espontâneos PT-BR com recorte regional (CETUC, CV 21.0, MLS-PT, MTEDx-PT, ALIP, C-ORAL Brasil I, NURC-Recife, SP2010, NURC-SP, MuPe); deploy via `onnx-asr`
- [freds0/TAGARELA](https://huggingface.co/datasets/freds0/TAGARELA) — 8.972 h (91% PT-BR), 7,1 M segmentos, FLAC 16 kHz, 1,76 TB, split único, derivado de *Cem Mil Podcasts*, labels via ElevenLabs Scribe + Whisper large-v3 fine-tuned, **CC-BY-NC-SA-4.0**
- [nvidia/parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) — 600 M, FastConformer+TDT, CC-BY-4.0, 25 línguas, RTFx 3.332,74, WER PT (Fleurs 4,76 / MLS 7,50 / CoVoST 3,96), treino em PT europeu, 670 k h (660 k pseudo-rotuladas via Granary)
- [nvidia/parakeet-ctc-1.1b](https://huggingface.co/nvidia/parakeet-ctc-1.1b) — 1,1 B, CTC, **English-only**, CC-BY-4.0, RTFx 2.728,52
- [nvidia/canary-1b-v2](https://huggingface.co/nvidia/canary-1b-v2) — ~978 M, AED, CC-BY-4.0, 25 línguas
- [nvidia/stt_pt_fastconformer_hybrid_large_pc](https://huggingface.co/nvidia/stt_pt_fastconformer_hybrid_large_pc) — 115 M, PT-BR, CTC+Transducer, P&C, **CC-BY-NC-4.0**, WER MCV16 12,03% / MLS 24,78%
- [CORAA — GitHub](https://github.com/nilc-nlp/CORAA) · [TaRSila](https://sites.google.com/view/tarsila-c4ai/coraa-versions) — **CC-BY-NC-ND 4.0**
- [MLS — OpenSLR 94](https://www.openslr.org/94/) — CC-BY-4.0
- [On-Device Streaming ASR — arXiv:2604.14493](https://arxiv.org/html/2604.14493v2) — FastConformer CTC ONNX int8 em CPU: RTFx 7,15-7,30× (modelo **compacto**, não 600 M)

### Não verificadas nesta revisão

- [Zipformer — arXiv:2310.11230](https://arxiv.org/html/2310.11230v4)
- [icefall — Zipformer recipes](https://k2-fsa.github.io/icefall/recipes/Finetune/from_supervised/finetune_zipformer.html)
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)
- [NeMo ASR Models](https://docs.nvidia.com/nemo-framework/user-guide/latest/nemotoolkit/asr/models.html)
- [Cohere Transcribe — HF Blog](https://huggingface.co/blog/CohereLabs/cohere-transcribe-03-2026)
- [PROPOR 2026 — Synthetic + Real PT-BR](https://aclanthology.org/2026.propor-1.83/)
- [CAMÕES Benchmark — arXiv:2508.19721](https://arxiv.org/abs/2508.19721) — **relevante:** treino multi-varietal PT-BR/PT-EU/PT-AF
- [Projeto SOTAQUE](https://github.com/fabriciocarraro/projeto-sotaque)

---

## 11. Histórico de correções

### v1.0 → v2.0 (verificação factual)

| # | v1.0 dizia | Realidade |
|---|---|---|
| 1 | CORAA utilizável | `CC-BY-NC-ND 4.0` — o `ND` proíbe derivar |
| 2 | "Fine-tune do Canary/Parakeet" com CTC | Canary é AED; Parakeet v3 é TDT. Nenhum é CTC |
| 3 | Parakeet CTC 1.1B como base para PT | **English-only** |
| 4 | "RTFx ~2.793 (GPU)" | **2.728,52** — separador decimal lido como milhar |
| 5 | "RTFx ~4,5 em CPU single-core" (1.1B) | Sem fonte; a model card não menciona CPU |
| 6 | Teto de 600 M × recomendar 1.1 B | Contradição interna direta |
| 7 | WER alvo < 10% | Não comparável entre datasets; recalibrado |

### v2.0 → v3.0 (dataset)

| # | Corrigido |
|---|---|
| 8 | Tagarela **não** combina CORAA+CV+CML-TTS — deriva de *Cem Mil Podcasts* |
| 9 | Pool de dados: 384 h → **8.972 h** |
| 10 | Storage: ~300 GB → **≥ 3 TB** |
| 11 | Tese reformulada — labels vêm do Whisper, logo o alvo é paridade, não superioridade |

### v3.0 → v4.0 (restrições de produto)

| # | Corrigido |
|---|---|
| 12 | **Orçamento de CPU é do pipeline**, não do modelo. Alvo do ASR: 3× → **≥ 6×** |
| 13 | Streaming exige treino **cache-aware**; não se converte modelo offline depois |
| 14 | **Diarização** e **timestamps por palavra** entram no escopo (ausentes até a v3.0) |
| 15 | **Recomendação invertida** — Zipformer monolíngue PT-BR (~80-120 M) vira rota principal; Parakeet 600 M vira rota de controle. Motivo: foco PT-BR + edge + streaming; e o TAGARELA removeu a falta de dados que descartava o Zipformer |
