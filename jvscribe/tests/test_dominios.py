"""As invariantes de DESENHO do pacote — o que a reorganização de 2026-07-31 comprou.

Reorganizar é barato; **manter** reorganizado não é. Sem estas guardas, a próxima pessoa
recria a fragmentação sem que nada falhe — foi exatamente assim que o repositório chegou a
sete pipelines para quinze domínios, com duas pastas-lixeira.

Cada teste aqui corresponde a um defeito que existiu e foi medido:

| invariante | o defeito que ela impede |
|---|---|
| cross-pipeline só de `common/` | 5 violações, todas por domínio na pasta errada |
| um símbolo, um caminho de import | a régua de WER errada sobreviveu por ter dois caminhos |
| toda pipeline declara seu domínio | `tools/` acumulou 7 domínios sem ninguém notar |
| nenhuma constante de domínio duplicada | `SR = 16000` estava em 7 arquivos |
"""
from __future__ import annotations

import ast
import collections
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]

# As nove pipelines. `common/` é o shared kernel — o ÚNICO destino legal de import
# cross-pipeline; as outras oito são domínios de aplicação.
KERNEL = "common"
PIPELINES = ("corpus", "finetune", "batch", "realtime", "eval", "bench", "probes", "audit")
TODAS = (KERNEL,) + PIPELINES


def _mapa_modulo_para_pipeline() -> dict[str, str]:
    return {
        f.stem: d
        for d in TODAS
        for f in (PKG / d).rglob("*.py")
        if f.stem != "__init__" and "__pycache__" not in f.parts
    }


def _imports(arquivo: Path) -> list[tuple[int, str, list[str]]]:
    """[(linha, módulo, nomes)] de cada import — por AST, não por texto."""
    try:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    out = []
    for n in ast.walk(arvore):
        if isinstance(n, ast.ImportFrom) and n.module:
            # Import RELATIVO (`from .channel import`) é interno ao pacote — não é um segundo
            # caminho para consumidor externo. Contá-lo acusava o subpacote `audio/` de
            # ambiguidade consigo mesmo.
            if n.level:
                continue
            out.append((n.lineno, n.module.split(".")[0], [a.name for a in n.names]))
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.append((n.lineno, a.name.split(".")[0], []))
    return out


