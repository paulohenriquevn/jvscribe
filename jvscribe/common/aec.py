"""Cancelamento de eco acústico (AEC) — opcional, e com a troca de RNF declarada.

**O padrão continua sendo não ter AEC.** Com fone de ouvido não há vazamento do alto-falante para
o microfone, e o desenho `mic = atendente / loopback = cliente` vale sem processamento nenhum.

O que esta opção resolve, medido em 2026-07-31: com o áudio saindo pela caixa, o microfone captura
o que as caixas tocam. Os dois canais recebem a **mesma fonte** e o sistema produz um **diálogo
falso — dois falantes onde há um — com confiança total**, porque a premissa da captura por canal
nunca é verificada. As duas transcrições do mesmo áudio divergiram em **10,5%** `[MEDIDO]`, que é
da ordem do WER inteiro do modelo.

Não é problema de diarização: uma pessoa falou. É AEC, o problema clássico de VoIP. E o nosso caso
é privilegiado — todo AEC exige o sinal de referência do *far-end*, e nós **já capturamos o
loopback por construção**.

⚠️ **A troca de RNF-01 é consciente, e por isso é explícita.**

| | RTFx |
|---|---|
| LocalVQE v1.4-AEC, README `[LITERATURA]` | 19,0× |
| **medido nesta CPU** `[MEDIDO]` | **10,3×** (min 8,4 · max 10,7) |
| combinado com o ASR ao vivo (3,58×) | **2,65×** |
| alvo RNF-01 | 3,0× |

O dono aceitou operar em **2,5×** com esta opção ligada. Aceitar é decisão legítima de produto;
aceitar **em silêncio** não é — daí `aceitar` ser um parâmetro obrigatório para destravar, e o
motivo devolvido sempre citar o alvo original de que se abriu mão.

Uma observação de hardware que o log do LocalVQE entrega: ele sobe com `threads=4` numa CPU
híbrida onde o nosso ASR já usa `intra=2`. Os dois disputam os mesmos P-cores — exatamente o modo
de falha que a afinidade de CPU já custou a este projeto (25% melhor isolada, 46% pior no
pipeline). O RTFx combinado real pode ficar **abaixo** dos 2,65× aritméticos.
"""
from __future__ import annotations

import ctypes
import pathlib
from typing import Protocol, runtime_checkable

import numpy as np

from cpu import ALVO_RNF01, rtfx_combinado


@runtime_checkable
class Aec(Protocol):
    """O que o pipeline precisa de um cancelador de eco.

    Interface do **domínio** (DIP): o motor entrega um hop de mic e o hop correspondente da
    referência, e recebe o mic limpo. Não conhece GGML, ctypes nem filtro adaptativo.
    """

    rtfx: float
    """RTFx **medido** desta implementação — entra na conta do orçamento."""

    hop: int
    """Tamanho do hop em amostras. Passar outro corrompe o estado interno em silêncio."""

    def processar(self, mic: np.ndarray, ref: np.ndarray) -> np.ndarray:
        """Um hop de microfone, limpo do eco da referência."""
        ...


class SemAec:
    """O padrão: devolve o microfone intacto.

    Não é stub — é a implementação **correta** com fone de ouvido, que é o caso de produção.
    """

    rtfx = float("inf")
    hop = 0

    def processar(self, mic: np.ndarray, ref: np.ndarray) -> np.ndarray:  # noqa: ARG002
        # Devolve o MESMO array, sem cópia: no caminho quente, uma cópia por hop é desperdício
        # que ninguém enxerga no profile porque some no ruído — e some multiplicada por 2 canais.
        return mic

    def __repr__(self) -> str:
        return "SemAec()"


