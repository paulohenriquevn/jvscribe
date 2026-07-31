"""Uma régua de normalização, um colapso CTC — para todo o repositório.

Este projeto mede WER em seis lugares. Quando cada um normaliza do seu jeito, os números
param de ser comparáveis **sem que nada falhe**. Já aconteceu duas vezes:

1. `eval_public_hf.py` tinha `norm()` própria que preservava acento. O **16,14%** publicado
   saiu dela; os **15,99%** medidos com a canônica, no mesmo subconjunto. A diferença foi
   atribuída a ruído de amostra — não era.
2. `eval_runtime_wer.py`, `analyze_error_composition.py` e `prep_icefall.py` tinham
   `normalize_ptbr` próprio. Duas cópias eram idênticas (`880d4ed1`) e a terceira **já havia
   divergido** (`7a5d69b8`) — o modo de falha que DRY existe para evitar.

O caso mais grave era o `prep_icefall.py`: ele normaliza o **corpus de treino**. Régua
diferente ali não é número divergente, é mismatch treino/eval.
"""
import ast
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
PKG = REPO / "jvscribe"
sys.path.insert(0, str(PKG / "common"))

# Estes reimplementam de propósito e a razão está registrada:
#   blank_penalty_probe — aplica penalidade β no logit de blank ANTES do argmax; é o ponto da sonda
#   streaming.ctc_words — produz (palavras, TIMESTAMPS); o kernel não dá tempo
#   ctc.py / text.py — são o kernel
ISENTOS_CTC = {"blank_penalty_probe.py", "streaming.py", "ctc.py"}
# `text.py` É o kernel da normalização — os dois módulos viraram um em 2026-07-31.
ISENTOS_NORM = {"text.py"}


def _fontes_de_producao():
    for d in ("common", "corpus", "finetune", "batch", "realtime", "eval", "tools"):
        yield from sorted((PKG / d).glob("*.py"))


