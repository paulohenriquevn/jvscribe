# ASR Evidence Discipline

Source of Truth da disciplina de evidência para **todos** os agents técnicos do
Macaw Voice (`.claude/agents/`). Contrato, não sugestão: um agent que viola esta
regra produz um artefato inválido, independente de quão bem escrito ele esteja.

Existe porque o próprio PRD registra uma falha de método já cometida neste projeto
— a escolha de Zipformer foi sustentada por benchmarks medidos em arquitetura
Moonshine, modelos sem parentesco (`PRD.md` § 8.1, "Correção de análise
registrada"). A regra abaixo é a vacina contra a repetição desse erro.

## § 0 — Estado do projeto: discover contínuo (LOCKED)

**Nada de arquitetura está escolhido.** Encoder, decoder, tokenização e tamanho
seguem `⏸ PENDENTE` em `PRD.md` § 8.1 e continuarão pendentes até que M2 produza
blueprint + ADR e M4 produza medição própria. O projeto está em **discover
contínuo**: o default de qualquer agent é *investigar e medir*, não *escolher*.

Consequências operacionais, válidas para todos os agents:

| Situação | Postura correta |
|---|---|
| Alguém pede "qual arquitetura usar?" | Responder com o estado da evidência e o experimento que falta — nunca com uma escolha |
| Trabalho que **depende** da arquitetura (decoder, hotwords, backend do encoder) | Marcar `BLOQUEADO POR M2` e não implementar (`PRD.md` § 8.2, § 9) |
| Trabalho **independente** da arquitetura (captura, VAD, buffers, log-mel, afinidade, harness de medição) | Liberado — pode avançar já |
| Um candidato parece obviamente melhor | Registrar como hipótese rotulada, abrir experimento; convicção não é evidência |
| Um artefato do projeto ainda fixa arquitetura | Sinalizar a inconsistência; a arquitetura é output de ciclo, não de documento |

Escrever "vamos de X" em qualquer artefato antes do ADR de M2 é violação desta
regra, mesmo que X venha a ganhar depois.

## § 1 — Rotulagem obrigatória de todo número

Nenhum número entra em artefato sem rótulo de proveniência. Sem rótulo, o número
é tratado como inexistente por qualquer agent que o leia.

| Rótulo | Significa | Exige |
|---|---|---|
| `[MEDIDO]` | Rodamos o experimento | comando exato, hardware, nº de repetições, média ± desvio |
| `[LITERATURA]` | Reportado por terceiro | citação resolvível (paper/model card/URL) + condições do experimento original |
| `[ESTIMATIVA]` | Derivado por cálculo | fórmula explícita + premissas de entrada |
| `[DESCONHECIDO]` | Não sabemos | o que seria preciso medir para saber |

Um `[LITERATURA]` **nunca** é promovido a `[MEDIDO]` por conveniência. Um
`[ESTIMATIVA]` que sustenta decisão bloqueante deve virar `[MEDIDO]` antes da
decisão ser travada.

## § 2 — Hipótese, evidência e conclusão são seções distintas

Todo artefato de decisão separa explicitamente:

1. **Hipótese** — a afirmação testável, escrita *antes* da medição.
2. **Evidência** — o que foi observado, com metodologia reproduzível.
3. **Conclusão** — o que a evidência sustenta, e **apenas** isso.

Conclusão que excede a evidência é defeito de severidade máxima, mesmo quando a
conclusão acaba se provando correta depois.

## § 3 — Falácias que invalidam o artefato (os sinais negativos)

Cada item abaixo é motivo de recusa. O agent que detecta um destes em input alheio
**deve** sinalizar em vez de seguir adiante.

| # | Falácia | Por que invalida |
|---|---|---|
| 1 | Usar benchmark de GPU para justificar performance em CPU | Regimes de memória e paralelismo diferentes; não transfere |
| 2 | Generalizar resultado entre arquiteturas sem parentesco | O erro já cometido neste PRD (§ 8.1) |
| 3 | Reportar só média de latência, sem p99 | RNF-02 é p99; média esconde a cauda que quebra o produto |
| 4 | Benchmark curto (< 10 min) em notebook | RNF-04: chip U de 15 W não sustenta turbo; 30 s medem o turbo e mentem |
| 5 | Ignorar thermal throttling | Idem RNF-04 |
| 6 | Tratar WER público como equivalente a WER de call center | Telefonia 8 kHz custa fator 2-3× (`PRD.md` § 7.1) |
| 7 | Defender arquitetura antes de medir os candidatos | Os 8 critérios foram fixados antes justamente para conter isso (`PRD.md` § 8.1) |
| 8 | Confundir tamanho de modelo com velocidade de inferência | Relação não é linear e depende de topologia e do runtime |
| 9 | Medir sem carga concorrente | RNF-05 exige softphone/Zoom ativo |
| 10 | Deixar pseudo-label entrar no test set | Mede concordância com o professor, não acurácia (`PRD.md` § 7.3, invariante) |
| 11 | Comparar RTFx de componente com orçamento de pipeline | Taxas somam pelo inverso (`PRD.md` § 6, racional RNF-07) |
| 12 | Concluir de test set sem intervalo de confiança | 20 min de áudio têm IC largo (`ROADMAP.md` M1, risco 1) |

## § 4 — Honestidade sobre incerteza

- "Não sei" é resposta aceitável e preferível a uma resposta plausível sem lastro
  (Regra Inquebrável 3).
- Todo agent declara os limites da própria abordagem ao concluir.
- Divergência entre agents é sinal de alto valor: registrar a divergência, não
  dissolvê-la em consenso de conveniência.
- Experimento sem evidência de valor deve ser cancelado, não prorrogado.

## § 5 — Âncoras do projeto (citar, não reescrever)

| Âncora | Onde |
|---|---|
| Requisitos funcionais RF-01..RF-11 | `PRD.md` § 5 |
| Critérios de real-time RNF-01..RNF-08 | `PRD.md` § 6 |
| Alvos de WER e suite de avaliação | `PRD.md` § 7 |
| Invariantes e pendências da arquitetura + 8 critérios de decisão | `PRD.md` § 8.1 |
| Runtime Rust e o que está liberado antes da decisão | `PRD.md` § 8.2, § 9 |
| Riscos e questões em aberto (Q-01, Q-03, Q-08, Q-09, Q-10) | `PRD.md` § 10, § 11 |
| Milestones M0..M8 com DoD e riscos | `ROADMAP.md` |
| Peers clonados e vereditos de licença | `knowledge-base/references/_catalog.md` |

Agent nenhum reescreve estas fontes por conta própria: propõe a mudança e a
registra em `CHANGELOG.md` conforme a Regra Inquebrável 6.

## § 6 — Anti-patterns

- Produzir um relatório longo cuja conclusão não é rastreável a nenhuma linha de evidência.
- "Provavelmente é rápido o bastante" sem número e sem rótulo.
- Citar `knowledge-base/references/...` sem ter aberto o arquivo.
- Reportar sucesso parcial como sucesso (Regra Inquebrável 3).
- Travar decisão pendente do PRD dentro de um artefato de agent, em vez de via ADR.

## Cross-references

- Time de agents: `.claude/agents/README.md`
- Escopo e requisitos: `PRD.md`
- Milestones: `ROADMAP.md`
- Testes: `.claude/rules/testing.md`
- Error handling: `.claude/rules/error-handling.md`
- Ciclo de descoberta que decide a arquitetura: `.claude/rules/cycle-discover.md`
- Contrato de plano: `.claude/rules/cycle-plan.md`
