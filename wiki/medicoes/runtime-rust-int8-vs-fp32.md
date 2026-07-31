---
type: Medição
title: int8 é lossless contra fp32
description: Medido no runtime Rust: int8 (27 MB) contra fp32 (92 MB) — a diferença fica dentro do ruído.
tags: [medicao, int8, quantizacao, rust]
timestamp: 2026-07-31T00:00:00Z
---

# Eval do Runtime Rust — WER + RTFx através do caminho de produção

**Data:** 2026-07-26 · **Máquina:** i7-1355U de referência · **Modelo:** `model.int8.onnx` (Zipformer-CTC small 22M, int8) · **Harness:** `training/scripts/eval_runtime_wer.py`

Responde "dá pra testar o runtime? qual a qualidade?". Antes desta sessão só havia
harness de **velocidade** (`macaw-audio/src/harness.rs`) + prova funcional em **1**
utterance. Faltava eval de **acurácia (WER)** através do runtime Rust sobre um test set.

## Acurácia — WER do runtime Rust `[MEDIDO]`

Extrai N utterances do FLEURS pt_br test (cache HF), roda cada uma pelo runtime de
produção (`macaw-cli transcribe` = wav → `jvscribe_audio::kaldi_fbank` → `AsrEngine::transcribe`
→ `ctc_greedy`) e computa WER real (Levenshtein de palavras) vs a referência normalizada
com a **mesma `normalize_ptbr` do treino**.

> ⚠️ **RESSALVA DE RÉGUA (registrada em 2026-07-31, revisão de código).** Os WERs desta
> tabela foram medidos com a régua de **TREINO** (`normalize_train_target`), que **preserva
> acento** — cada acento errado conta como palavra inteira errada. A régua canônica de
> comparação do projeto (`normalize_for_wer_compare`) **remove** acento. `[MEDIDO]`: numa
> frase em que só o acento difere, a de treino dá **62,5%** onde a canônica dá **0%**.
>
> **Consequência:** estes números **não são comparáveis** com os 15,99% do FLEURS nem com
> qualquer outro número medido pela canônica. A comparação INTERNA da tabela (runtime 29,92%
> vs decode Python 29,97%) permanece válida — os dois lados usaram a mesma régua, e a
> conclusão "o runtime não degrada" não depende de qual régua foi usada.
>
> **Não é re-medível:** o runtime Rust foi removido do repositório em 2026-07-30 (commit
> 266253f). Reproduzir exige checkout do commit anterior. `jvscribe/tools/eval_runtime_wer.py`
> já foi corrigido para a canônica, então uma re-medição futura daria número diferente **e
> correto**.

| Caminho | WER | CER | n |
|---|---|---|---|
| **Runtime Rust** (macaw-cli) — amostra grande | **29,92%** | — | 470 utterances |
| **Runtime Rust** — com CER | **28,21%** | **10,99%** | 100 utterances |
| Decode Python (icefall) | 29,97% | (não medido) | test completo (21.471 palavras) |

**CER ≪ WER (10,99% vs 28,21%) `[MEDIDO]`:** o modelo acerta ~89% dos caracteres; a
maioria dos erros de palavra são deslizes de 1-2 caracteres foneticamente próximos
("dirigir→dirigira", "lugares→logares") que o WER pune como palavra inteira errada.
Sinal de arquitetura saudável — o gap para SOTA é de refinamento (augmentação + dados
de M5), não de erro grosseiro.

**Conclusão:** o runtime Rust **não degrada** a acurácia vs o decode de treino — em
n=470 o WER converge para **29,92%, praticamente idêntico aos 29,97%** do decode Python
(o n=40 = 25,75% era só ruído de subconjunto; com n grande o número casa). Prova que a
cadeia Rust (kaldi_fbank 80-bin + transcribe + ctc_greedy) é **funcionalmente equivalente
ao decode Python do icefall**. Transcrições sensatas (ex: "consequentemente duas espécies
de peixe entraram em extinção" — perfeita; "os anúncios regulares no metrô..." — 17,8 s
correta).

