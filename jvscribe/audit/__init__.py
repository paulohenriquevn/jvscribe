"""Auditoria de corpus — prova que o dado de treino não contamina o de teste.

Saiu de `tools/`. O que une: cada arquivo responde a uma pergunta de INTEGRIDADE DO DADO,
cuja resposta errada invalida todo WER medido depois.

| arquivo | pergunta |
|---|---|
| `coraa_speaker_overlap.py` | o mesmo locutor aparece em train e test? |
| `tagarela_coraa_leak_check.py` | há vazamento cruzado entre os dois corpora? |
| `tagarela_noise_audit.py` | quanto ruído de pseudo-rótulo entrou no mux? |

Invariante: pseudo-label nunca entra no test set — mede concordância com o professor,
não acurácia. Estes scripts são o que torna essa invariante verificável.
"""
