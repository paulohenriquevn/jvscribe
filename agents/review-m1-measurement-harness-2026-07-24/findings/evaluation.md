# Evaluation/evidence-discipline review findings
- EVID-01 MEDIUM: m1-baseline-report.md [MEDIDO] sem bloco de proveniência (comando/hardware/seed/n_boot). Fix: add provenance no render_report.
- EVID-02 MEDIUM: soak 10min (RNF-04) NÃO rodado; "17,81× sustentado"+"térmica 1,34" são proxy ~30s. Fix: relabel "janela curta (proxy)", RNF-04 = [DESCONHECIDO — soak não executado].
- EVID-03 MEDIUM: 17,81× sem carga concorrente (RNF-05) sem caveat inline. Fix: anotar "sem carga concorrente".
- EVID-04 LOW: "domínio exato" exagera (minds14 é locutor único pt-PT). Fix wording.
- EVID-05 LOW: IC largo n=15 não enquadrado como risco 1. Fix: add framing.
- EVID-06 INFO: baseline nativo desviou (não exercita a-law ponta-a-ponta no baseline; só T2.1).
- Núcleo respeita disciplina: RTFx áudio/parede, warmup, p99, IC c/ seed, pseudo-label rejeitado. Zero BLOCKER/HIGH.
