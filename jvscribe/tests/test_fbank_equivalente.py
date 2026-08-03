"""O fbank de produção tem de ser BIT-A-BIT o do treino — ou o modelo vê outra distribuição.

Contexto: o `lhotse` arrasta **695 MB de torch** só para extrair fbank, e não instala no ambiente
de produção. O `kaldi-native-fbank` (k2-fsa, mesmo autor do sherpa-onnx) substitui sem torch.

⚠️ **O perigo não é a biblioteca — são os DEFAULTS.** Três parâmetros do lhotse divergem do padrão
Kaldi, e o kaldi-native-fbank usa o padrão Kaldi:

| parâmetro | lhotse | Kaldi (default do knf) |
|---|---|---|
| `snip_edges` | **False** | True |
| `high_freq` | **−400,0** | 0 |
| `dither` | **0,0** | 1,0 |

E há uma quarta armadilha, de escala: o Kaldi convenciona amostras em faixa **int16**; o lhotse usa
float **[−1, 1]**. Passar int16 desloca todo o log-mel por `2·ln(32768) = 20,79` — `[MEDIDO]`.

Sem este teste, qualquer um dos quatro erros passa em silêncio: o pipeline roda, produz texto
plausível, e o WER degrada sem sintoma. É o mesmo modo de falha do vocabulário trocado.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))

knf = pytest.importorskip("kaldi_native_fbank", reason="extrator de produção não instalado")
lhotse = pytest.importorskip("lhotse", reason="extrator de referência não instalado")


def opcoes_de_producao():
    """A ÚNICA configuração que reproduz o fbank do treino. Alterar aqui muda o modelo."""
    o = knf.FbankOptions()
    o.frame_opts.samp_freq = 16000
    o.frame_opts.frame_shift_ms = 10.0
    o.frame_opts.frame_length_ms = 25.0
    o.frame_opts.dither = 0.0            # lhotse: 0,0 — Kaldi usaria 1,0
    o.frame_opts.preemph_coeff = 0.97
    o.frame_opts.remove_dc_offset = True
    o.frame_opts.window_type = "povey"
    o.frame_opts.round_to_power_of_two = True
    o.frame_opts.snip_edges = False      # lhotse: False — Kaldi usaria True
    o.mel_opts.num_bins = 80
    o.mel_opts.low_freq = 20.0
    o.mel_opts.high_freq = -400.0        # lhotse: −400 — Kaldi usaria 0
    return o


def extrair(x, sr=16000):
    f = knf.OnlineFbank(opcoes_de_producao())
    f.accept_waveform(sr, x.tolist())
    f.input_finished()
    return np.array([f.get_frame(i) for i in range(f.num_frames_ready)], dtype=np.float32)


def referencia(x, sr=16000):
    from lhotse import Fbank, FbankConfig
    return np.asarray(Fbank(FbankConfig(num_mel_bins=80)).extract(x, sr), dtype=np.float32)


@pytest.fixture
def sinal():
    return (np.random.default_rng(7).standard_normal(16000 * 2) * 0.05).astype(np.float32)


def test_mesmo_numero_de_frames(sinal):
    """`snip_edges` errado muda a contagem — e o desalinhamento é silencioso."""
    assert extrair(sinal).shape == referencia(sinal).shape


def test_features_equivalentes_dentro_da_precisao(sinal):
    """`[MEDIDO]` em áudio real: |diff| médio 3e-6, máximo 1,3e-3.

    O limite é frouxo de propósito — não se exige bit-a-bit entre duas implementações em ponto
    flutuante. Se estourar, é erro de CONFIGURAÇÃO, não de arredondamento.
    """
    d = np.abs(extrair(sinal) - referencia(sinal))
    assert d.max() < 0.01, f"divergência de {d.max():.4f} — algum parâmetro não casa"
    assert d.mean() < 1e-4


def test_a_armadilha_da_escala_int16_e_detectavel(sinal):
    """Passar amostras em faixa int16 desloca o log-mel por 2·ln(32768) ≈ 20,79.

    Guarda contra o erro mais provável de quem vem da convenção Kaldi.
    """
    deslocado = extrair(sinal * 32768.0)
    ref = referencia(sinal)
    n = min(len(deslocado), len(ref))
    assert np.median(deslocado[:n] - ref[:n]) == pytest.approx(2 * np.log(32768), abs=0.5)


@pytest.mark.parametrize("campo,errado", [("snip_edges", True), ("dither", 1.0)])
def test_default_do_kaldi_diverge_e_o_teste_pega(sinal, campo, errado):
    """Se alguém usar o default do Kaldi em vez do do lhotse, isto FALHA — que é o ponto."""
    o = opcoes_de_producao()
    setattr(o.frame_opts, campo, errado)
    f = knf.OnlineFbank(o)
    f.accept_waveform(16000, sinal.tolist())
    f.input_finished()
    K = np.array([f.get_frame(i) for i in range(f.num_frames_ready)], dtype=np.float32)
    ref = referencia(sinal)
    n = min(len(K), len(ref))
    divergiu = K.shape != ref.shape or np.abs(K[:n] - ref[:n]).max() > 0.01
    assert divergiu, f"{campo}={errado} deveria divergir do lhotse e não divergiu"
