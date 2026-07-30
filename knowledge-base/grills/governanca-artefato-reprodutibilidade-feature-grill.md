---
slug: governanca-artefato-reprodutibilidade
generated_by: roadmap-feature
date: 2026-07-30
milestone_id: M9
status: completed
---

# Grill — M9 Governança de artefato e reprodutibilidade

## Origem

Auditoria de system design (`/loop-system-design`, modo full) de 2026-07-30. Fonte:
`system-design-output/final_report.md` — 51 achados, 4 quality gates aprovados.

## Step 3 — cross-check de out-of-scope

**Sobreposição detectada:** "versionamento de modelo", dentro do item **Plataforma de frota**.

**Decisão do dono:** remover do out-of-scope (a decisão original foi revisitada).

**Aplicação restritiva pelo coordenador, declarada e passível de reversão:** removido apenas
o termo "versionamento de modelo" da lista entre parênteses. Distribuição BYOD, telemetria e
monitoramento de WER em produção **permanecem fora de escopo** — remover o bullet inteiro
traria a plataforma de frota completa para V1, colidindo com o desenho de M7/M8 e excedendo
em muito o que o M9 requer. Nota de data registrada na seção do ROADMAP.

## Q1 — O que é e por que agora

Fechar as lacunas de integridade e reprodutibilidade da auditoria antes de M6 começar. O
gatilho: M6 medirá os cinco critérios de RNF sobre um runtime cujo artefato de modelo é
ambíguo (dois `model.int8.onnx` com vocabulários de 502 e 503 linhas) e cuja suíte não roda
fora da máquina do dono. Medir antes de fechar produz número que não transfere.

## Q2 — Dependências

**M5.** O artefato a canonizar precisa existir. M5 está `[~]` (2/3 DoDs; o telefônico foi
deferido por limite de dado), mas o export do modelo existe — suficiente para a dependência.

## Q3 — Escopo do DoD

**"Tudo do relatório, menos o R1"** — 10 bullets. O R1 (teto de threads no runtime + re-medição
sobre o binário entregue) **não entra**: já é o terceiro bullet do DoD de M6, que está `[ ]` e
não começou. Duplicá-lo violaria o anti-pattern nº 1 do skill.

## Q4 — Riscos novos

Registrados os 4 (o dono escolheu "ambos os pares"):

1. Fail-fast de `vocab_size` quebra fluxos que hoje passam em silêncio com o modelo errado.
2. CI expõe a quantidade real de testes que fazem SKIP sem ambiente.
3. Consolidar as 7 cópias do colapso CTC pode mudar o resultado de alguma pipeline e
   invalidar um número já publicado.
4. Mover o artefato para `models/current/` quebra scripts com caminho hard-coded.

## Step 5 — SOTA delta

**Nenhum peer novo.** O escopo do M9 é higiene e governança de repositório (CI, licença,
artefato canônico, shared kernel) — não há domínio técnico novo que exija prior art. Os 8
peers existentes em `knowledge-base/references/` permanecem intocados; `_catalog.md` não foi
editado.

## Invariante registrado por instrução explícita do dono

**NUNCA excluir modelos.** Nenhum arquivo de modelo, peso ou vocabulário sai do repositório,
em nenhuma etapa deste milestone. Verificado: dos 21 achados de remoção da auditoria, zero
tocam peso ou vocabulário. Persistido também em memória de projeto (`never-delete-models.md`).
