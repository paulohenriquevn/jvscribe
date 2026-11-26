"""Auditoria de ruído de pseudo-rótulo no mux train (experimento decisivo M5).
Mede a fração de segmentos com assinaturas de alucinação do Whisper que o nosso
`is_hallucinated_text` atual NÃO pega — repetição consecutiva de palavra/frase
(o lever de -14pp do OLMoASR). Separa CORAA (humano, id 'coraa_') de TAGARELA (pseudo).
GPU-free. Roda na instância.

Uso:
    python3 jvscribe/audit/tagarela_noise_audit.py [--manifest CAMINHO] [--amostra N]

⚠️ A interface era POSICIONAL e não documentada, na ordem contraintuitiva
`[amostra] [manifesto]` — passar o caminho primeiro dava
`ValueError: invalid literal for int()`. E era parseada em nível de MÓDULO: importar o
arquivo já lia `sys.argv`. Encontrado no live test de 2026-07-31.
"""
from __future__ import annotations

import argparse
from collections import Counter

from lhotse import CutSet

MANIFEST_PADRAO = "/workspace/icefall/egs/commonvoice/ASR/data/mux/cv-pt_cuts_train.jsonl.gz"
AMOSTRA_PADRAO = 120000  # amostra p/ velocidade


def consecutive_word_repeat(words, k=3):
    """Alguma palavra repetida >=k vezes consecutivas (loop do Whisper)."""
    run = 1
    for i in range(1, len(words)):
        run = run + 1 if words[i] == words[i-1] else 1
        if run >= k:
            return True
    return False


def ngram_loop(words, n=2, k=2):
    """Algum n-grama repetido >=k vezes consecutivas (ex.: 'muito bem muito bem')."""
    if len(words) < n * k:
        return False
    for i in range(len(words) - n*k + 1):
        block = words[i:i+n]
        ok = all(words[i+j*n:i+(j+1)*n] == block for j in range(k))
        if ok:
            return True
    return False


def low_unique_ratio(words, thr=0.45):
    if len(words) < 6:
        return False
    return len(set(words)) / len(words) < thr


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=MANIFEST_PADRAO,
                    help="manifest Lhotse do mux train (default: o da instância de treino)")
    ap.add_argument("--amostra", type=int, default=AMOSTRA_PADRAO,
                    help="quantos cuts examinar (default: %(default)s)")
    a = ap.parse_args()
    MANIFEST, SAMPLE = a.manifest, a.amostra

    import pathlib as _p
    if not _p.Path(MANIFEST).exists():
        # Fail-fast COM instrução: antes vinha o ValueError cru da lib
        # (error-handling.md § 2, "mensagens genéricas").
        raise SystemExit(
            f"manifest não encontrado: {MANIFEST}\n"
            f"Este script roda na instância de treino, sobre o mux gerado por "
            f"`finetune/prep_tagarela.py`. Passe --manifest <caminho> se estiver em outro lugar."
        )
    cs = CutSet.from_file(MANIFEST)
    stats = {c: Counter() for c in ("coraa", "tagarela")}
    dur = {c: 0.0 for c in ("coraa", "tagarela")}
    flagged_dur = {c: 0.0 for c in ("coraa", "tagarela")}
    n = 0
    for cut in cs:
        n += 1
        if n > SAMPLE:
            break
        corp = "coraa" if cut.id.startswith("coraa_") else "tagarela"
        text = cut.supervisions[0].text if cut.supervisions else ""
        w = text.split()
        d = cut.duration
        dur[corp] += d
        stats[corp]["total"] += 1
        hit = False
        if consecutive_word_repeat(w, 3):
            stats[corp]["word_repeat3"] += 1; hit = True
        if ngram_loop(w, 2, 2) or ngram_loop(w, 3, 2):
            stats[corp]["ngram_loop"] += 1; hit = True
        if low_unique_ratio(w):
            stats[corp]["low_unique"] += 1; hit = True
        if hit:
            stats[corp]["ANY_FLAG"] += 1
            flagged_dur[corp] += d
    print(f"amostra={min(n-1, SAMPLE)} cuts")
    for corp in ("coraa", "tagarela"):
        t = stats[corp]["total"] or 1
        print(f"\n=== {corp.upper()} (n={t}, {dur[corp]/3600:.1f}h na amostra) ===")
        for k in ("word_repeat3", "ngram_loop", "low_unique", "ANY_FLAG"):
            v = stats[corp][k]
            print(f"  {k:14s}: {v:6d}  ({100*v/t:5.2f}%)")
        print(f"  horas afetadas (ANY_FLAG): {flagged_dur[corp]/3600:.1f}h "
              f"({100*flagged_dur[corp]/(dur[corp] or 1):.1f}%)")


if __name__ == "__main__":
    main()
