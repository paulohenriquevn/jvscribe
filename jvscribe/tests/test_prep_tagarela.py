"""Contrato do prep_tagarela (fase de dados de M5, D4 — mux CORAA+TAGARELA).

Cobre (revisão de corpus 2026-07-28):
  - reuso (não duplicação) do normalize_ptbr e alinhamento de texto ao CORAA;
  - AUSÊNCIA estrutural de qualquer capacidade de emitir split dev/test (§7.3);
  - F3: filtro determinístico de alucinação de pseudo-label (repetição + char/s);
  - F4: downmix efetivo para MONO (podcast estéreo → 1 canal);
  - F8: teste comportamental com parquet+FLAC sintéticos — manifest, não-vazamento de id
    (tagarela_* disjunto de coraa_* gerado de fato), só `tagarela_cuts_train` escrito."""

from __future__ import annotations

import inspect
import io
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("lhotse", reason="lhotse não instalado")
pytest.importorskip("pyarrow", reason="pyarrow não instalado")
pytest.importorskip("soundfile", reason="soundfile não instalado")
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import soundfile as sf  # noqa: E402

import prep_coraa  # noqa: E402
import prep_icefall  # noqa: E402
import prep_tagarela  # noqa: E402


# ---------------------------------------------------------------- fixtures sintéticas

def _flac_bytes(seconds=2.0, sr=16000, channels=1) -> bytes:
    n = int(seconds * sr)
    rng = np.random.default_rng(0)
    arr = (rng.standard_normal((n, channels)) * 0.1).astype("float32")
    if channels == 1:
        arr = arr[:, 0]
    buf = io.BytesIO()
    sf.write(buf, arr, sr, format="FLAC")
    return buf.getvalue()


def _write_parquet(path, rows):
    """rows: list de (flac_bytes, sentence, accent, rel_path)."""
    audio_type = pa.struct([("bytes", pa.binary()), ("path", pa.string())])
    audio = pa.array([{"bytes": b, "path": p} for (b, _, _, p) in rows], type=audio_type)
    table = pa.table({
        "audio": audio,
        "sentence": pa.array([s for (_, s, _, _) in rows]),
        "accent": pa.array([a for (_, _, a, _) in rows]),
        "path": pa.array([p for (_, _, _, p) in rows]),
    })
    pq.write_table(table, str(path))


def _canonical_rows():
    """Uma linha por caminho de filtro + 2 válidas (1 estéreo, 1 mono)."""
    return [
        (_flac_bytes(3.0, 16000, 2), "olá isso é um teste do tagarela em português hoje",
         "pt-br", "showA/ep01/seg0.flac"),                         # válida ESTÉREO → kept
        (_flac_bytes(3.0, 16000, 1), "outro exemplo de fala espontânea gravada aqui agora",
         "pt-br", "showB/ep02/seg0.flac"),                         # válida MONO   → kept
        (_flac_bytes(3.0, 16000, 1), "isto está em português europeu",
         "pt-pt", "showC/ep03/seg0.flac"),                         # accent errado → drop
        (_flac_bytes(3.0, 16000, 1), "   ", "pt-br", "showA/ep01/seg1.flac"),  # vazio → drop
        (_flac_bytes(3.0, 16000, 1), "obrigado obrigado obrigado obrigado obrigado",
         "pt-br", "showA/ep01/seg2.flac"),                         # alucinação → drop
        (_flac_bytes(6.0, 16000, 1), "oi", "pt-br", "showB/ep02/seg1.flac"),   # cps baixo → drop
    ]


# ---------------------------------------------------------------- reuso / constantes

def test_reusa_normalize_do_prep_icefall_sem_duplicar():
    # audit D2: normalize_ptbr NÃO deve ser reimplementado aqui — vem do prep_icefall
    assert prep_tagarela.PI is prep_icefall
    assert not hasattr(prep_tagarela, "normalize_ptbr")


def test_target_sr_16k():
    assert prep_tagarela.TARGET_SR == 16000


def test_accent_keep_e_pt_br():
    assert prep_tagarela.ACCENT_KEEP == "pt-br"


