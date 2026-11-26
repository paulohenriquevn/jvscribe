"""Experimentos de pesquisa — sondas que testam uma hipótese e podem dar NULO.

Saiu de `tools/`. Estes arquivos não são ferramenta de operação: são o registro executável
de uma pergunta científica, e o resultado negativo tem o mesmo valor do positivo.

| sonda | hipótese |
|---|---|
| `tta_feature_align_probe.py` | alinhar estatísticas de feature recupera o gap telefônico? (DISC-05) |
| `blank_penalty_probe.py` | adaptar o DECODER ajuda onde a feature falhou? (DISC-06) |

Os dois reportam com bootstrap pareado e IC95%, e declaram "inconclusivo" quando o IC cruza
zero — a recusa explícita a declarar vencedor sem separação.
"""
