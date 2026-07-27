# `training/smoke/` — artefatos congelados do smoke de M4 (NÃO usar em produção)

Estes scripts serviram **apenas** para provar a infra de treino na GPU antes do piloto
real. Foram movidos para cá (audit `/loop-system-design`, 2026-07-25, findings B1/D3)
para **remover o risco de copy-paste** ao lado do único código de produção
(`../prep_icefall.py`). A lição de cada um já está registrada em `../results/` e no
`CHANGELOG.md` — não os mantenha, não os estenda, não os copie.

| Arquivo | O que foi | Por que está congelado |
|---|---|---|
| `train_ctc.py` | wrapper self-contained do smoke | **bugs confirmados** (sem `src_key_padding_mask`, cabeça de fonema ad-hoc, configs por escala). O piloto usa a recipe REAL do icefall (`train.py`), não isto |
| `decode_ctc.py` | decode greedy do smoke | importa `train_ctc` internamente; só faz sentido dentro do smoke |
| `prep_fleurs.py` | prep anterior (formato `fleurs_*_cuts`) | **superado** por `../prep_icefall.py` (formato `cv-*_cuts` do datamodule real); tem bug latente D5 (sobrescreve `transcript_words.txt` por split) |
| `gen_phonemes.py` | alvos G2P do smoke | a supervisão fonética real será extensão do `model.py` do icefall em M5, não este util |

**O piloto real e o de M5 usam a recipe do icefall + `../prep_icefall.py`.** Ver
`../run_pilot_icefall.md` e `../results/m4-pilot-fleurs-results.md`.
