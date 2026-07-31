# Cobertura — o que está testado, o que não está, e por quê

`[MEDIDO]` 2026-07-31. **484 testes**, `ruff F,E9,B` limpo, **38/38 entrypoints** respondem a
`--help` sem traceback.

> **Cobertura de linha não é a meta.** `.claude/rules/testing.md` § 1: *"testes protegem
> comportamento, não linhas; 100% com assertions vazios é pior que 60% com testes
> significativos"*. Este documento existe para dizer **o que cada número esconde** — onde a
> linha não coberta é um risco real e onde ela é I/O que só a execução exercita.

## Por domínio

| domínio | início | final | Δ |
|---|---|---|---|
| `raiz` | 100,0% | **100,0%** | — |
| `common` (kernel) | 94,4% | **93,5%** | −0,9 |
| `common/audio` | 91,8% | **91,8%** | — |
| `batch` | 70,0% | **70,0%** | — |
| `realtime` | 63,4% | **69,8%** | +6,4 |
| `corpus` | 68,6% | **68,6%** | — |
| `finetune` | 58,7% | **63,8%** | +5,1 |
| `eval` | 56,0% | **57,2%** | +1,2 |
| `probes` | 43,4% | **43,4%** | — |
| `bench` | 28,8% | **35,3%** | +6,5 |
| `audit` | 26,9% | **40,4%** | +13,5 |
| **TOTAL** | 60,6% | **63,7%** | **+3,1** |

O `common` caiu 0,9 p.p. porque ganhou `report.py` e o bloco de carga em `cpu.py` — código novo
com teste de comportamento, não de linha. É a troca certa.

## O que os +3,1 p.p. compraram (não é o número, são os defeitos)

| domínio | o que passou a ser guardado |
|---|---|
| `audit` **+13,5** | Os detectores de **vazamento treino/teste** tinham **zero** teste. Um falso negativo ali não faz nada falhar — deixa o WER publicado subir e ninguém descobre |
| `bench` **+6,5** | `_Janela.rtfx()/p99_ms()` — os dois números sobre os quais o veredito de RNF-04 repousa — e a ordem **round-robin**, que é o que impede a flutuação de carga de eleger um vencedor falso |
| `realtime` **+6,4** | A tabela de vereditos deixou de contradizer o caveat abaixo dela |
| `finetune` **+5,1** | Idempotência dos patchers, preservação do backup do upstream, e a revisão do icefall que os patches assumem |

## Por script


**`audio/`**

| script | cobertura | testes que o citam | entrypoint |
|---|---|---|---|
| `channel.py` | 100% | 6 | — |
| `codecs.py` | 82% | 4 | — |
| `lhotse_transform.py` | 98% | 2 | — |

**`audit/`**

| script | cobertura | testes que o citam | entrypoint |
|---|---|---|---|
| `coraa_speaker_overlap.py` | 42% | 1 | ✅ |
| `tagarela_coraa_leak_check.py` | 60% | 1 | ✅ |
| `tagarela_noise_audit.py` | 23% | 1 | ✅ |

**`batch/`**

| script | cobertura | testes que o citam | entrypoint |
|---|---|---|---|
| `batch_transcribe.py` | 96% | 6 | ✅ |
| `decode_onnx_local.py` | 44% | 5 | ✅ |
| `eval_public_hf.py` | 52% | 4 | ✅ |

**`bench/`**

| script | cobertura | testes que o citam | entrypoint |
|---|---|---|---|
| `bench_rtfx.py` | 32% | 3 | ✅ |
| `calibrate.py` | 33% | 4 | ✅ |
| `finetune_smoke.py` | 22% | 1 | ✅ |
| `runtime_bench.py` | 54% | 3 | ✅ |
| `stress_test.py` | 39% | 4 | ✅ |

**`common/`**

| script | cobertura | testes que o citam | entrypoint |
|---|---|---|---|
| `artifact.py` | 92% | 5 | ✅ |
| `cpu.py` | 90% | 7 | — |
| `ctc.py` | 100% | 9 | — |
| `engine.py` | 78% | 4 | — |
| `metrics.py` | 93% | 3 | — |
| `onnx_session.py` | 100% | 1 | — |
| `report.py` | 100% | 7 | — |
| `stats.py` | 98% | 3 | — |
| `streaming.py` | 98% | 5 | — |
| `text.py` | 100% | 43 | — |

