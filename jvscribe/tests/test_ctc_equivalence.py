"""T3.1 (M9) — mede a equivalência das implementações de colapso CTC ANTES de consolidar.

Risco R2 do plano: consolidar as cópias pode mudar sutilmente o resultado de alguma pipeline
e invalidar um número já publicado no CHANGELOG ou no paper. A ordem teste-primeiro é o que
transforma esse risco em evidência: se divergirem, sabemos QUAL e EM QUE ENTRADA antes de
mudar qualquer coisa.

Inventário medido em 2026-07-30 — 5 implementações Python + 1 Rust. Todas as cópias Python
foram desde então delegadas ao kernel (`common/ctc.py`); a Rust saiu do repositório junto com
o runtime, em 2026-07-30. O inventário fica registrado porque é a evidência de POR QUE o
kernel existe — 6 colapsos CTC independentes que ninguém sabia que divergiam.

  jvscribe/batch/batch_transcribe.py        greedy(log_probs_row, valid_len, id2tok) -> str
  jvscribe/batch/decode_onnx_local.py       greedy_ctc(log_probs, lens)              -> ids
  jvscribe/eval/measure_callcenter.py       greedy(lp, id2tok)                       -> str
  jvscribe/eval/measure_realcodec.py        greedy(logp, lens, sp)                   -> str (sp.decode)
  jvscribe/tools/tta_feature_align_probe.py greedy(logp, id2tok)                     -> str
  (removida) crate Rust do runtime          ctc_greedy(...)                          -> ids
"""
import numpy as np
import pytest

# `lhotse` puxa a stack de treino e não está no requirements-test.txt (deliberado:
# é pesada e o CI model-free não precisa dela). SKIP visível > erro de coleta.
pytest.importorskip("lhotse")

BLANK = 0


def _fixture_logits(seed: int = 42, t: int = 60, v: int = 12) -> np.ndarray:
    """Matriz (T,V) determinística — sem RNG livre, o teste tem de ser reprodutível."""
    rng = np.random.default_rng(seed)
    return rng.normal(size=(t, v)).astype(np.float32)


def _collapse_reference(ids) -> list[int]:
    """A regra canônica: remove blank e colapsa repetição adjacente."""
    out, prev = [], -1
    for i in ids:
        i = int(i)
        if i != prev and i != BLANK:
            out.append(i)
        prev = i
    return out


def test_o_colapso_do_kernel_concorda_com_a_referencia():
    """O núcleo compartilhado: a sequência de ids colapsada tem de bater com a referência.

    Esta guarda comparava o kernel contra a cópia de `decode_onnx_local.greedy_ctc`. A cópia
    foi **removida** (o kernel existe justamente porque este colapso já apareceu 7× no
    repositório), então a comparação passou a ser contra a implementação de referência do
    próprio teste — e o teste seguinte garante que a cópia não volte.
    """
    import ctc

    logits = _fixture_logits()
    esperado = _collapse_reference(logits.argmax(-1))
    obtido = ctc.greedy_ids(logits, logits.shape[0])
    assert obtido == esperado, (
        f"ctc.greedy_ids divergiu do colapso de referência\n"
        f"  esperado[:10]={esperado[:10]}\n  obtido[:10]={obtido[:10]}"
    )


def test_nenhum_entrypoint_reimplementa_o_colapso_ctc():
    """A guarda que substitui a comparação: a cópia não pode voltar.

    Comparar cópias prova que concordam HOJE. Proibir a cópia elimina a divergência de vez.
    """
    import pathlib as _p

    raiz = _p.Path(__file__).resolve().parents[1]
    reincidentes = []
    for f in list((raiz / "batch").glob("*.py")) + list((raiz / "realtime").glob("*.py")):
        fonte = f.read_text(encoding="utf-8")
        if "def greedy_ctc" in fonte or "def ids_to_text" in fonte:
            reincidentes.append(f.name)
    assert not reincidentes, (
        "colapso CTC reimplementado em: " + ", ".join(reincidentes) + " — use common/ctc.py"
    )


def test_detokenizacao_join_replace_e_consistente_entre_as_copias():
    """As cópias que usam `join + replace('▁',' ')` têm de produzir texto idêntico."""
    logits = _fixture_logits()
    id2tok = {i: f"▁t{i}" if i % 3 == 0 else f"x{i}" for i in range(12)}

    from batch_transcribe import greedy as greedy_batch
    from measure_callcenter import greedy as greedy_cc

    a = greedy_batch(logits, logits.shape[0], id2tok)
    b = greedy_cc(logits[None], id2tok)
    assert a == b, f"divergência de detokenização:\n  batch      = {a!r}\n  callcenter = {b!r}"


def test_divergencia_conhecida_de_detokenizacao_esta_documentada():
    """`measure_realcodec.py` detokeniza com `sp.decode`, não com `join + replace`.

    Isso NÃO é bug — é uma escolha diferente, e produz resultado diferente em byte-fallback.
    O teste existe para que a consolidação de T3.1 seja uma decisão consciente sobre QUAL
    convenção adotar, e não uma unificação cega que muda um número publicado.
    """
    src = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "eval"
        / "measure_realcodec.py"
    ).read_text(encoding="utf-8")
    # Verifica a INTENÇÃO (a detokenização continua sendo do SentencePiece), não o nome da
    # variável: o colapso foi delegado ao kernel e `toks` deixou de existir, sem que a
    # convenção de detokenização mudasse. Um check por literal transformaria uma refatoração
    # correta em falha — foi o que aconteceu quatro vezes nesta revisão.
    assert "sp.decode(" in src, (
        "a divergência documentada sumiu — reavalie antes de consolidar a detokenização"
    )
    assert 'replace("▁", " ")' not in src, (
        "adotou a convenção `join + replace` do kernel; isso muda um número publicado"
    )
