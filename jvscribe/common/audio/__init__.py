"""Domínio de áudio — a taxa que o modelo consome e o canal telefônico.

Vivia em `corpus/` por acidente histórico: nasceu na augmentação de M3. Mas os consumidores
são três pipelines — `corpus` (augmentação de treino), `eval` (test set 8 kHz proxy) e
`tools` (probes de domínio) — e por isso três deles furavam a fronteira
"cross-pipeline apenas a partir de `common/`" para alcançá-lo. Movido em 2026-07-31; as
violações somem por construção, não por exceção na guarda.

| módulo | o quê |
|---|---|
| `channel` | a cadeia em memória: banda 300-3400 + G.711 A-law |
| `codecs` | pool realista (GSM/Opus/G.711) para augmentação sorteada |
| `lhotse_transform` | adapter `CutSet → CutSet` para o datamodule do icefall |
| `augment.sh` | a MESMA cadeia em `sox`, para quem não quer numpy |

⚠️ `channel.py` e `augment.sh` implementam a mesma degradação por caminhos diferentes.
`[MEDIDO]` correlação **0,9978** depois de alinhar 51 amostras de atraso de grupo — a
duplicação é deliberada e verificada por `tests/test_scripts_invocados.py`."""
from __future__ import annotations

# A taxa de amostragem que o modelo consome, fixada pelo fbank do treino. Estava declarada
# **7 vezes** no repositório (`SR = 16000` em batch, realtime, eval, bench…) — a mesma classe
# de duplicação de conhecimento que já produziu duas réguas de texto e sete colapsos CTC.
# Trocar a taxa exige retreinar, então a divergência seria silenciosa e cara.
SR = 16000
