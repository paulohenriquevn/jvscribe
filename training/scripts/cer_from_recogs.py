#!/usr/bin/env python3
"""CER a partir de um recogs-*.txt do icefall (ref=[...] / hyp=[...]).

Fecha a tabela comparativa de M4: o WER pune deslize de 1-2 chars como palavra
inteira errada; o CER mede a distância real de caractere. Reutiliza o MESMO
`word_edit_distance` de `eval_runtime_wer.py` (Levenshtein S+D+I) aplicado à
sequência de caracteres sem espaços — idêntico ao método que produziu o CER do
Zipformer, para comparação apples-to-apples entre arquiteturas.

Uso: python3 training/scripts/cer_from_recogs.py <recogs.txt>
"""
import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_runtime_wer import word_edit_distance  # reuso, não reinventa (Regra 9)

# `<utt>:\tref=['a', 'b', ...]` — captura o rótulo (ref|hyp) e a lista literal.
LINE = re.compile(r":\t(ref|hyp)=(\[.*\])$")


def score_recogs(text: str) -> dict:
    """Computa WER+CER de um recogs do icefall (lógica pura, sem I/O — testável).

    Falha alto (`ValueError`) se ref/hyp ficarem desemparelhados (caso negativo:
    recogs truncado ou corrompido não pode virar um número silenciosamente).
    """
    refs: dict[str, list[str]] = {}
    hyps: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = LINE.search(line)
        if not m:
            continue  # timestamp_hyp e afins são ignorados
        utt = line.split(":", 1)[0]
        words = ast.literal_eval(m.group(2))
        (refs if m.group(1) == "ref" else hyps)[utt] = words

    unpaired = set(refs) ^ set(hyps)
    if unpaired:
        raise ValueError(f"ref/hyp desemparelhados em {len(unpaired)} utterances: {sorted(unpaired)[:3]}")

    tot_cerr = tot_chars = tot_werr = tot_words = 0
    for utt, ref in refs.items():
        hyp = hyps[utt]
        tot_werr += word_edit_distance(ref, hyp)
        tot_words += len(ref)
        ref_c, hyp_c = list("".join(ref)), list("".join(hyp))
        tot_cerr += word_edit_distance(ref_c, hyp_c)
        tot_chars += len(ref_c)

    return {
        "utterances": len(refs),
        "words": tot_words,
        "chars": tot_chars,
        "werr": tot_werr,
        "cerr": tot_cerr,
        "wer": 100.0 * tot_werr / max(tot_words, 1),
        "cer": 100.0 * tot_cerr / max(tot_chars, 1),
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("uso: cer_from_recogs.py <recogs.txt>")
    path = Path(sys.argv[1])
    if not path.exists():
        raise SystemExit(f"recogs ausente: {path}")
    try:
        r = score_recogs(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit(str(e)) from e
    print(f"[MEDIDO] {path.name}")
    print(f"  utterances={r['utterances']}  palavras={r['words']}  caracteres={r['chars']}")
    print(f"  WER = {r['wer']:.2f}%  ({r['werr']}/{r['words']})")
    print(f"  CER = {r['cer']:.2f}%  ({r['cerr']}/{r['chars']})")


if __name__ == "__main__":
    main()
