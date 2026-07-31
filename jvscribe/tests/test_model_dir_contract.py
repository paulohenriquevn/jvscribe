"""O contrato do diretório de artefato: o que o código resolve tem de existir.

Defeito real encontrado em 2026-07-30: `models/current` (symlink de M9/T1.3) aponta para um
diretório cujo modelo se chama `model.int8.onnx`, enquanto `batch_transcribe.py` tinha default
literal `m5_avg.int8.onnx`. Apontar o symlink canônico para o artefato certo e o script quebrar
por nome de arquivo é o pior dos dois mundos: o operador acha que canonizou e não canonizou.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jvscribe" / "batch"))
sys.path.insert(0, str(REPO / "jvscribe" / "common"))

pytest.importorskip("lhotse")


def test_o_default_resolvido_aponta_para_um_modelo_que_existe():
    """Exercita o RESOLVEDOR, não o texto do código — comportamento, não estrutura."""
    from batch_transcribe import _default_model_path

    caminho = Path(_default_model_path())
    if not (REPO / "models" / "current").exists():
        pytest.skip("models/current ausente (artefatos não versionados)")
    assert caminho.exists(), (
        f"o default resolvido ({caminho}) não existe — o artefato canônico e o script "
        "discordam sobre o nome do modelo"
    )
    assert caminho.suffix == ".onnx"


def test_resolvedor_honra_JVSCRIBE_MODEL_DIR(monkeypatch, tmp_path):
    from batch_transcribe import _default_model_path

    (tmp_path / "model.int8.onnx").write_bytes(b"x")
    monkeypatch.setenv("JVSCRIBE_MODEL_DIR", str(tmp_path))
    assert Path(_default_model_path()).parent == tmp_path


def test_o_resolvedor_obedece_ao_model_card_e_nao_ao_nome_do_arquivo(monkeypatch, tmp_path):
    """O `model_card.json` é a autoridade sobre QUAL peso é o canônico.

    Defeito real de 2026-07-30: dois pesos coabitam o diretório canônico — `model.int8.onnx`
    (WER 17,32%) e `m5_avg.int8.onnx` (WER 15,99%, IC95 do delta [-2,25, -0,43] pp, medido em
    FLEURS pt_br test[0:100]). Escolher pelo NOME entrega o pior dos dois em silêncio: nada
    falha, a transcrição só fica mensuravelmente pior. É a mesma classe de falha do M9 —
    artefatos indistinguíveis por metadado superficial.
    """
    import json

    from batch_transcribe import _default_model_path

    (tmp_path / "model.int8.onnx").write_bytes(b"pior")
    (tmp_path / "m5_avg.int8.onnx").write_bytes(b"melhor")
    (tmp_path / "model_card.json").write_text(
        json.dumps({"model_file": "m5_avg.int8.onnx"}), encoding="utf-8"
    )
    monkeypatch.setenv("JVSCRIBE_MODEL_DIR", str(tmp_path))

    assert Path(_default_model_path()).name == "m5_avg.int8.onnx"


def test_o_resolvedor_ignora_card_que_aponta_para_peso_inexistente(monkeypatch, tmp_path):
    """Card corrompido/desatualizado não pode derrubar a resolução — degrada para os nomes conhecidos."""
    import json

    from batch_transcribe import _default_model_path

    (tmp_path / "model.int8.onnx").write_bytes(b"unico")
    (tmp_path / "model_card.json").write_text(
        json.dumps({"model_file": "sumiu.onnx"}), encoding="utf-8"
    )
    monkeypatch.setenv("JVSCRIBE_MODEL_DIR", str(tmp_path))

    assert Path(_default_model_path()).name == "model.int8.onnx"


def test_o_artefato_canonico_tem_tokens_e_card():
    current = REPO / "models" / "current"
    if not current.exists():
        pytest.skip("models/current ausente")
    for obrigatorio in ("tokens.txt", "model_card.json"):
        assert (current / obrigatorio).exists(), f"{obrigatorio} ausente no artefato canônico"


def test_todos_os_entrypoints_resolvem_o_MESMO_modelo_canonico():
    """Um artefato canônico, um resolvedor — não um default literal por script.

    Defeito real de 2026-07-30: `mic_transcribe.py` carregava `m5_avg.int8.onnx` fixo no
    código. Ao renomear o artefato para o padrão SOTA, o lote continuou funcionando e o
    tempo real quebrou — porque cada entrypoint resolvia o modelo por conta própria.
    Default duplicado é default que diverge.
    """
    import importlib

    sys.path.insert(0, str(REPO / "jvscribe" / "common"))
    from batch_transcribe import _default_model_path

    canonico = Path(_default_model_path())
    if not (REPO / "models" / "current").exists():
        pytest.skip("models/current ausente")

    mic = importlib.import_module("mic_transcribe")
    assert Path(mic._default_model_path()).resolve() == canonico.resolve(), (
        "mic_transcribe e batch_transcribe discordam sobre o modelo canônico"
    )


# --- renomeação MACAW_MODEL_DIR → JVSCRIBE_MODEL_DIR ------------------------
# O produto se chama jvscribe; "macaw" era resquício. Mas renomear variável de ambiente sem
# rede faz quem a tem exportada cair em SILÊNCIO para `models/current` — o mesmo modo de falha
# que já entregou o modelo errado neste projeto.
#
# ⚠️ Este bloco cita o nome ANTIGO de propósito. Uma varredura de renomeação já passou por
# aqui e trocou as duas variáveis pela mesma, fazendo a segunda sobrescrever a primeira — o
# teste de precedência passou a comparar a variável consigo mesma.


def test_a_variavel_nova_e_honrada(monkeypatch, tmp_path):
    from batch_transcribe import _default_model_path

    (tmp_path / "model.int8.onnx").write_bytes(b"x")
    monkeypatch.delenv("MACAW_MODEL_DIR", raising=False)
    monkeypatch.setenv("JVSCRIBE_MODEL_DIR", str(tmp_path))
    assert Path(_default_model_path()).parent == tmp_path


def test_a_variavel_antiga_continua_funcionando(monkeypatch, tmp_path):
    """Compatibilidade: quem já tem a variável antiga exportada não pode quebrar."""
    from batch_transcribe import _default_model_path

    (tmp_path / "model.int8.onnx").write_bytes(b"x")
    monkeypatch.delenv("JVSCRIBE_MODEL_DIR", raising=False)
    monkeypatch.setenv("MACAW_MODEL_DIR", str(tmp_path))
    assert Path(_default_model_path()).parent == tmp_path


def test_a_variavel_nova_tem_precedencia_sobre_a_antiga(monkeypatch, tmp_path):
    """Com as duas setadas, a nova ganha — senão a migração nunca termina."""
    from batch_transcribe import _default_model_path

    nova = tmp_path / "nova"; nova.mkdir(); (nova / "model.int8.onnx").write_bytes(b"n")
    velha = tmp_path / "velha"; velha.mkdir(); (velha / "model.int8.onnx").write_bytes(b"v")
    monkeypatch.setenv("JVSCRIBE_MODEL_DIR", str(nova))
    monkeypatch.setenv("MACAW_MODEL_DIR", str(velha))
    assert Path(_default_model_path()).parent == nova


def test_a_variavel_antiga_avisa_que_esta_obsoleta(monkeypatch, tmp_path):
    """Compatibilidade silenciosa vira permanente. O aviso é o que faz a migração acabar.

    Usa `DeprecationWarning` da stdlib, não um flag de módulo: a primeira versão guardava
    "já avisei" num global e criou dependência de ordem entre testes — passava isolado e
    falhava na suíte.
    """
    import warnings as w

    from artifact import default_model_path

    (tmp_path / "model.int8.onnx").write_bytes(b"x")
    monkeypatch.delenv("JVSCRIBE_MODEL_DIR", raising=False)
    monkeypatch.setenv("MACAW_MODEL_DIR", str(tmp_path))

    with w.catch_warnings(record=True) as avisos:
        w.simplefilter("always")
        default_model_path()
    assert any("MACAW_MODEL_DIR" in str(a.message) for a in avisos), (
        "a variável obsoleta tem de emitir DeprecationWarning"
    )
