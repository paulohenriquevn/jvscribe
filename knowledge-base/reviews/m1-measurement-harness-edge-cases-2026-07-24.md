# Discover Edge Case Review — m1-measurement-harness

Date: 2026-07-24
Discovery plan analyzed: knowledge-base/discoveries/plans/m1-measurement-harness-plan.md
Research questions analyzed: 6
Edge cases found: 5 (MUST FIX: 2, SHOULD TEST: 1, DOCUMENT: 2)

## MUST FIX

### EC-1: Fase A de Q4 (`Glob test/*.py`) não acha os testes de resample/augment de lhotse
- **Affected question:** Q4
- **Family:** Method
- **Scenario:** O plano manda `Glob test/*.py`, mas os testes de augmentação/resample de lhotse vivem em **subdiretórios**: `lhotse/test/audio/test_resample_randomized.py`, `lhotse/test/augmentation/test_torchaudio.py`, `lhotse/test/cut/test_cut_augmentation.py` (verificado por `find`). Um glob não-recursivo do topo de `test/` retorna zero matches.
- **Impact:** Fase A esgota em 3 retries → Q4 é marcada BLOCKED "Fase A exhausted" incorretamente → o corner **Integration tests** fica sem seção → blueprint cai para INVALID no `discover-confidence` (corner vazio é hard cap).
- **Suggested fix:** Trocar a Fase A de Q4 para apontar os subdirs reais: `Glob lhotse/test/audio/*resampl* lhotse/test/augmentation/*.py` + `Grep 'allclose\|rtol\|Resample'` neles.

### EC-2: Fase A de Q5 lê `pyproject.toml` (só `numpy`) e perde as deps reais de avaliação
- **Affected question:** Q5
- **Family:** Method / Reference path
- **Scenario:** `moonshine/python/pyproject.toml` declara apenas `numpy` como dependency. As deps que **de fato** rodam a avaliação estão nos **imports** de `moonshine/scripts/eval-librispeech.py`: `jiwer` (cálculo de WER), `datasets` (load do corpus), `soundfile`, `scipy.signal.resample_poly`, `whisper.normalizers` (verificado por grep dos imports). Grep de `dependencies` no pyproject retorna `numpy` e mente sobre o que o eval precisa.
- **Impact:** Q5 responde "o baseline precisa de numpy", que é falso e inútil para o plano; o padrão de eval emprestável (jiwer + normalização + load_dataset) fica invisível.
- **Suggested fix:** Fase A de Q5 passa a ler os **imports** de `moonshine/scripts/eval-librispeech.py` (linhas ~48-60) como fonte primária das deps de avaliação; o `pyproject.toml` vira secundário (deps de inferência do runtime moonshine).

## SHOULD TEST

### EC-3: bootstrap de WER exige granularidade por-utterance, mas ambos os peers reportam WER agregado corpus-wide por padrão
- **Affected question:** Q2
- **Suggested halt-loop checkpoint:** Antes de fechar Q2, validar que o blueprint capturou a **estrutura por-utterance** de `write_error_stats` (`results: List[Tuple[cut_id, ref, hyp]]`, `icefall/icefall/utils.py:689` e o laço `for cut_id, ref, hyp in results`), e não apenas o agregado. Confirmado que a entrada É por-utterance (o bootstrap é viável), mas tanto icefall quanto moonshine (`eval-librispeech.py:20` — "WER is aggregated corpus-wide") **reportam** o agregado. Se o blueprint copiar só o número agregado, o bootstrap fica impossível. O checkpoint garante que a saída por-segmento seja preservada como insumo do IC.

## DOCUMENT

### EC-4: whisper-large-v3 e o modelo TAGARELA não têm deps derivávies dos peers clonados
- **Affected question:** Q5
- **Accepted risk:** Só a parte **Moonshine** do baseline é derivável de peer clonado (via `eval-librispeech.py`). `whisper-large-v3` e `alefiury/...-TAGARELA` são artefatos HuggingFace/`transformers`; suas deps e comando de execução vêm do **model card** (`[LITERATURA]`), fora de `knowledge-base/references/`. É correto e honesto: a descoberta mapeia o padrão de eval emprestável dos peers + marca whisper/TAGARELA como `[LITERATURA]` a resolver no `/to-plan`. A descoberta **não instala nem roda** modelos (isso é implementação de M1, não descoberta) — alinhado a `.claude/rules/asr-evidence-discipline.md` § 2 (conclusão não excede evidência).

### EC-5: normalização de texto é parte do WER, mas o normalizador dos peers é inglês
- **Affected question:** Q3, Q5
- **Accepted risk:** `eval-librispeech.py:60` usa `whisper.normalizers.EnglishTextNormalizer` — confirma que **normalização** (números, pontuação, caixa) é etapa obrigatória do cálculo de WER, mas o normalizador é EN e **não serve** para PT-BR (acentos, "R$", "pra"/"para", numerais por extenso). O blueprint deve registrar que existe um passo de normalização PT-BR **próprio** (não emprestável), como componente do harness — não como falha, mas como fronteira conhecida. Ancora em `PRD.md` § 7.2 (WER não é a métrica final).

## Summary

| Question | Edges found | MUST FIX | SHOULD TEST | DOCUMENT |
|----------|-------------|----------|-------------|----------|
| Q1 | 0 | 0 | 0 | 0 |
| Q2 | 1 | 0 | 1 | 0 |
| Q3 | 1 | 0 | 0 | 1 |
| Q4 | 1 | 1 | 0 | 0 |
| Q5 | 2 | 1 | 0 | 1 |
| Q6 | 0 | 0 | 0 | 0 |

**Verdict:** DISCOVERY PLAN NEEDS ADJUSTMENT (2 MUST FIX — corrigir Fase A de Q4 e Q5 antes do execute)