def test_cut_id_prefix_disjunto_do_coraa():
    assert prep_tagarela.CUT_ID_PREFIX.startswith("tagarela_")
    assert not prep_tagarela.CUT_ID_PREFIX.startswith("coraa_")


def test_funcoes_do_contrato_existem():
    for fn in ("iter_parquet_shards", "build_split", "prepare", "main",
               "is_hallucinated_text", "show_key"):
        assert callable(getattr(prep_tagarela, fn))


# ---------------------------------------------------------------- invariante §7.3

def test_so_o_manifest_de_train_e_escrito_nunca_dev_test():
    """Invariante estrutural §7.3 corrigido (F8): a garantia real é o filename hardcoded
    `tagarela_cuts_train.jsonl.gz` e a ausência de parâmetro de split — não o substring
    'dev' (que casa 'development' etc.). Assertamos a fonte do módulo diretamente."""
    src = inspect.getsource(prep_tagarela)
    assert "tagarela_cuts_train.jsonl.gz" in src
    assert "cuts_dev" not in src and "cuts_test" not in src
    assert 'add_argument("--split"' not in src and "add_argument('--split'" not in src


def test_main_nao_aceita_argumento_de_split(monkeypatch, tmp_path):
    argv = ["prep_tagarela.py", "--out", str(tmp_path), "--parquet-dir", str(tmp_path),
            "--split", "test"]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        prep_tagarela.main()


def test_iter_parquet_shards_falha_alto_quando_dir_vazio(tmp_path):
    with pytest.raises(FileNotFoundError):
        prep_tagarela.iter_parquet_shards(tmp_path)


# ---------------------------------------------------------------- F3: alucinação

def test_hallucination_repeticao_consecutiva():
    assert prep_tagarela.is_hallucinated_text("obrigado obrigado obrigado obrigado")


def test_hallucination_loop_de_bigrama():
    assert prep_tagarela.is_hallucinated_text("a b a b a b a b a b")


def test_texto_legitimo_nao_e_alucinacao():
    assert not prep_tagarela.is_hallucinated_text(
        "o brasil é um país de dimensões continentais com muita diversidade cultural")


def test_texto_curto_nao_e_alucinacao():
    # < REP_MIN_WORDS palavras e sem repetição consecutiva → não dispara
    assert not prep_tagarela.is_hallucinated_text("bom dia a todos")


def test_hallucination_run_de_caractere():
    # regressão: alucinação char-level do Whisper (visto no treino de M5) — o filtro
    # de PALAVRA não pega, o de CHAR-RUN sim. Casos reais que poluíam o mux.
    assert prep_tagarela.is_hallucinated_text("mãe bêêêêêêêêêêêêêêêêêêêêêê")
    assert prep_tagarela.is_hallucinated_text("peça nos de gása vamos de gó uêêêêêêêêêê")
    assert prep_tagarela.is_hallucinated_text("aaaaaaaa")


def test_hallucination_palavra_longa_demais():
    assert prep_tagarela.is_hallucinated_text("supercalifragilisticexpialidociousmuitomaislongo")


def test_elongacao_enfatica_legitima_nao_e_alucinacao():
    # fala espontânea tem elongação enfática curta ("siim", "nãão") — CHAR_RUN_MAX=6 não derruba
    assert not prep_tagarela.is_hallucinated_text("siim claro nãão sei")
    assert not prep_tagarela.is_hallucinated_text("carro passar coelho")  # duplas legítimas


def test_show_key_pega_primeiro_segmento():
    assert prep_tagarela.show_key("showA/ep01/seg0.flac") == "showA"
    assert prep_tagarela.show_key("/showA/ep01") == "showA"
    assert prep_tagarela.show_key("") == "<unknown>"


# ---------------------------------------------------------------- F8: comportamental

def test_build_split_filtra_e_conta_por_categoria(tmp_path):
    """Cada filtro exclui exatamente a linha esperada; contadores expostos no stats."""
    _write_parquet(tmp_path / "shard0.parquet", _canonical_rows())
    recs, sups, stats = prep_tagarela.build_split(
        prep_tagarela.iter_parquet_shards(tmp_path), tmp_path / "wav", limit=None)
    assert stats["kept"] == 2
    assert stats["wrong_accent"] == 1
    assert stats["empty"] == 1
    assert stats["hallucination"] == 1
    assert stats["bad_ratio"] == 1
    assert len(recs) == len(sups) == 2


