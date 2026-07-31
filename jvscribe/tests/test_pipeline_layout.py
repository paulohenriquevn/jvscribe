"""Prova que a estrutura por pipeline resolve imports por nome (via conftest.py) e as
invariantes estruturais da reorganização (EC-3 sem imports cross-pipeline, EC-5 sem
basename duplicado). Ver wiki/index.md."""
import ast
import pathlib

import pytest

# `lhotse` puxa a stack de treino e não está no requirements-test.txt (deliberado:
# é pesada e o CI model-free não precisa dela). SKIP visível > erro de coleta.
pytest.importorskip("lhotse")

TRAIN = pathlib.Path(__file__).resolve().parents[1]
# TODAS as pipelines — `corpus` e `tools` ficavam de fora, e foi por isso que cinco
# violações de fronteira passaram despercebidas até a auditoria de 2026-07-31.
PIPES = ("finetune", "batch", "realtime", "eval", "corpus", "bench", "probes", "audit")
# `common` é o shared kernel (M9/T3.1): é o ÚNICO destino permitido para import
# cross-pipeline. A regra ficou mais forte — antes ela era contornada por cópia, que
# é invisível para ela (o colapso CTC acabou replicado 7×).
SHARED = "common"


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
    # nenhum .py/.sh vivo pode ficar solto na raiz de jvscribe/ (só conftest.py é permitido)
    soltos = [f.name for f in TRAIN.glob("*.py")] + [f.name for f in TRAIN.glob("*.sh")]
    soltos = [n for n in soltos if n != "conftest.py"]
    assert soltos == [], f"scripts soltos na raiz de jvscribe/: {soltos}"


def test_no_duplicate_module_basenames():  # EC-5
    seen = {}
    for pipe in PIPES:
        for f in (TRAIN / pipe).glob("*.py"):
            if f.name == "__init__.py":
                continue          # marcador de pacote, não módulo — duplica por construção
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


# --- M9/T3.1+T3.3 — o shared kernel e o buraco que a guarda não via -----------------


def test_import_de_common_e_permitido():
    """`common/` é o destino legítimo do conhecimento compartilhado.

    Sem ele, a regra "nenhum import cross-pipeline" empurrava para a cópia — o colapso CTC
    acabou replicado 7× e `normalize_ptbr` 5×, com semânticas incompatíveis.
    """
    import ctc  # vive em jvscribe/common/, exposto pelo conftest

    assert ctc.collapse([0, 5, 5, 0, 3]) == [5, 3]


def test_common_nao_importa_de_pipeline():
    """A dependência é unidirecional: pipelines → common, nunca o contrário."""
    home = _module_home()
    offenders = []
    for f in (TRAIN / SHARED).glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module.split(".")[0]]
            for m in mods:
                if m in home:
                    offenders.append(f"{SHARED}/{f.name} importa `{m}` (vive em {home[m]}/)")
    assert not offenders, "common/ não pode depender de pipeline: " + "; ".join(offenders)


def test_modulo_de_pipeline_nao_pode_viver_fora_da_arvore():
    """Fecha o buraco por onde as cópias escaparam.

    A guarda vigiava apenas `jvscribe/`. Cópias byte-idênticas de `decode_onnx_local.py` e
    `mic_transcribe.py` foram parar em `models/m5-final-medium-phoneme/` — invisíveis para
    ela. Hoje são idênticas; a divergência é questão de tempo.
    """
    import subprocess

    repo = TRAIN.parent
    # Só arquivos VERSIONADOS: a guarda protege o repositório, e diretórios gitignored
    # (models/, data/) são artefatos locais do operador, não parte do contrato do repo.
    tracked = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.split()
    # `__init__.py` é marcador de pacote, não módulo de pipeline — casaria por stem em qualquer
    # pacote do repo.
    known = {n for n in _module_home() if n != "__init__"}
    known |= {f.stem for f in (TRAIN / SHARED).glob("*.py") if f.stem != "__init__"}
    # `.claude/` é ferramental de AGENTE (skills, hooks, plugins), não código do produto:
    # não está em `sys.path` do jvscribe e não pode sombrear módulo nenhum. Confundir os dois
    # fez esta guarda acusar `quality-init/scripts/lib/calibrate.py` quando `bench/calibrate.py`
    # nasceu — um falso positivo que forçaria renomear código do produto por causa de uma skill.
    FORA_DO_PRODUTO = (".claude/", "scripts/", "docs/")
    offenders = [
        rel
        for rel in tracked
        if not rel.startswith("jvscribe/")
        and not rel.startswith(FORA_DO_PRODUTO)
        and pathlib.Path(rel).stem in known
    ]
    assert not offenders, (
        "módulo de pipeline duplicado fora de jvscribe/: " + "; ".join(sorted(offenders))
    )


