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

from dual_capture import CaptureError, DualCapture, Stream, default_sources, list_sources


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


def test_read_drena_a_fila_em_vez_de_devolver_um_chunk_por_stream():
    """Defeito real de 2026-07-31: `read()` devolvia 1 chunk por stream por chamada.

    Com o `parec` produzindo ~30 chunks/s por canal e o consumidor chamando `read()` a cada
    ciclo de decode, o consumo era ESTRUTURALMENTE menor que a produção: o backlog media
    101 → 227 chunks em 4,4 s, crescendo sem limite. A app de tempo real reprovava RNF-03
    (backlog) e RNF-02 (p99 792 ms) por encanamento, não por lentidão do modelo.
    """
    from queue import Queue

    cap = DualCapture.__new__(DualCapture)
    cap.streams = [Stream(label="mic", source="s1"), Stream(label="loopback", source="s2")]
    for st in cap.streams:
        st.queue = Queue()
        for i in range(5):
            st.queue.put(bytes([i]))

    lidos = cap.read(timeout=0.01)

    assert len(lidos) == 10, f"esperava drenar os 10 chunks enfileirados, veio {len(lidos)}"
    assert cap.backlog() == {"mic": 0, "loopback": 0}


def test_read_respeita_um_teto_para_nao_travar_o_consumidor():
    """Drenar não pode virar laço infinito quando o produtor é mais rápido que o loop."""
    from queue import Queue

    cap = DualCapture.__new__(DualCapture)
    cap.streams = [Stream(label="mic", source="s1")]
    cap.streams[0].queue = Queue()
    for i in range(500):
        cap.streams[0].queue.put(bytes([i % 256]))

    lidos = cap.read(timeout=0.01, max_chunks=64)

    assert len(lidos) == 64, "o teto por chamada tem de ser respeitado"
    assert cap.backlog()["mic"] == 436


def test_um_stream_cheio_nao_mata_de_fome_o_outro():
    """`max_chunks` é teto POR STREAM, não orçamento global disputado.

    Se o mic tem 1000 chunks na fila e o teto for global, ele consome tudo e o loopback
    fica com um chunk só — na prática, perder o áudio do CLIENTE. O rótulo de falante
    continuaria certo, mas metade da conversa sumiria.
    """
    from queue import Queue

    cap = DualCapture.__new__(DualCapture)
    cap.streams = [Stream(label="mic", source="s1"), Stream(label="loopback", source="s2")]
    for st in cap.streams:
        st.queue = Queue()
    for i in range(300):
        cap.streams[0].queue.put(b"m")
    for i in range(300):
        cap.streams[1].queue.put(b"l")

    lidos = cap.read(timeout=0.01, max_chunks=64)

    por_stream = {"mic": 0, "loopback": 0}
    for label, _ in lidos:
        por_stream[label] += 1
    assert por_stream == {"mic": 64, "loopback": 64}, (
        f"cada stream deve render até 64; veio {por_stream}"
    )