def test_build_split_faz_downmix_para_mono(tmp_path):
    """F4: a linha 0 é FLAC ESTÉREO; o wav gravado deve ser MONO (1 canal)."""
    _write_parquet(tmp_path / "shard0.parquet", _canonical_rows())
    recs, _, _ = prep_tagarela.build_split(
        prep_tagarela.iter_parquet_shards(tmp_path), tmp_path / "wav", limit=None)
    assert all(r.num_channels == 1 for r in recs)


def test_ids_gerados_sao_disjuntos_dos_ids_gerados_do_coraa(tmp_path):
    """F1/F8: os ids REALMENTE gerados (não só a constante) não colidem com o padrão de
    id do CORAA — impede substituição silenciosa no `--use-mux`."""
    _write_parquet(tmp_path / "shard0.parquet", _canonical_rows())
    recs, _, _ = prep_tagarela.build_split(
        prep_tagarela.iter_parquet_shards(tmp_path), tmp_path / "wav", limit=None)
    tag_ids = {r.id for r in recs}
    coraa_ids = {f"coraa_train_{i:07d}" for i in range(len(recs))}
    assert tag_ids.isdisjoint(coraa_ids)
    assert all(rid.startswith("tagarela_train_") for rid in tag_ids)


def test_prepare_emite_so_manifest_de_train_com_texto_normalizado_como_coraa(tmp_path):
    """test_tagarela_manifest_and_no_test_leak (Task 0.3): comportamento de `build_split`
    (filtro/mono/id/normalize) + manifest só de train. Exercita NOSSO código, não o
    `compute_and_store_features` do lhotse (plumbing, testado pelo lhotse e frágil ao env
    de áudio local — memória baseline-python-env-quirks)."""
    from lhotse import CutSet, RecordingSet, SupervisionSet, load_manifest_lazy
    _write_parquet(tmp_path / "shard0.parquet", _canonical_rows())
    recs, sups, stats = prep_tagarela.build_split(
        prep_tagarela.iter_parquet_shards(tmp_path), tmp_path / "wav", limit=None)

    # filtro (F3): 6 linhas → 2 mantidas; cada caminho de descarte contado
    assert stats["kept"] == 2
    assert stats["empty"] == 1 and stats["wrong_accent"] == 1
    assert stats["hallucination"] == 1 and stats["bad_ratio"] == 1
    # downmix MONO efetivo (F4): a linha estéreo vira 1 canal
    assert all(r.num_channels == 1 for r in recs)
    # ids tagarela_train_* disjuntos do padrão coraa_* (não-vazamento por id, F1/F8)
    assert all(r.id.startswith("tagarela_train_") for r in recs)
    assert not any(r.id.startswith("coraa_") for r in recs)
    # normalize IDÊNTICO à convenção do CORAA (mesma função reusada)
    got = sorted(sp.text for sp in sups)
    expected = sorted(prep_coraa.PI.normalize_ptbr(s) for s in (
        "olá isso é um teste do tagarela em português hoje",
        "outro exemplo de fala espontânea gravada aqui agora"))
    assert got == expected
    # cobertura F7: show_counts populado por show (showA/showB), não por segmento
    assert set(stats["show_counts"]) == {"showA", "showB"}

    # manifest SÓ de train, sem features (evita o compute env-frágil): só tagarela_cuts_train
    out = tmp_path / "out"
    out.mkdir()
    cuts = CutSet.from_manifests(
        recordings=RecordingSet.from_recordings(recs),
        supervisions=SupervisionSet.from_segments(sups))
    cuts.to_file(str(out / "tagarela_cuts_train.jsonl.gz"))
    assert (out / "tagarela_cuts_train.jsonl.gz").exists()
    assert len(list(load_manifest_lazy(str(out / "tagarela_cuts_train.jsonl.gz")))) == 2
    # NENHUM manifesto dev/test materializado (pseudo nunca no anchor de eval — §7.3)
    assert not list(out.glob("*cuts_dev*")) and not list(out.glob("*cuts_test*"))


