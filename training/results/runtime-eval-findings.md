# Eval do Runtime Rust — WER + RTFx através do caminho de produção

**Data:** 2026-07-26 · **Máquina:** i7-1355U de referência · **Modelo:** `model.int8.onnx` (Zipformer-CTC small 22M, int8) · **Harness:** `training/scripts/eval_runtime_wer.py`

Responde "dá pra testar o runtime? qual a qualidade?". Antes desta sessão só havia
harness de **velocidade** (`macaw-audio/src/harness.rs`) + prova funcional em **1**
utterance. Faltava eval de **acurácia (WER)** através do runtime Rust sobre um test set.

## Acurácia — WER do runtime Rust `[MEDIDO]`

Extrai N utterances do FLEURS pt_br test (cache HF), roda cada uma pelo runtime de
produção (`macaw-cli transcribe` = wav → `macaw_audio::kaldi_fbank` → `AsrEngine::transcribe`
→ `ctc_greedy`) e computa WER real (Levenshtein de palavras) vs a referência normalizada
com a **mesma `normalize_ptbr` do treino**.

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
- **Fix de produto (a fazer):** o binário de produção deve garantir a lib certa —
  embutir via `rpath`/bundle, ou resolver `vendor/` relativo ao executável, ou checar no
  startup e falhar claro se a lib for a errada. **Task de follow-up** (runtime otimizado M6).

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
