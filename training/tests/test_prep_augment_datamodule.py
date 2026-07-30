"""Contrato do patch `prep_augment_datamodule.py` (M5 — Task 2.1). Protege as
garantias do patch reprodutível: injeta as 5 peças (import Reverb, import do
adapter telefônico, as 2 flags novas, o bloco Reverb, o bloco telephone), o
resultado COMPILA, respeita a ORDEM física da ADR D2 (Reverb -> musan ->
telephone -> input_transforms), é idempotente e falha-alto quando um anchor
não bate 1×.

Não testa o comportamento em runtime do datamodule (isso precisa de icefall +
manifests reais na instância) — testa o MECANISMO de patch offline, mesmo
idioma de `test_prep_finetune.py`. O comportamento do adapter em si (a peça
DSP nova) é testado em `scripts/tests/test_telephone_channel_transform.py`
com `lhotse` real.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prep_augment_datamodule  # noqa: E402


# asr_datamodule.py mínimo com os 5 anchors que o patch procura (subconjunto
# fiel do arquivo real, validado à parte contra
# knowledge-base/references/icefall/.../commonvoice/ASR/zipformer/asr_datamodule.py).
FIXTURE_DATAMODULE_PY = '''\
from lhotse.dataset import (  # noqa F401 for PrecomputedFeatures
    CutConcatenate,
    CutMix,
    DynamicBucketingSampler,
    K2SpeechRecognitionDataset,
    PrecomputedFeatures,
    SimpleCutSampler,
    SpecAugment,
)

from icefall.utils import str2bool


class CommonVoiceAsrDataModule:
    @classmethod
    def add_arguments(cls, parser):
        group = parser.add_argument_group(title="ASR data related options")

        group.add_argument(
            "--enable-musan",
            type=str2bool,
            default=True,
            help="When enabled, select noise from MUSAN and mix it"
            "with training dataset. ",
        )

        group.add_argument(
            "--input-strategy",
            type=str,
            default="PrecomputedFeatures",
            help="AudioSamples or PrecomputedFeatures",
        )

    def train_dataloaders(self, cuts_train, sampler_state_dict=None):
        transforms = []
        if self.args.enable_musan:
            cuts_musan = load_manifest(self.args.manifest_dir / "musan_cuts.jsonl.gz")
            transforms.append(
                CutMix(cuts=cuts_musan, p=0.5, snr=(10, 20), preserve_id=True)
            )
        else:
            pass

        if self.args.concatenate_cuts:
            transforms = [CutConcatenate()] + transforms

        input_transforms = []
        if self.args.enable_spec_aug:
            input_transforms.append(SpecAugment())
        else:
            pass

        train = K2SpeechRecognitionDataset(
            cut_transforms=transforms,
            input_transforms=input_transforms,
        )
        return train
'''


def _write_fixture(tmp_path: Path, content: str = FIXTURE_DATAMODULE_PY) -> Path:
    f = tmp_path / "asr_datamodule.py"
    f.write_text(content)
    return f


def test_injeta_as_cinco_pecas_e_compila(tmp_path):
    f = _write_fixture(tmp_path)
    prep_augment_datamodule.patch_datamodule_py(f)
    out = f.read_text()
    assert "    ReverbWithImpulseResponse,\n" in out
    assert "from telephone_channel_transform import TelephoneChannelTransform" in out
    assert '"--enable-telephone-aug"' in out
    assert '"--rir-manifest"' in out
    assert "if self.args.rir_manifest:" in out
    assert "if self.args.enable_telephone_aug:" in out
    ast.parse(out)


def test_ordem_reverb_antes_de_musan_e_telephone_por_ultimo(tmp_path):
    f = _write_fixture(tmp_path)
    prep_augment_datamodule.patch_datamodule_py(f)
    out = f.read_text()
    i_reverb = out.index("if self.args.rir_manifest:")
    i_musan = out.index("if self.args.enable_musan:")
    i_telephone = out.index("if self.args.enable_telephone_aug:")
    i_input_transforms = out.index("input_transforms = []")
    # ADR D2: sala (reverb) -> ruido ambiente (musan/CutMix) -> codec (telephone),
    # telephone e o ULTIMO cut_transform (antes mesmo de input_transforms comecar).
    assert i_reverb < i_musan < i_telephone < i_input_transforms


def test_idempotente_quando_marcador_presente(tmp_path):
    f = _write_fixture(tmp_path)
    prep_augment_datamodule.patch_datamodule_py(f)
    first = f.read_text()
    prep_augment_datamodule.patch_datamodule_py(f)  # 2a vez: marcador presente -> no-op
    assert f.read_text() == first
    assert first.count("class TelephoneChannelTransform") == 0  # nunca duplica a import
    assert first.count("from telephone_channel_transform import TelephoneChannelTransform") == 1


def test_falha_alto_quando_anchor_ausente(tmp_path):
    # remove o anchor de input_transforms -> patch deve abortar (SystemExit)
    broken = FIXTURE_DATAMODULE_PY.replace("        input_transforms = []\n", "")
    f = _write_fixture(tmp_path, broken)
    with pytest.raises(SystemExit):
        prep_augment_datamodule.patch_datamodule_py(f)


def test_falha_alto_quando_datamodule_py_inexistente(tmp_path):
    with pytest.raises(SystemExit):
        prep_augment_datamodule.patch_datamodule_py(tmp_path / "nao_existe.py")