def test_entrypoints_de_pipeline_rodam_standalone():
    """A convenção do `jvscribe/README.md` é que cada script roda sozinho.

    O `conftest.py` põe as pipelines no `sys.path` **para os testes** — mas um humano
    executando `python3 jvscribe/batch/batch_transcribe.py` só tem o diretório do próprio
    script no path. Um import que só resolve sob pytest passa em toda a suíte e quebra em
    produção; foi exatamente o que aconteceu em M9/T3.1 (`ModuleNotFoundError: No module
    named 'ctc'`), sem que nenhum teste percebesse.
    """
    import subprocess
    import sys

    falhas = []
    for rel in (
        "batch/batch_transcribe.py",
        "batch/decode_onnx_local.py",
        "batch/bench_rtfx.py",
        # Entrypoints que o README raiz documenta no quickstart. Comando documentado que não
        # roda é a mesma classe de falha que link quebrado — e o README já teve 5 de 5 links
        # apontando para o vazio.
        "realtime/live_transcribe.py",
        "bench/runtime_bench.py",
        "bench/stress_test.py",
        "eval/compare_models.py",
        "bench/finetune_smoke.py",
        "bench/calibrate.py",
        # `corpus/` estava FORA desta lista, e por isso `run_pipeline.py` quebrava standalone
        # com `ModuleNotFoundError: No module named 'text_normalize_ptbr'` — o mesmo defeito
        # de M9/T3.1, num diretório que a guarda não cobria.
        "corpus/run_pipeline.py",
    ):
        script = TRAIN / rel
        if not script.exists():
            continue
        r = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=TRAIN.parent,
        )
        if r.returncode != 0 and "ModuleNotFoundError" in r.stderr:
            ultima = r.stderr.strip().splitlines()[-1]
            faltante = ultima.split("'")[1] if "'" in ultima else ""
            # Só é defeito de LAYOUT quando o módulo ausente é NOSSO — aí o caminho de import
            # está errado (foi o caso do `ctc` em M9/T3.1). Dependência de terceiro ausente é
            # ambiente, não layout, e o teste não pode confundir os dois.
            nossos = set(_module_home()) | {f.stem for f in (TRAIN / SHARED).glob("*.py")}
            if faltante in nossos:
                falhas.append(f"{rel}: {ultima}")
    assert not falhas, "entrypoint não roda standalone: " + "; ".join(falhas)


def test_nao_existe_pasta_lixeira_chamada_scripts():
    """Duas pastas `scripts/` conviviam — o anti-pattern de pasta-lixeira.

    `scripts/` (raiz) e `jvscribe/scripts/` misturavam setup de ambiente, ferramentas de
    avaliação, biblioteca de corpus e utilitários. Nomes genéricos (`scripts`, `utils`,
    `helpers`, `misc`, `common` como catch-all) acumulam código sem relação porque não
    exigem decisão de onde algo pertence. Hoje cada pasta diz o que contém.
    """
    repo = TRAIN.parent
    proibidas = {"scripts", "utils", "helpers", "misc", "lib"}
    achadas = [
        str(d.relative_to(repo))
        for d in repo.rglob("*")
        if d.is_dir()
        and d.name in proibidas
        and not any(p in {".git", ".claude", "target", ".venv", "node_modules",
                          "knowledge-base", "models", "vendor"} for p in d.parts)
    ]
    assert not achadas, "pasta com nome genérico voltou: " + ", ".join(achadas)


def test_cada_pipeline_declarada_existe():
    """O `conftest.py` e a realidade não podem divergir."""
    declaradas = ("common", "corpus", "finetune", "batch", "realtime", "eval",
                  "bench", "probes", "audit")
    faltando = [d for d in declaradas if not (TRAIN / d).is_dir()]
    assert not faltando, f"pipelines declaradas no conftest mas ausentes: {faltando}"
