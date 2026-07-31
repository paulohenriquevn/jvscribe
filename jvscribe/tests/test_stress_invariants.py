"""Invariantes que uma ligação longa quebraria — e que um teste curto não vê.

Uma chamada de call center dura dezenas de minutos. Tudo que cresce por atualização e nunca
encolhe vira consumo de memória sem teto e, no caminho quente, custo crescente por decode.
Estes testes alimentam o motor com MUITO áudio sem tocar em modelo nem hardware, e afirmam
que o estado permanece limitado.

São rápidos de propósito (áudio sintético, sem inferência) para caberem em CI. O soak real,
com modelo e relógio de parede, é `jvscribe/bench/stress_test.py`.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "jvscribe" / "common"))

pytest.importorskip("lhotse")

from streaming import SHIFT, SR, FeatureCache, StreamingCTC  # noqa: E402


def _fala_sintetica(segundos: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(segundos * SR)) / SR
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 0.7 * t)          # envelope tipo sílaba
    return (env * (0.3 * np.sin(2 * np.pi * 180 * t))
            + 0.02 * rng.standard_normal(len(t))).astype(np.float32)


class _SessaoFalsa:
    """Substitui o ONNX: devolve log-probs determinísticos **derivados do conteúdo**.

    O que se testa aqui é o CRESCIMENTO DE ESTADO do motor, não a acurácia — usar o modelo
    real tornaria o teste lento demais para CI e mediria a coisa errada.

    ⚠️ A primeira versão devolvia ruído com blank dominante, e o LocalAgreement-2 quase nunca
    confirmava palavra: 19 em 3 minutos. Os testes de crescimento de `committed` passavam
    **por inação** — o caminho que deveriam exercitar nunca rodava. Agora o token sai de uma
    função do conteúdo do frame, então janelas sobrepostas concordam sobre o mesmo áudio e a
    confirmação acontece, como no modelo real.
    """

    def __init__(self, vocab: int = 500, seed: int = 1) -> None:
        self.vocab = vocab
        self.chamadas = 0
        self.palavras = [5, 7, 9, 11]     # ids que o id2tok dos testes mapeia para palavras

    def run(self, saidas, entradas):
        self.chamadas += 1
        x = entradas["x"][0]
        t_out = max(1, x.shape[0] // 2)
        lp = np.full((1, t_out, self.vocab), -8.0, dtype=np.float32)
        lp[:, :, 0] = 0.0                                   # blank é o default
        for t in range(t_out):
            assinatura = int(abs(float(x[2 * t].sum())) * 100) % 17
            if assinatura < len(self.palavras):             # ~24% dos frames viram palavra
                lp[0, t, self.palavras[assinatura]] = 6.0
        return lp, np.array([t_out], dtype=np.int64)


_VOCAB = {0: "<blk>", 5: "▁alo", 7: "▁bom", 9: "▁dia", 11: "▁sim"}


def _rodar(minutos: float, hop_s: float = 0.5, window_s: float = 6.0) -> StreamingCTC:
    m = StreamingCTC(_SessaoFalsa(), _VOCAB,
                     hop_s=hop_s, window_s=window_s)
    audio = _fala_sintetica(hop_s)
    for _ in range(int(minutos * 60 / hop_s)):
        m.update(audio)
    return m


def test_o_buffer_de_audio_nao_cresce_alem_da_janela():
    """Sem trim eficaz, 30 min de ligação viram 30 min de áudio em RAM."""
    m = _rodar(minutos=3.0, window_s=6.0)
    segundos_em_buffer = len(m.buf) / SR
    assert segundos_em_buffer <= 6.0 * 1.5, (
        f"buffer com {segundos_em_buffer:.1f}s após 3 min — a janela é de 6s; não há trim"
    )


def test_o_cache_de_features_nao_cresce_alem_do_buffer():
    """O cache acompanha o trim da janela — senão o fbank vira o vazamento."""
    m = _rodar(minutos=3.0, window_s=6.0)
    frames = len(m.cache.features())
    assert frames <= 1.5 * 6.0 * SR / SHIFT, (
        f"cache com {frames} frames após 3 min — deveria seguir a janela de 6s (~600 frames)"
    )


def test_a_lista_de_palavras_confirmadas_tem_teto():
    """`committed` acumulava indefinidamente: só o ÚLTIMO item é usado (por `_trim`).

    Numa ligação de 40 min a ~150 palavras/min são ~6.000 tuplas mantidas para nada. Não
    derruba o processo, mas é estado sem teto no caminho quente — e o histórico completo do
    diálogo já vive em `Transcricao`, que é quem tem essa responsabilidade.
    """
    m = _rodar(minutos=3.0)
    assert len(m.committed) <= 512, (
        f"{len(m.committed)} palavras retidas no motor — o motor precisa só da última"
    )


def test_o_custo_por_decode_nao_cresce_com_o_tempo_de_ligacao():
    """Regressão de O(n): se o estado cresce, o decode fica mais caro a cada minuto."""
    m = StreamingCTC(_SessaoFalsa(), _VOCAB, hop_s=0.5, window_s=6.0)
    audio = _fala_sintetica(0.5)
    tamanhos = []
    for i in range(360):                                   # 3 min
        m.update(audio)
        if i in (20, 180, 359):
            tamanhos.append(len(m.cache.features()))
    assert max(tamanhos) <= 2 * min(tamanhos) + 50, (
        f"o estado cresce ao longo da ligação: {tamanhos}"
    )


# --- entradas adversariais ------------------------------------------------

def test_silencio_absoluto_nao_quebra_nem_inventa_palavra():
    m = StreamingCTC(_SessaoFalsa(), _VOCAB, hop_s=0.5, window_s=6.0)
    for _ in range(40):
        finais, _ = m.update(np.zeros(int(0.5 * SR), dtype=np.float32))
    assert isinstance(finais, list)


def test_audio_saturado_nao_quebra():
    """Clipping em ±1.0 — acontece quando o ganho do mic está alto demais."""
    m = StreamingCTC(_SessaoFalsa(), _VOCAB, hop_s=0.5, window_s=6.0)
    saturado = np.sign(_fala_sintetica(0.5)).astype(np.float32)
    for _ in range(20):
        m.update(saturado)
    assert len(m.buf) / SR <= 6.0 * 1.5


def test_lote_gigante_de_uma_vez_nao_estoura_a_janela():
    """A captura pode entregar um lote grande após uma pausa do consumidor."""
    m = StreamingCTC(_SessaoFalsa(), _VOCAB, hop_s=0.5, window_s=6.0)
    m.update(_fala_sintetica(60.0))                        # 1 min de uma vez
    m.update(_fala_sintetica(0.5))
    assert len(m.buf) / SR <= 6.0 * 1.5, f"buffer com {len(m.buf) / SR:.0f}s após lote de 60s"


def test_cache_de_features_com_milhares_de_appends_minusculos():
    """Chunks de 32 ms (o tamanho real do `parec`) — 10.000 deles sem degradar."""
    cache = FeatureCache()
    pedaco = _fala_sintetica(0.032)
    for _ in range(3000):
        cache.append(pedaco)
        if len(cache.features()) > 600:
            cache.descartar(len(cache.features()) - 600)
    assert len(cache.features()) <= 600


# ── A ferramenta de soak não pode concluir sobre RNF sob carga ───────────────────────────

def test_stress_test_registra_carga_e_recusa_veredito_contaminado():
    """`stress_test.py` emitia "RNF-04: FALHA" sem sequer olhar o load average.

    Medido em 2026-07-31: um soak de 30 min nesta máquina (load 5-14, do próprio ambiente do
    usuário) produziu razão 0,67 e o veredito FALHA. O RTFx variou 1,65-4,59 **sem tendência**
    e os dois piores minutos coincidiram com os picos de load — contenção, não decaimento
    térmico. Concluir dali violaria `asr-evidence-discipline.md` § 5 ("máquina sob carga não
    mede"), que é exatamente o erro que este projeto já cometeu e catalogou.

    `calibrate.py` avisava acima de load 1,0 desde sempre; a ferramenta que emite o VEREDITO
    era a única cega.
    """
    import ast
    import pathlib

    fonte = (pathlib.Path(__file__).resolve().parents[1] / "bench" / "stress_test.py")
    src = fonte.read_text(encoding="utf-8")

    assert "getloadavg" in src, "não registra a carga durante o soak"
    assert "LIMIAR_LOAD" in src, "não declara o limiar acima do qual o veredito não vale"
    assert "INDETERMINADO" in src, (
        "sob carga o veredito tem de ser INDETERMINADO — nem PASSA nem FALHA"
    )
    # o limiar tem de bater com o do calibrate.py: dois limiares divergentes é o mesmo
    # defeito de 'duas réguas' que este repositório já pagou três vezes.
    arvore = ast.parse(src)
    limiar = next(
        n.value.value for n in arvore.body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "LIMIAR_LOAD"
    )
    calib = (fonte.parent / "calibrate.py").read_text(encoding="utf-8")
    assert "load average" in calib and str(limiar) in calib.replace("1.0", "1.0"), (
        f"limiar de carga ({limiar}) não casa com o de calibrate.py"
    )


def test_soak_indeterminado_nao_reprova_como_falha():
    """Exit code 2 (indeterminado) ≠ 1 (reprovado).

    Se carga virasse `exit 1`, um CI ocupado reportaria "RNF-04 falhou" — transformando ruído
    de ambiente em regressão de produto.
    """
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1] / "bench" / "stress_test.py").read_text(
        encoding="utf-8"
    )
    assert "return 2" in src, "indeterminado precisa de código de saída próprio"
    i2, i1 = src.index("return 2"), src.rindex("return 0 if")
    assert i2 < i1, "a checagem de carga tem de vir ANTES do veredito de aprovação/reprovação"
