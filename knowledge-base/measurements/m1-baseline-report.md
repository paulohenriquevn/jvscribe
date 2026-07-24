# M1 — Baseline Report (test set 8 kHz)

**Corpus:** minds14 pt-PT (PolyAI, CC-BY-4.0) — fala telefônica bancária REAL 8 kHz nativa, 15 utterances, transcrição humana. Medido no canal nativo (sem augmentação sintética — a cadeia a-law é validada à parte por T2.1). Caveats honestos (falácia § 3 #6): (a) pt-PT europeu, NÃO pt-BR — o test set pt-BR definitivo depende de corpus consentido (LGPD, fora de escopo); (b) minds14 tem code-switching (algumas refs em inglês), o que infla o WER de um modelo transcrevendo com language=pt; (c) faster-whisper-base é fraco — é piso, não teto (large-v3 faria muito melhor).

> Transcrição humana (NUNCA pseudo-label — `PRD.md` § 7.3). Números `[MEDIDO]`; WER sempre com IC 95% via bootstrap por-utterance (blueprint ADR D3), nunca ponto isolado.

| Modelo | WER | IC 95% | n (utterances) |
|---|---|---|---|
| faster-whisper-base (int8, CPU) | WER = 68.3% | [IC95: 46.8%–96.9%] | 15 | `[MEDIDO]`

