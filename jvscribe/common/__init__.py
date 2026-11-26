"""Shared kernel das pipelines de treino/avaliação (M9/T3.1).

Existe porque a guarda `test_pipeline_layout.py` proíbe import cross-pipeline — regra certa,
com um efeito colateral não previsto: **sem um destino permitido, o código compartilhado foi
empurrado para a duplicação**. O colapso CTC acabou reimplementado 7× e `normalize_ptbr` 5×,
com semânticas incompatíveis.

A guarda agora permite import cross-pipeline **apenas a partir deste pacote**. A regra ficou
mais forte, não mais fraca: antes ela era contornada por cópia, que é invisível para ela.
"""
