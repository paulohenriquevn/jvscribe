"""Contrato do prep_coraa (fase de dados de M5). A correção de I/O (unzip+wav+fbank) é
verificada por execução real na instância; aqui garantimos o contrato do módulo, o reuso
(não duplicação) do normalize_ptbr e o guarda-corpo do invariante de eval (§7.3)."""

from __future__ import annotations

import csv
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("lhotse", reason="lhotse não instalado")
import prep_coraa  # noqa: E402


def test_reusa_normalize_do_prep_icefall_sem_duplicar():
    # audit D2: normalize_ptbr NÃO deve ser reimplementado aqui — vem do prep_icefall
    import prep_icefall
    assert prep_coraa.PI is prep_icefall
    assert not hasattr(prep_coraa, "normalize_ptbr")  # não redefinido no prep_coraa


def test_target_sr_16k():
    # fbank misturando taxa de amostragem é bug; CORAA deve casar com o treino (16k)
    assert prep_coraa.TARGET_SR == 16000


def test_funcoes_do_contrato_existem():
    for fn in ("read_rows", "build_split", "prepare", "main"):
        assert callable(getattr(prep_coraa, fn))


def test_read_rows_le_csv_sem_pandas(tmp_path):
    # o env da instância não tem pandas; o loader deve usar csv puro
    meta = tmp_path / "metadata_dev_final.csv"
    with meta.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file_path", "text", "up_votes", "down_votes"])
        w.writeheader()
        w.writerow({"file_path": "dev/sp/1_sp_.wav", "text": "é é é bom", "up_votes": "2", "down_votes": "0"})
    rows = list(prep_coraa.read_rows(tmp_path, "dev"))
    assert len(rows) == 1
    assert rows[0]["text"] == "é é é bom"


def test_read_rows_falha_alto_quando_csv_ausente(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(prep_coraa.read_rows(tmp_path, "test"))


def test_min_net_votes_proibido_no_anchor_de_eval(monkeypatch, tmp_path):
    # invariante §7.3: filtro de voto não pode tocar dev/test (anchor comparável ao benchmark)
    argv = ["prep_coraa.py", "--audio-root", str(tmp_path), "--meta-dir", str(tmp_path),
            "--splits", "test", "--min-net-votes", "1"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        prep_coraa.main()