def _define(arquivo: Path, nomes: set[str]) -> list[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    return [n.name for n in ast.walk(arvore)
            if isinstance(n, ast.FunctionDef) and n.name in nomes]


def test_nenhum_modulo_define_a_propria_regua_de_normalizacao():
    """Uma régua. Sem isto, nenhum WER do repositório é comparável com outro.

    A guarda só vigiava `normalize_ptbr|norm|normalize_for_wer|normaliza` — e por isso deixou
    passar `eval/measure_callcenter.py::normalize`, que preservava acento enquanto a canônica
    remove. Um terceiro WER do projeto medido com régua diferente, publicado ao lado dos
    outros. `normalize` entrou na lista; a lição é que a guarda tem de cobrir o NOME ÓBVIO.
    """
    reincidentes = []
    for f in _fontes_de_producao():
        if f.name in ISENTOS_NORM:
            continue
        achados = _define(f, {"normalize_ptbr", "norm", "normalize", "normalize_for_wer",
                              "normaliza", "normalizar", "_norm"})
        # Compor é permitido: pré-processar o domínio e FECHAR na régua canônica. O que a
        # guarda proíbe é reimplementar — logo, quem define o nome tem de citar a canônica.
        achados = [a for a in achados
                   if "normalize_for_wer_compare" not in f.read_text(encoding="utf-8")]
        if achados:
            reincidentes.append(f"{f.parent.name}/{f.name}: {achados}")
    assert not reincidentes, (
        "régua de normalização própria em: " + "; ".join(reincidentes)
        + " — use common/text.normalize_for_wer_compare"
    )


def test_nenhum_modulo_reimplementa_o_colapso_ctc():
    """O kernel existe porque este colapso já apareceu 7× no repositório."""
    reincidentes = []
    for f in _fontes_de_producao():
        if f.name in ISENTOS_CTC:
            continue
        achados = _define(f, {"greedy_ctc", "ids_to_text", "collapse_ctc", "_greedy"})
        if achados:
            reincidentes.append(f"{f.parent.name}/{f.name}: {achados}")
    assert not reincidentes, (
        "colapso CTC reimplementado em: " + "; ".join(reincidentes) + " — use common/ctc.py"
    )


def test_as_isencoes_declaram_o_motivo_no_proprio_arquivo():
    """Isenção sem motivo escrito vira permissão permanente.

    Quem reimplementa tem de dizer no arquivo POR QUE o kernel não serve — senão a próxima
    pessoa copia o padrão achando que é aceitável.
    """
    faltando = []
    for nome in ISENTOS_CTC - {"ctc.py"}:
        alvos = list(PKG.rglob(nome))
        if not alvos:
            continue
        fonte = alvos[0].read_text(encoding="utf-8").lower()
        if "kernel" not in fonte and "common/ctc" not in fonte:
            faltando.append(nome)
    assert not faltando, (
        "isenção sem motivo declarado no arquivo: " + ", ".join(faltando)
    )


def test_a_regua_canonica_faz_mais_que_baixar_caixa():
    """Documenta o que as cópias perdiam: elas só faziam lower + strip de pontuação.

    A canônica remove acento **e** normaliza semanticamente — `R$` vira "reais", `Nº` vira
    "no". Sem isso, o mesmo enunciado conta como erro só por estar escrito diferente.
    """
    from text import normalize_for_wer_compare as canon

    assert canon("José") == "jose"
    assert "reais" in canon("R$ 10")
    assert canon("Nº 42") == "no 42"


def test_o_colapso_delegado_produz_os_mesmos_ids():
    """Equivalência comportamental do que foi delegado ao kernel.

    As duas cópias removidas (`measure_realcodec`, `tta_feature_align_probe`) faziam o mesmo
    colapso mas **detokenizavam diferente** — uma com `sp.decode()` do SentencePiece, a outra
    com `join + replace ▁`. Só o colapso foi unificado; a detokenização de cada uma foi
    preservada, porque ali a diferença é real.
    """
    import numpy as np

    import ctc

    lp = np.full((8, 6), -9.0, dtype=np.float32)
    for t, tok in enumerate([3, 3, 0, 5, 5, 5, 0, 2]):
        lp[t, tok] = 0.0

    # colapso de referência, escrito à mão como as cópias faziam
    ids, prev = [], -1
    for t in lp.argmax(-1):
        if t != prev and t != 0:
            ids.append(int(t))
        prev = t

    assert ctc.greedy_ids(lp, len(lp)) == ids


# ── Qual régua, para qual propósito ──────────────────────────────────────────────────────
#
# As duas semânticas existem de propósito, mas NÃO são intercambiáveis por módulo:
#
#   normalize_train_target      PRESERVA acento — alvo de TREINO (o modelo tem de acentuar)
#   normalize_for_wer_compare   REMOVE   acento — régua de COMPARAÇÃO de WER
#
# Escolher pelo módulo errado não levanta erro: produz um WER inflado e plausível. Medido
# nesta revisão: numa frase em que só o acento difere, a régua de treino dá 62,5% de WER
# onde a canônica dá 0%. Foi assim que o WER de runtime (29,92%) saiu incomparável com os
# demais — e a correção anterior ("preservar acento em prep_icefall é deliberado") foi
# **super-aplicada** a dois módulos que medem WER, em vez de preparar corpus.
SINAIS_DE_MEDICAO = ("word_edit_distance", "jiwer", "paired_bootstrap", "wer(")

# Único propósito legítimo da régua de treino: preparar o corpus que vai para o treino.
PREPARA_CORPUS = {"prep_icefall.py"}


def _importa_regua_de_treino(arquivo: Path) -> bool:
    """Detecta o IMPORT por AST, não por substring.

    A primeira versão desta guarda casava a string no arquivo inteiro e acusava dois
    inocentes: `common/text.py`, que **define** as duas réguas, e um módulo onde o nome
    aparecia só num comentário explicando a distinção. Substring não distingue uso de
    menção — é o mesmo erro de "verificar o texto em vez da estrutura" que esta revisão
    já cometeu quatro vezes em outras guardas.
    """
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    return any(
        isinstance(n, ast.ImportFrom)
        and any(a.name == "normalize_train_target" for a in n.names)
        for n in ast.walk(arvore)
    )


def test_quem_mede_wer_nao_pode_usar_a_regua_de_treino():
    """A régua de treino conta acento como erro — num medidor de WER isso infla o número."""
    culpados = []
    for f in _fontes_de_producao():
        if f.name in ISENTOS_NORM or f.name in PREPARA_CORPUS:
            continue
        if not _importa_regua_de_treino(f):
            continue
        if any(s in f.read_text(encoding="utf-8") for s in SINAIS_DE_MEDICAO):
            culpados.append(f"{f.parent.name}/{f.name}")
    assert not culpados, (
        "importa normalize_train_target (preserva acento) e MEDE WER: " + "; ".join(culpados)
        + " — use normalize_for_wer_compare; a de treino é só para preparar corpus"
    )


def test_a_regua_de_treino_so_e_usada_por_quem_prepara_corpus():
    """Inverso do teste acima: fecha a porta para um novo módulo adotá-la por engano."""
    usam = {f.name for f in _fontes_de_producao()
            if f.name not in ISENTOS_NORM and _importa_regua_de_treino(f)}
    inesperados = usam - PREPARA_CORPUS
    assert not inesperados, (
        "normalize_train_target fora da preparação de corpus: " + ", ".join(sorted(inesperados))
        + " — se for legítimo, adicione a PREPARA_CORPUS com a justificativa"
    )


def test_as_duas_reguas_divergem_de_fato_em_acento():
    """Ancora a diferença que torna a escolha material — se sumir, os testes acima viram teatro."""
    from text import normalize_for_wer_compare, normalize_train_target

    assert normalize_train_target("coração") == "coração"
    assert normalize_for_wer_compare("coração") == "coracao"
