# M1 — Medição do Harness (evidência [MEDIDO])

**Data:** 2026-07-24
**Comando:** `./scripts/bench.sh 10` (P-cores fixados via `taskset -c 0-1`, release build)
**Hardware:** máquina de referência do dev (i7 híbrido); **NÃO** é o piso da frota BYOD (Q-01 — `[DESCONHECIDO]`)
**Subject:** encoder emprestado de 600M (`models/m0-borrowed/encoder-model.onnx`), 10 iterações (2 de warmup), 2,98 s de áudio por iteração
**Rótulo:** `[MEDIDO — encanamento apenas]` — números do modelo **emprestado**, não do produto. Provam que a **régua** funciona, não que o modelo é bom (o modelo próprio vem em M5/M6).

## Resultado

| Métrica | Valor medido | Alvo (PRD § 6) | Observação |
|---|---|---|---|
| RTFx sustentado (áudio/parede) | **17,81×** | RNF-07 ≥ 6× (ASR isolado) | Warm; ver efeito do warmup abaixo |
| Latência p50/p95/p99 | **154,9 / 237,8 / 237,8 ms** | RNF-02 p99 ≤ 500 ms | 8 amostras medidas (p95=p99 por nearest-rank) |
| Razão térmica (2ª½ ÷ 1ª½) | **1,34** | RNF-04 ≥ 0,80 no soak de 10 min | > 1: ainda aquecendo no proxy curto; o soak real de 10 min via `bench.sh` mede throttling |
| Backlog | n/a offline | RNF-03 = 0 em 99,9% | Medido no modo `live` com captura real |

## O warmup importa (valida o ADR D2 do plano)

- **1ª iteração fria** (`macaw-cli fixture`, sem warmup): 1981 ms → RTFx ≈ **1,5×**.
- **Sustentado quente** (bench, 2 warmup descartados): ~155 ms/iter → RTFx **17,81×**.

Um benchmark que inclui o run frio na média (como `sherpa-onnx/…rtf-cxx-api.cc:120`)
reportaria um número entre os dois e **mentiria** sobre o regime sustentado — exatamente
a falácia § 3 #4 de `asr-evidence-discipline.md`. A régua descarta o warmup por
construção (`RtfxMeter::new(warmup_iters)`).

## Limites conhecidos (honestidade — § 4)

- **8 amostras** é pouco para p99 estável; o soak de 10 min (RNF-04) coleta milhares.
- **Razão térmica > 1** é artefato do proxy curto (2ª metade mede o modelo mais quente que a 1ª); só o soak de 10 min sob carga mede throttling real do chip U de 15 W.
- **Máquina de referência ≠ piso da frota** (Q-01) — extrapolar estes 17,81× para "a frota" seria a falácia mais provável do projeto (`CLAUDE.md`).

## Reprodução

```bash
./scripts/bench.sh 10          # sem carga concorrente
./scripts/bench.sh 30 --load   # com carga nos E-cores (RNF-05)
```
