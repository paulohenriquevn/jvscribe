# Mapa de domínios × arquivos — onde o sistema está fragmentado

Medido em 2026-07-31 sobre 109 arquivos `.py` + 4 `.sh` (7.879 LoC de produção).
Método: AST para grafo de import, classificação por domínio a partir do que cada arquivo
**faz** (não de onde ele está), e cruzamento domínio × diretório nos dois sentidos.

---

## O diagnóstico em uma frase

**O sistema não está fragmentado em excesso de arquivos — está fragmentado porque a divisão
por pastas não é a divisão por domínio.** Sete pipelines abrigam quinze domínios, e quatro
domínios atravessam pastas. As duas pastas mais desalinhadas são justamente as que a
`architecture.md` do projeto nomeia como anti-pattern: `common/` e `tools/`.

---

## 1. Domínios que atravessam pastas (4 de 15)

| Domínio | Arquivos | LoC | Espalhado por |
|---|---|---|---|
| **preparo de corpus** | 9 | 1.212 | `corpus/` (4) + `finetune/` (5) |
| **medição de WER (harness)** | 9 | 1.141 | `eval/` (7) + `tools/` (2) |
| **runtime / CPU** | 7 | 871 | `common/` (3) + `tools/` (3) + `batch/` (1) |
| **métrica WER/CER** | 6 | 545 | `tools/` (4) + `eval/` (1) + `common/` (1) |

O caso mais claro é **métrica WER/CER**: seis arquivos, três pastas, um só conceito —
"quanto o modelo errou e a diferença é significativa".

```
tools/wer_core.py          20 LoC   distância de edição (o numerador)
tools/bootstrap_wer_ci.py 109 LoC   IC bootstrap pareado
tools/cer_from_recogs.py   91 LoC   CER a partir de recogs do icefall
tools/compare_models.py   115 LoC   compara dois modelos na mesma régua
eval/eval_wer.py          112 LoC   WER com IC95 bootstrap
common/stats.py            98 LoC   comparação pareada, recusa veredito sem separação
```

> ⚠️ **Correção (2026-07-31).** Este parágrafo afirmava que `bootstrap_wer_ci.py` e `stats.py`
> "fazem a mesma coisa". **Estava errado, e fundi-los teria corrompido todo delta de WER
> publicado.** Medido no mesmo par de utterances:
>
> | método | Δ |
> |---|---|
> | razão de somas (`bootstrap_wer_ci`) — correto para WER | **4,76 p.p.** |
> | média de diferenças pareadas (`stats`) — correto para latência | **26,25 p.p.** |
>
> São a mesma *técnica* (bootstrap pareado) sobre *estatísticas diferentes*. Não se faz média
> de WERs por utterance: uma frase de 2 palavras pesaria igual a uma de 40. Os dois módulos
> são vizinhos e permanecem **separados de propósito** — está escrito no topo de
> `common/metrics.py` para que ninguém repita a tentativa.

---

## 2. Pastas que abrigam múltiplos domínios

| Pasta | Domínios | Veredito |
|---|---|---|
| **`tools/`** | **7** | lixeira |
| **`common/`** | **5** | lixeira |
| `eval/`, `corpus/`, `batch/`, `finetune/` | 2 cada | aceitável |
| `realtime/` | 1 | coeso |

`architecture.md § 6` deste projeto lista exatamente isto como anti-pattern:

> **God modules** named `utils`, `helpers`, `common`, `misc`, `shared` — these accumulate
> unrelated code. Be specific.

`tools/` (2.007 LoC, o maior pipeline) contém: probes de pesquisa, benchmarks de runtime,
calibração, auditorias de corpus, o núcleo de WER, bootstrap, smoke de finetune e um extrator
de fixture. Nada os une além de "não coube em outro lugar".

`common/` é menos grave — é o *shared kernel* e por definição agrega — mas abriga cinco
domínios, e dois deles (`stats.py`, `cpu_topology.py`) têm gêmeos em `tools/`.

---

## 3. Fragmentação de caminho: o mesmo símbolo por dois módulos

| Símbolo | Caminhos | Divisão |
|---|---|---|
| `normalize_for_wer_compare` | `text_normalize_ptbr` · `text` | 12 × 5 |
| `apply_telephone_channel` | `telephone_channel` · `corpus.telephone_channel` | 4 × 2 |
| `RecordingSet` | `lhotse` · `lhotse.audio` | 2 × 6 |

O primeiro é o mais sério. **`common/text.py` é uma fachada de 47 linhas** cujo conteúdo real
são 7 (`normalize_train_target`); a outra função apenas re-exporta de
`text_normalize_ptbr.py`. Dois módulos, um domínio, consumidores divididos.

