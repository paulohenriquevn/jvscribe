---
slug: macaw-voice-asr-ptbr
date: 2026-07-24
generated_by: roadmap-init
questions_answered: 7
unresolved_dims: []
status: in_progress
---

# Roadmap grill: macaw-voice-asr-ptbr

> **Nota de método.** Cinco das sete dimensões já estavam resolvidas antes desta
> invocação, com rastro em `PRD.md` e em
> `knowledge-base/grills/asr-ptbr-cpu-realtime-grill.md` (15 perguntas). Elas são
> registradas aqui por herança, com a fonte citada — não foram re-perguntadas.
> Apenas as duas dimensões genuinamente abertas foram levadas ao usuário.

### Q1/7: problema raiz

**Question:** Qual o problema raiz que este projeto resolve, e para quem dói hoje?

**Herdado de:** `PRD.md` § 2

**Answer:** Transcrição de atendimento em escala via API é economicamente
proibitiva. Para 1.000 atendentes × 6 h/dia × 22 dias = **132.000 h/mês**, o custo
em API (~$0,36/h) é **~$47.500/mês** (~$570k/ano). Rodar no notebook do atendente
torna o compute marginal **zero** — hardware já pago e ocioso. Dói para a operação
que precisa de transcrição de todas as chamadas para monitoramento de qualidade e
classificação de intenção, mas não pode pagar por hora transcrita.

### Q2/7: usuários primários

**Question:** Quem são os usuários primários?

**Herdado de:** `PRD.md` § 4 · grill anterior Q13

**Answer:** **Atendentes de call center**, na casa dos **milhares**, usando
**notebooks pessoais (BYOD)** — hardware heterogêneo e não controlado. Consumidor
secundário: o data lake e o classificador de intenção downstream.

### Q3/7: escopo do V1

**Question:** O que está em escopo para o V1?

**Herdado de:** `PRD.md` § 3.1 · grill anterior Q1-Q15

**Answer:** Dois componentes: **(A) o modelo ASR** — monolíngue PT-BR, treinado do
zero, nativo 8 kHz, streaming e batch — e **(B) o motor de inferência em Rust** —
captura de dois streams, VAD, decoder, quantização, thread affinity. Mais o corpus,
a cadeia de augmentação telefônica e o protocolo de avaliação.

### Q4/7: fora de escopo

**Question:** O que está explicitamente fora de escopo?

**Herdado de:** `PRD.md` § 3.2

**Answer:** **Plataforma de frota** (distribuição BYOD, versionamento, telemetria,
monitoramento de WER em produção) — sub-projeto C. **Compliance LGPD / mascaramento
de PII** — sub-projeto D, mas é dependência crítica que pode invalidar o desenho.
**Classificação de intenção** — consumidor downstream. **UI / produto.**

### Q5/7: restrições duras

**Question:** Quais as restrições duras?

**Herdado de:** `PRD.md` § 4, § 6 · grill anterior Q3, Q8, Q15

**Answer:**

| Restrição | Valor |
|---|---|
| Hardware | **CPU apenas**, no dispositivo do usuário; orçamento ≤ 2 P-cores |
| Máquina de referência | Intel i7-1355U (2 P + 8 E cores, AVX-VNNI, sem AVX-512) — **medida** |
| Áudio | **8 kHz banda estreita, G.711 a-law**, filtro 300-3400 Hz |
| Idioma | **PT-BR exclusivo**, com code-switching lexical PT/EN |
| Modo | Streaming ao vivo **e** batch |
| Real-time | RTFx ≥ 3×, p99 ≤ 500 ms, backlog zero, estabilidade térmica ≥ 80% em 30 min, sob carga concorrente |
| Falantes | máx. 3, tipicamente 2 |
| Orçamento de GPU | ~$5.000-8.000 (treino) |

### Q6/7: critério mensurável de ship do V1

**Question:** Qual o critério mensurável de sucesso para dizer que o V1 está pronto?

**Recommended:** Paridade de WER com a solução atual, com os 5 critérios de
real-time atendidos, sustentada por ~20 atendentes reais durante 4 semanas sem
intervenção manual.

**User answer:** Aceito. Como não há baseline medido da solução atual informado, o
critério fica em forma **absoluta**:

> **V1 shipped quando, simultaneamente:**
>
> | # | Condição |
> |---|---|
> | 1 | **WER ≤ 25%** no test set de call center 8 kHz (teto da faixa realista fixada em `PRD.md` § 7.1) |
> | 2 | Os **5 critérios de real-time** (`PRD.md` § 6, RNF-01..05) atendidos no hardware de referência |
> | 3 | **~20 atendentes reais**, em BYOD heterogêneo |
> | 4 | **4 semanas consecutivas** de uso |
> | 5 | **Sem intervenção manual** — nenhum restart ou ajuste por operador |

Racional registrado: **paridade, não superioridade**. O argumento econômico é
substituir ~$47.500/mês de API por compute marginal zero — empatar em WER a custo
zero já vence. Exigir superioridade moveria a trave contra uma estratégia de dados
(destilação sobre pseudo-labels) que estruturalmente tende à paridade. Condições 3-5
alinham com `rules/dogfood-golden-rule.md`, que exige status `running` (uso
sustentado real), não `wired`.
