"""O corpus é preparado numa máquina e treinado em outra — o manifesto precisa viajar.

O lhotse grava caminho ABSOLUTO em `storage_path` e em `recording.sources[].source`.
Enquanto o treino roda onde extraiu, ninguém percebe. Mas a preparação acontece no Colab
e a Fase 3 na vast.ai: lá esses caminhos não existem, e `load_features()` falharia
utterance a utterance no meio de um treino pago.
"""

from __future__ import annotations

import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "finetune"))

import export_corpus as EX  # noqa: E402


def _manifesto(path, cuts):
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for c in cuts:
            fh.write(json.dumps(c) + "\n")


def _cut(cid, raiz, dur=1.5):
    return {
        "id": cid, "duration": dur, "type": "MonoCut",
        "features": {"storage_path": f"{raiz}/feats_train_000.lca",
                     "storage_type": "lilcom_chunky"},
        "recording": {"id": cid, "sources": [
            {"type": "file", "source": f"{raiz}/wav_train/{cid}.wav"}]},
    }


def test_caminhos_viram_relativos_a_raiz(tmp_path):
    raiz = tmp_path / "corpus"; raiz.mkdir()
    _manifesto(raiz / "m.jsonl.gz", [_cut("a", raiz), _cut("b", raiz)])

    r = EX.relativizar(raiz, raiz / "m.jsonl.gz", raiz / "out.jsonl.gz")

    assert r["cuts"] == 2 and r["fora_da_raiz"] == 0
    assert r["relativizados"] == 4          # 2 features + 2 recordings
    linhas = [json.loads(x) for x in
              gzip.open(raiz / "out.jsonl.gz", "rt", encoding="utf-8")]
    for cut in linhas:
        assert cut["features"]["storage_path"] == "feats_train_000.lca"
        assert not cut["recording"]["sources"][0]["source"].startswith("/")


def test_duracao_total_e_preservada(tmp_path):
    raiz = tmp_path / "corpus"; raiz.mkdir()
    _manifesto(raiz / "m.jsonl.gz", [_cut("a", raiz, 3600.0), _cut("b", raiz, 1800.0)])
    r = EX.relativizar(raiz, raiz / "m.jsonl.gz", raiz / "out.jsonl.gz")
    assert r["horas"] == pytest.approx(1.5)


def test_caminho_fora_da_raiz_e_contado_nao_falsificado(tmp_path):
    """Relativizar o que não está sob a raiz produziria um manifesto que PARECE portável.

    Ele falharia na primeira leitura, na outra máquina, depois do upload. Contar é o
    único jeito honesto: o chamador decide, sabendo.
    """
    raiz = tmp_path / "corpus"; raiz.mkdir()
    fora = _cut("c", raiz)
    fora["features"]["storage_path"] = "/algum/outro/lugar/feats.lca"
    _manifesto(raiz / "m.jsonl.gz", [fora])

    r = EX.relativizar(raiz, raiz / "m.jsonl.gz", raiz / "out.jsonl.gz")
    assert r["fora_da_raiz"] == 1
    cut = json.loads(gzip.open(raiz / "out.jsonl.gz", "rt", encoding="utf-8").readline())
    assert cut["features"]["storage_path"] == "/algum/outro/lugar/feats.lca", \
        "o caminho de fora foi reescrito e o manifesto ficou mentindo"


def test_caminho_ja_relativo_e_deixado_em_paz(tmp_path):
    raiz = tmp_path / "corpus"; raiz.mkdir()
    c = _cut("a", raiz)
    c["features"]["storage_path"] = "feats_train_000.lca"
    _manifesto(raiz / "m.jsonl.gz", [c])
    r = EX.relativizar(raiz, raiz / "m.jsonl.gz", raiz / "out.jsonl.gz")
    assert r["relativizados"] == 1   # só o recording; a feature já estava relativa


def test_card_nao_afirma_taxa_de_retencao():
    """Este script vê só o manifesto final, que já é o que sobrou.

    Afirmar quantos por cento sobreviveram seria publicar uma medição que ninguém fez.
    """
    texto = EX.CARD.format(nome="x", horas=1.0)
    assert "cc-by-nc-sa-4.0" in texto
    assert "22.7%" in texto, "a divergência medida entre professores precisa estar no card"
    assert "not verified by a human" in texto
    assert "%  of utterances survived" not in texto
