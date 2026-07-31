"""Treino — patches determinísticos do icefall e preparo do que vai para a GPU.

O que une estes arquivos: cada um transforma o repositório do icefall ou o corpus bruto no
estado exato que um run de treino exige, de forma **reproduzível**. Nada aqui roda em
produção; tudo aqui roda uma vez, na instância de GPU, antes do treino.

| grupo | arquivos |
|---|---|
| patch do icefall | `patch_ctc_decode`, `prep_finetune`, `prep_augment_datamodule`, `prep_phoneme_head` |
| preparo de corpus p/ GPU | `prep_coraa`, `prep_tagarela`, `prep_icefall`, `download_tagarela_subset`, `gen_phonemes` |

⚠️ `prep_icefall.py` é o **único** módulo do repositório que legitimamente usa
`text.normalize_train_target` (preserva acento). Todo o resto mede WER e usa a régua de
comparação — estender a de treino a um medidor já aconteceu e inflou um número publicado.
"""
