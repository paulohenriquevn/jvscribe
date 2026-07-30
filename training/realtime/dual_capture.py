"""Captura dual mic + loopback com seleção de source POR STREAM (jvscribe).

Substitui a capacidade que vivia no runtime Rust removido em 2026-07-30. O requisito de
produto é separar **atendente** (microfone) de **cliente** (áudio que sai pela placa, o
"loopback"/monitor) numa ligação — sem isso não há rotulagem de falante.

## Por que `parec` e não `sounddevice`

`sounddevice` (PortAudio/ALSA) **não expõe monitor sources**: verificado nesta máquina em
2026-07-30, `sd.query_devices()` lista 8 entradas e **zero** monitores. É o mesmo motivo que
levou o ADR D2 a escolher libpulse em vez de cpal — a API não permite escolher a source.

`parec` resolve porque cada invocação recebe `--device=<source>`, o que dá seleção por stream:

    parec --device=alsa_input...           → microfone (atendente)
    parec --device=alsa_output....monitor  → loopback  (cliente)

Cada stream é um processo, lendo PCM cru do stdout. É o mesmo mecanismo do libpulse, com o
custo de um pipe a mais e a vantagem de não precisar de binding nativo.

## Invariantes

- **Não converte nem reamostra**: `parec` entrega exatamente o formato pedido (`s16le`, taxa e
  canais declarados). Reamostragem em Python no caminho quente seria custo desnecessário.
- **Falha alto**: source inexistente ou `parec` ausente levantam erro tipado, nunca degradam em
  silêncio para "sem áudio" (`.claude/rules/error-handling.md` § 2).
- **Encerra limpo**: `stop()` termina os processos e aguarda; sem processo órfão segurando o
  dispositivo de áudio.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from queue import Empty, Queue

SAMPLE_RATE = 16_000
CHANNELS = 1
_BYTES_PER_SAMPLE = 2  # s16le


class CaptureError(RuntimeError):
    """Erro tipado da fronteira de captura, com contexto para diagnóstico sem debugger."""


@dataclass
class Stream:
    """Um stream de captura: um `parec` preso a uma source específica."""

    label: str
    source: str
    proc: subprocess.Popen | None = None
    queue: Queue = field(default_factory=Queue)
    _reader: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)


def list_sources() -> list[str]:
    """Sources do PulseAudio disponíveis, na ordem que o `pactl` reporta."""
    if shutil.which("pactl") is None:
        raise CaptureError("pactl não encontrado — o PulseAudio/PipeWire é requisito da captura")
    out = subprocess.run(
        ["pactl", "list", "short", "sources"], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise CaptureError(f"pactl falhou (código {out.returncode}): {out.stderr.strip()}")
    return [line.split("\t")[1] for line in out.stdout.splitlines() if "\t" in line]


def default_sources() -> tuple[str, str]:
    """Devolve `(mic, loopback)` escolhidos por convenção: monitor = loopback.

    Falha alto quando não há um de cada — é melhor recusar do que capturar duas vezes o
    mesmo lado da conversa e produzir rotulagem de falante errada.
    """
    sources = list_sources()
    mics = [s for s in sources if not s.endswith(".monitor")]
    monitors = [s for s in sources if s.endswith(".monitor")]
    if not mics:
        raise CaptureError(f"nenhuma source de entrada encontrada em {sources}")
    if not monitors:
        raise CaptureError(
            f"nenhuma source .monitor (loopback) encontrada em {sources} — sem ela não é "
            "possível separar o cliente do atendente"
        )
    return mics[0], monitors[0]


def _spawn(source: str, sample_rate: int, channels: int) -> subprocess.Popen:
    if shutil.which("parec") is None:
        raise CaptureError("parec não encontrado — instale pulseaudio-utils")
    return subprocess.Popen(
        [
            "parec",
            f"--device={source}",
            "--format=s16le",
            f"--rate={sample_rate}",
            f"--channels={channels}",
            "--latency-msec=32",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


class DualCapture:
    """Captura simultânea de dois streams, cada um preso à sua source.

    Uso:
        with DualCapture() as cap:
            for label, pcm in cap.read(timeout=1.0):
                ...
    """

    def __init__(
        self,
        mic_source: str | None = None,
        loopback_source: str | None = None,
        sample_rate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
        chunk_ms: int = 32,
    ) -> None:
        if mic_source is None or loopback_source is None:
            auto_mic, auto_loop = default_sources()
            mic_source = mic_source or auto_mic
            loopback_source = loopback_source or auto_loop
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_bytes = int(sample_rate * chunk_ms / 1000) * channels * _BYTES_PER_SAMPLE
        self.streams = [
            Stream(label="mic", source=mic_source),
            Stream(label="loopback", source=loopback_source),
        ]

    # -- ciclo de vida -----------------------------------------------------------

    def start(self) -> "DualCapture":
        for st in self.streams:
            st.proc = _spawn(st.source, self.sample_rate, self.channels)
        # `parec` com source inválida SOBE e só morre depois — sem esta verificação a captura
        # degradaria em silêncio para "sem áudio", que é o modo de falha mais perigoso aqui:
        # a transcrição sairia vazia e ninguém saberia por quê. Confere o estado logo após o
        # spawn e propaga o stderr do processo, que traz a mensagem real do PulseAudio.
        time.sleep(0.25)
        for st in self.streams:
            assert st.proc is not None
            if st.proc.poll() is not None:
                erro = ""
                if st.proc.stderr is not None:
                    erro = st.proc.stderr.read().decode("utf-8", "replace").strip()
                self.stop()
                raise CaptureError(
                    f"captura de '{st.label}' morreu ao iniciar na source {st.source!r} "
                    f"(código {st.proc.returncode if st.proc else '?'}): {erro or 'sem stderr'}"
                )
        for st in self.streams:
            st._reader = threading.Thread(target=self._pump, args=(st,), daemon=True)
            st._reader.start()
        return self

    def _pump(self, st: Stream) -> None:
        assert st.proc is not None and st.proc.stdout is not None
        while not st._stop.is_set():
            data = st.proc.stdout.read(self.chunk_bytes)
            if not data:
                break
            st.queue.put(data)

    def stop(self) -> None:
        """Encerra os dois streams. Nunca deixa processo órfão segurando o dispositivo."""
        for st in self.streams:
            st._stop.set()
            if st.proc is not None:
                st.proc.terminate()
                try:
                    st.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    st.proc.kill()
                    st.proc.wait(timeout=2)
                st.proc = None

    def __enter__(self) -> "DualCapture":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()

    # -- leitura -----------------------------------------------------------------

    def read(self, timeout: float = 1.0) -> list[tuple[str, bytes]]:
        """Um chunk de cada stream que tiver dado disponível, rotulado pela origem."""
        out: list[tuple[str, bytes]] = []
        for st in self.streams:
            try:
                out.append((st.label, st.queue.get(timeout=timeout)))
            except Empty:
                continue
        return out

    def backlog(self) -> dict[str, int]:
        """Chunks acumulados por stream — observabilidade do consumidor mais lento.

        Sem isto, um consumidor que não acompanha a captura acumula em silêncio até estourar
        memória. Este era o `BacklogCounter` do runtime removido.
        """
        return {st.label: st.queue.qsize() for st in self.streams}