Não é teórico: foi exatamente essa ambiguidade de caminho que permitiu ao defeito de régua
sobreviver — `eval_runtime_wer.py` importava de `text`, `measure_callcenter.py` de
`text_normalize_ptbr`, e ninguém via que mediam com réguas diferentes.

---

## 4. Violações da regra de fronteira do próprio projeto

A guarda `tests/test_pipeline_layout.py` exige *"cross-pipeline apenas a partir de `common/`"*.
O grafo de import mostra **5 violações**, e todas apontam para o mesmo fato:

```
eval  → corpus   make_telephone_test.py  → telephone_channel
eval  → corpus   measure_realcodec.py    → telephone_channel, codec_pool
tools → corpus   tta_feature_align_probe → telephone_channel
tools → realtime stress_test.py          → streaming
```

**O canal telefônico não é um domínio de corpus.** É processamento de sinal, consumido por
`corpus`, `eval` e `tools`. Está em `corpus/` por acidente histórico (nasceu na augmentação
de M3), e por isso três pipelines furam a fronteira para alcançá-lo.

Mesmo caso de `streaming.py`: é o motor de decodificação incremental, não um detalhe de
`realtime/` — `tools/stress_test.py` precisa dele para medir.

---

## 5. Fragmentos verdadeiros (arquivo pequeno demais para ser unidade)

| Arquivo | LoC | Conteúdo real |
|---|---|---|
| `tools/wer_core.py` | 20 | uma função — a distância de edição |
| `common/text.py` | 47 | 7 linhas próprias + uma re-exportação |
| `common/calibracao.py` | 53 | duas funções de aritmética de ocupação |
| `common/ctc.py` | 54 | o colapso greedy |

`wer_core.py` foi extraído por uma razão **legítima e documentada** (evitar que ferramentas de
texto puro arrastassem numpy/soundfile). `common/text.py` não tem razão equivalente.

---

## 6. O que NÃO está fragmentado

Vale registrar, porque a conclusão não é "reorganize tudo":

- **`realtime/`** — um domínio, quatro arquivos, fronteiras claras. É o melhor pipeline do repositório.
- **`finetune/patch_*`** — os quatro "patch determinístico do icefall" são um sub-domínio coeso.
- **`corpus/` canal telefônico** — os três arquivos são coesos *entre si*; o problema é a pasta onde estão, não a divisão interna.
- **`batch/`** — três arquivos, um domínio + o `bench_rtfx` que pertence a runtime.

---

## Proposta de consolidação, ordenada por relação valor/risco

| # | Ação | Risco | Por que vale |
|---|---|---|---|
| 1 | ✅ **FEITO** — `common/text.py` é o módulo único; `text_normalize_ptbr.py` removido | baixo | Equivalência provada em 3.000 strings antes da remoção; 13 arquivos repontados |
| 2 | ❌ **CANCELADO** — a medição refutou a premissa (ver a correção acima) | — | Fundir teria mudado todo delta de WER publicado |
| 3 | **Mover o canal telefônico para `common/audio/`** (ou `signal/`) | médio | Remove 4 das 5 violações de fronteira; o domínio passa a estar onde seus três consumidores podem alcançá-lo legalmente |
| 4 | **Quebrar `tools/` nos domínios reais** — `probes/`, `audit/`, `bench/` | médio | 7 domínios numa pasta é o anti-pattern que a própria `architecture.md` nomeia |
| 5 | **Consolidar métrica WER/CER num só lugar** (`common/metrics/`) | médio | 6 arquivos, 3 pastas, 1 conceito |
| 6 | Mover `batch/bench_rtfx.py` → junto de `runtime_bench.py` | baixo | Pertence a runtime, não a lote |

**Não recomendo** unificar `corpus/` com `finetune/` (o "preparo de corpus" espalhado): são
9 arquivos e 1.212 LoC com uma fronteira defensável — `corpus/` monta manifests, `finetune/`
prepara o que vai para a GPU. A sobreposição existe mas o custo de mover supera o ganho.

---

## Método e limites

O que este mapa mede: grafo de import por AST, LoC, e classificação por domínio.
O que ele **não** mede: coesão *interna* de cada arquivo (as funções de um arquivo operam
sobre os mesmos dados?). Um arquivo pode estar na pasta certa e ainda ser incoerente por
dentro — isso exigiria análise de LCOM ou leitura, e não foi feito aqui.

A classificação por domínio é **minha**, não derivada mecanicamente. Alguém pode discordar de
que "canal telefônico" e "preparo de corpus" são domínios distintos — a tabela existe para que
essa discordância seja discutível, não para encerrá-la.