def test_prepare_falha_alto_quando_tudo_filtrado(tmp_path):
    """Fail-fast: se nada sobra (todos pt-pt), erro claro em vez de manifesto vazio."""
    from lhotse import Fbank, FbankConfig
    rows = [(_flac_bytes(2.0, 16000, 1), "só português europeu", "pt-pt", "x/y.flac")]
    _write_parquet(tmp_path / "shard0.parquet", rows)
    out = tmp_path / "out"; out.mkdir()
    with pytest.raises(RuntimeError):
        prep_tagarela.prepare(tmp_path, out, Fbank(FbankConfig(num_mel_bins=80)), 1, None)


# ── Perda de dado no corpus de TREINO não pode ser silenciosa ────────────────────────────

def test_decode_error_em_massa_falha_alto(monkeypatch, tmp_path):
    """Um shard truncado no download derrubaria a maioria das utterances.

    Antes, o pipeline imprimia a contagem numa linha de log e seguia montando o corpus com o
    que sobrou — o efeito só apareceria como WER pior no fim de um run de GPU pago.
    """
    import prep_tagarela as PT

    _write_parquet(tmp_path / "shard0.parquet",
                   [(_flac_bytes(1.0, 16000, 1), "oi", "pt-br", "s/a.flac")])
    stats = {"total": 1000, "kept": 400, "empty": 0, "wrong_accent": 0,
             "hallucination": 0, "bad_ratio": 0, "decode_error": 600, "show_counts": {}}
    monkeypatch.setattr(PT, "build_split", lambda *a, **k: ([], [], stats))
    with pytest.raises(RuntimeError, match="falharam ao decodificar"):
        PT.prepare(tmp_path, tmp_path, extractor=None, num_jobs=1, limit=None)


def test_alguns_flacs_corrompidos_nao_derrubam_o_run(monkeypatch, tmp_path):
    """O caso legítimo: perda pontual segue sendo fail-soft por item.

    O limiar existe para separar "shard quebrado" de "alguns arquivos ruins" — se ele
    disparasse com 1%, o pipeline ficaria inutilizável no caso normal.
    """
    import prep_tagarela as PT

    _write_parquet(tmp_path / "shard0.parquet",
                   [(_flac_bytes(1.0, 16000, 1), "oi", "pt-br", "s/a.flac")])
    stats = {"total": 1000, "kept": 990, "empty": 0, "wrong_accent": 0,
             "hallucination": 0, "bad_ratio": 0, "decode_error": 10, "show_counts": {}}
    monkeypatch.setattr(PT, "build_split", lambda *a, **k: ([], [], stats))
    # Roda até o fim: 1% de perda é o caso normal e não pode abortar o pipeline.
    PT.prepare(tmp_path, tmp_path, extractor=None, num_jobs=1, limit=None)



# A guarda de `except` largo virou `test_erros_nao_engolidos.py`, do PACOTE inteiro —
# a mesma classe apareceu em `common/audio/codecs.py`. Escopar por arquivo era DRY ao contrário.


# ── Preparação em LOTES: o pico de disco não pode crescer com o corpus ───────────────────
#
# `build_split` grava um .wav por utterance mantida — ~115 MB por hora de áudio `[MEDIDO]`.
# Num lote único isso é disco proporcional ao corpus INTEIRO: ~170 GB em 1.500 h, contra os
# 236 GB do disco de sessão do Colab, que ainda precisa hospedar os parquets e as features.
# Processar em lotes bounda o pico ao lote.

def _dois_shards(tmp_path, por_shard=2):
    for i in range(2):
        rows = [(_flac_bytes(1.0, 16000, 1), f"frase {i}{j}", "pt-br", f"show{i}/a{j}.flac")
                for j in range(por_shard)]
        _write_parquet(tmp_path / f"shard{i}.parquet", rows)


