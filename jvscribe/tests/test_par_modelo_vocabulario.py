"""O par (modelo, vocabulário) não é intercambiável — e nada verificava isso.

`CLAUDE.md` registra o modo de falha como fato medido deste projeto:

  > Dois artefatos deste projeto têm 500 tokens emitíveis e **492 dos 500 ids mapeiam para
  > tokens diferentes**. Trocar o `tokens.txt` produz português plausível e errado, sem erro
  > nenhum. Valide pelo `vocab_fingerprint` do `model_card.json`, **nunca** pela contagem.

Auditado em 2026-07-31: os cinco entrypoints (`batch_transcribe`, `decode_onnx_local`,
`eval_public_hf`, `streaming`, `live_transcribe`) carregavam modelo e tokens **sem nenhuma
verificação**. Era também o DoD#2 de M9, aberto.

O que torna isto perigoso e não apenas incorreto: a saída é português **plausível**. Não há
exceção, não há caractere estranho, não há queda de confiança — só um WER pior que ninguém
consegue explicar. O teste abaixo constrói exatamente esse cenário.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG / "common"))


def _artefato(tmp: Path, tokens: list[str], *, fingerprint: str | None = None) -> Path:
    """Monta um diretório de artefato mínimo: modelo fake, tokens.txt e model_card.json."""
    from artifact import vocab_fingerprint

    d = tmp / "artefato"
    d.mkdir(parents=True, exist_ok=True)
    (d / "model.int8.onnx").write_bytes(b"onnx-falso")
    (d / "tokens.txt").write_text(
        "".join(f"{t} {i}\n" for i, t in enumerate(tokens)), encoding="utf-8"
    )
    card = {
        "schema": "jvscribe-model-card/1",
        "model_file": "model.int8.onnx",
        "tokens_file": "tokens.txt",
        "vocab_real_len": len(tokens),
        "vocab_fingerprint": fingerprint or vocab_fingerprint(d / "tokens.txt"),
    }
    (d / "model_card.json").write_text(json.dumps(card), encoding="utf-8")
    return d


TOKENS_A = ["<blk>", "▁a", "▁de", "▁que", "ção"]
# MESMA cardinalidade, ids mapeando tokens diferentes — o cenário real do projeto.
TOKENS_B = ["<blk>", "▁o", "▁da", "▁qual", "ções"]


def test_par_coerente_passa(tmp_path):
    from artifact import validar_par_modelo_vocabulario

    d = _artefato(tmp_path, TOKENS_A)
    validar_par_modelo_vocabulario(d)  # não levanta


def test_vocabulario_trocado_com_a_MESMA_contagem_e_detectado(tmp_path):
    """O caso que a contagem não pega — e é o que de fato aconteceu no projeto."""
    from artifact import ParVocabularioInvalido, validar_par_modelo_vocabulario

    d = _artefato(tmp_path, TOKENS_A)
    # troca o tokens.txt por outro de MESMO tamanho, sem tocar no card
    (d / "tokens.txt").write_text(
        "".join(f"{t} {i}\n" for i, t in enumerate(TOKENS_B)), encoding="utf-8"
    )
    with pytest.raises(ParVocabularioInvalido) as e:
        validar_par_modelo_vocabulario(d)
    msg = str(e.value)
    assert "fingerprint" in msg
    assert "500" not in msg or "contagem" in msg.lower()  # não vende contagem como prova


def test_a_contagem_sozinha_NAO_distinguiria(tmp_path):
    """Ancora por que a validação é por fingerprint: a cardinalidade é idêntica.

    Se este teste falhar, o cenário deixou de representar o defeito real e os dois testes
    acima viram teatro.
    """
    assert len(TOKENS_A) == len(TOKENS_B)
    assert sum(a != b for a, b in zip(TOKENS_A, TOKENS_B)) >= 4


def test_card_sem_fingerprint_falha_claro(tmp_path):
    """Artefato antigo sem o campo: falha dizendo o que fazer, não com KeyError."""
    from artifact import ParVocabularioInvalido, validar_par_modelo_vocabulario

    d = _artefato(tmp_path, TOKENS_A)
    card = json.loads((d / "model_card.json").read_text())
    del card["vocab_fingerprint"]
    (d / "model_card.json").write_text(json.dumps(card), encoding="utf-8")
    # A mensagem tem de dizer O QUE RODAR para consertar. O módulo que gera o card foi
    # absorvido por `artifact.py` — a guarda verifica a INSTRUÇÃO, não o nome antigo.
    with pytest.raises(ParVocabularioInvalido, match=r"regenere com.*artifact\.py"):
        validar_par_modelo_vocabulario(d)


def test_tokens_ausente_falha_claro(tmp_path):
    from artifact import ParVocabularioInvalido, validar_par_modelo_vocabulario

    d = _artefato(tmp_path, TOKENS_A)
    (d / "tokens.txt").unlink()
    with pytest.raises(ParVocabularioInvalido, match="tokens"):
        validar_par_modelo_vocabulario(d)


def test_sem_model_card_e_no_op_explicito(tmp_path):
    """Sem card não há o que comparar — não inventa aprovação nem quebra o legado.

    Levantar aqui tornaria a validação impossível de adotar incrementalmente; aprovar em
    silêncio seria mentir. O contrato é devolver `False` (não validado) e seguir.
    """
    from artifact import validar_par_modelo_vocabulario

    d = _artefato(tmp_path, TOKENS_A)
    (d / "model_card.json").unlink()
    assert validar_par_modelo_vocabulario(d) is False


def test_o_artefato_canonico_do_repositorio_e_coerente():
    """Regressão sobre o artefato real — o par publicado tem de conferir."""
    from artifact import default_model_path, validar_par_modelo_vocabulario

    modelo = Path(default_model_path())
    if not modelo.exists():
        pytest.skip(f"artefato canônico ausente: {modelo}")
    assert validar_par_modelo_vocabulario(modelo.parent) is True


def test_tokens_passado_a_mao_tambem_e_validado(tmp_path):
    """O `--tokens` dos entrypoints é o caso em que o erro é MAIS provável.

    Sem o override, a validação conferiria o tokens declarado no card enquanto o processo
    carrega outro arquivo — aprovando justamente o cenário que ela existe para pegar.
    """
    from artifact import ParVocabularioInvalido, validar_par_modelo_vocabulario

    d = _artefato(tmp_path, TOKENS_A)
    outro = tmp_path / "vocab_de_outro_modelo.txt"
    outro.write_text("".join(f"{t} {i}\n" for i, t in enumerate(TOKENS_B)), encoding="utf-8")

    assert validar_par_modelo_vocabulario(d) is True          # o do card confere
    with pytest.raises(ParVocabularioInvalido):               # o passado à mão, não
        validar_par_modelo_vocabulario(d, tokens_path=outro)


def test_todo_entrypoint_que_carrega_modelo_valida_o_par():
    """Guarda de fiação — **descoberta**, não lista escrita à mão.

    A primeira versão desta guarda enumerava QUATRO entrypoints. Passou verde enquanto OITO
    outros carregavam modelo e vocabulário sem conferir se combinam:

        bench/bench_rtfx · bench/calibrate · bench/runtime_bench · bench/stress_test
        eval/measure_callcenter · probes/blank_penalty_probe
        probes/tta_feature_align_probe · realtime/mic_transcribe

    A causa foi a fragmentação da sequência de carga: ela estava replicada em treze lugares, e
    o passo de validação só existia onde alguém lembrou. `common/engine.py` unificou a
    sequência; esta guarda garante que ninguém volte a montá-la à mão sem validar.

    Validação que ninguém chama é código morto que finge proteger.
    """

    culpados = []
    for f in sorted(PKG.rglob("*.py")):
        if "__pycache__" in f.parts or f.parent.name == "tests":
            continue
        fonte = f.read_text(encoding="utf-8", errors="replace")
        if '__name__ == "__main__"' not in fonte:
            continue
        carrega = "criar_sessao" in fonte or "InferenceSession" in fonte
        if not carrega:
            continue
        # Vale tanto chamar a validação direto quanto usar o carregador que a embute.
        valida = any(
            s in fonte for s in ("validar_par_modelo_vocabulario", "Motor.carregar", "engine.resolver",
                                 "from engine import")
        )
        if not valida:
            culpados.append(str(f.relative_to(PKG)))
    assert not culpados, (
        "entrypoint carrega modelo sem validar o par (modelo, vocabulário) — use "
        "`engine.Motor.carregar` ou chame `validar_par_modelo_vocabulario`:\n  "
        + "\n  ".join(culpados)
    )
