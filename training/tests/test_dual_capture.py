"""Prova que a captura dual sobreviveu à remoção do Rust (jvscribe).

O runtime Rust removido em 2026-07-30 capturava mic + loopback com seleção de source POR
STREAM via libpulse — a capacidade que separa atendente de cliente numa ligação. Estes testes
existem para garantir que a migração para Python preservou isso, e não apenas alegou preservar.
"""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "realtime"))

from dual_capture import CaptureError, DualCapture, default_sources, list_sources


def _tem_pulse() -> bool:
    return shutil.which("pactl") is not None and shutil.which("parec") is not None


pytestmark = pytest.mark.skipif(not _tem_pulse(), reason="pactl/parec ausentes neste ambiente")


def test_lista_sources_do_sistema():
    sources = list_sources()
    assert sources, "esperava ao menos uma source de áudio"


def test_separa_mic_de_loopback():
    """O requisito de produto: mic e monitor são sources DIFERENTES."""
    mic, loop = default_sources()
    assert mic != loop, "mic e loopback não podem ser a mesma source"
    assert loop.endswith(".monitor"), f"loopback deve ser um monitor, veio {loop}"
    assert not mic.endswith(".monitor"), f"mic não pode ser um monitor, veio {mic}"


def test_source_inexistente_falha_alto():
    """Caso negativo: nunca degradar em silêncio para 'sem áudio'."""
    cap = DualCapture(mic_source="fonte-que-nao-existe-xyz", loopback_source="idem-xyz")
    with pytest.raises(Exception) as exc:
        cap.start()
        cap.read(timeout=0.5)
        cap.stop()
    assert exc.value is not None


def test_captura_os_dois_streams_simultaneamente():
    """O DoD: dois streams entregam áudio ao mesmo tempo, cada um da sua source."""
    with DualCapture() as cap:
        rotulos = set()
        for _ in range(20):
            for label, pcm in cap.read(timeout=1.0):
                if pcm:
                    rotulos.add(label)
            if rotulos == {"mic", "loopback"}:
                break
    assert rotulos == {"mic", "loopback"}, (
        f"esperava áudio dos dois streams, obteve {rotulos or 'nenhum'}"
    )


def test_backlog_e_observavel():
    """Sem contador de backlog, um consumidor lento acumula em silêncio até estourar."""
    with DualCapture() as cap:
        b = cap.backlog()
    assert set(b) == {"mic", "loopback"}
    assert all(isinstance(v, int) for v in b.values())


def test_encerra_sem_deixar_processo_orfao():
    cap = DualCapture().start()
    procs = [st.proc for st in cap.streams]
    assert all(p is not None and p.poll() is None for p in procs), "processos deveriam estar vivos"
    cap.stop()
    assert all(st.proc is None for st in cap.streams), "stop() deve zerar as referências"
    for p in procs:
        assert p.poll() is not None, "processo de captura ficou órfão após stop()"
