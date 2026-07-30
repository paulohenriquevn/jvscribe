"""Adapta o ctc_decode.py do librispeech → commonvoice (Regra 9: reusa o decoder CTC
testado; troca só o datamodule e a seção de test-sets). Roda NA instância."""
import py_compile
import sys

LIBRI = "/workspace/icefall/egs/librispeech/ASR/zipformer/ctc_decode.py"
OUT = "/workspace/icefall/egs/commonvoice/ASR/zipformer/ctc_decode.py"

src = open(LIBRI).read()

repls = [
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

for old, new in repls:
    if old not in src:
        sys.exit(f"FALHA: padrão não encontrado:\n{old[:80]}")
    src = src.replace(old, new)

# nenhuma referência remanescente ao var/classe do librispeech
if "librispeech" in src or "LibriSpeechAsrDataModule" in src:
    sys.exit("FALHA: ainda há referência a librispeech após o patch")

open(OUT, "w").write(src)
py_compile.compile(OUT, doraise=True)
print("PATCH_OK: ctc_decode.py do commonvoice gerado e compila")
