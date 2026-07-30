"""Prova que a estrutura por pipeline resolve imports por nome (via conftest.py) e as
invariantes estruturais da reorganização (EC-3 sem imports cross-pipeline, EC-5 sem
basename duplicado). Ver knowledge-base/plans/repo-faang-reorg-plan.md."""
import ast
import pathlib

TRAIN = pathlib.Path(__file__).resolve().parents[1]
PIPES = ("finetune", "batch", "realtime", "eval")


def _module_home():
    """basename do módulo -> pipeline em que vive."""
    home = {}
    for pipe in PIPES:
        for f in (TRAIN / pipe).glob("*.py"):
            home[f.stem] = pipe
    return home


def test_import_por_pipeline_resolve_por_nome():
    # símbolos leves de batch/ e finetune/ importam por nome (conftest pôs os subdirs no path)
    from batch_transcribe import greedy          # batch/
    from prep_phoneme_head import apply_patch    # finetune/
    assert callable(greedy) and callable(apply_patch)
    # realtime/ e eval/ podem exigir deps de áudio p/ importar — valida a presença do arquivo
    assert (TRAIN / "realtime" / "mic_transcribe.py").exists()
    assert (TRAIN / "eval" / "measure_callcenter.py").exists()


def test_sem_scripts_soltos_na_raiz_de_training():
    # nenhum .py/.sh vivo pode ficar solto na raiz de training/ (só conftest.py é permitido)
    soltos = [f.name for f in TRAIN.glob("*.py")] + [f.name for f in TRAIN.glob("*.sh")]
    soltos = [n for n in soltos if n != "conftest.py"]
    assert soltos == [], f"scripts soltos na raiz de training/: {soltos}"


def test_no_duplicate_module_basenames():  # EC-5
    seen = {}
    for pipe in PIPES:
        for f in (TRAIN / pipe).glob("*.py"):
            assert f.name not in seen, (
                f"basename duplicado entre pipelines: {f.name} em {pipe} e {seen[f.name]}"
            )
            seen[f.name] = pipe


def test_no_cross_pipeline_imports():  # EC-3
    home = _module_home()
    offenders = []
    for pipe in PIPES:
        for f in (TRAIN / pipe).glob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        names.add(a.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names.add(node.module.split(".")[0])
            for n in names:
                if n in home and home[n] != pipe:
                    offenders.append(f"{pipe}/{f.name} importa `{n}` (vive em {home[n]}/)")
    assert not offenders, "imports cross-pipeline (quebram standalone): " + "; ".join(offenders)
