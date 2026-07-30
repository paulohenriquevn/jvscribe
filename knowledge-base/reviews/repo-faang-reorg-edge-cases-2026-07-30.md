# Edge Case Review — repo-faang-reorg

Date: 2026-07-30
Tasks analyzed: 9 (T1.1–T1.3, T2.1–T2.3, T3.1–T3.2, T4.1)
Cases found: 7 (EDGE: 3, NEGATIVE: 4 | MUST FIX: 3, SHOULD TEST: 2, DOCUMENT: 2)

Escopo é um refactor de filesystem (git mv/rm + conftest). "Boundaries" reais = resolução de import,
coleta do pytest, e o padrão de `grep` usado como guarda. Nada de rede/concorrência/persistência.

## MUST FIX

### EC-1: guarda de deleção do T1.1 não pega `from X import` (falso-negativo)
- **Affected task:** T1.1
- **Kind:** NEGATIVE (padrão de verificação inválido)
- **Family:** Format
- **Scenario:** a guarda usa `grep "import prep_mls\|..."`. A linha real de consumo é
  `from prep_mls import download_extract_mls` (`prep_nemo.py:21`) — que **não contém** a substring
  `import prep_mls` (contém `prep_mls import`). A guarda retornaria vazio mesmo se um survivor
  importasse o módulo via `from … import`, autorizando uma deleção que quebra o survivor.
- **Impact:** deletar um módulo ainda importado → `ImportError` em runtime não coberto pelos testes.
- **Suggested fix:** trocar o padrão para `grep -REn "^(from|import) (prep_icefall|prep_mls|prep_nemo|prep_conformer_ctc_decode|patch_ctc_decode|resume_tagarela_feats|download_tagarela_subset|gen_phonemes)\b"` (pega os dois estilos). No caso atual o par é deletado junto, mas a guarda tem de ser correta.

### EC-2: `git mv` exige o diretório-destino existir
- **Affected task:** T2.2
- **Kind:** NEGATIVE (pré-condição de I/O ausente)
- **Family:** Resource
- **Scenario:** `git mv training/batch_transcribe.py training/batch/` falha com "destination directory
  does not exist" se `training/batch/` ainda não existe. O plano lista os subdirs como "(NEW dirs)" mas
  não cria explicitamente antes do primeiro `git mv`.
- **Impact:** T2.2 aborta no primeiro move.
- **Suggested fix:** adicionar sub-passo no T2.2: `mkdir -p training/{finetune,batch,realtime,eval}` ANTES dos `git mv` (dirs vazios não são tracked, mas o `git mv` para dentro deles passa a rastrear).

### EC-3: co-location incompleta — só os 2 pares conhecidos foram verificados
- **Affected task:** T2.2
- **Kind:** NEGATIVE (contrato de import cross-pipeline não exaustivo)
- **Family:** Integration
- **Scenario:** co-loquei `eval_public_hf↔batch_transcribe` e `prep_finetune/prep_augment↔prep_phoneme_head`
  a partir de um grep pontual. Se QUALQUER outro script importar por nome um módulo que caia em pipeline
  DIFERENTE (ex.: um `measure_*` importar `decode_onnx_local`, ou `make_telephone_test` importar algo de
  finetune), o import quebra em runtime após o move.
- **Impact:** import cross-dir quebrado, invisível aos testes de import por nome (o conftest mascara em
  teste, mas o script rodado standalone falha).
- **Suggested fix:** no T2.2, ANTES de mover, rodar o grafo completo: `grep -REn "^(from|import) [a-z_]+" training/*.py | grep -vE "os|sys|re|json|pathlib|numpy|torch|…"` e confirmar que cada par (importador, importado) cai no MESMO subdir; ajustar o mapa de destino se aparecer par cross-pipeline. Adicionar teste `test_no_cross_pipeline_imports` que asserta isso.

## SHOULD TEST

### EC-4: conftest.py carregado independente do CWD de invocação
- **Affected task:** T2.1
- **Kind:** EDGE (limite válido)
- **Suggested test:** `test_pipeline_layout` deve passar tanto com `pytest training/tests` (da raiz)
  quanto com `cd training && pytest tests` — assert que o import por nome resolve nos dois CWDs (pytest
  carrega `training/conftest.py` como ancestral em ambos).

### EC-5: colisão de nome entre subdirs de pipeline no sys.path
- **Affected task:** T2.1
- **Kind:** NEGATIVE (ambiguidade silenciosa)
- **Suggested test:** `test_no_duplicate_module_basenames` — assert que não há dois `.py` com o mesmo
  basename em subdirs diferentes (senão a ordem de `sys.path.insert` decide silenciosamente qual vence).
  Hoje não há colisão; o teste protege a invariante contra moves futuros.

## DOCUMENT

### EC-6: possível segundo `mic_transcribe.py` sob models/ (Q1 do plano)
- **Kind:** EDGE
- **Accepted risk:** o paper §10 cita `models/…/mic_transcribe.py`. O move só toca o de `training/`. Se
  um teste importar `mic_transcribe` por nome e ambos existirem, o de `realtime/` (conftest) vence.
  Confirmar em T2.2 que os dois são distintos e que nenhum teste depende do de `models/`. Já registrado
  como Q1 (Unresolved Questions).

### EC-7: bleed do sys.path do conftest ao rodar `pytest training/tests scripts/tests` juntos
- **Kind:** NEGATIVE
- **Accepted risk:** `training/conftest.py` insere os subdirs globalmente na sessão pytest; `scripts/tests`
  importa de `scripts/` (nomes distintos — `bootstrap_wer_ci`, `blank_penalty_probe`). Sem colisão de
  nome hoje → risco nulo na prática. EC-5 (teste de basenames) cobre a regressão futura.

## Summary

| Task | EDGE | NEGATIVE | MUST FIX | SHOULD TEST | DOCUMENT |
|------|------|----------|----------|-------------|----------|
| T1.1 | 0 | 1 | 1 (EC-1) | 0 | 0 |
| T1.2 | 0 | 0 | 0 | 0 | 0 |
| T1.3 | 0 | 0 | 0 | 0 | 0 |
| T2.1 | 1 | 1 | 0 | 2 (EC-4,5) | 0 |
| T2.2 | 1 | 2 | 2 (EC-2,3) | 0 | 1 (EC-6) |
| T2.3 | 0 | 0 | 0 | 0 | 1 (EC-7) |
| T3.x | 0 | 0 | 0 | 0 | 0 |
| T4.1 | 1 | 0 | 0 | 0 | 0 |

**Coverage check:** cada task que toca fronteira de import/FS teve lente EDGE e NEGATIVE consideradas.
Tasks de doc (T3) e gitignore (T1.3) não têm fronteira de dados relevante.

**Verdict:** PLAN NEEDS ADJUSTMENT — 3 MUST FIX (EC-1 padrão de grep, EC-2 mkdir, EC-3 grafo de imports completo) absorvidos na v1.1 antes do `/plan-confidence`.
