#!/usr/bin/env python3
"""Grava fala lida do microfone para avaliação controlada — e separa gravar de transcrever.

**Por que os dois passos são separados.** O caminho ao vivo mistura o erro do modelo com o
efeito da carga da máquina: a mesma configuração já mediu 3,51× e 2,50× de RTFx só por causa de
contenção (`asr-evidence-discipline` § 5), e sob saturação o texto que sai é de minutos atrás.
Gravando primeiro e decodificando depois, com a CPU livre, o que sobrar de erro é **do modelo**.

Existe porque o test set curado de call center é o DoD de M1 que nunca foi entregue — o que há
hoje são 64 cortes de 8,4 min com o campo de transcrição **vazio**. Uma leitura controlada não
substitui fala espontânea real, e isso está dito nas limitações de todo artefato que a use; mas
é o instrumento mais barato que produz um par (áudio, referência) confiável.

Uso:
    python3 jvscribe/eval/gravar_leitura.py --segundos 75
    python3 jvscribe/eval/gravar_leitura.py --segundos 90 --saida data/eval/leitura/paulo.wav
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

import numpy as np

# Abaixo disto o sinal é fraco demais para a medição significar alguma coisa: o RMS medido numa
# captura de mic distante foi 0,015, e a fala próxima fica em 0,05–0,20.
PICO_MINIMO = 0.02


def nivel_e_utilizavel(x: np.ndarray) -> tuple[bool, str]:
    """`(ok, motivo)` — fail-fast antes de a pessoa descobrir depois que gravou em vão.

    Devolver o motivo, e não só um booleano, é o que permite ao chamador dizer **o que fazer**
    em vez de "deu ruim" (`error-handling` § 2).
    """
    if x.size == 0:
        return False, "gravação vazia — o dispositivo de entrada não entregou amostras"
    pico = float(np.abs(x).max())
    rms = float(np.sqrt(np.mean(x**2)))
    if pico < PICO_MINIMO:
        return False, (f"nível muito baixo (pico {pico:.4f} < {PICO_MINIMO}) — aproxime-se do "
                       f"microfone ou aumente o ganho, e regrave")
    if pico > 0.999:
        return False, f"sinal CLIPADO (pico {pico:.3f}) — reduza o ganho e regrave"
    return True, f"pico {pico:.3f} · RMS {rms:.4f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--segundos", type=float, default=75.0)
    ap.add_argument("--saida", type=pathlib.Path,
                    default=pathlib.Path("data/eval/leitura/leitura.wav"))
    ap.add_argument("--device", type=int, default=None)
    a = ap.parse_args()

    import sounddevice as sd
    import soundfile as sf

    a.saida.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n  Gravando {a.segundos:.0f}s em {a.saida}")
    print("  PODE COMEÇAR A LER AGORA.\n", flush=True)

    x = sd.rec(int(a.segundos * 16000), samplerate=16000, channels=1,
               dtype="float32", device=a.device)
    restante = int(a.segundos)
    while restante > 0:
        time.sleep(min(5, restante))
        restante -= 5
        if restante > 0:
            print(f"    faltam {restante:3d}s", flush=True)
    sd.wait()
    x = x.ravel()

    ok, motivo = nivel_e_utilizavel(x)
    sf.write(str(a.saida), x, 16000)
    print(f"\n  gravado: {a.saida}  ·  {motivo}")
    if not ok:
        print(f"  ⚠️  {motivo}")
        return 1
    print("  ✓ nível utilizável")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
