# Discover Edge Case Review — m9-artifact-governance

Date: 2026-07-30
Discovery plan analyzed: `knowledge-base/discoveries/plans/m9-artifact-governance-plan.md`
Research questions analyzed: 8
Edge cases found: 6 (MUST FIX: 2, SHOULD TEST: 2, DOCUMENT: 2)

Verificação de citações executada primeiro: **11/11 caminhos citados resolvem em disco**.
Nenhum MUST FIX de citação fabricada.

## MUST FIX

### EC-1: O plano não registra a versão do clone — toda citação `arquivo:linha` fica sem âncora

- **Afetada:** todas (Q1-Q8)
- **Família:** Reference path
- **Cenário:** o blueprint vai citar `offline-recognizer-ctc-impl.h:188`. O `sherpa-onnx` é
  um projeto ativo; um `git pull` no clone move as linhas. Seis meses depois, quem tentar
  auditar a evidência abre a linha 188 e encontra outra coisa — e não terá como saber se o
  blueprint mentiu ou se o arquivo mudou.
- **Impacto:** a evidência `[FONTE-REPO]` perde a propriedade que a torna mais forte que
  `[LITERATURA]` — a reprodutibilidade. Segundo `asr-evidence-discipline.md` § 1, a citação
  `arquivo:linha` **tem de resolver e exibir o fato**; sem versão, isso é indecidível.
- **Correção sugerida:** adicionar ao § 3 do plano: *"Clone auditado:
  `116a44e72c5bb631dcdbdb9c176f0304f5fc6fb0` (2026-07-30, `--depth 1 --filter=blob:none`).
  Toda citação `arquivo:linha` refere-se a este SHA."*

### EC-2: 199 workflows e 22 arquivos de teste — Q5/Q6/Q7 sem critério de amostragem viram scope creep

- **Afetadas:** Q5, Q6, Q7
- **Família:** Scope
- **Cenário:** Q6 pergunta se o CI distingue teste executado de pulado. Com 199 workflows,
  o halt-loop pode varrer indefinidamente procurando o contraexemplo, estourando o orçamento
  de 3 h antes de chegar em Q7/Q8.
- **Impacto:** questões dos corners de teste ficam `blocked` por exaustão de orçamento, e não
  por ausência de resposta — exatamente o modo de falha que o ADR-D3 tentou evitar.
- **Correção sugerida:** adicionar ao método de Q5/Q6: *"Amostra fixa — `linux.yaml`
  (529 linhas) + os 3 workflows cujo nome casa `test|style|lint`, mais um `grep -l` global de
  `GTEST_SKIP` em `csrc/`. Não varrer os 199."* E em Q7: *"amostrar 3 dos 22 `*-test.cc`,
  escolhidos por serem os únicos que não dependem de modelo baixado."*

## SHOULD TEST

### EC-3: Q6 tem resposta negativa plausível e o plano não define o que a comprova

- **Afetada:** Q6
- **Checkpoint sugerido no halt-loop:** *"Se a varredura da amostra não encontrar mecanismo
  de distinção skip-vs-run, a questão só pode ser marcada `done` com a asserção negativa
  explícita — 'a amostra X não contém mecanismo Y' — nomeando o que foi varrido. Ausência
  não observada não é ausência."*
- **Racional:** provar ausência é epistemicamente diferente de provar presença. Sem esta
  regra, o executor pode registrar "não há" depois de olhar dois arquivos, e isso vira uma
  conclusão que excede a evidência (`asr-evidence-discipline.md` § 2).

### EC-4: Q3 pode não ser respondível pelo lado de leitura dos headers

- **Afetada:** Q3
- **Checkpoint sugerido no halt-loop:** *"Se os headers `*-model-meta-data.h` só mostrarem o
  consumo do metadata e não como ele é gravado, registrar isso como resposta parcial e
  apontar o script de export correspondente (ou declarar que o export está fora do clone),
  em vez de inferir o mecanismo de escrita."*

## DOCUMENT

### EC-5: Q2 depende conceitualmente de Q1, e o plano não declara ordem

- **Risco aceito:** a ordem natural de leitura (contrato → validação) já resolve, e as duas
  questões compartilham os mesmos arquivos-alvo. Impor ordem explícita adicionaria cerimônia
  sem reduzir risco — o executor lê `offline-model-config.*` uma vez e responde as duas.

### EC-6: Uma única fonte (sherpa-onnx) para três perguntas de design

- **Risco aceito e já registrado como ADR-D1 do plano.** O peer é o caso de referência
  exato, e a alternativa (8 peers) dilui o sinal. **Mitigação já presente:** os corners de
  Tools e Techniques têm fontes web na allowlist como segunda opinião. O risco residual é
  que uma escolha de design de M9 se apoie em uma única implementação — e isso deve aparecer
  como caveat explícito no blueprint, não ser corrigido aqui.

## Summary

| Questão | Edges | MUST FIX | SHOULD TEST | DOCUMENT |
|---|---|---|---|---|
| Q1 | 1 | 1 (EC-1) | 0 | 0 |
| Q2 | 2 | 1 (EC-1) | 0 | 1 (EC-5) |
| Q3 | 2 | 1 (EC-1) | 1 (EC-4) | 0 |
| Q4 | 1 | 1 (EC-1) | 0 | 0 |
| Q5 | 2 | 2 (EC-1, EC-2) | 0 | 0 |
| Q6 | 3 | 2 (EC-1, EC-2) | 1 (EC-3) | 0 |
| Q7 | 2 | 2 (EC-1, EC-2) | 0 | 0 |
| Q8 | 1 | 1 (EC-1) | 0 | 0 |

(EC-1 e EC-2 são transversais; contados uma vez por questão afetada.)

**Verdict:** DISCOVERY PLAN NEEDS ADJUSTMENT — 2 MUST FIX a absorver antes de
`/discover-execute`.
