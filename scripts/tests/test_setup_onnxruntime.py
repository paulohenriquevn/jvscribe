"""T2.2 (M9) — o download do ONNX Runtime tem de verificar integridade.

Por que importa: [MEDIDO] em M6, uma `libonnxruntime` errada deixou a inferência **até 40×
mais lenta** e custou uma investigação inteira. O script baixava e extraía sem nenhuma
verificação — um tarball corrompido, truncado ou substituído passaria silenciosamente.

O peer faz isso desde sempre: `cmake/googletest.cmake:37` usa `URL_HASH` obrigatório mesmo
com URL de tag imutável [FONTE-REPO].
"""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "setup_onnxruntime.sh"
SUMFILE = REPO / "scripts" / "onnxruntime-1.23.0.sha256"


def test_arquivo_de_checksum_existe_e_tem_formato_valido():
    assert SUMFILE.exists(), f"checksum esperado ausente: {SUMFILE}"
    body = SUMFILE.read_text(encoding="utf-8").strip()
    assert re.match(r"^[0-9a-f]{64}\s+\S+$", body), f"formato inválido: {body!r}"


def test_script_verifica_o_checksum_antes_de_extrair():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "sha256sum" in src, "o script precisa verificar integridade"
    i_check = src.index("sha256sum")
    i_tar = src.index("tar xzf")
    assert i_check < i_tar, "a verificação DEVE vir antes da extração"


def test_checksum_rejeita_arquivo_adulterado(tmp_path):
    """O oráculo real: um arquivo com conteúdo errado tem de reprovar."""
    fake = tmp_path / "onnxruntime-linux-x64-1.23.0.tgz"
    fake.write_bytes(b"conteudo adulterado")
    expected = SUMFILE.read_text(encoding="utf-8").split()[0]
    (tmp_path / "sums").write_text(f"{expected}  {fake.name}\n", encoding="utf-8")
    r = subprocess.run(
        ["sha256sum", "-c", "sums"], cwd=tmp_path, capture_output=True, text=True
    )
    assert r.returncode != 0, "sha256sum -c deveria falhar com conteúdo adulterado"


def test_script_e_idempotente_quando_ja_presente():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "já presente" in src and "exit 0" in src, "idempotência deve ser preservada"
