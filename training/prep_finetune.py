"""Patch determinístico: porta o mecanismo `do_finetune` do icefall para o
`zipformer/train.py` (M5 — fine-tune do medium+fonema em CORAA+TAGARELA).

Regra 9 — NÃO reescreve o loop de treino: edita in-place `train.py` com substrings
exatas (`apply_patch` de `prep_phoneme_head.py`, reusado — DRY), assert count==1
(senão falha alto), valida compilação. Mecanismo idêntico ao
`egs/wenetspeech/KWS/zipformer/finetune.py` (zipformer + `--use-ctc`), blueprint
`m5-scale-model-wer-blueprint.md` Q1/Q2.

O que injeta:
1. `add_finetune_arguments(parser)` — flags `--do-finetune/--init-modules/--finetune-ckpt`.
2. `load_model_params(ckpt, model, init_modules, strict)` — carga seletiva de módulos
   do base ckpt (prefixos), otimizador nasce fresco depois (fine-tune ≠ resume).
3. Bloco `if params.do_finetune:` ANTES de `assert params.start_epoch > 0` — carrega o
   base ckpt (M4 medium+fonema) no modelo antes do otimizador. `--init-modules
   "encoder,ctc_output"` reaproveita encoder+cabeça CTC principal (a de fonema fica
   fora se não listada — EC-4). `--start-epoch 1` obrigatório (não é resume — D1).

Uso (na instância, em egs/commonvoice/ASR):
    python3 /workspace/prep_finetune.py            # usa o path default da instância
    python3 prep_finetune.py --train-py CAMINHO    # aponta um train.py específico
Idempotente (marcador `def add_finetune_arguments` já presente → no-op). Faz backup
`.orig-phoneme-patch` (sufixo de `apply_patch`, reusado) antes de escrever.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Reusa a máquina de patch já validada (garante 1×, idempotência, fail-fast, backup).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prep_phoneme_head import apply_patch  # noqa: E402

DEFAULT_TRAIN_PY = Path("/workspace/icefall/egs/commonvoice/ASR/zipformer/train.py")
MARKER = "def add_finetune_arguments"

# ── Código portado do finetune.py (KWS zipformer, use_ctc-compatível) ───────────
_FINETUNE_FUNCS = '''\
def add_finetune_arguments(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--do-finetune",
        type=str2bool,
        default=False,
        help="Se True, carrega --finetune-ckpt como base e treina com LR baixo (fine-tune, nao resume).",
    )
    parser.add_argument(
        "--init-modules",
        type=str,
        default=None,
        help="Prefixos de parametro a carregar do base ckpt, separados por virgula "
        "(ex.: 'encoder,ctc_output'). None = carrega o modelo inteiro.",
    )
    parser.add_argument(
        "--finetune-ckpt",
        type=str,
        default=None,
        help="Caminho do .pt base para fine-tune (idealmente um averaged model).",
    )


def load_model_params(ckpt, model, init_modules=None, strict=True):
    """Carrega pesos do base ckpt no model. Se init_modules for dado, carrega apenas
    os parametros cujo nome comeca com um dos prefixos (o resto fica com init aleatorio).
    Portado de egs/wenetspeech/KWS/zipformer/finetune.py (Regra 9)."""
    import logging as _logging

    import torch as _torch

    _logging.info(f"[finetune] Loading base checkpoint from {ckpt}")
    checkpoint = _torch.load(ckpt, map_location="cpu", weights_only=False)

    if not init_modules:
        if next(iter(checkpoint["model"])).startswith("module."):
            dst_state_dict = model.state_dict()
            src_state_dict = checkpoint["model"]
            for key in dst_state_dict.keys():
                src_key = "{}.{}".format("module", key)
                dst_state_dict[key] = src_state_dict.pop(src_key)
            assert len(src_state_dict) == 0
            model.load_state_dict(dst_state_dict, strict=strict)
        else:
            model.load_state_dict(checkpoint["model"], strict=strict)
    else:
        src_state_dict = checkpoint["model"]
        dst_state_dict = model.state_dict()
        for module in init_modules:
            _logging.info(f"[finetune] Loading parameters with prefix {module}")
            src_keys = [
                k for k in src_state_dict.keys() if k.startswith(module.strip() + ".")
            ]
            dst_keys = [
                k for k in dst_state_dict.keys() if k.startswith(module.strip() + ".")
            ]
            assert set(src_keys) == set(dst_keys)  # os dois conjuntos devem bater
            for key in src_keys:
                dst_state_dict[key] = src_state_dict.pop(key)
        model.load_state_dict(dst_state_dict, strict=strict)

    return None


'''

_DO_FINETUNE_BLOCK = '''\
    if params.do_finetune:
        assert params.start_epoch == 1, (
            "fine-tune deve iniciar em --start-epoch 1 (carrega o base ckpt, nao resume "
            "o schedule do treino original)"
        )
        assert params.finetune_ckpt is not None, "--finetune-ckpt obrigatorio com --do-finetune"
        modules = params.init_modules.split(",") if params.init_modules else None
        load_model_params(
            ckpt=params.finetune_ckpt, model=model, init_modules=modules
        )

    assert params.start_epoch > 0, params.start_epoch'''


def build_repls() -> list[tuple[str, str]]:
    """As 3 substituicoes (anchor -> anchor+injecao). Anchors curtos e unicos p/
    robustez entre versoes do train.py (senao apply_patch falha alto — EC-P3)."""
    return [
        # 1. define as funcoes antes de get_parser()
        ("def get_parser():", _FINETUNE_FUNCS + "def get_parser():"),
        # 2. registra as flags no parser
        (
            "    add_model_arguments(parser)",
            "    add_finetune_arguments(parser)\n    add_model_arguments(parser)",
        ),
        # 3. carrega o base ckpt antes do assert de start_epoch (e do otimizador)
        (
            "    assert params.start_epoch > 0, params.start_epoch",
            _DO_FINETUNE_BLOCK,
        ),
    ]


def patch_train_py(train_py: Path) -> None:
    if not train_py.exists():
        sys.exit(f"FALHA: train.py nao encontrado em {train_py}")
    apply_patch(train_py, build_repls(), already_applied_marker=MARKER)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train-py",
        type=Path,
        default=DEFAULT_TRAIN_PY,
        help="Caminho do zipformer/train.py a ser patcheado.",
    )
    args = parser.parse_args()
    patch_train_py(args.train_py)
    print(f"[finetune] patch aplicado em {args.train_py}")


if __name__ == "__main__":
    main()
