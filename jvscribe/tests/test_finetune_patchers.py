"""Os patchers do icefall — o que a execução real expôs em 2026-07-31.

Clonar o icefall e rodar os três patchers mostrou que **a receita está intacta e mesmo assim
não roda**: contra o `HEAD` do upstream, `model.py` falha. A âncora

    '        return ctc_loss\\n\\n    def forward_transducer(\\n'

parou de casar em `693d84a` (2024-10-21, "Add Consistency-Regularized CTC" #1766), que inseriu
um `forward_ctc` com `return ctc_loss, cr_loss` entre os dois trechos. Em `f84270c` — o pai
desse commit — os três aplicam `PATCH_OK` e o resultado compila `[MEDIDO]`.

Nada disso estava registrado no repositório. Sem o pino, a falha aparece na hora de preparar o
treino: numa GPU alugada, com a instância já faturando.

Uma armadilha da investigação, registrada porque custa tempo: `egs/commonvoice/ASR/zipformer/
model.py` é **symlink** para o de `librispeech`. Bissectar no caminho do commonvoice mostra um
commit só e sugere que o arquivo nunca mudou.
"""
from __future__ import annotations

import re

import pytest

from finetune.prep_phoneme_head import (
    ICEFALL_REV_QUEBROU,
    ICEFALL_REV_TESTADO,
    apply_patch,
)


def test_a_revisao_alvo_do_icefall_esta_registrada():
    """Um pino que não é um SHA não pinta nada."""
    for rev in (ICEFALL_REV_TESTADO, ICEFALL_REV_QUEBROU):
        assert re.fullmatch(r"[0-9a-f]{7,40}", rev), f"não parece um commit: {rev!r}"
    assert ICEFALL_REV_TESTADO != ICEFALL_REV_QUEBROU


def test_ancora_que_nao_bate_diz_qual_revisao_usar(tmp_path):
    """A mensagem tem de conter a saída, não só o diagnóstico.

    Antes dizia apenas "padrão não bate 1x" e mostrava o padrão — verdadeiro e inútil: de um
    trecho de código-fonte ninguém deduz "o upstream mudou, faça checkout de f84270c".
    """
    alvo = tmp_path / "model.py"
    alvo.write_text("def outra_coisa():\n    pass\n", encoding="utf-8")

    with pytest.raises(SystemExit) as e:
        apply_patch(alvo, [("padrão ausente", "substituto")], "MARCADOR")

    msg = str(e.value)
    assert ICEFALL_REV_TESTADO in msg, "a mensagem não diz qual revisão funciona"
    assert "worktree" in msg, "a mensagem não diz o comando para sair do problema"


def test_patch_e_idempotente_e_nao_duplica(tmp_path):
    """Re-rodar depois de uma falha parcial não pode aplicar duas vezes.

    Importa porque o modo de falha real é justamente parcial: `zipformer.py` é patchado, e só
    então `model.py` explode. A pessoa corrige e roda de novo — sobre uma árvore já meio
    patchada. `[MEDIDO]`: `aux_ctc_layer_idx` seguiu com 4 ocorrências após a segunda corrida.
    """
    alvo = tmp_path / "zipformer.py"
    alvo.write_text("x = 1\n", encoding="utf-8")

    apply_patch(alvo, [("x = 1", "x = 1\n# MARCADOR\ny = 2")], "MARCADOR")
    depois_da_primeira = alvo.read_text(encoding="utf-8")

    apply_patch(alvo, [("x = 1", "x = 1\n# MARCADOR\ny = 2")], "MARCADOR")
    assert alvo.read_text(encoding="utf-8") == depois_da_primeira
    assert depois_da_primeira.count("y = 2") == 1


def test_backup_do_original_e_preservado(tmp_path):
    """O patcher escreve no arquivo do icefall — sem cópia, um patch errado é irreversível."""
    alvo = tmp_path / "train.py"
    alvo.write_text("original = True\n", encoding="utf-8")

    apply_patch(alvo, [("original = True", "# MARCADOR\npatchado = True")], "MARCADOR")

    backup = alvo.with_suffix(alvo.suffix + ".orig-phoneme-patch")
    assert backup.exists(), "nenhum backup — o original do icefall se perdeu"
    assert backup.read_text(encoding="utf-8") == "original = True\n"


def test_backup_nao_e_sobrescrito_por_uma_segunda_corrida(tmp_path):
    """Se a segunda corrida regravasse o backup, ele guardaria a versão JÁ patchada.

    O backup existe para voltar ao original do upstream; um backup que guarda o estado
    intermediário é pior que nenhum, porque parece uma saída e não é.
    """
    alvo = tmp_path / "model.py"
    alvo.write_text("v = 0\n", encoding="utf-8")
    apply_patch(alvo, [("v = 0", "# M1\nv = 1")], "M1")
    apply_patch(alvo, [("v = 1", "# M2\nv = 2")], "M2")

    backup = alvo.with_suffix(alvo.suffix + ".orig-phoneme-patch")
    assert backup.read_text(encoding="utf-8") == "v = 0\n", (
        "o backup foi regravado com o estado intermediário"
    )
