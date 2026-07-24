# Deps Audit: m1-measurement-harness

**Date:** 2026-07-24
**Mode:** plan-bound:m1-measurement-harness
**Verdict:** PASS
**Hard caps triggered:** [] (nenhum)

## Summary
- Ecosystems detected: Rust (workspace, 4 Cargo.toml), Python (deps NEW do plano — ainda não em manifesto)
- Total deps audited: Rust 44 (via Cargo.lock) + Python 47 resolvidas (jiwer/soundfile/numpy/openai-whisper + transitivas)
- Vulnerabilities found: 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW
- Outdated: n/a (auditoria de CVE, não de outdated, nesta rodada)
- Allowlist hits: 0
- Auditor coverage: { cargo-audit: ran (exit 0, clean), pip-audit: ran (47 deps, "No known vulnerabilities found"), osv-scanner: ran (Cargo.lock 44 pkgs, "No issues found") }

## Vulnerabilities (sorted by severity)

Nenhuma.

## Outdated (non-vulnerable)

- `jiwer` latest 4.0.0; plano pina `>=3.0,<4.0` — pin deliberado abaixo do major novo (boa higiene, não é finding).
- `soundfile` latest 0.14.0; plano `>=0.12,<1.0` — coberto.

## Plan validation (Mode 2)

| Plan dep | Section | Registry match | Audit clean? | Rule 9 OK? | Verdict |
|---|---|---|---|---|---|
| `jiwer >=3.0,<4.0` | NEW | sim (PyPI, 3.x existe) | sim (sem CVE) | sim (2 alternativas rejeitadas: edit-distance à mão, evaluate.load) | OK |
| `soundfile >=0.12,<1.0` | NEW | sim (PyPI 0.14) | sim | sim (scipy.io.wavfile, wave stdlib rejeitados) | OK |
| `numpy >=1.24,<3.0` | NEW | sim | sim | sim (laços puros rejeitados) | OK |
| `openai-whisper >=20231117` | NEW | sim (PyPI, MIT) | sim | sim (faster-whisper/transformers rejeitados) | OK |
| Rust (nenhuma dep nova) | — | — | sim (cargo audit + osv limpos) | n/a | OK |

## Recommended next steps

1. Nenhum bump necessário — todas as deps declaradas estão sem CVE conhecida nas versões pinadas.
2. Proceder para `/plan-confidence`.

## Notas de proveniência

- `cargo audit` e `osv-scanner` rodaram sobre o `Cargo.lock` real do workspace (deps de M0). O plano de M1 **não adiciona crate Rust** — o harness reusa `metrics.rs`/`AsrEngine`.
- As deps Python são NEW (ainda não instaladas). A auditoria rodou `pip-audit -r` sobre as versões pinadas do plano, resolvendo 47 deps transitivas (inclui torch via openai-whisper) — todas sem CVE conhecida na data.
- Nenhum número foi fabricado; toda saída vem verbatim dos auditores (Regra 9 / anti-pattern 4).
