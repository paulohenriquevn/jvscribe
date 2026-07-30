# Review final — M9 Governança de artefato e reprodutibilidade

Data: 2026-07-30 · Escopo: `99b243a^..HEAD` na branch `workspace`

## Veredito: READY_TO_MERGE

O review independente emitiu `NEEDS_FIXES` com 1 BLOCKER e 6 achados. Todos foram corrigidos
e re-verificados na fonte.

| Achado | Severidade | Estado | Evidência |
|---|---|---|---|
| Execução standalone quebrada por T3.1 | **BLOCKER** | ✅ corrigido | `python3 training/batch/batch_transcribe.py --help` → exit 0; coberto por `test_entrypoints_de_pipeline_rodam_standalone` |
| CI nunca executou | HIGH | ✅ corrigido | 7 defeitos reais expostos; Rust no container: 79 testes/10 SKIPs; Python em venv virgem: 91 passed/14 skipped |
| `normalize_ptbr` ambíguo | HIGH | ✅ corrigido | divergente renomeada para `normalize_for_wer_compare`, 5 callers migrados, teste trava a regressão |
| Guarda de layout vacuamente verde | MEDIUM | ✅ escopada | varredura por `git ls-files`: `models/` é gitignored, artefato local do operador, não contrato do repo |
| README diverge do ROADMAP | MEDIUM | ✅ corrigido | 0 estados órfãos |
| `LICENSE` era stub | LOW | ✅ corrigido | 202 linhas, com o apêndice que a Apache-2.0 §4(a) exige distribuir |
| Hash do ORT em arquivo separado | LOW | aceito | design melhor que o critério literal |

## Hard gates (`cycle-review.md`)

| Gate | Resultado |
|---|---|
| Testes falhando | 0 — Rust 79, Python 192 |
| Segredo commitado | nenhum |
| Commit direto em `main` | não — branch `workspace` |
| Trailer de coautoria proibido | 0 ocorrências |
| CHANGELOG atualizado | sim |

## Invariante do dono

**Zero arquivos de modelo, peso ou vocabulário removidos** em todo o M9 — verificado por
`git diff 99b243a^..HEAD --diff-filter=D` e por inventário antes/depois em cada operação
(27 arquivos, listagem idêntica).

## Os 7 defeitos que só a execução expôs

Três quebram para qualquer clone do repositório, não apenas no CI:

1. `rustup` ausente no container — o CI não era verificável localmente
2. `libpulse-dev` nunca instalado — **falharia no GitHub também**
3. Teste exigia servidor de áudio — falso vermelho em container
4. **Panic em `/fixture` envenenava o mutex e derrubava `/metrics`** — defeito de runtime
5. PEP 668 recusa `pip install` global — CI
6. **10 dependências usadas e não declaradas** — suíte
7. **Erro de coleta abortava a suíte inteira** — qualquer clone

Nenhum era visível na máquina do dono; nenhum apareceria em revisão de código.

## Limites honestos

- O CI foi validado com `act` (container local) e com venv virgem, **não** com um run real do
  GitHub Actions — não houve push para o remoto nesta sessão.
- `training/smoke/` permanece no HEAD. Estava no Grupo A da auditoria, mas a remoção não foi
  executada: exigiria re-verificar callers, e o benefício (447 linhas) não justificava o risco
  sem essa checagem.
- O scorecard e as severidades são julgamento; as contagens são medidas.
