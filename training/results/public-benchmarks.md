# Benchmarks públicos (reprodutíveis) — modelo M5 entregue

Medido com `training/batch_transcribe.py` + `training/eval_public_hf.py` (ONNX int8, CPU, greedy).
Todo número `[MEDIDO]`.

## FLEURS pt_br (test) — fala LIDA/limpa, banda-larga

`python3 training/eval_public_hf.py 100`

| Métrica | Valor |
|---|---|
| WER | **16,14%** |
| acertos / subs / del / ins | 87,9% / 10,9% / 1,3% / 4,0% |
| amostras / palavras-ref | 100 / 2552 |
| RTFx agregado (batch, CPU) | 24,6× |

**Leitura:** em áudio de **boa qualidade banda-larga** (perfil de 128 kbps), o modelo entrega
~16% WER — melhor que os 23% de fala espontânea (CORAA) e muito abaixo do telefônico 8 kHz
(~32–40%). Confirma que o gargalo do telefônico é **canal/dado**, não o modelo.
