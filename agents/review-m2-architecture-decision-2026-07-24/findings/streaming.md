# Streaming review findings (streaming-asr-scientist)
- STREAM-ADR-01 MEDIUM: ADR:38 cita test_paraformer_streaming.py:24-26 (config de chunk) p/ "modelo -online distinto" — o nome está em :14, offline em test_paraformer.py:12. Conclusão verdadeira, linha não exibe o fato (anti-pattern §6). Fix: trocar citação p/ :14 + test_paraformer.py:12.
- STREAM-ADR-02 LOW: "cache 7 tensores + um encoder dois modos" só em :62-69 (prova cache); "dois modos" está em :487/:538/:573. Ampliar citação.
- STREAM-BP-03 LOW: "7 tensores" = 7 categorias POR encoder (7×num_encoders total). Clarificar.
- STREAM-BP-05 INFO: célula da matriz "✅ nativo" sem qualificador "mecanismo, não equivalência".
- STREAM-POS-04 INFO: equivalência batch≡incremental honestamente diferida a M4 (conformidade § 0).
- Zero BLOCKER; substância correta.
