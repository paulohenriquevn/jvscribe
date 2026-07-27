"""Adapta o conformer_ctc3/decode.py do librispeech -> commonvoice/pt (M4:
decode do 2o finalista Conformer-CTC, MESMO protocolo do Zipformer-CTC:
ctc-greedy-search, mesmo test set FLEURS via cv-pt_cuts_test.jsonl.gz).
Regra 9: reusa o loop de decode testado do icefall (CTC greedy search +
write_error_stats_with_timestamps, que degrada graciosamente pra WER puro
quando não há alinhamento de palavra — não há alinhamento no corpus FLEURS/CV
usado aqui) -- troca só o datamodule (CommonVoice em vez de LibriSpeech) e o
test set (1 split "test" em vez de test-clean/test-other). Espelha o padrão
de prep_conformer_ctc.py (train.py, mesma recipe, rodado direto na instância)
e de patch_ctc_decode.py (o análogo para o zipformer/ctc_decode.py) já usados
neste projeto. Roda NA instância, em egs/commonvoice/ASR.

NOTA (bug upstream descoberto ao rodar): o decode.py do librispeech tem
save_results() com dois bugs quando o corpus não tem alinhamento de palavra
(nosso caso): (1) write_error_stats_with_timestamps(..., with_end_time=True)
retorna mean_delay/var_delay como tupla, e o `float(mean_delay)` na linha de
retorno quebra; (2) o sort de test_set_delays usa `x[1][0][0]`, que também
assume tupla. O patch abaixo já aplica with_end_time=False (correto pro nosso
caso: sem alinhamento, delay não tem sentido) e ajusta o sort key para
`x[1][0]` -- ambos aplicados directamente no decode.py gerado, não no
icefall/utils.py compartilhado."""
import py_compile
import sys
from pathlib import Path

LIBRI = "/workspace/icefall/egs/librispeech/ASR/conformer_ctc3/decode.py"
OUT_DIR = Path("/workspace/icefall/egs/commonvoice/ASR/conformer_ctc3")
OUT = OUT_DIR / "decode.py"

src = open(LIBRI).read()

NEW_DOCSTRING = '''"""
Usage (M4 -- Conformer-CTC pt, ctc-greedy-search, MESMO protocolo do
Zipformer-CTC medium para comparacao justa em M4):

./conformer_ctc3/decode.py \\
  --epoch 30 --avg 10 --use-averaged-model 1 \\
  --exp-dir conformer_ctc3/exp-medium-ctc \\
  --language pt --cv-manifest-dir data/pt \\
  --lang-dir data/pt/lang_bpe_500 \\
  --decoding-method ctc-greedy-search \\
  --max-duration 400

Adaptado do conformer_ctc3/decode.py do librispeech (Regra 9 -- nao reinventa
o loop de decode CTC k2). Trocas: (1) datamodule original (LibriSpeech) ->
CommonVoiceAsrDataModule (mesma classe usada por zipformer/ctc_decode.py do
commonvoice, mesmo cv-pt_cuts_test.jsonl.gz = FLEURS test); (2) um unico
split "test" em vez de test-clean/test-other (CommonVoiceAsrDataModule so
expoe test_cuts()); write_error_stats_with_timestamps degrada para WER puro
(sem symbol-delay) quando o corpus nao tem alinhamento de palavra -- e o
caso aqui, nao ha crash, so mean/var delay ficam "inf".

NOTA: encoder_dim/nhead/dim_feedforward/num_encoder_layers NAO sao flags de
CLI neste recipe (diferente do zipformer) -- ficam hardcoded em get_params()
de train.py, ja casados ao checkpoint treinado (512/8/2048/10, 64.7M params).
Passar essas flags no --help falha (argparse: unrecognized arguments).
"""'''

OLD_DOCSTRING_START = '"""\nUsage:\n'
OLD_DOCSTRING_END = "    --manifest-dir data/fbank_ali\nNote: It supports calculating symbol delay with following decoding methods:\n    - ctc-decoding\n    - 1best\n\"\"\""
start_idx = src.index(OLD_DOCSTRING_START)
end_idx = src.index(OLD_DOCSTRING_END) + len(OLD_DOCSTRING_END)
old_docstring = src[start_idx:end_idx]

