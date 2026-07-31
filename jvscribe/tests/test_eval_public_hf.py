"""`eval_public_hf` — o script que produziu o WER publicado do projeto.

Ele não tinha teste nenhum, e carregava quatro defeitos que a suíte inteira não via:

1. apontava para `m5_avg.int8.onnx`, renomeado — **estava quebrado**;
2. tinha régua de normalização **própria**, que preservava acentos enquanto a canônica os
   remove — o WER de 16,14% publicado saiu dela;
3. duplicava a resolução de artefato em vez de ler o `model_card.json`;
4. não tinha guarda `__main__`: importar o módulo baixava o dataset e rodava inferência.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jvscribe" / "batch"))
sys.path.insert(0, str(REPO / "jvscribe" / "common"))

pytest.importorskip("lhotse")


def test_importar_o_modulo_nao_dispara_download_nem_inferencia():
    """Negativo: a versão anterior executava tudo em nível de módulo.

    Este teste passa por CONSEGUIR importar: se o corpo voltasse a rodar no import, ele
    tentaria baixar o FLEURS e travaria a suíte.
    """
    import eval_public_hf

    assert callable(eval_public_hf.main)


def test_usa_a_regua_canonica_e_nao_uma_propria():
    """A régua local preservava acento; a canônica remove. WER medido com réguas diferentes
    não é comparável — e os dois números foram publicados como se fossem."""
    import eval_public_hf
    from text_normalize_ptbr import normalize_for_wer_compare

    assert not hasattr(eval_public_hf, "norm"), (
        "a régua local voltou — use normalize_for_wer_compare"
    )
    R, H = eval_public_hf.medir({"a": "Não é a mesma régua, José!"}, Path("/nao-existe"))
    assert R == [normalize_for_wer_compare("Não é a mesma régua, José!")]
    assert R == ["nao e a mesma regua jose"], "acentos têm de sair, como na régua canônica"


def test_hipotese_ausente_vira_string_vazia_em_vez_de_quebrar():
    """Negativo: um arquivo de saída que não existe é falha de transcrição, não do medidor.

    A versão anterior fazia `.read_text()` direto — um arquivo faltando derrubava a medição
    inteira depois de já ter rodado a inferência.
    """
    import eval_public_hf

    R, H = eval_public_hf.medir({"x": "alguma referência"}, Path("/nao-existe"))
    assert R and H == [""]


def test_referencia_vazia_e_descartada_do_par():
    """Referência vazia não mede nada e distorce o denominador do WER."""
    import eval_public_hf

    R, H = eval_public_hf.medir({"a": "   ", "b": "texto real"}, Path("/nao-existe"))
    assert len(R) == 1


def test_o_modelo_default_vem_do_artefato_canonico():
    """Nome de peso codificado já entregou o modelo errado duas vezes neste projeto."""
    import inspect

    import eval_public_hf

    fonte = inspect.getsource(eval_public_hf)
    assert "m5_avg.int8.onnx" not in fonte, "nome de peso codificado voltou"
    assert "default_model_path" in fonte


def test_n_invalido_falha_com_mensagem(monkeypatch):
    """Negativo: `--n 0` produziria divisão por zero no cálculo dos percentuais."""
    import eval_public_hf

    monkeypatch.setattr(sys, "argv", ["eval_public_hf.py", "--n", "0"])
    with pytest.raises(SystemExit, match="n tem de ser"):
        eval_public_hf.main()


def test_o_diretorio_temporario_e_gerenciado_por_context_manager():
    """`mkdtemp` sem cleanup deixava N wavs em /tmp a cada execução.

    Verifica a CHAMADA, não a menção: o comentário que explica por que o `mkdtemp` saiu
    contém a palavra, e proibi-la no texto faria o teste brigar com a própria documentação.
    """
    import ast
    import inspect

    import eval_public_hf

    arvore = ast.parse(inspect.getsource(eval_public_hf))
    chamadas = {
        n.func.attr
        for n in ast.walk(arvore)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "mkdtemp" not in chamadas, "voltou a criar tempdir sem cleanup"
    assert "TemporaryDirectory" in chamadas
