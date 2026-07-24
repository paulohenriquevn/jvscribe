# Test review findings
- TEST-M1-01 MEDIUM: augmentation_test band test unwrap_or(0.0) → falso-verde se parse falhar. Fix: assert rms_mid>0 && rms_high>0.
- TEST-M1-02 MEDIUM: EC-5 "0 após transcrição" é branch inalcançável em run_baseline.py + teste dispara caminho diferente. Fix: remover branch morto OU testar de verdade + match=.
- TEST-M1-03 LOW: SampleCounter test baixo valor (overlap W1 — remover).
- TEST-M1-04 LOW: IC-mais-largo-para-N-pequeno não asserido.
- TEST-M1-05 LOW: negative Python tests sem match=.
- TEST-M1-06 LOW: augmentation temp filenames fixos (colisão em CI paralelo).
- TEST-M1-07 INFO: bench mode sem auto-test (aceito pelo plano).
- Determinismo OK, concorrência não-flaky. Sem BLOCKER/HIGH.
