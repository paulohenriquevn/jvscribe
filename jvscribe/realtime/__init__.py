"""Tempo real — os dois lados da ligação, ao vivo, no notebook do atendente.

O que une: latência é requisito, não consequência. Cada arquivo aqui paga custo para responder
no ritmo da fala, e o desenho inteiro existe por causa disso.

| arquivo | papel |
|---|---|
| `dual_capture` | dois `parec` independentes — mic **é** o atendente, loopback **é** o cliente |
| `live_transcribe` | a app: dois canais, rótulo de falante, turnos, `MetricasRNF` |
| `mic_transcribe` | versão de um canal só, anterior à dual |

⚠️ **O modelo NÃO é streaming.** É não-causal; o que se faz aqui é *simular* streaming com
janela deslizante + LocalAgreement-2. Custo medido: 121 ms para reprocessar 6 s contra 11 ms
de processar só os 0,5 s novos — **10,6× de retrabalho por hop**. É o piso de latência do
desenho, e só sai com treino causal.

O motor (`common/streaming.py`) vive no kernel: `bench/stress_test.py` precisa dele para medir.
"""
