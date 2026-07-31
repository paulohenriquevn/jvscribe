"""T1.3 (M9) — model_card.json e o diretório canônico.

Invariante inegociável deste milestone: **nenhum arquivo de modelo é movido ou removido**.
"Canonizar" é symlink, nunca `rm`/`mv`.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

# Fingerprint MEDIDO pela implementação Rust (Vocab::fingerprint) em 2026-07-30 sobre
# jvscribe/results/onnx/tokens.txt. O Python DEVE reproduzi-lo bit a bit — é o teste de
# conformidade cross-language que o blueprint recomendou.
RUST_FINGERPRINT_RUNTIME = "4e145aadda045ce654171add157ae7c56e704275dd173b51a9f2754140212647"


def test_fingerprint_python_reproduz_o_do_rust():
    from make_model_card import vocab_fingerprint

    tokens = REPO / "jvscribe/results/onnx/tokens.txt"
    if not tokens.exists():
        import pytest

        pytest.skip(f"artefato ausente: {tokens}")
    assert vocab_fingerprint(tokens) == RUST_FINGERPRINT_RUNTIME


def test_real_len_exclui_desambiguacao(tmp_path):
    from make_model_card import vocab_real_len

    p = tmp_path / "tokens.txt"
    p.write_text("<blk> 0\na 1\nb 2\n#0 3\n#1 4\n", encoding="utf-8")
    assert vocab_real_len(p) == 3


def test_model_card_contem_campos_obrigatorios(tmp_path):
    from make_model_card import build_card

    (tmp_path / "tokens.txt").write_text("<blk> 0\na 1\n#0 2\n", encoding="utf-8")
    (tmp_path / "model.int8.onnx").write_bytes(b"fake-onnx-bytes")
    card = build_card(tmp_path, generated_at="2026-07-30T00:00:00Z")
    for k in ("model_sha256", "vocab_fingerprint", "vocab_real_len", "generated_at", "model_file"):
        assert k in card, f"campo obrigatório ausente: {k}"
    assert card["vocab_real_len"] == 2


def test_gerar_card_nunca_remove_nem_move_arquivo(tmp_path):
    """O invariante do dono: modelo nunca é excluído."""
    from make_model_card import build_card, write_card

    (tmp_path / "tokens.txt").write_text("<blk> 0\na 1\n", encoding="utf-8")
    (tmp_path / "model.int8.onnx").write_bytes(b"pesos")
    before = sorted(p.name for p in tmp_path.iterdir())

    write_card(tmp_path, build_card(tmp_path, generated_at="2026-07-30T00:00:00Z"))
    write_card(tmp_path, build_card(tmp_path, generated_at="2026-07-30T00:00:00Z"))  # idempotente

    after = sorted(p.name for p in tmp_path.iterdir())
    assert set(before).issubset(set(after)), "nenhum arquivo pode sumir"
    assert (tmp_path / "model.int8.onnx").read_bytes() == b"pesos", "pesos intactos"


def test_eval_public_hf_nao_tem_caminho_absoluto():
    """Critério de aceite T1.3: o script não pode estar amarrado à máquina do dono."""
    src = (REPO / "jvscribe/batch/eval_public_hf.py").read_text(encoding="utf-8")
    assert "/home/paulo" not in src, "caminho absoluto ainda presente"
    # A checagem era pelo literal `JVSCRIBE_MODEL_DIR`. O script passou a DELEGAR ao
    # `common/artifact.py`, que resolve a variável **e** lê o `model_card.json` — melhor que
    # reimplementar a cadeia. A guarda segue o mesmo propósito: não amarrar à máquina do dono.
    assert "default_model_path" in src, "deve resolver pelo artefato canônico"


def test_models_current_e_symlink_nao_copia():
    """`models/current` canoniza por symlink — nunca por cópia ou movimentação de pesos."""
    current = REPO / "models" / "current"
    if not current.exists():
        import pytest

        pytest.skip("models/current ausente (artefatos não versionados)")
    assert current.is_symlink(), "models/current DEVE ser symlink, não diretório copiado"
    assert (current / "tokens.txt").exists(), "o symlink deve resolver para um artefato válido"


def test_o_schema_declara_o_nome_do_produto():
    """O schema é `jvscribe-model-card`, não `jvscribe-model-card`.

    "jvscribe" era o nome antigo do produto. Um card publicado com o nome errado confunde quem
    consome o artefato — e ele É consumido: está no HuggingFace.
    """
    import make_model_card as m

    # O que importa é o que é ESCRITO. O nome antigo pode (e deve) continuar na lista de
    # aceitos na leitura — ver o teste seguinte.
    assert m.SCHEMA == "jvscribe-model-card/1"


def test_leitor_de_card_aceita_o_schema_antigo():
    """Compatibilidade: cards já gerados (inclusive o publicado) trazem o nome antigo.

    Recusá-los quebraria a leitura de um artefato válido — o schema mudou de nome, não de
    formato.
    """
    import make_model_card as m

    assert hasattr(m, "SCHEMAS_ACEITOS"), "falta o conjunto de schemas aceitos na leitura"
    assert "jvscribe-model-card/1" in m.SCHEMAS_ACEITOS
    assert "jvscribe-model-card/1" in m.SCHEMAS_ACEITOS
