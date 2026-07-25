# Edge Case Review — m2-architecture-decision (plan)

Date: 2026-07-24
Tasks analyzed: 2 (T1.1 escrever ADR, T1.2 atualizar PRD)
Cases found: 2 (EDGE: 1, NEGATIVE: 1 | MUST FIX: 0, SHOULD TEST: 0, DOCUMENT: 2)

M2 é um plano de **documento** (ADR + PRD + CHANGELOG) — sem código, sem I/O, sem concorrência. As lentes edge/negative aplicam-se de forma limitada. Verificação empírica confirma que os critérios de aceite grep-based são sólidos: "receita completa publicada" aparece exatamente 1× no PRD (critério `count==0` válido após a edição); o blueprint ainda não é referenciado; o ADR não existe. Nenhum MUST FIX.

## MUST FIX

Nenhum.

## SHOULD TEST

Nenhum.

## DOCUMENT

### EC-1: critérios de aceite grep-based são um piso, não prova de qualidade do ADR
- **Affected task:** T1.1
- **Kind:** EDGE (extremo válido — o grep casa a string mas não julga se o ADR é bom)
- **Accepted risk:** `grep "Zipformer+CTC"` confirma que o finalista foi **nomeado**, não que o raciocínio está correto. Isso é aceito: o grep é o piso mecânico do DoD; a **qualidade do ADR** (raciocínio, alternativas bem justificadas, não-travagem respeitada) é validada por humano no `/review` (o gate mais rigoroso, que lê o ADR contra o blueprint e a disciplina de evidência). Piso mecânico + review humano é a cobertura correta para um artefato de decisão.

### EC-2: a correção do PRD assume que a frase aparece só onde se espera
- **Affected task:** T1.2
- **Kind:** NEGATIVE (input inesperado — a frase poderia estar em outro lugar)
- **Accepted risk:** Verificado empiricamente que "receita completa publicada" ocorre **exatamente 1×** (linha 237). Se uma edição futura do PRD reintroduzisse a frase em outro ponto, o critério `count==0` a pegaria (fail-safe correto). O risco é nulo hoje e o critério é robusto a reintroduções.

## Summary

| Task | EDGE | NEGATIVE | MUST FIX | SHOULD TEST | DOCUMENT |
|------|------|----------|----------|-------------|----------|
| T1.1 | 1 | 0 | 0 | 0 | 1 |
| T1.2 | 0 | 1 | 0 | 0 | 1 |

**Coverage check:** T1.1 (input = evidência do blueprint) tem a lente EDGE considerada (grep-floor); T1.2 (input = PRD atual) tem a NEGATIVE (frase em outro lugar). Ambas documentadas como risco aceito — não há boundary de dados que quebre.

**Verdict:** PLAN OK (nenhum MUST FIX; 2 riscos documentados, é plano de documento)
