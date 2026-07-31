# M4 — ablação da cabeça de fonema

Artefatos do run que mediu o ganho da supervisão fonética auxiliar: **WER 29,97% → 28,58%**
(−4,63% relativo, IC95% bootstrap pareado [2,63%; 6,63%], n=919). Análise em
[`../m4-phoneme-ablation-results.md`](../m4-phoneme-ablation-results.md).

| arquivo | o que é |
|---|---|
| `recogs-test-*.txt` | **A evidência.** Hipótese e referência por utterance — permitem **recomputar** WER e CER do zero |
| `decode_phoneme_avg{1,10}.log` | log dos dois decodes |
| `log-decode-*` | log bruto do icefall em cada decode |
| `gen_phonemes.log` | geração dos alvos G2P |
| `train_phoneme_small.metrics.log` | linhas de métrica do treino (loss, época, WER/CER) |

## O log de treino completo foi removido

`train_phoneme_small.log` tinha **55 MB e 480.955 linhas** — acima do limite recomendado de
50 MB do GitHub, e **49,2% eram `FutureWarning` repetidos** do torch. Só **1.410 linhas**
(0,29%) carregavam métrica.

O sinal foi extraído para `train_phoneme_small.metrics.log` (356 KB) e o restante descartado.
Nenhuma conclusão deste projeto dependia das outras 479.545 linhas: o que sustenta o número é
o par `recogs-*`, do qual WER e CER são recomputáveis — foi assim que o WER de outro run foi
regenerado antes de remover os `errs-*` correspondentes.

⚠️ **A remoção não apaga o arquivo do histórico do git.** Todo clone continua baixando os
55 MB do commit que o introduziu. Apagar de verdade exige reescrever o histórico
(`git filter-repo`) e force-push, que as regras do projeto proíbem em `develop`.