def test_import_cross_pipeline_so_a_partir_do_kernel():
    """Uma pipeline não alcança outra — só o kernel.

    Era violada 5× em 2026-07-31, e as cinco tinham a MESMA causa: um domínio na pasta
    errada. O canal telefônico morava em `corpus/` e era consumido por três pipelines; virou
    `common/audio/` e as violações sumiram por construção, não por exceção na guarda.
    """
    onde = _mapa_modulo_para_pipeline()
    violacoes = []
    for pipe in TODAS:
        for f in sorted((PKG / pipe).rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            for linha, mod, _ in _imports(f):
                destino = onde.get(mod)
                if destino and destino != pipe and destino != KERNEL:
                    violacoes.append(f"{pipe}/{f.name}:{linha} importa `{mod}` (vive em {destino}/)")
    assert not violacoes, (
        "import cross-pipeline fora do kernel — o módulo está na pasta errada, ou o import "
        "deveria passar por common/:\n  " + "\n  ".join(violacoes)
    )


def test_um_simbolo_do_kernel_tem_um_caminho_de_import():
    """O MESMO objeto não pode ser alcançável por dois módulos.

    `normalize_for_wer_compare` era importável de `text` e de `text_normalize_ptbr` — 12
    arquivos por um caminho, 5 pelo outro. Foi essa ambiguidade que permitiu ao defeito de
    régua sobreviver: dois medidores usavam réguas diferentes e ninguém enxergou.

    Só vale para símbolos do KERNEL. Homônimos entre pipelines (três funções `greedy`, uma por
    pipeline) são coisas diferentes com o mesmo nome — os testes as comparam de propósito.
    """
    do_kernel = {
        f.stem for f in (PKG / KERNEL).rglob("*.py")
        if f.stem != "__init__" and "__pycache__" not in f.parts
    }
    # subpacotes do kernel (`audio/`) entram pelo nome do pacote, não pelo `__init__`
    do_kernel |= {d.name for d in (PKG / KERNEL).iterdir() if (d / "__init__.py").exists()}
    caminhos: dict[str, set[str]] = collections.defaultdict(set)
    for f in sorted(PKG.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        for _, mod, nomes in _imports(f):
            if mod in do_kernel:
                for nome in nomes:
                    caminhos[nome].add(mod)
    ambiguos = {n: sorted(m) for n, m in caminhos.items() if len(m) > 1}
    assert not ambiguos, (
        "símbolo do kernel alcançável por mais de um módulo — funde os módulos ou escolhe um "
        f"caminho: {ambiguos}"
    )


def test_toda_pipeline_declara_o_dominio_que_a_une():
    """`__init__.py` com a frase que justifica a pasta existir.

    Se não dá para escrever "o que une estes arquivos é X", a pasta é uma lixeira. `tools/`
    não tinha essa frase e acumulou sete domínios — probes, benchmarks, auditorias, o núcleo
    de WER e um extrator de fixture, unidos só por "não coube em outro lugar".
    """
    faltando = []
    for pipe in TODAS:
        init = PKG / pipe / "__init__.py"
        if not init.exists():
            faltando.append(f"{pipe}/ sem __init__.py")
            continue
        doc = ast.get_docstring(ast.parse(init.read_text(encoding="utf-8")))
        if not doc or len(doc.strip()) < 80:
            faltando.append(f"{pipe}/__init__.py sem docstring que declare o domínio")
    assert not faltando, "pipeline sem domínio declarado:\n  " + "\n  ".join(faltando)


def test_nenhuma_constante_de_dominio_duplicada():
    """`SR = 16000` estava declarado em SETE arquivos.

    Constante de domínio replicada é duplicação de CONHECIMENTO — a mesma classe das duas
    réguas de texto e dos sete colapsos CTC. Trocar a taxa exige retreinar, então a
    divergência entre cópias seria silenciosa e cara.
    """
    VIGIADAS = ("SR", "BLANK", "TELEPHONE_SR")
    onde: dict[str, list[str]] = collections.defaultdict(list)
    for pipe in TODAS:
        for f in sorted((PKG / pipe).rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            try:
                arvore = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for n in arvore.body:                       # só topo de módulo
                if (isinstance(n, ast.Assign) and len(n.targets) == 1
                        and isinstance(n.targets[0], ast.Name)
                        and n.targets[0].id in VIGIADAS
                        and isinstance(n.value, ast.Constant)):
                    onde[n.targets[0].id].append(f"{pipe}/{f.name}")
    duplicadas = {k: v for k, v in onde.items() if len(v) > 1}
    assert not duplicadas, (
        "constante de domínio declarada em mais de um lugar — mova para o kernel e importe: "
        f"{duplicadas}"
    )


def test_a_sequencia_de_carga_do_motor_nao_e_remontada_a_mao():
    """Um entrypoint não reimplementa "resolver → validar → sessão → vocabulário".

    Estava replicada em **treze** entrypoints, e a consequência não foi estética: o passo de
    VALIDAÇÃO existia em apenas quatro deles. Os outros nove carregavam um par (modelo,
    vocabulário) sem conferir se combinam — o defeito que a validação existe para impedir,
    sobrevivendo porque a sequência estava fragmentada.

    A contagem de `def main()` foi o que revelou isso: 37 entrypoints, e `--model`/`--tokens`
    declarados à mão em 8 deles.
    """
    reincidentes = []
    for f in sorted(PKG.rglob("*.py")):
        if "__pycache__" in f.parts or f.parent.name == "tests":
            continue
        fonte = f.read_text(encoding="utf-8", errors="replace")
        if '__name__ == "__main__"' not in fonte:
            continue
        if not ("criar_sessao" in fonte or "InferenceSession" in fonte):
            continue
        usa_kernel = any(s in fonte for s in ("from engine import", "Motor.carregar", "resolver("))
        if not usa_kernel:
            reincidentes.append(str(f.relative_to(PKG)))
    assert not reincidentes, (
        "entrypoint monta a sequência de carga à mão — use `engine.Motor.carregar` (sequência "
        "completa) ou `engine.resolver` (quando a sessão é a variável sob teste):\n  "
        + "\n  ".join(reincidentes)
    )


def test_um_so_parser_de_tokens_txt():
    """Havia SEIS implementações do mesmo parser de `tokens.txt`.

    `load_tokens` × 3, `carregar_tokens` × 2, `load_id2tok` × 1 — todas equivalentes
    `[MEDIDO]`, o que é justamente o perigo: equivalentes hoje, e nada garante amanhã. Só a do
    kernel recusa vocabulário vazio, e um vocabulário vazio decodifica para string vazia sem
    erro nenhum.
    """
    NOMES = {"load_tokens", "carregar_tokens", "load_id2tok"}
    definem = []
    for f in sorted(PKG.rglob("*.py")):
        if "__pycache__" in f.parts or f.parent.name == "tests":
            continue
        if f.name == "engine.py":
            continue          # o kernel É a implementação
        try:
            arvore = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for n in arvore.body:
            if isinstance(n, ast.FunctionDef) and n.name in NOMES:
                definem.append(f"{f.relative_to(PKG)}:{n.lineno} {n.name}")
    assert not definem, (
        "parser de tokens.txt reimplementado — use `engine.carregar_tokens`:\n  "
        + "\n  ".join(definem)
    )
