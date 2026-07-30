"""T2.3 (M9) — o CI separa teste model-free de teste que exige artefato.

Racional [FONTE-REPO]: nenhum dos 22 `*-test.cc` do sherpa-onnx toca modelo — o falso verde
é eliminado por DESIGN, não detectado por relatório. Aqui a suíte mistura as duas camadas no
mesmo comando (`cargo test --workspace`), e testes de integração degradam com `SKIP`
silencioso. A separação em dois jobs desfaz a ambiguidade.
"""
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CI = REPO / ".github" / "workflows" / "ci.yml"


def _load():
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def test_workflow_existe_e_parseia():
    assert CI.exists(), f"workflow ausente: {CI}"
    assert _load() is not None


def test_declara_os_dois_jobs():
    jobs = _load()["jobs"]
    assert "test-model-free" in jobs, "job obrigatório ausente"
    assert "test-with-artifact" in jobs, "job condicional ausente"


def test_job_model_free_nao_referencia_artefato_de_modelo():
    """O job obrigatório não pode depender de peso não versionado."""
    body = yaml.dump(_load()["jobs"]["test-model-free"])
    for proibido in ("models/", "results/onnx", ".onnx", "m5-final"):
        assert proibido not in body, (
            f"o job obrigatório referencia artefato de modelo ({proibido!r}) — "
            "isso o torna não-reprodutível em runner limpo"
        )


def test_job_model_free_roda_as_duas_suites():
    body = yaml.dump(_load()["jobs"]["test-model-free"])
    assert "cargo test" in body, "suíte Rust ausente"
    assert "pytest" in body, "suíte Python ausente"


def test_job_com_artefato_e_condicional_e_nao_bloqueia():
    """Ausência de artefato não pode pintar o build de verde nem de vermelho por engano."""
    job = _load()["jobs"]["test-with-artifact"]
    body = yaml.dump(job)
    assert "--ignored" in body, "deve rodar justamente os testes marcados #[ignore]"
    assert "if" in job or "continue-on-error" in body, (
        "o job precisa ser explicitamente condicional"
    )
