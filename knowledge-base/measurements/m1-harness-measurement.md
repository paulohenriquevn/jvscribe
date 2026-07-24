# M1 — Medição do Harness (evidência [MEDIDO])

**Data:** 2026-07-24
**Comando:** `./scripts/bench.sh 10` (P-cores fixados via `taskset -c 0-1`, release build)
**Hardware:** máquina de referência do dev (i7 híbrido); **NÃO** é o piso da frota BYOD (Q-01 — `[DESCONHECIDO]`)
**Subject:** encoder emprestado de 600M (`models/m0-borrowed/encoder-model.onnx`), 10 iterações (2 de warmup), 2,98 s de áudio por iteração
**Rótulo:** `[MEDIDO — encanamento apenas]` — números do modelo **emprestado**, não do produto. Provam que a **régua** funciona, não que o modelo é bom (o modelo próprio vem em M5/M6).

## Resultado

**Escopo desta medição (review EVID-02/03):** prova o **encanamento da régua** numa
**janela curta** (~30 s de áudio, 10 iterações) e **sem carga concorrente**. NÃO é a
medição RNF-04 (soak ≥ 10 min) nem RNF-05 (sob carga) — esses seguem `[DESCONHECIDO]`
até rodarem de verdade (ver abaixo).

| Métrica | Valor medido | Alvo (PRD § 6) | Observação |
|---|---|---|---|
| RTFx janela curta (áudio/parede), **sem carga** | **17,81×** | RNF-07 ≥ 6× (ASR isolado) | Warm; NÃO é o RTFx sob carga concorrente (RNF-05 não exercido); ver warmup abaixo |
| Latência p50/p95/p99 | **154,9 / 237,8 / 237,8 ms** | RNF-02 p99 ≤ 500 ms | 8 amostras (p95=p99 por nearest-rank) — amostra pequena |
| RNF-04 (razão térmica no soak ≥ 10 min) | **`[DESCONHECIDO]`** | ≥ 0,80 | Soak de 10 min **não executado** neste ambiente; a razão 1,34 abaixo é só proxy de ~30 s, não a métrica |
| — proxy curto (2ª½ ÷ 1ª½) | 1,34 | (referência) | > 1: 2ª metade mais quente que a 1ª; NÃO mede throttling — só o soak real mede |
| RNF-05 (RTFx sob carga concorrente) | **`[DESCONHECIDO]`** | obrigatório | Requer `bench.sh N --load` rodado em soak; não executado aqui |
| Backlog | n/a offline | RNF-03 = 0 em 99,9% | Medido no modo `live` com captura real, não no bench offline |

## O warmup importa (valida o ADR D2 do plano)

- **1ª iteração fria** (`macaw-cli fixture`, sem warmup): 1981 ms → RTFx ≈ **1,5×**.
- **Quente, janela curta** (bench, 2 warmup descartados): ~155 ms/iter → RTFx **17,81×** (não confundir com o RTFx sustentado do soak de 10 min, que não rodou).

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