def test_id_offset_torna_os_ids_unicos_entre_lotes(tmp_path):
    """Sem offset, cada lote reinicia em `tagarela_00000000`.

    O CutSet concatenado ficaria com ids duplicados — o lhotse não reclama, e a mesma
    utterance entraria duas vezes no treino. Silenciosamente.
    """
    _dois_shards(tmp_path)
    shards = prep_tagarela.iter_parquet_shards(tmp_path)
    recs_a, _, st_a = prep_tagarela.build_split([shards[0]], tmp_path / "w", None, id_offset=0)
    recs_b, _, _ = prep_tagarela.build_split(
        [shards[1]], tmp_path / "w", None, id_offset=st_a["kept"])

    ids_a = {r.id for r in recs_a}
    ids_b = {r.id for r in recs_b}
    assert ids_a and ids_b
    assert not (ids_a & ids_b), f"ids colidiram entre lotes: {sorted(ids_a & ids_b)}"


def test_lotes_produzem_o_mesmo_corpus_que_um_lote_unico(tmp_path):
    """Lotear é decisão de memória, não de conteúdo: o manifesto tem de ser o mesmo."""
    from lhotse import CutSet, Fbank, FbankConfig

    src = tmp_path / "src"; src.mkdir()
    _dois_shards(src, por_shard=2)
    ext = Fbank(FbankConfig(num_mel_bins=80))

    inteiro = tmp_path / "inteiro"; inteiro.mkdir()
    prep_tagarela.prepare(src, inteiro, ext, num_jobs=1, limit=None)

    loteado = tmp_path / "loteado"; loteado.mkdir()
    prep_tagarela.prepare(src, loteado, ext, num_jobs=1, limit=None, shards_per_batch=1)

    a = CutSet.from_file(str(inteiro / "tagarela_cuts_train.jsonl.gz"))
    b = CutSet.from_file(str(loteado / "tagarela_cuts_train.jsonl.gz"))
    # O id do CUT carrega o índice dentro do CutSet que o originou, e esse índice reinicia
    # a cada lote. O que precisa bater — e o que o treino consome — é o conjunto de
    # RECORDINGS e a duração total.
    assert sorted(c.recording_id for c in a) == sorted(c.recording_id for c in b)
    assert len(set(b.ids)) == len(list(b.ids)), "ids duplicados no manifesto loteado"
    assert round(sum(c.duration for c in a), 3) == round(sum(c.duration for c in b), 3)


def test_drop_audio_apaga_os_wav_e_preserva_as_features(tmp_path):
    """O áudio só some DEPOIS das features; o manifesto continua utilizável para treino."""
    from lhotse import CutSet, Fbank, FbankConfig

    src = tmp_path / "src"; src.mkdir()
    _dois_shards(src, por_shard=2)
    out = tmp_path / "out"; out.mkdir()
    prep_tagarela.prepare(src, out, Fbank(FbankConfig(num_mel_bins=80)), num_jobs=1,
                          limit=None, shards_per_batch=1, drop_audio=True)

    assert not (out / "wav_train").exists() or not list((out / "wav_train").glob("*.wav"))
    cuts = CutSet.from_file(str(out / "tagarela_cuts_train.jsonl.gz"))
    assert len(cuts) == 4
    assert next(iter(cuts)).load_features().shape[1] == 80


def test_guarda_de_decode_dispara_no_lote_antes_do_fbank(tmp_path):
    """Descobrir um shard truncado só no total custaria horas de extração em 1.500 h."""
    stats = {"total": 1000, "kept": 400, "empty": 0, "wrong_accent": 0,
             "hallucination": 0, "bad_ratio": 0, "decode_error": 600, "show_counts": {}}
    with pytest.raises(RuntimeError, match="lote 1/1: 600/1000"):
        prep_tagarela._guarda_decode(stats, "lote 1/1")


def test_drop_audio_sem_lote_e_recusado(tmp_path, monkeypatch):
    """Com um lote único o áudio só sairia no fim — quando o pico de disco já aconteceu."""
    monkeypatch.setattr(sys, "argv",
                        ["prep_tagarela.py", "--parquet-dir", str(tmp_path),
                         "--drop-audio-after-features"])
    with pytest.raises(SystemExit, match="não economiza nada"):
        prep_tagarela.main()