class CancelamentoDuplo:
    """Pareia o mic com o loopback em frames de `hop`, sem perder amostra.

    Os dois `parec` são processos independentes: chegam em blocos de tamanho arbitrário e nunca
    alinhados. O AEC exige exatamente `hop` amostras por chamada. Entre os dois fatos há duas
    armadilhas, e as duas custam áudio:

    - **o resto do bloco** — 10 amostras com hop 4 são 2 frames e 2 amostras. Descartar as 2
      é engolir áudio a cada bloco, para sempre. Elas são retidas e saem no bloco seguinte.
    - **a referência seca** — o cliente pode estar em silêncio. Sem far-end não há eco: processa
      contra zeros, que é a resposta correta, em vez de travar esperando referência.

    O filtro do LocalVQE tolera atraso entre os dois caminhos (`dmax=16` frames ≈ 256 ms), então
    o alinhamento por ordem de chegada basta — não é preciso sincronizar por amostra, o que seria
    impossível com dois processos separados.
    """

    def __init__(self, aec: Aec) -> None:
        self._aec = aec
        self._ref = np.zeros(0, dtype=np.float32)
        self._resto = np.zeros(0, dtype=np.float32)

    def alimentar_referencia(self, x: np.ndarray) -> None:
        """O que o cliente falou — o sinal que vaza do alto-falante para o mic."""
        self._ref = np.concatenate([self._ref, np.asarray(x, dtype=np.float32)])

    def limpar(self, mic: np.ndarray) -> np.ndarray:
        hop = self._aec.hop
        if hop <= 0:  # SemAec — o caminho padrão não paga nem uma concatenação
            return mic
        buf = np.concatenate([self._resto, np.asarray(mic, dtype=np.float32)])
        n = (len(buf) // hop) * hop
        self._resto = buf[n:]
        saida = []
        for i in range(0, n, hop):
            ref, self._ref = self._ref[:hop], self._ref[hop:]
            if len(ref) < hop:
                ref = np.pad(ref, (0, hop - len(ref)))
            saida.append(self._aec.processar(buf[i:i + hop], ref))
        return np.concatenate(saida) if saida else np.zeros(0, dtype=np.float32)


def checar_orcamento_do_aec(
    rtfx_asr: float, rtfx_aec: float, aceitar: float | None
) -> tuple[bool, str]:
    """`(pode_ligar, motivo)`. O motivo cita **sempre** o alvo original.

    `aceitar=None` significa "não negociei nada" → exige o RNF-01 cheio. Um valor rebaixa o alvo
    **explicitamente**, e o texto devolvido registra de quanto se abriu mão — para que o relatório
    da corrida diga que o requisito foi negociado, e não pareça que ele foi cumprido.

    Rebaixar o alvo **não** é um cheque em branco: se nem o valor aceito for atingido, recusa.
    """
    combinado = rtfx_combinado(rtfx_asr, rtfx_aec)
    if combinado >= ALVO_RNF01:
        return True, (
            f"cabe sem negociação: ASR {rtfx_asr:.2f}× + AEC {rtfx_aec:.2f}× = "
            f"{combinado:.2f}× ≥ {ALVO_RNF01:g}× (RNF-01)."
        )
    if aceitar is None:
        return False, (
            f"não cabe: ASR {rtfx_asr:.2f}× + AEC {rtfx_aec:.2f}× = {combinado:.2f}× "
            f"(taxas somam pelo inverso), abaixo do RNF-01 de {ALVO_RNF01:g}×. "
            f"Para ligar assim mesmo, declare o piso aceito com `--aceitar-rtfx`."
        )
    if combinado < aceitar:
        return False, (
            f"não cabe nem no piso negociado: ASR {rtfx_asr:.2f}× + AEC {rtfx_aec:.2f}× = "
            f"{combinado:.2f}×, abaixo do aceito de {aceitar:g}× (RNF-01 é {ALVO_RNF01:g}×)."
        )
    return True, (
        f"RNF-01 NEGOCIADO — alvo original {ALVO_RNF01:g}×, piso aceito {aceitar:g}×, "
        f"entregue {combinado:.2f}× (ASR {rtfx_asr:.2f}× + AEC {rtfx_aec:.2f}×). "
        f"Abriu-se mão de {ALVO_RNF01 - combinado:.2f}× em troca de sinal sem eco."
    )


class LocalVqeAec:
    """LocalVQE v1.4-AEC via `ctypes` — 203K parâmetros, GGML, Apache 2.0.

    `ctypes` é stdlib: nenhuma dependência Python nova entra por causa disto (degrau 2 da escada
    de parcimônia). A `.so` e o `.gguf` são artefatos externos, passados por caminho.

    Escolhido entre as variantes por **medição, não por catálogo**: as versões que também fazem
    supressão de ruído e desreverberação (1,3M a 8,9× e 4,8M a 5,0×) foram reprovadas pelo
    orçamento antes de qualquer download — 5,0× ao lado de 3,58× dá 2,09×.
    """

    def __init__(self, so: pathlib.Path, gguf: pathlib.Path, rtfx: float) -> None:
        for caminho, o_que in ((so, "biblioteca"), (gguf, "modelo")):
            if not pathlib.Path(caminho).exists():
                raise FileNotFoundError(
                    f"{o_que} do LocalVQE não encontrado: {caminho}\n"
                    "Compile com `cmake -S ggml -B ggml/build -DLOCALVQE_BUILD_SHARED=ON` e "
                    "baixe os pesos de https://huggingface.co/LocalAI-io/LocalVQE"
                )
        self.rtfx = rtfx
        self._lib = ctypes.CDLL(str(so))
        self._declarar_assinaturas()
        self._ctx = self._lib.localvqe_new(str(gguf).encode())
        if not self._ctx:
            raise RuntimeError(f"LocalVQE recusou o modelo {gguf}")
        self.hop = int(self._lib.localvqe_hop_length(self._ctx))
        self._saida = np.zeros(self.hop, dtype=np.float32)

    def _declarar_assinaturas(self) -> None:
        f32 = np.ctypeslib.ndpointer(np.float32, flags="C_CONTIGUOUS")
        self._lib.localvqe_new.restype = ctypes.c_void_p
        self._lib.localvqe_new.argtypes = [ctypes.c_char_p]
        self._lib.localvqe_hop_length.restype = ctypes.c_int
        self._lib.localvqe_hop_length.argtypes = [ctypes.c_void_p]
        self._lib.localvqe_free.argtypes = [ctypes.c_void_p]
        self._lib.localvqe_process_frame_f32.restype = ctypes.c_int
        self._lib.localvqe_process_frame_f32.argtypes = [
            ctypes.c_void_p, f32, f32, ctypes.c_int, f32,
        ]

    def processar(self, mic: np.ndarray, ref: np.ndarray) -> np.ndarray:
        if len(mic) != self.hop or len(ref) != self.hop:
            raise ValueError(
                f"hop errado: esperado {self.hop}, veio mic={len(mic)} ref={len(ref)}. "
                "O filtro adaptativo mantém estado entre chamadas; um hop de tamanho diferente "
                "o corrompe sem levantar erro na biblioteca."
            )
        m = np.ascontiguousarray(mic, dtype=np.float32)
        r = np.ascontiguousarray(ref, dtype=np.float32)
        if self._lib.localvqe_process_frame_f32(self._ctx, m, r, self.hop, self._saida) != 0:
            raise RuntimeError("LocalVQE falhou ao processar o hop")
        return self._saida.copy()

    def __del__(self) -> None:
        ctx = getattr(self, "_ctx", None)
        if ctx:
            self._lib.localvqe_free(ctx)

    def __repr__(self) -> str:
        return f"LocalVqeAec(hop={getattr(self, 'hop', '?')}, rtfx={self.rtfx})"
