"""Contrato do orquestrador que baixa e prepara o TAGARELA em ciclos.

O ganho que este script existe para dar é de DISCO: baixar 157 shards de uma vez deixa
107,7 GB de parquet parados até o fim da extração, e numa sessão do Colab com 117,5 GB
livres `[MEDIDO]` isso baixa o teto do corpus de 2.523 h para 800 h. Ciclar download e
preparação torna o parquet vivo o de um grupo.

O que os testes protegem:
  - id de cut único ENTRE ciclos (o lhotse aceita duplicata em silêncio);
  - o parquet só some depois das features do grupo;
  - retomada: ciclo com manifesto não rebaixa, e o transcript ainda sai completo —
    ele treina o BPE, e montá-lo do acumulado em memória cegaria o tokenizer para os
    ciclos que a sessão anterior preparou.
"""

from __future__ import annotations

import io
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "finetune"))

pytest.importorskip("lhotse", reason="lhotse não instalado")
pytest.importorskip("pyarrow", reason="pyarrow não instalado")
pytest.importorskip("soundfile", reason="soundfile não instalado")
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import soundfile as sf  # noqa: E402
from lhotse import CutSet  # noqa: E402

import prepare_corpus_streaming as ST  # noqa: E402


def _flac(seconds=1.0, sr=16000) -> bytes:
    arr = (np.random.default_rng(0).standard_normal(int(seconds * sr)) * 0.1).astype("float32")
    buf = io.BytesIO()
    sf.write(buf, arr, sr, format="FLAC")
    return buf.getvalue()


def _parquet(path, n, show):
    audio_type = pa.struct([("bytes", pa.binary()), ("path", pa.string())])
    rows = [(_flac(), f"frase numero {j}", "pt-br", f"{show}/a{j}.flac") for j in range(n)]
    pq.write_table(pa.table({
        "audio": pa.array([{"bytes": b, "path": p} for (b, _, _, p) in rows], type=audio_type),
        "sentence": pa.array([s for (_, s, _, _) in rows]),
        "accent": pa.array([a for (_, _, a, _) in rows]),
        "path": pa.array([p for (_, _, _, p) in rows]),
    }), str(path))


@pytest.fixture
def rede_falsa(monkeypatch):
    """Substitui o download por escrita local de parquet sintético.

    O teste é do CICLO (offset, ordem de remoção, retomada), não do curl.
    """
    baixados = []

    def _fake(i, total, pattern, out, token):
        dest = out / f"train-{i:05d}-of-{total:05d}.parquet"
        _parquet(dest, n=2, show=f"show{i}")
        baixados.append(i)
        return dest

    monkeypatch.setattr(ST.DL, "download_shard", _fake)
    return baixados


def _args(out, **kw):
    import argparse
    d = dict(out=str(out), horas_alvo=40.0, shards_por_ciclo=2, shards_por_lote=1,
             num_jobs=1, total_shards=8, pattern=ST.DL.SHARD_PATTERN, token="")
    d.update(kw)
    return argparse.Namespace(**d)


# ── dimensionamento ─────────────────────────────────────────────────────────────────────

def test_shards_para_horas_usa_a_taxa_medida():
    assert ST.shards_para_horas(296.8) == 31
    assert ST.shards_para_horas(1500) == 157


def test_horas_alvo_nao_positivo_falha_alto():
    with pytest.raises(ValueError, match="horas-alvo"):
        ST.shards_para_horas(0)


def test_ciclo_de_tamanho_invalido_falha_alto():
    with pytest.raises(ValueError, match="shards-por-ciclo"):
        ST.grupos([1, 2, 3], 0)


def test_grupos_cobrem_todos_os_indices_sem_repetir():
    g = ST.grupos(list(range(7)), 3)
    assert [len(x) for x in g] == [3, 3, 1]
    assert sorted(i for x in g for i in x) == list(range(7))


# ── o invariante que o lhotse não protege ───────────────────────────────────────────────

def test_ids_sao_unicos_entre_ciclos(tmp_path, rede_falsa, monkeypatch):
    """Cada ciclo continua a contagem do anterior.

    Sem isso o manifesto consolidado teria `tagarela_00000000` várias vezes: o lhotse não
    reclama, e a mesma utterance entraria no treino uma vez por ciclo.
    """
    monkeypatch.setattr(sys, "argv", ["x"])
    monkeypatch.setattr(ST.argparse.ArgumentParser, "parse_args",
                        lambda self: _args(tmp_path))
    ST.main()
    cuts = CutSet.from_file(str(tmp_path / "tagarela_cuts_train.jsonl.gz"))
    recs = [c.recording_id for c in cuts]
    assert len(recs) == 8, recs          # 4 shards × 2 utts
    assert len(set(recs)) == len(recs), "ids colidiram entre ciclos"


def test_parquet_do_ciclo_e_apagado_e_a_feature_sobrevive(tmp_path, rede_falsa, monkeypatch):
    """O parquet é o item que domina o pico; ele tem de sair. A feature é o que fica."""
    monkeypatch.setattr(ST.argparse.ArgumentParser, "parse_args",
                        lambda self: _args(tmp_path))
    ST.main()
    assert not list(tmp_path.glob("raw_*")), "parquet do ciclo não foi apagado"
    cuts = CutSet.from_file(str(tmp_path / "tagarela_cuts_train.jsonl.gz"))
    assert next(iter(cuts)).load_features().shape[1] == 80


