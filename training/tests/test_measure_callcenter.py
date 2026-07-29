"""Testes do parser/normalizador do medidor de call center (lógica pura, sem I/O).

Cobre parse_transcript (timestamps HH:MM:SS e MM:SS, blocos, descarte de ⚠️) e
normalize (lowercase, máscaras de PII, pontuação, acentos). Não abre áudio/ONNX.
"""
import tempfile, os
from measure_callcenter import parse_transcript, normalize


def _write(txt):
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(txt); f.close()
    return f.name


def test_parse_timestamps_hms_e_ms():
    p = _write("0:00:03\nalô tudo bem\n\n00:01:16\noutra fala aqui\n")
    try:
        blocks = parse_transcript(p)
    finally:
        os.unlink(p)
    assert blocks == [(3, "alô tudo bem"), (76, "outra fala aqui")]


def test_parse_descarta_warning_e_junta_linhas():
    p = _write("00:00:09\nlinha um\nlinha dois\n⚠️\n00:00:31\nsegundo bloco\n")
    try:
        blocks = parse_transcript(p)
    finally:
        os.unlink(p)
    assert blocks == [(9, "linha um linha dois"), (31, "segundo bloco")]


def test_normalize_remove_pontuacao_mantem_acento():
    assert normalize("Alô? Alô! Tudo bem, é você?") == "alô alô tudo bem é você"


def test_normalize_remove_mascaras_pii_e_warning():
    assert normalize("o _______ da plataforma ⚠️") == "o da plataforma"


def test_normalize_mantem_numeros():
    assert normalize("cinquenta mil reais 2024") == "cinquenta mil reais 2024"
