"""`download_shard` — o cache que evita rebaixar 500 h, e o token que não pode vazar.

Era a única função de I/O deste módulo sem nenhuma linha exercitada. O que ela decide antes de
tocar a rede é testável sem rede: pular o que já está em disco, montar a URL do shard e anexar
o `Authorization` só quando há token.

O caso do arquivo TRUNCADO é o que dói: um download interrompido deixa um `.parquet` de 0 bytes.
Se `download_shard` o tratasse como cache válido, o `prep_tagarela` leria um shard vazio e o
manifesto sairia menor sem ninguém notar — treino com menos dados do que se acredita ter.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from finetune.download_tagarela_subset import download_shard, select_indices

PADRAO = "data/train-{i:05d}-of-{total:05d}.parquet"


class _Curl:
    """Dublê de `subprocess.run` que registra o comando em vez de executá-lo."""

    def __init__(self) -> None:
        self.cmds: list[list[str]] = []

    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"parquet")
        return None


@pytest.fixture()
def curl(monkeypatch):
    c = _Curl()
    monkeypatch.setattr("finetune.download_tagarela_subset.subprocess.run", c)
    return c


def test_shard_ja_baixado_nao_e_rebaixado(curl, tmp_path):
    """Sem o cache, retomar uma corrida interrompida rebaixa centenas de GB."""
    destino = tmp_path / "train-00007-of-01764.parquet"
    destino.write_bytes(b"ja estava aqui")

    assert download_shard(7, 1764, PADRAO, tmp_path, token="") == destino
    assert curl.cmds == [], "rebaixou um shard que já estava em disco"
    assert destino.read_bytes() == b"ja estava aqui"


def test_arquivo_truncado_e_rebaixado_em_vez_de_aceito(curl, tmp_path):
    """0 byte é download interrompido, não cache.

    Aceitá-lo faria `prep_tagarela` ler um shard vazio: o manifesto sai menor e o treino roda
    com menos dados do que se acredita ter — sem erro nenhum.
    """
    truncado = tmp_path / "train-00007-of-01764.parquet"
    truncado.write_bytes(b"")

    download_shard(7, 1764, PADRAO, tmp_path, token="")
    assert len(curl.cmds) == 1, "aceitou um arquivo de 0 byte como cache"


def test_url_aponta_o_shard_pedido(curl, tmp_path):
    download_shard(42, 1764, PADRAO, tmp_path, token="")
    url = next(a for a in curl.cmds[0] if a.startswith("https://"))
    assert "train-00042-of-01764.parquet" in url


def test_token_so_entra_quando_existe(curl, tmp_path):
    download_shard(1, 1764, PADRAO, tmp_path, token="")
    assert not any("Authorization" in a for a in curl.cmds[0])

    download_shard(2, 1764, PADRAO, tmp_path, token="segredo")
    assert any(a == "Authorization: Bearer segredo" for a in curl.cmds[1])


def test_falha_de_http_sobe_em_vez_de_deixar_arquivo_pela_metade(monkeypatch, tmp_path):
    """`curl -f` + `check=True`: 404 vira exceção, não um shard silenciosamente ausente."""
    import subprocess

    def explode(cmd, **kw):
        raise subprocess.CalledProcessError(22, cmd)

    monkeypatch.setattr("finetune.download_tagarela_subset.subprocess.run", explode)
    with pytest.raises(subprocess.CalledProcessError):
        download_shard(1, 1764, PADRAO, tmp_path, token="")


class TestSelectIndices:
    """A amostragem estratificada — baixar 120 de 1764 shards SEM viés de posição."""

    def test_cobre_as_duas_pontas(self):
        idx = select_indices(1764, 120)
        assert idx[0] == 0 and idx[-1] == 1763, (
            "amostra que não toca as pontas enviesa o subset para o meio do corpus"
        )

    def test_devolve_indices_unicos_e_ordenados(self):
        idx = select_indices(1764, 120)
        assert idx == sorted(set(idx))

    def test_pedir_tudo_devolve_tudo(self):
        assert select_indices(10, 10) == list(range(10))

    def test_pedir_mais_do_que_existe_nao_inventa_shard(self):
        assert select_indices(5, 50) == list(range(5))

    def test_um_shard_pega_o_primeiro(self):
        assert select_indices(1764, 1) == [0]
