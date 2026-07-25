# M4 — Piloto comparativo: resumo de implementação (PARCIAL — honesto)

**Plano:** `knowledge-base/discoveries/plans/m4-pilot-plan.md` · **Blueprint:** `m4-pilot-blueprint.md` (SHIPPABLE 100)
**Data:** 2026-07-25 · **Status:** pipeline de treino PROVADO na GPU; piloto completo (500 h) PENDENTE de crédito/tempo

## O que foi ENTREGUE (com evidência real)

| Entregável | Evidência |
|---|---|
| **Discover SHIPPABLE 100** — recipe icefall lida, G2P medido, custo com fórmula | `m4-pilot-blueprint.md` (3 agentes, 8 questões) |
| **G2P PT-BR (Q-08)** — cobertura/determinismo 100% `[MEDIDO]`, GPLv3 (só treino) | Blueprint § Corner 4/Q3 |
| **Estimativa de custo** — fórmula: piloto ~$98-200, M5 ~$1.350-2.000/run `[ESTIMATIVA]` | Blueprint § Corner 3/Q7 |
| **Pipeline de treino executável** — `training/{prep_fleurs,gen_phonemes,train_ctc,decode_ctc}.py` | rodou end-to-end na GPU (abaixo) |
| **Cabeça de fonema construída** (decisão do dono) — não existe na recipe (Q2) | `train_ctc.py` (2ª cabeça + alvos G2P) |

## Evidência `[MEDIDO]` do treino real (vast.ai RTX 3090, ~$0,35)

O pipeline Zipformer-CTC treinou do zero em FLEURS pt_br numa GPU real (imagem oficial
`k2fsa/icefall` — o gargalo k2/CUDA do discover resolvido por reuso). WER medido:

| Modelo | WER validation | WER **test held-out** |
|---|---|---|
| Baseline | 41,17% | 95,21% |
| + fonema | 17,89% | 99,27% |

**Achado honesto (a lição):** o ganho no validation era **overfitting** (corpus de 1 h,
modelo 6,1M, 30 épocas → memorização). No held-out ambos são inúteis e o fonema é pior.
A ablação da supervisão fonética é **inconclusiva no smoke** — só testável no piloto de
500 h. Detalhe: `training/results/m4-smoke-results.md`.

## O que FALTA para M4 = MILESTONE_COMPLETED (o piloto real)

O DoD de M4 **não está 100%** — reportá-lo completo seria falso (`asr-evidence-discipline`):

- [ ] 2 finalistas treinados em **~500 h** (feito: 1 finalista em 1 h de smoke) → precisa de crédito ($98-200) + dias
- [ ] Ablação da supervisão fonética **no held-out com corpus grande** (o critério ≥ 3% só é medível aí)
- [ ] Curva **WER × RTFx** nos 3 tamanhos (feito: 1 tamanho, WER; falta RTFx + 2 tamanhos)
- [ ] **FastConformer** (2º finalista) — não treinado
- [x] G2P Q-08, estimativa de GPU-horas — feitos no discover

## Validação do `prep_icefall.py` (o único código nosso do piloto)

- **Parte pura testada** `[MEDIDO]`: `training/tests/test_prep_icefall.py` (7/7 verde) — `normalize_ptbr`
  preserva diacríticos PT-BR, colapsa espaço, trata `None`; estrutura de `SOURCES` (fleurs/mls com
  `repo/path/splits/text_col`, splits `train/dev/test`).
- **Lógica de I/O exercitada localmente**: numa execução local o script rodou download → parse do
  parquet FLEURS → `Recording` → `Fbank.compute` com sucesso; parou só na **escrita** da feature
  pelo `open_best` do lhotse, que carrega `smart_open`→`pyOpenSSL` — e o ambiente **local** tem
  `pyOpenSSL` incompatível com `cryptography 49.0.0` (`_lib.GEN_EMAIL`). É quirk de ambiente
  (ver memória `baseline-python-env-quirks`), **não** defeito do script.
- **I/O idêntico já provado na imagem limpa**: `prep_fleurs.py` — mesma cadeia
  `Recording→Fbank→to_file` — gerou cuts válidos e treináveis na instância vast.ai (`k2fsa/icefall`,
  onde `pyOpenSSL` não está quebrado). O end-to-end do `prep_icefall.py` roda ali, na hora do piloto.

## Reuso (Regra 9) — o que a comunidade faz, aplicado

- **Imagem Docker oficial `k2fsa/icefall`** na vast.ai — mata o setup k2/CUDA (o maior risco).
- **Módulos do icefall** (`zipformer.py`, `scaling.py`, `subsampling.py`, `optim.py`) importados, não reescritos.
- O mínimo próprio: as cabeças CTC + o loop + a cabeça de fonema (que a recipe não tem).