**`corpus/`**

| script | cobertura | testes que o citam | entrypoint |
|---|---|---|---|
| `agreement_filter.py` | 100% | 1 | — |
| `build_manifest.py` | 83% | 1 | — |
| `pseudo_label.py` | 96% | 2 | — |
| `run_pipeline.py` | 54% | 4 | ✅ |

**`eval/`**

| script | cobertura | testes que o citam | entrypoint |
|---|---|---|---|
| `analyze_error_composition.py` | 67% | 3 | ✅ |
| `baseline_fleurs_ptbr.py` | 34% | 3 | ✅ |
| `baseline_minds14.py` | 34% | 1 | ✅ |
| `bootstrap_wer_ci.py` | 62% | 1 | ✅ |
| `cer_from_recogs.py` | 57% | 1 | ✅ |
| `compare_models.py` | 69% | 3 | ✅ |
| `eval_runtime_wer.py` | 32% | 3 | ✅ |
| `eval_wer.py` | 91% | 1 | — |
| `extract_fleurs_one_wav.py` | 88% | — | ✅ |
| `make_callcenter_cuts.py` | 36% | — | ✅ |
| `make_telephone_test.py` | 54% | 2 | ✅ |
| `measure_callcenter.py` | 59% | 5 | ✅ |
| `measure_realcodec.py` | 41% | 2 | ✅ |
| `run_baseline.py` | 92% | 1 | — |

**`finetune/`**

| script | cobertura | testes que o citam | entrypoint |
|---|---|---|---|
| `download_tagarela_subset.py` | 74% | 1 | ✅ |
| `gen_phonemes.py` | 58% | 1 | ✅ |
| `patch_ctc_decode.py` | 69% | 1 | ✅ |
| `prep_augment_datamodule.py` | 92% | 1 | ✅ |
| `prep_coraa.py` | 40% | 2 | ✅ |
| `prep_finetune.py` | 92% | 2 | ✅ |
| `prep_icefall.py` | 42% | 5 | ✅ |
| `prep_phoneme_head.py` | 52% | 5 | ✅ |
| `prep_tagarela.py` | 83% | 3 | ✅ |

**`jvscribe/`**

| script | cobertura | testes que o citam | entrypoint |
|---|---|---|---|
| `conftest.py` | 100% | 2 | — |

**`probes/`**

| script | cobertura | testes que o citam | entrypoint |
|---|---|---|---|
| `blank_penalty_probe.py` | 48% | 5 | ✅ |
| `tta_feature_align_probe.py` | 40% | 6 | ✅ |

**`realtime/`**

| script | cobertura | testes que o citam | entrypoint |
|---|---|---|---|
| `dual_capture.py` | 92% | 2 | — |
| `live_transcribe.py` | 70% | 7 | ✅ |
| `mic_transcribe.py` | 36% | 5 | ✅ |

## O que NÃO está coberto — e o motivo, sem eufemismo

| lacuna | por que a linha não é exercitada | risco residual |
|---|---|---|
| `main()` de `bench/*` e `eval/*` | precisam de sessão ONNX, áudio real e máquina ociosa | baixo — cobertos pelo live test, que **registra a carga** |
| `finetune/finetune_smoke.py` (22%) | `construir_modelo()` exige `torch` + `k2` | médio — só roda na instância de GPU |
| `probes/*` `main()` | pesquisa que pode dar nulo por desenho; o núcleo (`greedy_penalized`, `greedy`) **tem** teste | baixo |
| `download_shard` de rede | o dublê cobre cache, URL e token; o `curl` real, não | baixo |
| WER em 8 kHz e fala espontânea | o áudio de call center é local por LGPD | **alto** — é o `[DESCONHECIDO]` que mais importa |
| RNF-01/04/05 conclusivos | esta máquina hospeda o desktop do dono e nunca fica ociosa | **alto** — exige bancada dedicada |

## Duas coisas que este documento não prova

1. **Que o treino funciona.** Os patchers aplicam `PATCH_OK` e o resultado **compila** contra
   `f84270c`; que a cabeça de fonema aprenda algo é outra medição, e ela precisa de GPU.
2. **Que os números de desempenho valem.** Toda corrida desta sessão foi feita com a máquina em
   load 1,1–6,3. O que está provado é que os scripts **rodam e produzem saída correta**.