repls = [
    (old_docstring, NEW_DOCSTRING),
    (
        "from asr_datamodule import LibriSpeechAsrDataModule",
        "from asr_datamodule import CommonVoiceAsrDataModule",
    ),
    (
        '    parser.add_argument(\n'
        '        "--exp-dir",\n'
        '        type=str,\n'
        '        default="pruned_transducer_stateless4/exp",\n'
        '        help="The experiment dir",\n'
        '    )',
        '    parser.add_argument(\n'
        '        "--exp-dir",\n'
        '        type=str,\n'
        '        default="conformer_ctc3/exp-medium-ctc",\n'
        '        help="The experiment dir",\n'
        '    )',
    ),
    (
        '    parser.add_argument(\n'
        '        "--lang-dir",\n'
        '        type=Path,\n'
        '        default="data/lang_bpe_500",\n'
        '        help="The lang dir containing word table and LG graph",\n'
        '    )',
        '    parser.add_argument(\n'
        '        "--lang-dir",\n'
        '        type=Path,\n'
        '        default="data/pt/lang_bpe_500",\n'
        '        help="The lang dir containing word table and LG graph",\n'
        '    )',
    ),
    (
        "    parser = get_parser()\n"
        "    LibriSpeechAsrDataModule.add_arguments(parser)",
        "    parser = get_parser()\n"
        "    CommonVoiceAsrDataModule.add_arguments(parser)",
    ),
    (
        "    # we need cut ids to display recognition results.\n"
        "    args.return_cuts = True\n"
        "    librispeech = LibriSpeechAsrDataModule(args)\n"
        "\n"
        "    test_clean_cuts = librispeech.test_clean_cuts()\n"
        "    test_other_cuts = librispeech.test_other_cuts()\n"
        "\n"
        "    test_clean_dl = librispeech.test_dataloaders(test_clean_cuts)\n"
        "    test_other_dl = librispeech.test_dataloaders(test_other_cuts)\n"
        "\n"
        "    test_sets = [\"test-clean\", \"test-other\"]\n"
        "    test_dl = [test_clean_dl, test_other_dl]\n",
        "    # we need cut ids to display recognition results.\n"
        "    args.return_cuts = True\n"
        "    commonvoice = CommonVoiceAsrDataModule(args)\n"
        "\n"
        "    test_cuts = commonvoice.test_cuts()\n"
        "    test_cuts_dl = commonvoice.test_dataloaders(test_cuts)\n"
        "\n"
        "    test_sets = [\"test\"]\n"
        "    test_dl = [test_cuts_dl]\n",
    ),
    (
        "                with_end_time=True,\n",
        "                # M4: with_end_time=False -- este corpus (FLEURS/CV pt)\n"
        "                # nao tem alinhamento de palavra; write_error_stats_with_timestamps\n"
        "                # com with_end_time=True retorna mean/var_delay como tupla e o\n"
        "                # save_results() original (bug upstream) faz float(tupla) e quebra\n"
        "                # DEPOIS de already ter escrito recogs/errs e logado o %WER.\n"
        "                with_end_time=False,\n",
    ),
    (
        "    test_set_delays = sorted(test_set_delays.items(), key=lambda x: x[1][0][0])\n",
        "    # M4: com with_end_time=False, val[0] (mean_delay) ja e float, nao tupla\n"
        "    # -- x[1][0][0] (escrito para o caso with_end_time=True) quebraria aqui.\n"
        "    test_set_delays = sorted(test_set_delays.items(), key=lambda x: x[1][0])\n",
    ),
]

for old, new in repls:
    if old not in src:
        sys.exit(f"FALHA: padrao nao encontrado (len={len(old)}):\n{old[:300]}")
    n = src.count(old)
    if n != 1:
        sys.exit(f"FALHA: padrao nao-unico ({n}x):\n{old[:300]}")
    src = src.replace(old, new)

# nenhuma referência remanescente ao datamodule/variável do librispeech
for banned in ("LibriSpeechAsrDataModule", "librispeech.", "test_clean", "test_other"):
    if banned in src:
        sys.exit(f"FALHA: ainda há referência a '{banned}' após o patch")

OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT.write_text(src)
OUT.chmod(0o755)
py_compile.compile(str(OUT), doraise=True)
print(f"PATCH_OK: {OUT} gerado e compila")
