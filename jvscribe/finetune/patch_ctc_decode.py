"""Adapta o `ctc_decode.py` do librispeech → commonvoice.

Regra 9 na prática: reusa o decoder CTC já testado do icefall e troca **só** o datamodule e a
seção de test-sets. Nada do algoritmo de decode é reescrito.

⚠️ Como todo patcher deste diretório, ancora em trechos literais do upstream — ver
`prep_phoneme_head.ICEFALL_REV_TESTADO` para a revisão contra a qual as âncoras foram escritas.

Este módulo executava **em nível de módulo**: importá-lo abria `/workspace/icefall/...`,
escrevia o arquivo de saída e podia chamar `sys.exit`. Consequência medida: cobertura 0% — não
havia como importar para testar — e ele nem aparecia no inventário de entrypoints, porque não
tinha `if __name__ == "__main__"`. É o mesmo defeito de `audit/tagarela_noise_audit.py`.

Uso:
  python3 jvscribe/finetune/patch_ctc_decode.py \
      --librispeech <icefall>/egs/librispeech/ASR/zipformer/ctc_decode.py \
      --out <icefall>/egs/commonvoice/ASR/zipformer/ctc_decode.py
"""
from __future__ import annotations

import argparse
import py_compile
import sys
from pathlib import Path

LIBRI = Path("/workspace/icefall/egs/librispeech/ASR/zipformer/ctc_decode.py")
OUT = Path("/workspace/icefall/egs/commonvoice/ASR/zipformer/ctc_decode.py")

SUBSTITUICOES: list[tuple[str, str]] = [
    ("from asr_datamodule import LibriSpeechAsrDataModule",
     "from asr_datamodule import CommonVoiceAsrDataModule"),
    ("    LibriSpeechAsrDataModule.add_arguments(parser)",
     "    CommonVoiceAsrDataModule.add_arguments(parser)"),
    (
        "    librispeech = LibriSpeechAsrDataModule(args)\n"
        "\n"
        "    test_clean_cuts = librispeech.test_clean_cuts()\n"
        "    test_other_cuts = librispeech.test_other_cuts()\n"
        "\n"
        "    test_clean_dl = librispeech.test_dataloaders(test_clean_cuts)\n"
        "    test_other_dl = librispeech.test_dataloaders(test_other_cuts)\n"
        "\n"
        '    test_sets = ["test-clean", "test-other"]\n'
        "    test_dl = [test_clean_dl, test_other_dl]",
        "    commonvoice = CommonVoiceAsrDataModule(args)\n"
        "\n"
        "    test_cv_cuts = commonvoice.test_cuts()\n"
        "\n"
        "    test_cv_dl = commonvoice.test_dataloaders(test_cv_cuts)\n"
        "\n"
        '    test_sets = ["test"]\n'
        "    test_dl = [test_cv_dl]",
    ),
]

# Sobras que provam adaptação incompleta. Um `ctc_decode.py` que ainda cita librispeech decodifica
# contra o test set ERRADO — e produz WER plausível, sem erro nenhum, sobre outro corpus.
RESIDUOS_PROIBIDOS = ("librispeech", "LibriSpeechAsrDataModule")


def adaptar(src: str) -> str:
    """librispeech → commonvoice. Levanta `ValueError` em vez de escrever algo meia-boca.

    A checagem de resíduo é o que separa "substituí três trechos" de "o arquivo está adaptado":
    uma quarta referência ao librispeech que aparecesse num upstream futuro passaria pelas
    substituições sem erro e só apareceria como WER estranho depois do treino.
    """
    for old, new in SUBSTITUICOES:
        if old not in src:
            raise ValueError(
                f"padrão não encontrado — o upstream mudou:\n{old[:120]!r}\n"
                "Ver `prep_phoneme_head.ICEFALL_REV_TESTADO` para a revisão testada."
            )
        src = src.replace(old, new)

    sobrou = [r for r in RESIDUOS_PROIBIDOS if r in src]
    if sobrou:
        raise ValueError(
            f"ainda há referência a librispeech após o patch: {sobrou}. "
            "O decode rodaria contra o test set errado, produzindo WER de outro corpus."
        )
    return src


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--librispeech", type=Path, default=LIBRI,
                    help="ctc_decode.py de origem (egs/librispeech/ASR/zipformer)")
    ap.add_argument("--out", type=Path, default=OUT,
                    help="destino em egs/commonvoice/ASR/zipformer")
    a = ap.parse_args(argv)

    if not a.librispeech.exists():
        sys.exit(f"origem ausente: {a.librispeech} — passe --librispeech apontando para o clone "
                 f"do icefall.")
    try:
        adaptado = adaptar(a.librispeech.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"FALHA: {e}")

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(adaptado, encoding="utf-8")
    py_compile.compile(str(a.out), doraise=True)
    print(f"PATCH_OK: {a.out} gerado e compila")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
