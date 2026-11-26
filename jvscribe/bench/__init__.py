"""Benchmark e calibração do runtime — mede o PRODUTO nesta máquina.

Saiu de `tools/`, que acumulava sete domínios sem relação. O que une estes arquivos é a
pergunta: *quanto custa rodar isto aqui, e a configuração aguenta?*

| arquivo | responde |
|---|---|
| `calibrate.py` | qual janela e quantas threads esta CPU suporta |
| `runtime_bench.py` | qual configuração de sessão ONNX é melhor (pareado, IC95%) |
| `stress_test.py` | o RTFx do minuto 30 é o do minuto 1? (RNF-04) |
| `finetune_smoke.py` | o checkpoint publicado ainda treina? |

⚠️ Nenhum destes conclui sob carga. `stress_test` marca o veredito INDETERMINADO acima do
limiar de load; `calibrate` avisa. Máquina ocupada não mede (`asr-evidence-discipline` § 5).
"""