def test_retomada_nao_rebaixa_e_ainda_escreve_o_transcript_completo(
        tmp_path, rede_falsa, monkeypatch):
    """Sessão do Colab morre no meio; reexecutar não pode custar os GB já baixados.

    E o `transcript_words.txt` — que treina o BPE — tem de sair COMPLETO, incluindo os
    ciclos retomados, que não devolvem texto porque não rodaram nesta execução.
    """
    monkeypatch.setattr(ST.argparse.ArgumentParser, "parse_args",
                        lambda self: _args(tmp_path))
    ST.main()
    linhas_1 = (tmp_path / "transcript_words.txt").read_text(encoding="utf-8").splitlines()

    rede_falsa.clear()
    ST.main()
    linhas_2 = (tmp_path / "transcript_words.txt").read_text(encoding="utf-8").splitlines()

    assert rede_falsa == [], f"rebaixou shards já preparados: {rede_falsa}"
    assert linhas_2 == linhas_1
    assert len(linhas_2) == 8


def test_id_duplicado_no_consolidado_falha_alto(tmp_path, rede_falsa, monkeypatch):
    """A checagem final existe porque o modo de falha é silencioso.

    Se o offset entre ciclos quebrar, nada no lhotse avisa — o treino apenas veria a mesma
    utterance mais de uma vez. A guarda transforma isso em erro.
    """
    monkeypatch.setattr(ST.argparse.ArgumentParser, "parse_args",
                        lambda self: _args(tmp_path))
    real = ST.ciclo
    monkeypatch.setattr(ST, "ciclo",
                        lambda *a, **k: {**real(*a[:5], 0), "retomado": False})
    with pytest.raises(RuntimeError, match="ids duplicados"):
        ST.main()


# ── Rede instável: 157 downloads de ~690 MB não chegam todos na primeira tentativa ──────

def test_shard_perdido_nao_derruba_o_ciclo_mas_fica_registrado(tmp_path, monkeypatch):
    """Um shard vale ~9,6 h de 1.500 — 0,6%. Abortar 14 ciclos por isso é desproporcional.

    Mas perder shard também não pode ser invisível: o corpus fica menor que o alvo, e
    quem ler o manifesto depois precisa saber disso sem depender do scrollback.
    """
    import subprocess as sp
    chamadas = []

    def _falha_uma(i, total, pattern, out, token):
        chamadas.append(i)
        if i == chamadas[0] and len(chamadas) == 1:
            raise sp.CalledProcessError(92, ["curl"])
        dest = out / f"train-{i:05d}-of-{total:05d}.parquet"
        _parquet(dest, n=2, show=f"show{i}")
        return dest

    monkeypatch.setattr(ST.DL, "download_shard", _falha_uma)
    monkeypatch.setattr(ST.argparse.ArgumentParser, "parse_args", lambda self: _args(tmp_path))
    ST.main()

    nota = (tmp_path / "shards_perdidos.txt").read_text(encoding="utf-8")
    assert "1/4 shards perdidos" in nota
    cuts = CutSet.from_file(str(tmp_path / "tagarela_cuts_train.jsonl.gz"))
    assert len(cuts) == 6, "os 3 shards que chegaram deveriam ter sido preparados"


def test_perda_em_massa_aborta_em_vez_de_montar_corpus_com_buraco(tmp_path, monkeypatch):
    """Metade do grupo falhando é a rede fora, não shard ruim."""
    import subprocess as sp

    def _falha_tudo(i, total, pattern, out, token):
        raise sp.CalledProcessError(92, ["curl"])

    monkeypatch.setattr(ST.DL, "download_shard", _falha_tudo)
    monkeypatch.setattr(ST.argparse.ArgumentParser, "parse_args", lambda self: _args(tmp_path))
    with pytest.raises(RuntimeError, match="shards perdidos"):
        ST.main()


def test_run_sem_perda_nao_escreve_o_registro(tmp_path, rede_falsa, monkeypatch):
    """O arquivo é um aviso; existir sem motivo o esvazia de significado."""
    monkeypatch.setattr(ST.argparse.ArgumentParser, "parse_args", lambda self: _args(tmp_path))
    ST.main()
    assert not (tmp_path / "shards_perdidos.txt").exists()


# ── O plano de shards não pode mudar entre execuções de uma mesma --out ──────────────────

def test_plano_e_gravado_no_primeiro_run(tmp_path, rede_falsa, monkeypatch):
    monkeypatch.setattr(ST.argparse.ArgumentParser, "parse_args", lambda self: _args(tmp_path))
    ST.main()
    plano = (tmp_path / "plano_de_shards.txt").read_text(encoding="utf-8").strip()
    assert plano == ",".join(str(i) for i in ST.DL.select_indices(8, 4))


def test_mudar_o_alvo_no_meio_falha_em_vez_de_misturar_dois_planos(
        tmp_path, rede_falsa, monkeypatch):
    """A retomada pula ciclo por NOME de manifesto, não por conteúdo.

    Com outro `--horas-alvo`, `select_indices` escolhe outros shards; os ciclos prontos
    continuariam sendo pulados enquanto guardam shards que o novo plano não pediu. O
    corpus sairia metade de um plano e metade de outro, e a lista de auditoria descreveria
    só uma das metades.
    """
    monkeypatch.setattr(ST.argparse.ArgumentParser, "parse_args", lambda self: _args(tmp_path))
    ST.main()

    monkeypatch.setattr(ST.argparse.ArgumentParser, "parse_args",
                        lambda self: _args(tmp_path, horas_alvo=70.0))
    with pytest.raises(RuntimeError, match="alvo mudou entre execuções"):
        ST.main()


def test_retomar_com_o_mesmo_alvo_passa_pela_trava(tmp_path, rede_falsa, monkeypatch):
    """A trava protege contra plano trocado, não contra retomada legítima."""
    monkeypatch.setattr(ST.argparse.ArgumentParser, "parse_args", lambda self: _args(tmp_path))
    ST.main()
    rede_falsa.clear()
    ST.main()
    assert rede_falsa == []
