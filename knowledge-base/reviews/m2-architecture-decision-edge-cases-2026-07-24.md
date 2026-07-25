# Discover Edge Case Review — m2-architecture-decision

Date: 2026-07-24
Discovery plan analyzed: knowledge-base/discoveries/plans/m2-architecture-decision-plan.md
Research questions analyzed: 6
Edge cases found: 5 (MUST FIX: 1, SHOULD TEST: 2, DOCUMENT: 2)

Todos os 12 paths citados existem (verificado). O github releases (sherpa model zoo) está alcançável. O risco concentra-se em Q4 (a medição de RTFx) — tanto a **validade metodológica** quanto a **rodabilidade real** dos modelos.

## MUST FIX

### EC-1: Q4 mede RTFx sem fixar comparabilidade de tamanho nem explicar por que RTFx de modelo não-PT-BR é evidência válida
- **Affected question:** Q4
- **Family:** Method / Interpretation
- **Scenario:** Durante o execute, mediria-se o RTFx de um zipformer de 34M (inglês) e de um parakeet de 600M (TAGARELA) e compará-los-ia lado a lado — mas 34M vs 600M não é comparação de **arquitetura**, é de tamanho. Pior: um revisor pode objetar "isso é modelo inglês/chinês, não vale para o produto PT-BR".
- **Impact:** A matriz de RTFx vira maçã-com-laranja; a conclusão do critério 1 fica atacável (falácia §3 #8 — confundir tamanho com velocidade; e a objeção de idioma).
- **Suggested fix:** Q4 deve (a) medir RTFx em **faixas de tamanho comparáveis** (~30M/~80M/~123M, `PRD.md` § 8.1) por família, normalizando a comparação; e (b) registrar explicitamente que **RTFx é função da arquitetura+tamanho, NÃO do idioma** — o encoder faz o mesmo compute independente da língua, logo um zipformer inglês de 34M dá o RTFx daquela arquitetura-tamanho (evidência válida do critério 1), enquanto **WER é dependente de idioma e permanece `[LITERATURA]`**. Essa distinção é a fundação do método de M2.

## SHOULD TEST

### EC-2: TAGARELA cacheado é um blob único — pode não rodar em sherpa-onnx sem o formato completo
- **Affected question:** Q4
- **Kind:** feasibility
- **Suggested halt-loop checkpoint:** Antes de reportar o RTFx do parakeet/TAGARELA, validar que o modelo está no formato que o sherpa espera (encoder/decoder/joiner + `tokens.txt`, OU um `nemo-transducer` single-file com tokens). O cache atual (`models--alefiury--parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx`) tem **um único blob de 2,3 GB, sem tokens.txt** — provavelmente incompleto/não-sherpa. Se não rodar em 20 min, marca `[DESCONHECIDO — formato incompatível/incompleto]` (D1/D3 já cobrem) e usa um parakeet de referência do zoo sherpa para o RTFx da **família** parakeet-tdt.

### EC-3: verificar que o teste de streaming do funasr de fato assere equivalência batch↔incremental
- **Affected question:** Q6
- **Kind:** interpretation
- **Suggested halt-loop checkpoint:** Ao ler `funasr/tests_models/test_paraformer_streaming.py`, confirmar que há uma asserção de **equivalência** (batch ≡ streaming dentro de tolerância) e não só "roda sem erro". Se for só smoke, reportar honestamente que o peer não prova equivalência e que isso vira experimento de M4 para o finalista.

## DOCUMENT

### EC-4: Moonshine tem RTF de CPU publicado `[LITERATURA]` — usar se a medição própria falhar
- **Affected question:** Q4
- **Accepted risk:** Moonshine publica 69 ms (34M), 165 ms (123M), 269 ms (245M) em Linux x86 (`knowledge-base/references/_catalog.md`). Se rodar o moonshine ONNX via sherpa der `[MEDIDO]`, ótimo (compara na MESMA CPU que os outros); se não rodar, cita-se o `[LITERATURA]` com a ressalva de que é de outra CPU. Ambos honestos e rotulados — nunca se mistura o número publicado com os medidos sem rótulo.

### EC-5: parâmetros de arquitetura vêm de um config específico do peer, não do modelo PT-BR (que não existe)
- **Affected question:** Q1
- **Accepted risk:** `icefall/egs/reazonspeech/ASR/zipformer/zipformer.py` é um config de zipformer para japonês; a **topologia da família** (U-Net encoder, downsampling, atenção) é o que se extrai — representativa da arquitetura, não do modelo PT-BR final (que é treinado em M3+). É correto: M2 avalia arquitetura (família), não o modelo específico.

## Summary

| Question | Edges found | MUST FIX | SHOULD TEST | DOCUMENT |
|----------|-------------|----------|-------------|----------|
| Q1 | 1 | 0 | 0 | 1 |
| Q2 | 0 | 0 | 0 | 0 |
| Q3 | 0 | 0 | 0 | 0 |
| Q4 | 3 | 1 | 1 | 1 |
| Q5 | 0 | 0 | 0 | 0 |
| Q6 | 1 | 0 | 1 | 0 |

**Verdict:** DISCOVERY PLAN NEEDS ADJUSTMENT (1 MUST FIX — Q4 precisa fixar comparabilidade de tamanho + a fundação "RTFx é agnóstico a idioma, WER não")
