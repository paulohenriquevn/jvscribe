# Discover Edge Case Review — m4-pilot

Date: 2026-07-25
Discovery plan analyzed: knowledge-base/discoveries/plans/m4-pilot-plan.md
Research questions analyzed: 8
Edge cases found: 5 (MUST FIX: 2, SHOULD TEST: 1, DOCUMENT: 2)

## MUST FIX

### EC-1: medir "taxa de erro" de G2P (Q-08) exige um gold fonético PT-BR que pode não existir localmente
- **Affected question:** Q3
- **Family:** Method
- **Scenario:** Q3 promete "taxa de erro `[MEDIDO]`". Uma taxa de erro absoluta (PER — Phoneme Error Rate) exige transcrição fonética humana de referência (gold). Não há léxico fonético PT-BR gold no ambiente. Sem gold, o execute ou fabrica um número ou trava.
- **Impact:** Q-08 sem número defensável, ou número fabricado (viola § 1).
- **Suggested fix:** Q3 mede o que é honestamente medível SEM gold: (a) **cobertura** (% de palavras que o G2P mapeia sem falha/OOV), (b) **determinismo** (mesma entrada→mesma saída), (c) **concordância** entre variantes (pt-br vs pt-pt, ou espeak vs regra), (d) **inspeção qualitativa** de um conjunto de casos difíceis (nomes próprios, code-switching, dígitos). PER absoluto fica `[DESCONHECIDO]` (precisa de gold humano — trabalho de M4/M5 com anotador), declarado honestamente.

### EC-2: custo/infra (Q6, Q7) via web esbarra no allowlist vazio
- **Affected question:** Q6, Q7
- **Family:** Method
- **Scenario:** Q6 (preço de GPU) e Q7 (throughput de referência) precisam de números externos; o `discover-web-allowlist.txt` está vazio → WebFetch best-effort pode falhar.
- **Impact:** estimativa de custo sem lastro, ou fabricada.
- **Suggested fix:** usar valores `[LITERATURA]` de conhecimento estabelecido (faixas de $/hora de GPU preemptível; throughput de A100/3090 em TFLOPs) com o rótulo e a ressalva de que são ordens de grandeza, não cotações; a fórmula de Q7 (`[ESTIMATIVA]`) é explícita e o número exato só vem do 1º run real. Nunca apresentar faixa como cotação firme.

## SHOULD TEST

### EC-3: a recipe librispeech não traz 3 configs prontas de 30/80/123M
- **Affected question:** Q1
- **Suggested halt-loop checkpoint:** ao responder Q1, confirmar se os 3 tamanhos vêm de configs distintas OU de escalar `num_encoder_layers`/`encoder_dim`; se só houver 1 config default, registrar que os outros 2 são derivados por escala (parâmetro), não configs prontas — não afirmar "3 recipes existem" se há 1.

## DOCUMENT

### EC-4: a discovery LÊ a recipe de treino; não a executa (k2 quebrado + GPU)
- **Accepted risk:** Q1/Q2/Q8 respondem "como o icefall treina/valida" por LEITURA do código clonado — não dependem de k2 importável nem de GPU. Q4 (viabilidade de rodar) é separada e informa a decisão de infra. Ler ≠ treinar; nenhuma afirmação de treino medido sai da discovery.

### EC-5: FastConformer (2º finalista) sem recipe clonada
- **Accepted risk:** NeMo não está clonado (`_catalog.md`). FastConformer entra por `[LITERATURA]`/parakeet-rs (README), coerente com o ADR de M2 (elo mais fraco, a medir). O desenho de treino detalhado é do Zipformer (icefall clonado); FastConformer fica com o esboço + a ressalva de que a recipe vive no NeMo, a validar antes de tratá-lo como par.

## Summary

| Question | Edges | MUST FIX | SHOULD TEST | DOCUMENT |
|----------|-------|----------|-------------|----------|
| Q1 | 1 | 0 | 1 (EC-3) | 0 |
| Q3 | 1 | 1 (EC-1) | 0 | 0 |
| Q6/Q7 | 1 | 1 (EC-2) | 0 | 0 |
| (transversal) | 2 | 0 | 0 | 2 (EC-4, EC-5) |

**Verdict:** DISCOVERY PLAN NEEDS ADJUSTMENT — absorver EC-1 (método de Q-08 sem gold) e EC-2 (custo/infra best-effort com rótulo) no plano; EC-3 como checkpoint; EC-4/EC-5 como nota.
