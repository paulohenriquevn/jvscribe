"""Patch determinístico: anexa a augmentação de canal telefônico (+ reverb RIR)
à lista `cut_transforms` do `zipformer/asr_datamodule.py` do icefall (M5 —
Task 2.1, blueprint `m5-scale-model-wer-blueprint.md` Q3/Q6/EC-2, ADR D2).

Regra 9 — NÃO reescreve o datamodule: edita in-place `asr_datamodule.py` com
substrings exatas (`apply_patch` de `prep_phoneme_head.py`, reusado — DRY),
assert count==1 (senão falha alto), valida compilação. Mesmo idioma de
`prep_finetune.py`.

O que injeta (âncoras verificadas contra o `asr_datamodule.py` REAL de
`knowledge-base/references/icefall/egs/commonvoice/ASR/zipformer/`):

1. Import de `ReverbWithImpulseResponse` no bloco `from lhotse.dataset import
   (...)` — já importável de lá (blueprint Q3); `CutMix` já está.
2. Import FLAT de `TelephoneChannelTransform`
   (`training/corpus/telephone_channel_transform.py`) — o runbook de treino
   copia esse arquivo + `telephone_channel.py` para o MESMO diretório do
   `asr_datamodule.py` patcheado (mesma convenção de
   `training/make_telephone_test.py`).
3. Duas flags novas: `--enable-telephone-aug` (bool, molde de
   `--enable-musan`) e `--rir-manifest` (str, default None — a PRESENÇA do
   path já liga o reverb; não há `--enable-reverb` separado, parsimony-ladder
   rung 5, um flag a menos para o mesmo controle).
4. Bloco de Reverb ANTES do bloco `if self.args.enable_musan:` (ADR D2 —
   sala → ruído → codec; reverb é o PRIMEIRO estágio).
5. Bloco de telephone ANTES de `input_transforms = []` (ADR D2 — telephone é o
   ÚLTIMO estágio, depois até do `concatenate_cuts` que prependa
   `CutConcatenate`; fica fisicamente por último na lista `transforms`).

Restrição crítica (EC-P1, D2): a augmentação de canal degrada ÁUDIO, então o
fine-tune com `--enable-telephone-aug`/`--rir-manifest` EXIGE
`--on-the-fly-feats True` no runbook — feats pré-computadas anulam a
augmentação (o `train_dataloaders()` cai no branch `PrecomputedFeatures` que
nunca chama os `cut_transforms` sobre áudio).

Uso (na instância, em egs/commonvoice/ASR):
    python3 /workspace/prep_augment_datamodule.py            # path default
    python3 prep_augment_datamodule.py --datamodule-py PATH  # path explícito
Idempotente (marcador `TelephoneChannelTransform` já presente → no-op). Faz
backup `.orig-phoneme-patch` (sufixo de `apply_patch`, reusado) antes de
escrever.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Reusa a máquina de patch já validada (garante 1×, idempotência, fail-fast, backup).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prep_phoneme_head import apply_patch  # noqa: E402

DEFAULT_DATAMODULE_PY = Path(
    "/workspace/icefall/egs/commonvoice/ASR/zipformer/asr_datamodule.py"
)
MARKER = "TelephoneChannelTransform"

_TELEPHONE_IMPORT = (
    "from icefall.utils import str2bool\n"
    "\n"
    "# M5 -- canal telefonico on-the-fly (Regra 9: reusa\n"
    "# training/corpus/telephone_channel.py via o adapter\n"
    "# TelephoneChannelTransform; import flat pq o runbook copia o arquivo\n"
    "# para o mesmo dir de asr_datamodule.py na instancia -- mesma\n"
    "# convencao de training/make_telephone_test.py).\n"
    "from telephone_channel_transform import TelephoneChannelTransform"
)

_TELEPHONE_AUG_FLAGS = (
    "\n"
    "        group.add_argument(\n"
    '            "--enable-telephone-aug",\n'
    "            type=str2bool,\n"
    "            default=False,\n"
    '            help="When enabled, apply the M3 telephone channel (300-3400 Hz "\n'
    '            "band + G.711 A-law) on-the-fly as the LAST cut transform "\n'
    '            "(D2 -- room->noise->codec order; requires --on-the-fly-feats).",\n'
    "        )\n"
    "\n"
    "        group.add_argument(\n"
    '            "--rir-manifest",\n'
    "            type=str,\n"
    "            default=None,\n"
    '            help="Path to a RecordingSet manifest of RIRs (SLR28). When set, "\n'
    '            "enables reverb (ReverbWithImpulseResponse) as the FIRST cut "\n'
    '            "transform (D2). None disables reverb -- no separate "\n'
    '            "--enable-reverb flag; presence of the path is the switch "\n'
    '            "(parsimony-ladder.md rung 5).",\n'
    "        )"
)

_REVERB_BLOCK = (
    "        transforms = []\n"
    "        if self.args.rir_manifest:\n"
    '            logging.info("Enable Reverb (RIR)")\n'
    "            rir_recordings = load_manifest(self.args.rir_manifest)\n"
    "            transforms.append(\n"
    "                ReverbWithImpulseResponse(rir_recordings=rir_recordings, p=0.5)\n"
    "            )\n"
    "        else:\n"
    '            logging.info("Disable Reverb (no --rir-manifest)")\n'
    "        if self.args.enable_musan:"
)

_TELEPHONE_BLOCK = (
    "        if self.args.enable_telephone_aug:\n"
    '            logging.info("Enable telephone channel (M3 proxy, on-the-fly, D2 last)")\n'
    "            transforms.append(TelephoneChannelTransform(p=0.5))\n"
    "        else:\n"
    '            logging.info("Disable telephone channel augmentation")\n'
    "\n"
    "        input_transforms = []"
)


def build_repls() -> list[tuple[str, str]]:
    """As 5 substituicoes (anchor -> anchor+injecao). Anchors sao substrings
    EXATAS do asr_datamodule.py real (verificadas contra
    knowledge-base/references/icefall/.../commonvoice/ASR/zipformer/) --
    fail-fast (apply_patch/count==1) se a versao na instancia divergir."""
    return [
        # 1. ReverbWithImpulseResponse no bloco de import de lhotse.dataset
        (
            "from lhotse.dataset import (  # noqa F401 for PrecomputedFeatures\n"
            "    CutConcatenate,\n"
            "    CutMix,\n"
            "    DynamicBucketingSampler,\n"
            "    K2SpeechRecognitionDataset,\n"
            "    PrecomputedFeatures,\n"
            "    SimpleCutSampler,\n"
            "    SpecAugment,\n"
            ")",
            "from lhotse.dataset import (  # noqa F401 for PrecomputedFeatures\n"
            "    CutConcatenate,\n"
            "    CutMix,\n"
            "    DynamicBucketingSampler,\n"
            "    K2SpeechRecognitionDataset,\n"
            "    PrecomputedFeatures,\n"
            "    ReverbWithImpulseResponse,\n"
            "    SimpleCutSampler,\n"
            "    SpecAugment,\n"
            ")",
        ),
        # 2. import flat do nosso adapter (Regra 9)
        ("from icefall.utils import str2bool", _TELEPHONE_IMPORT),
        # 3. flags --enable-telephone-aug / --rir-manifest (molde --enable-musan)
        (
            "        group.add_argument(\n"
            '            "--enable-musan",\n'
            "            type=str2bool,\n"
            "            default=True,\n"
            '            help="When enabled, select noise from MUSAN and mix it"\n'
            '            "with training dataset. ",\n'
            "        )",
            "        group.add_argument(\n"
            '            "--enable-musan",\n'
            "            type=str2bool,\n"
            "            default=True,\n"
            '            help="When enabled, select noise from MUSAN and mix it"\n'
            '            "with training dataset. ",\n'
            "        )\n" + _TELEPHONE_AUG_FLAGS,
        ),
        # 4. Reverb ANTES do bloco enable_musan (D2: sala -> ruido -> codec)
        (
            "        transforms = []\n"
            "        if self.args.enable_musan:",
            _REVERB_BLOCK,
        ),
        # 5. telephone por ULTIMO, antes de input_transforms = []
        ("        input_transforms = []", _TELEPHONE_BLOCK),
    ]


def patch_datamodule_py(datamodule_py: Path) -> None:
    if not datamodule_py.exists():
        sys.exit(f"FALHA: asr_datamodule.py nao encontrado em {datamodule_py}")
    apply_patch(datamodule_py, build_repls(), already_applied_marker=MARKER)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--datamodule-py",
        type=Path,
        default=DEFAULT_DATAMODULE_PY,
        help="Caminho do zipformer/asr_datamodule.py a ser patcheado.",
    )
    args = parser.parse_args()
    patch_datamodule_py(args.datamodule_py)
    print(f"[augment-datamodule] patch aplicado em {args.datamodule_py}")


if __name__ == "__main__":
    main()