**Caveats (Regra 3):** o run de n=470 parou em u476 por um timeout transitório (contenção
de CPU durante o treino do large; u476 sozinho roda em 0,48 s) — o eval agora trata timeout
sem derrubar; 470/919 já dá IC apertado. É WER **wideband limpo** (não telefônico 8 kHz —
ver penalidade 1,29× em `m4-decision-161h-results.md`); é o modelo **small atual**, não o
WER final de M5.

## Velocidade — RTFx do runtime `[MEDIDO]`

| Áudio | decode (fbank+infer) | RTFx |
|---|---|---|
| 6,84 s | 123 ms | **55,4×** |
| 17,76 s | 368 ms | **48,2×** |

Muito acima do piso RNF-07 (6×). (RTFx exclui o load do modelo, custo único; mede o
custo por-utterance que importa em streaming.)

## Achado de deployment #1 — `ORT_DYLIB_PATH` é obrigatório no binário standalone `[MEDIDO]`

O `ort` (crate) usa `load-dynamic`: carrega a `libonnxruntime.so` em runtime. O
`.cargo/config.toml` seta `ORT_DYLIB_PATH` → a **ONNX Runtime 1.23.0 otimizada vendorizada**
(`vendor/onnxruntime-linux-x64-1.23.0/`), então **sob `cargo`** (test/run) tudo é rápido.
Mas o **binário standalone** (rodado direto, sem cargo) **não herda esse env** → o
`load-dynamic` cai numa `libonnxruntime` lenta do sistema (do node), causando lentidão
**patológica** (clip de 6,84 s: 0,12 s com a lib certa → **>30 s** com a errada; 40×+).

- **Diagnóstico:** não era o modelo (Python faz o mesmo modelo a 41-90× RTFx), não era
  O(T²), não era utterance longa — era **a biblioteca ONNX Runtime errada**.
- **Fix operacional (hoje):** exportar `ORT_DYLIB_PATH=.../vendor/.../libonnxruntime.so`
  ao rodar o binário fora do cargo (o eval faz isso).
- **Fix de produto (FEITO, task #26, commit 283282e):** `crates/macaw-cli/src/ort_setup.rs`
  — `ensure_ort_dylib()` no startup resolve a lib vendorizada subindo a árvore (relativo ao
  executável e ao manifest) e a seta, ou **falha alto** com mensagem acionável (nunca degrada
  em silêncio). Prova: `env -u ORT_DYLIB_PATH macaw-cli transcribe` acha a lib e roda RTFx 28,8×.

## Achado de deployment #2 — `GraphOptimizationLevel::Level3` DEGRADA o int8 aqui `[MEDIDO]`

Hipótese testada e **refutada por medição**: subir o nível de otimização de grafo para
`Level3` (esperando fusão QDQ do int8) **piorou** — clip de 6,84 s: 0,55 s (Disable) →
>30 s (Level3), com esta `libonnxruntime` via `load-dynamic`. O `AsrEngine::load` fica
com `Disable` (documentado em `crates/macaw-asr/src/lib.rs`). A velocidade boa vem da
**lib certa** (achado #1), não do nível de otimização.

## Como reproduzir

```bash
cargo build -p macaw-cli --release
export ORT_DYLIB_PATH=$PWD/vendor/onnxruntime-linux-x64-1.23.0/lib/libonnxruntime.so
python3 training/scripts/eval_runtime_wer.py --n 40   # WER do runtime
```

## EXP-01 — int8 vs fp32 (lição T-Mimi) `[MEDIDO]`

Small finalista, MESMA engine Rust (`macaw-cli transcribe`, override `MACAW_MODEL`), n=100:

| Modelo | tamanho | WER | CER |
|---|---|---|---|
| int8 (`model.int8.onnx`) | 27 MB | 28,21% | 10,99% |
| fp32 (`model.onnx`) | 92 MB | 28,45% | 10,93% |

**int8 NÃO degrada acurácia** — Δ 0,24pp WER / 0,06pp CER, dentro do ruído (n=100). A
quantização int8 é essencialmente **lossless** aqui. **Deploy do int8 (3,4× menor) tem
custo zero de acurácia.** Refuta a hipótese de quantização mista/QAT (T-Mimi) para o
nosso caso: não há acurácia a recuperar. Reprodução: `MACAW_MODEL=model.fp32.onnx
python3 training/scripts/eval_runtime_wer.py --n 100` (com ORT_DYLIB_PATH setado).
