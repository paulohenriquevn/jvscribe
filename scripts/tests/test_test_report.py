"""T2.3 (M9) — `test_report.sh` não pode reportar sucesso quando o build falha.

Defeito real observado em 2026-07-30: com o build quebrado (toolchain 1.75 incompatível com
`ort`), o script imprimiu "testes 'ok': 0 / SKIPs efetivos: 0" e saiu 0 — um relatório
tranquilizador sobre uma suíte que não rodou. A ferramenta que existe para impedir falso
verde produziu o falso verde mais puro possível.
"""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "test_report.sh"


def test_script_propaga_falha_de_build():
    src = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"\$\?|PIPESTATUS|rc=", src), (
        "o script precisa capturar o código de saída do cargo test"
    )
    assert "exit 1" in src or "exit \"$rc\"" in src or "exit $rc" in src, (
        "o script precisa sair != 0 quando a suíte não roda"
    )


def test_script_falha_quando_zero_testes_executaram():
    """Zero testes executados nunca é sucesso — ou o build quebrou, ou o filtro está errado."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "0" in src and ("nenhum teste" in src.lower() or "zero" in src.lower()), (
        "o script precisa tratar explicitamente o caso de zero testes executados"
    )


def test_comportamento_real_com_comando_quebrado(tmp_path):
    """Oráculo executável: simula build quebrado e exige exit != 0."""
    fake = tmp_path / "report.sh"
    body = SCRIPT.read_text(encoding="utf-8").replace(
        "cargo test --workspace -- --nocapture", "false"
    )
    fake.write_text(body, encoding="utf-8")
    fake.chmod(0o755)
    r = subprocess.run(["bash", str(fake)], capture_output=True, text=True, cwd=REPO)
    assert r.returncode != 0, (
        f"com o build quebrado o script DEVE falhar; saiu {r.returncode}\n{r.stdout}\n{r.stderr}"
    )
