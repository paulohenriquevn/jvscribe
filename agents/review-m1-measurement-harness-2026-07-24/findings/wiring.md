# Wiring review findings
- W1 HIGH: SampleCounter (harness.rs:169-192) é export público test-only, sem caller de produção nem observabilidade. bench é sequencial. Fix: remover (YAGNI) — soak concorrente é futuro.
- W2 LOW: baseline_minds14.py é o runnable real (não run_baseline.py como no plano) — sem teste direto (orquestração fina). Documentar.
- W3 INFO: baseline usa faster-whisper-base/minds14 pt-PT, não Moonshine/pt-BR — honestamente rotulado, DoD satisfeito.
- Núcleo (3 medidores + HarnessError) WIRED e comprovado por execução real.
