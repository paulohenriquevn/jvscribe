"""Expõe os subdirs de pipeline ao sys.path para que os testes (e scripts) importem os
módulos por nome depois da reorganização por pipeline (finetune/batch/realtime/eval).

pytest auto-carrega este conftest do rootdir `training/` antes de coletar `tests/`, então
`from batch_transcribe import ...` resolve via `training/batch/` sem tocar em cada teste.
Ver ADR D2 em knowledge-base/plans/repo-faang-reorg-plan.md."""
import sys
import pathlib

_ROOT = pathlib.Path(__file__).parent
for _pipe in ("finetune", "batch", "realtime", "eval"):
    _p = str(_ROOT / _pipe)
    if _p not in sys.path:
        sys.path.insert(0, _p)
