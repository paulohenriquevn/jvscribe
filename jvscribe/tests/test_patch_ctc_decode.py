"""O adaptador librispeech → commonvoice do decoder CTC.

Tinha **0% de cobertura** e o motivo não era desleixo: o módulo executava em nível de módulo.
Importá-lo abria `/workspace/icefall/...`, escrevia o arquivo de saída e podia chamar
`sys.exit` — não havia como importar para testar. Também não tinha `if __name__ ==
"__main__"`, então escapou até do inventário de entrypoints.

O que a lógica protege: um `ctc_decode.py` que ainda cite `librispeech` decodifica contra o
test set ERRADO e devolve um WER plausível sobre outro corpus, sem erro nenhum. É a mesma
classe do vocabulário trocado — saída crível e falsa.
"""
from __future__ import annotations

import pytest

from finetune.patch_ctc_decode import SUBSTITUICOES, adaptar

ORIGEM = (
    "from asr_datamodule import LibriSpeechAsrDataModule\n"
    "def main():\n"
    "    LibriSpeechAsrDataModule.add_arguments(parser)\n"
    "    librispeech = LibriSpeechAsrDataModule(args)\n"
    "\n"
    "    test_clean_cuts = librispeech.test_clean_cuts()\n"
    "    test_other_cuts = librispeech.test_other_cuts()\n"
    "\n"
    "    test_clean_dl = librispeech.test_dataloaders(test_clean_cuts)\n"
    "    test_other_dl = librispeech.test_dataloaders(test_other_cuts)\n"
    "\n"
    '    test_sets = ["test-clean", "test-other"]\n'
    "    test_dl = [test_clean_dl, test_other_dl]\n"
)


def test_importar_o_modulo_nao_executa_nada():
    """A garantia que faltava: import é import.

    Enquanto o patch rodava no import, qualquer coisa que tocasse o módulo — um teste, uma
    ferramenta de análise, um `python -c` — tentava escrever no icefall.
    """
    import finetune.patch_ctc_decode as m

    assert callable(m.adaptar) and callable(m.main)


def test_troca_datamodule_e_test_sets():
    out = adaptar(ORIGEM)
    assert "CommonVoiceAsrDataModule" in out
    assert 'test_sets = ["test"]' in out


def test_nenhum_residuo_de_librispeech_sobrevive():
    """A checagem que separa "substituí três trechos" de "está adaptado"."""
    out = adaptar(ORIGEM)
    assert "librispeech" not in out and "LibriSpeech" not in out


def test_upstream_mudado_levanta_com_a_ancora_no_texto():
    with pytest.raises(ValueError, match="padrão não encontrado"):
        adaptar("arquivo completamente diferente\n")


def test_residuo_inesperado_e_recusado(monkeypatch):
    """Uma quarta referência ao librispeech num upstream futuro passaria pelas substituições.

    Sem esta guarda ela só apareceria como WER estranho depois do treino — caro e tardio.
    """
    origem = ORIGEM + "    print('librispeech extra')\n"
    with pytest.raises(ValueError, match="ainda há referência"):
        adaptar(origem)


def test_as_substituicoes_sao_todas_efetivas():
    """Nenhuma entrada decorativa: cada par muda o texto."""
    for old, new in SUBSTITUICOES:
        assert old != new and old in ORIGEM
