"""T3.2 (M9) — as duas semânticas de normalização PT-BR, medidas e nomeadas.

Cinco funções chamadas `normalize_ptbr` conviviam no repo. Medido em 2026-07-30: são
**2 semânticas distintas**, com 3 cópias byte-idênticas de uma delas.

  REMOVE acento  → scripts/text_normalize_ptbr.py:52        (comparação de WER)
  PRESERVA acento→ training/finetune/prep_icefall.py:49      (alvo de treino)
                   training/scripts/eval_runtime_wer.py:37   (cópia idêntica, documentada)
                   training/scripts/analyze_error_composition.py:37 (cópia idêntica)

Enquanto as duas compartilhavam um nome, todo WER do projeto carregava uma ambiguidade
silenciosa sobre qual régua foi usada — e comparar "35,53% telefônico" com "16,14% FLEURS"
pressupõe a mesma normalização.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "training" / "scripts"))

ACENTUADO = "coração, ATENÇÃO! não é ótimo?"


def test_as_duas_semanticas_divergem_de_fato():
    """Oráculo da ambiguidade: mesmo nome, resultados diferentes."""
    from text_normalize_ptbr import normalize_for_wer_compare as remove_acento
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
    from text_normalize_ptbr import normalize_for_wer_compare as remove_acento
    from prep_icefall import normalize_ptbr as preserva_acento
    from text import normalize_for_wer_compare, normalize_train_target

    for amostra in (ACENTUADO, "", "  ", "R$ 1.234,56 e três vírgulas", "ÁÉÍÓÚ ãõ çÇ"):
        assert normalize_for_wer_compare(amostra) == remove_acento(amostra), amostra
        assert normalize_train_target(amostra) == preserva_acento(amostra), amostra


def test_as_tres_copias_da_semantica_de_treino_sao_equivalentes():
    """Medição do inventário: 3 cópias, 1 semântica."""
    from prep_icefall import normalize_ptbr as a
    from eval_runtime_wer import normalize_ptbr as b
    from analyze_error_composition import normalize_ptbr as c

    for amostra in (ACENTUADO, "ÁÉÍÓÚ ãõ çÇ", "sem acento aqui"):
        assert a(amostra) == b(amostra) == c(amostra), amostra


def test_nao_existe_mais_normalize_ptbr_com_semantica_divergente():
    """O critério que importa não é "zero definições" — é zero AMBIGUIDADE.

    Quatro cópias da mesma semântica são redundância (tolerável). Duas semânticas opostas sob
    o mesmo nome são uma armadilha: comparar dois WERs pressupõe uma régua que ninguém
    verificou. A divergente foi renomeada para `normalize_for_wer_compare` em M9/T3.2.
    """
    import subprocess

    src = subprocess.run(
        ["grep", "-rln", "def normalize_ptbr", "scripts", "training", "--include=*.py"],
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
