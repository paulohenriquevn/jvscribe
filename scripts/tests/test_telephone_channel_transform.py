"""Teste de contrato do adapter on-the-fly `telephone_channel_transform.py` (M5 —
Task 2.1, blueprint `m5-scale-model-wer-blueprint.md` Q6, ADR D2).

Offline, sem GPU: usa `lhotse` real (instalado no ambiente de dev) com cuts
sintéticos (seno gravado em `tmp_path`) — sem baixar corpus nem treinar nada.
Replica os invariantes de `test/cut/test_cut_augmentation.py` do lhotse (Q6):
determinismo, preservação de duração, ausência de NaN/Inf, e a composição
física `Reverb -> CutMix(ruído) -> telephone` com telephone por ÚLTIMO.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "corpus"))

pytest.importorskip("lhotse", reason="lhotse não instalado")
pytest.importorskip("soundfile", reason="soundfile não instalado")

import soundfile as sf  # noqa: E402
from lhotse import CutSet, MonoCut, Recording, SupervisionSegment  # noqa: E402
from lhotse.audio import RecordingSet  # noqa: E402
from lhotse.cut.mixed import MixedCut  # noqa: E402
from lhotse.dataset.cut_transforms import CutMix, ReverbWithImpulseResponse  # noqa: E402

import telephone_channel  # noqa: E402 -- import FLAT (nao `corpus.telephone_channel`):
import telephone_channel_transform as tct  # noqa: E402
# `telephone_channel_transform.py` importa `telephone_channel` FLAT internamente
# (mesma convencao de `make_telephone_test.py` -- ver docstring do modulo); import
# via `corpus.telephone_channel` carregaria um 2o objeto de modulo (mesmo arquivo,
# nome qualificado diferente) e quebraria o teste de identidade `is` abaixo.

SR = 16000


def _sine_cut(tmp_path, cid: str, freq: float = 440.0, dur: float = 1.0, text: str = "ola") -> MonoCut:
    t = np.arange(int(SR * dur)) / SR
    x = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    wav = tmp_path / f"{cid}.wav"
    sf.write(str(wav), x, SR)
    rec = Recording.from_file(str(wav), recording_id=cid)
    return MonoCut(
        id=cid,
        start=0.0,
        duration=rec.duration,
        channel=0,
        recording=rec,
        supervisions=[
            SupervisionSegment(
                id=f"{cid}-sup", recording_id=cid, start=0.0, duration=rec.duration, text=text
            )
        ],
    )


def _rir_recording(tmp_path) -> Recording:
    """Impulso de sala sintético: pico direto + cauda exponencial curta."""
    rng = np.random.RandomState(1)
    rir = np.zeros(1600, dtype=np.float32)
    rir[0] = 1.0
    rir[1:400] = (0.3 * rng.randn(399) * np.exp(-np.arange(399) / 80)).astype(np.float32)
    wav = tmp_path / "rir.wav"
    sf.write(str(wav), rir, SR)
    return Recording.from_file(str(wav), recording_id="rir1")


# ── Reuso do DSP do M3 (não duplicado) ───────────────────────────────────────


def test_reusa_apply_telephone_channel_do_m3_sem_duplicar():
    assert tct.apply_telephone_channel is telephone_channel.apply_telephone_channel


# ── Invariantes de Q6 sobre um cut mono simples ──────────────────────────────


def test_duracao_preservada(tmp_path):
    cut = _sine_cut(tmp_path, "c1")
    out = list(tct.TelephoneChannelTransform(p=1.0)(CutSet.from_cuts([cut])))[0]
    assert out.duration == cut.duration
    assert out.num_samples == cut.num_samples


def test_sem_nan_ou_inf(tmp_path):
    cut = _sine_cut(tmp_path, "c1")
    out = list(tct.TelephoneChannelTransform(p=1.0)(CutSet.from_cuts([cut])))[0]
    audio = out.load_audio()
    assert np.all(np.isfinite(audio))


def test_shape_consistente_com_num_samples(tmp_path):
    cut = _sine_cut(tmp_path, "c1")
    out = list(tct.TelephoneChannelTransform(p=1.0)(CutSet.from_cuts([cut])))[0]
    audio = out.load_audio()
    assert audio.shape == (1, out.num_samples)


def test_texto_da_supervision_intacto(tmp_path):
    cut = _sine_cut(tmp_path, "c1", text="ola mundo")
    out = list(tct.TelephoneChannelTransform(p=1.0)(CutSet.from_cuts([cut])))[0]
    assert out.supervisions[0].text == "ola mundo"


def test_determinismo_com_seed_42(tmp_path):
    cut = _sine_cut(tmp_path, "c1")
    out1 = list(tct.TelephoneChannelTransform(p=1.0, seed=42)(CutSet.from_cuts([cut])))[0]
    out2 = list(tct.TelephoneChannelTransform(p=1.0, seed=42)(CutSet.from_cuts([cut])))[0]
    assert np.allclose(out1.load_audio(), out2.load_audio())


def test_p_zero_nao_degrada(tmp_path):
    cut = _sine_cut(tmp_path, "c1")
    out = list(tct.TelephoneChannelTransform(p=0.0)(CutSet.from_cuts([cut])))[0]
    assert out.id == cut.id
    assert np.allclose(out.load_audio(), cut.load_audio())


# ── Composição física D2: Reverb -> CutMix(ruído) -> telephone (por último) ──


def test_ordem_composta_telephone_e_o_ultimo_transform(tmp_path):
    """Replica a cadeia real do datamodule (ADR D2): telephone entra DEPOIS do
    CutMix, então o cut que chega até ele já é um MixedCut -- e o
    TelephoneChannel precisa ser o ÚLTIMO transform aplicado (executa por
    último em MixedCut.load_audio())."""
    src = _sine_cut(tmp_path, "src1")
    noise = _sine_cut(tmp_path, "noise1", freq=120.0, text="")
    rir = _rir_recording(tmp_path)

    cuts = CutSet.from_cuts([src])
    noise_cuts = CutSet.from_cuts([noise])
    rirs = RecordingSet.from_recordings([rir])

    reverb = ReverbWithImpulseResponse(rir_recordings=rirs, p=1.0)
    cutmix = CutMix(cuts=noise_cuts, p=1.0, snr=(10, 20), seed=42)
    telephone = tct.TelephoneChannelTransform(p=1.0, seed=42)

    composed = telephone(cutmix(reverb(cuts)))
    final = list(composed)[0]

    assert isinstance(final, MixedCut), "CutMix com p=1.0 deveria produzir um MixedCut"
    assert isinstance(final.transforms[-1], tct.TelephoneChannel), (
        "telephone precisa ser o ULTIMO transform (D2 -- canal e o estagio final)"
    )
    assert final.duration == src.duration
    audio = final.load_audio()
    assert np.all(np.isfinite(audio))


def test_composicao_e_deterministica(tmp_path):
    src = _sine_cut(tmp_path, "src1")
    noise = _sine_cut(tmp_path, "noise1", freq=120.0, text="")
    rir = _rir_recording(tmp_path)
    rirs = RecordingSet.from_recordings([rir])
    noise_cuts = CutSet.from_cuts([noise])

    def run():
        cuts = CutSet.from_cuts([_sine_cut(tmp_path, "src1")])
        reverb = ReverbWithImpulseResponse(rir_recordings=rirs, p=1.0)
        cutmix = CutMix(cuts=noise_cuts, p=1.0, snr=(10, 20), seed=42)
        telephone = tct.TelephoneChannelTransform(p=1.0, seed=42)
        out = telephone(cutmix(reverb(cuts)))
        return list(out)[0].load_audio()

    assert np.allclose(run(), run())


# ── Negativo: cut sem Recording e sem ser MixedCut -> fail-fast ─────────────


def test_falha_alto_sem_recording_nem_mixed():
    bare = MonoCut(id="bare", start=0.0, duration=1.0, channel=0, recording=None, supervisions=[])
    with pytest.raises(TypeError, match="nao tem Recording nem e MixedCut"):
        list(tct.TelephoneChannelTransform(p=1.0)(CutSet.from_cuts([bare])))
