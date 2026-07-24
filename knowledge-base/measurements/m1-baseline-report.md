# M1 — Baseline Report (test set 8 kHz)

**Corpus:** minds14 pt-PT (PolyAI, CC-BY-4.0) — fala telefônica bancária REAL 8 kHz nativa, 15 utterances, transcrição humana. Medido no canal nativo (sem augmentação sintética — a cadeia a-law é validada à parte por T2.1). Caveats honestos (falácia § 3 #6): (a) pt-PT europeu, NÃO pt-BR — o test set pt-BR definitivo depende de corpus consentido (LGPD, fora de escopo); (b) minds14 tem code-switching (algumas refs em inglês), o que infla o WER de um modelo transcrevendo com language=pt; (c) faster-whisper-base é fraco — é piso, não teto (large-v3 faria muito melhor).

> Transcrição humana (NUNCA pseudo-label — `PRD.md` § 7.3). Números `[MEDIDO]`; WER sempre com IC 95% via bootstrap por-utterance (blueprint ADR D3), nunca ponto isolado.

**Proveniência `[MEDIDO]`:** comando `python3 scripts/baseline_minds14.py 15 base`; modelo faster-whisper-base int8 CPU cpu_threads=1 beam_size=1; dataset PolyAI/minds14 pt-PT (parquet refs/convert/parquet); bootstrap seed=2026, n_boot=2000; hardware = máquina de referência do dev (NÃO o piso da frota BYOD, Q-01).

| Modelo | WER | IC 95% | n (utterances) |
|---|---|---|---|
| faster-whisper-base (int8, CPU) | WER = 73.0% | [IC95: 49.8%–104.6%] | 15 | `[MEDIDO]`

> **IC largo por poder estatístico, não defeito da régua.** Com n < 50 o IC de ~50 p.p. não decide entre candidatos — é o **risco 1 do ROADMAP** (`ROADMAP.md` § M1). Um test set maior é pré-requisito para M4 comparar finalistas.

