#!/usr/bin/env python3
"""E6 etapa 2a — texto para o modelo de linguagem, com a checagem de vazamento junto.

**O construtor e o auditor são o mesmo script de propósito.** Separá-los permitiria treinar um LM
sem nunca rodar a checagem, e o vazamento é a única coisa que pode invalidar a etapa 2 inteira.

⚠️ **Por que este risco é real e não paranoia.** O FLEURS deriva do FLoRes-101, cujas sentenças
fonte saem da Wikipédia. Treinar o LM em Wikipédia em português e avaliar em FLEURS pode significar
**dar ao LM as sentenças do test set**. O WER despencaria e o número não valeria nada — é a versão
em LM da falácia § 3 #10 (pseudo-label no test set).

A mitigação não é evitar a Wikipédia — é **medir**. O script conta quantas sentenças do FLEURS test
aparecem literalmente no corpus do LM. O pré-registro exige que esse número seja **0** e que ele
seja **publicado**, não afirmado.

A comparação é feita na régua canônica + expansão de número, que é o espaço onde o decoder e o LM
vivem — comparar em texto cru deixaria passar uma sentença idêntica que só difere na pontuação.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "common"))
from metrics import find_test_parquet  # noqa: E402
from text import expandir_numeros, normalize_for_wer_compare  # noqa: E402

# Sentenças curtas demais não ensinam contexto; longas demais em geral são lista ou tabela mal
# separada. A faixa é um filtro de qualidade, não uma otimização.
MIN_PALAVRAS, MAX_PALAVRAS = 5, 40
_FIM_DE_FRASE = re.compile(r"(?<=[.!?])\s+")


def normalizar(s: str) -> str:
    """A régua do decoder — o LM tem de viver no MESMO espaço que as hipóteses que vai pontuar."""
    return expandir_numeros(normalize_for_wer_compare(s))


def sentencas_do_teste() -> set[str]:
    import pyarrow.parquet as pq

    t = pq.read_table(find_test_parquet(), columns=["transcription"])
    return {normalizar(x) for x in t.column("transcription").to_pylist()}


def coletar(alvo_palavras: int, proibidas: set[str], destino: pathlib.Path) -> dict:
    """Escreve as sentenças **incrementalmente** e devolve as contagens.

    A escrita é incremental porque acumular em lista morreu: 20M palavras em `list[str]` estouram
    a RAM da máquina e o processo é morto pelo OOM killer **em silêncio**, sem stack trace e sem
    arquivo. Streaming para disco mantém a memória constante e deixa o resultado parcial em disco
    se algo interromper.

    A colisão com o test set é **contada e descartada**, não só contada: deixar a sentença entrar
    depois de detectá-la seria saber do vazamento e usá-lo assim mesmo.
    """
    from datasets import load_dataset

    ds = load_dataset("wikimedia/wikipedia", "20231101.pt", split="train", streaming=True)
    palavras = sentencas = colisoes = 0
    tipos: set[str] = set()
    with destino.open("w", encoding="utf-8") as fh:
        for artigo in ds:
            for bruta in _FIM_DE_FRASE.split(artigo["text"]):
                s = normalizar(bruta)
                toks = s.split()
                if not (MIN_PALAVRAS <= len(toks) <= MAX_PALAVRAS):
                    continue
                if s in proibidas:
                    colisoes += 1
                    continue
                fh.write(s + "\n")
                sentencas += 1
                palavras += len(toks)
                tipos.update(toks)
            if palavras >= alvo_palavras:
                break
    return {"sentencas": sentencas, "palavras": palavras, "tipos": len(tipos),
            "sentencas_do_teste_bloqueadas": colisoes}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--palavras", type=int, default=5_000_000)
    ap.add_argument("--saida", type=pathlib.Path,
                    default=pathlib.Path("data/lm/wikipedia-pt.txt"))
    a = ap.parse_args()

    print("  lendo as sentenças do FLEURS test (o que NÃO pode entrar)…", flush=True)
    proibidas = sentencas_do_teste()
    print(f"  {len(proibidas)} sentenças de teste na lista de bloqueio\n"
          f"  coletando ~{a.palavras:,} palavras da Wikipédia pt…", flush=True)

    a.saida.parent.mkdir(parents=True, exist_ok=True)
    cont = coletar(a.palavras, proibidas, a.saida)
    palavras, colisoes = cont["palavras"], cont["sentencas_do_teste_bloqueadas"]
    sentencas = range(cont["sentencas"])          # só o tamanho é usado daqui para baixo
    meta = {
        "fonte": "wikimedia/wikipedia 20231101.pt (streaming)",
        **cont,
        "regua": "normalize_for_wer_compare + expandir_numeros",
    }
    a.saida.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    print(f"\n  {cont['sentencas']:,} sentenças · {palavras:,} palavras · {cont['tipos']:,} tipos")
    print(f"  → {a.saida}")
    print(f"\n  VAZAMENTO: {colisoes} sentença(s) do FLEURS test apareceram no corpus "
          f"{'✅ nenhuma' if colisoes == 0 else '⚠️ e foram DESCARTADAS'}")
    if colisoes:
        print("  ⚠️ A contagem é diferente de zero. Ela ENTRA no relatório: o corpus da Wikipédia\n"
              "     realmente contém sentenças do test set, e o pré-registro previu esse risco.\n"
              "     As colididas foram removidas, mas sobreposição PARCIAL (mesma sentença com\n"
              "     uma palavra trocada) NÃO é detectada por igualdade literal — o resultado da\n"
              "     etapa 2 carrega essa limitação.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
