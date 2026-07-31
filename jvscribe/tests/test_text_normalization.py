"""T3.2 (M9) — as duas semânticas de normalização PT-BR, medidas e nomeadas.

Cinco funções chamadas `normalize_ptbr` conviviam no repo. Medido em 2026-07-30: são
**2 semânticas distintas**, com 3 cópias byte-idênticas de uma delas.

  REMOVE acento  → jvscribe/common/text.py:52        (comparação de WER)
  PRESERVA acento→ jvscribe/finetune/prep_icefall.py:49      (alvo de treino)
                   jvscribe/eval/eval_runtime_wer.py:37   (cópia idêntica, documentada)
                   jvscribe/eval/analyze_error_composition.py:37 (cópia idêntica)

Enquanto as duas compartilhavam um nome, todo WER do projeto carregava uma ambiguidade
silenciosa sobre qual régua foi usada — e comparar "35,53% telefônico" com "16,14% FLEURS"
pressupõe a mesma normalização.
"""
from pathlib import Path

import pytest

# `lhotse` puxa a stack de treino e não está no requirements-test.txt (deliberado:
# é pesada e o CI model-free não precisa dela). SKIP visível > erro de coleta.
pytest.importorskip("lhotse")

REPO = Path(__file__).resolve().parents[2]

ACENTUADO = "coração, ATENÇÃO! não é ótimo?"


def test_as_duas_semanticas_divergem_de_fato():
    """Oráculo da ambiguidade: mesmo nome, resultados diferentes."""
    from text import normalize_for_wer_compare as remove_acento
    from prep_icefall import normalize_ptbr as preserva_acento

    a, b = remove_acento(ACENTUADO), preserva_acento(ACENTUADO)
    assert a != b, f"esperava divergência entre as duas semânticas; ambas deram {a!r}"
    assert "ç" not in a and "ã" not in a, f"a de comparação deve remover acento: {a!r}"
    assert "ç" in b or "ã" in b, f"a de treino deve preservar acento: {b!r}"


def test_common_text_expoe_as_duas_com_nome_que_revela_o_contrato():
    from text import normalize_for_wer_compare, normalize_train_target

    assert "ç" not in normalize_for_wer_compare(ACENTUADO)
    assert "ç" in normalize_train_target(ACENTUADO)


def test_common_reproduz_exatamente_as_implementacoes_originais():
    """Migração sem mudança de comportamento — o que protege os números publicados."""
    from text import normalize_for_wer_compare as remove_acento
    from prep_icefall import normalize_ptbr as preserva_acento
    from text import normalize_for_wer_compare, normalize_train_target

    for amostra in (ACENTUADO, "", "  ", "R$ 1.234,56 e três vírgulas", "ÁÉÍÓÚ ãõ çÇ"):
        assert normalize_for_wer_compare(amostra) == remove_acento(amostra), amostra
        assert normalize_train_target(amostra) == preserva_acento(amostra), amostra


def test_cada_modulo_usa_a_regua_do_seu_proposito():
    """Este teste asseverava que os TRÊS módulos compartilham a semântica de treino.

    Eles nunca deveriam concordar. `prep_icefall` prepara o **corpus de treino** (preserva
    acento — o modelo tem de aprender a acentuar); os outros dois **medem WER** (removem, ou
    o acento errado conta como palavra errada). Enquanto os três casavam, o teste travava o
    agrupamento defeituoso como se fosse o desenho — e o WER de runtime (29,92%) saiu daí,
    incomparável com os números medidos pela régua canônica.

    Medido: numa frase em que só o acento difere, a régua de treino dá 62,5% de WER onde a
    canônica dá 0%.
    """
    from analyze_error_composition import normalize_ptbr as mede_erro
    from eval_runtime_wer import normalize_ptbr as mede_wer
    from prep_icefall import normalize_ptbr as prepara_corpus

    for amostra in (ACENTUADO, "ÁÉÍÓÚ ãõ çÇ", "sem acento aqui"):
        # os dois medidores concordam entre si
        assert mede_wer(amostra) == mede_erro(amostra), amostra

    # e divergem de quem prepara corpus — exatamente no acento
    assert prepara_corpus("coração") == "coração"
    assert mede_wer("coração") == "coracao"
    assert mede_erro("coração") == "coracao"


def test_nao_existe_mais_normalize_ptbr_com_semantica_divergente():
    """O critério que importa não é "zero definições" — é zero AMBIGUIDADE.

    Quatro cópias da mesma semântica são redundância (tolerável). Duas semânticas opostas sob
    o mesmo nome são uma armadilha: comparar dois WERs pressupõe uma régua que ninguém
    verificou. A divergente foi renomeada para `normalize_for_wer_compare` em M9/T3.2.
    """
    import subprocess

    src = subprocess.run(
        ["grep", "-rln", "def normalize_ptbr", "scripts", "jvscribe", "--include=*.py"],
        cwd=REPO, capture_output=True, text=True,
    ).stdout.split()
    # Todas as definições remanescentes preservam acento (semântica de alvo de treino).
    for rel in src:
        # `smoke/` está congelado por auditoria anterior; arquivos de teste citam o nome
        # em prosa e no próprio grep (auto-referência).
        if "smoke" in rel or "/tests/" in rel or rel.startswith("tests/"):
            continue
        body = (REPO / rel).read_text(encoding="utf-8")
        i = body.index("def normalize_ptbr")
        trecho = body[i : i + 400]
        assert "áàâãéêíóôõúçü" in trecho, (
            f"{rel} define normalize_ptbr com semântica que NÃO preserva acento — "
            "a ambiguidade que M9/T3.2 eliminou voltou"
        )
