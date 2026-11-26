---
type: Índice
title: Referências — os peers estudados
description: Projetos de terceiros lidos para sustentar citações [FONTE-REPO], com commit fixado.
tags: [referencias, prior-art, fonte-repo]
timestamp: 2026-07-31T00:00:00Z
---

# Referências

Projetos de terceiros lidos como prior art. Cada um fica **fixado num commit**, para que toda
citação `[FONTE-REPO]` seja verificável por qualquer pessoa — não só por quem tem o clone local.

| peer | licença | para quê |
|---|---|---|
| [sherpa-onnx.md](sherpa-onnx.md) | Apache-2.0 | Runtime CPU de referência — sessão ONNX, features incrementais, encoder streaming com estado |

## Por que permalink em vez de clone

Um clone local torna a citação verificável só para quem o tem, e o conteúdo muda quando alguém
atualiza. Um permalink no commit fixado é **estável e público**. O clone de 51 MB que existia
foi removido em favor disto.

Formato:

```
https://github.com/{org}/{repo}/blob/{commit}/{caminho}#L{linha}
```

A regra de `[FONTE-REPO]` continua valendo: **a linha citada tem de EXIBIR o fato**. Citar uma
linha vizinha é a falácia que originou a correção de método deste projeto — ver
[../disciplina/rotulos-de-proveniencia.md](../disciplina/rotulos-de-proveniencia.md).
