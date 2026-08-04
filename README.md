# jvscribe — transcrição PT-BR em tempo real, sobre CPU

Transcreva atendimento em português brasileiro **ao vivo, no notebook do próprio
atendente** — sem GPU, sem enviar áudio para a nuvem, sem custo por hora transcrita.

A aposta é **especialização**: um modelo que só faz PT-BR telefônico cabe em dezenas
de milhões de parâmetros onde um multilíngue de 600M não fecha tempo real em CPU.

Escopo deste repositório: **o modelo** e **o motor de inferência**. Plataforma de
frota, compliance LGPD e UI ficam fora ([`ROADMAP.md`](ROADMAP.md) § Scope).

---

## Estado do projeto

Projeto em **discover contínuo, orientado por evidência**: a arquitetura não é
escolhida por convicção, é medida. Progresso por milestones (`ROADMAP.md`, M0–M9).

| Milestone | Estado |
|---|---|
| M0 — Fundação do runtime · M1 — Instrumentação | ✅ concluídos |
| M2 — Decisão de arquitetura · M3 — Corpus | ✅ concluídos |
| M4 — Piloto comparativo | ✅ concluído |
| M5 — Modelo em escala | ⚠️ 2/3 DoDs — o telefônico ficou **deferido** por limite de dado ([evidência](wiki/medicoes/m5-modelo-final.md)) |
| M9 — Governança de artefato e reprodutibilidade | ✅ concluído |
| M6 — Runtime otimizado | 🔬 em medição ([profile por operador](wiki/medicoes/m6-profile-por-operador.md), [RNF ao vivo](wiki/medicoes/m6-rnf-ao-vivo.md)) |
| M7 — Escopo de produto · M8 — Piloto | ⏳ próximos |

> A tabela reflete o `ROADMAP.md`, que é a fonte da verdade. Um teste
> ([`test_readme_links.py`](jvscribe/tests/test_readme_links.py)) garante que todo link interno
> daqui resolve — em 2026-07-30, 5 de 5 apontavam para arquivos removidos por engano.

### A arquitetura, decidida por medição

Dos 5 candidatos avaliados contra 8 critérios, a família **CTC/transducer** venceu o critério
de velocidade em CPU (M2). O piloto comparativo de M4 então **travou o finalista**:
**Zipformer-CTC `medium` (64M), int8, com cabeça de fonema auxiliar** —
[ADR 0003](wiki/decisoes/0003-finalista-medium.md), que supersede o eixo de tamanho do
[ADR 0002](wiki/decisoes/0002-zipformer-ctc-small.md) após medição de soak e carga.

`[MEDIDO]` head-to-head com parâmetros equivalentes: Zipformer domina Conformer nos dois eixos
de acurácia (WER 28,86% vs 31,57%, IC95% do delta excluindo 0). A cabeça de fonema levou o
medium a **27,49% WER** ([evidência](wiki/medicoes/m4-cabeca-de-fonema-no-medium.md)).

**O achado de M2 que orientou a escolha da família** `[MEDIDO]`: em CPU, na mesma máquina e na mesma
clip de 12 s, o transducer é **~2× mais rápido** que o AED em tamanho comparável —
Zipformer 20M = 15,90 ± 2,06× tempo real vs Moonshine tiny 27M = 7,93 ± 0,72×
(n=10, separação estatística limpa;
[medição completa](wiki/medicoes/m2-rtfx-candidatos.md)). A razão é
arquitetural: o AED é autoregressivo (custo cresce com os tokens gerados), o
transducer/CTC faz um passe (custo fixo pelos frames de áudio).

> Nota de honestidade: esses números são medidos numa **máquina de dev, não no piso
> da frota BYOD** (ainda `[DESCONHECIDO]`) — o que transfere é a *razão entre
> arquiteturas*, não o valor absoluto. A magnitude "~2×" precisa de confirmação sob
> soak com carga concorrente em M4; reportar dispersão já baixou uma estimativa
> anterior de "~3×" (a diferença era carga de CPU).

---

## O modelo entregue

**`jvscribe-ptbr-zipformer-ctc-64m`** — Zipformer-CTC de 64M parâmetros, int8, com cabeça de
fonema auxiliar. Publicado em `paulohenriquevn/jvscribe` (HuggingFace, privado).

| | valor | condição |
|---|---|---|
| WER | **15,99%** | FLEURS pt_br `test[0:100]`, 2.552 palavras, greedy CTC |
| CER | **7,30%** | idem |
| RTFx | **40,0×** | i7 12-core, ONNX int8, 4 threads, load average < 1 |

`[MEDIDO]` 2026-07-31 e **reproduzido a partir do download do HuggingFace**, não dos arquivos
locais ([evidência](wiki/medicoes/reprodutibilidade.md)): sha256 e
`vocab_fingerprint` conferem com o model card, e o checkpoint publicado carrega, codifica
PT-BR e aceita treino.

Dos dois candidatos M5 que coabitavam o artefato, o oficial foi decidido por **bootstrap
pareado** — IC95% do delta em [−2,25; −0,43] pp, sem cruzar zero. O `model_card.json` é a
autoridade sobre qual peso roda; nome de arquivo não conhece WER.

> O número anterior deste README (27,49%) era o entregável de **M4**, uma geração atrás.

**Limites honestos:** WER em telefonia 8 kHz e em fala espontânea de call center seguem
`[DESCONHECIDO]` — FLEURS é leitura de notícias. E o modelo **não é streaming**: é não-causal,
usado ao vivo por janela deslizante ([por quê](docs/ARCHITECTURE.md)).

## Rodando

```bash
pip install -r requirements-eval.txt        # onnxruntime, lhotse, soundfile
export JVSCRIBE_MODEL_DIR=/caminho/do/artefato # ou deixe models/current apontar para ele

# lote — uma pasta de áudios em qualquer formato
python3 jvscribe/batch/batch_transcribe.py --input-dir ./audios --out-dir ./saida

# ao vivo, os dois lados da ligação (ATENDENTE = mic · CLIENTE = loopback)
python3 jvscribe/realtime/live_transcribe.py --duracao 60 --relatorio evidencia.md
```

O tempo real exige `pulseaudio-utils` (`parec`, `pactl`) — a captura precisa prender cada
stream à sua source, e `sounddevice` não expõe monitor sources.

| ferramenta | para quê |
|---|---|
| [`jvscribe/bench/runtime_bench.py`](jvscribe/bench/runtime_bench.py) | varredura de configuração do ONNX com bootstrap pareado |
| [`jvscribe/bench/stress_test.py`](jvscribe/bench/stress_test.py) | soak com o modelo real — degradação minuto a minuto |
| [`jvscribe/bench/finetune_smoke.py`](jvscribe/bench/finetune_smoke.py) | prova que um checkpoint carrega, codifica PT-BR e treina |
| [`jvscribe/eval/compare_models.py`](jvscribe/eval/compare_models.py) | compara dois modelos na mesma régua, com IC |
| [`jvscribe/bench/calibrate.py`](jvscribe/bench/calibrate.py) | **calibra o runtime para a máquina-alvo** — rode ao trocar de CPU |

---

## Como navegar

| Documento | Papel |
|---|---|
| [`docs/CALIBRATION.md`](docs/CALIBRATION.md) | **Runbook de calibração** — o que é portável entre CPUs e o que precisa ser remedido |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | **Como o modelo e o motor funcionam** — grafo, stacks, custo por operador, pipelines de lote e tempo real |
| [`ROADMAP.md`](ROADMAP.md) | Milestones M0–M9 com Definition of Done, escopo, restrições e questões abertas |
| [`wiki/medicoes/`](wiki/medicoes/) | Toda medição, com hipótese, evidência e limitações separadas |
| [`wiki/log.md`](wiki/log.md) | Histórico do projeto em ordem cronológica |
| [`wiki/`](wiki/index.md) | **Base de conhecimento** em Open Knowledge Format — modelo, motor, treino, otimização, medições e decisões |
| [`wiki/decisoes/`](wiki/decisoes/index.md) | ADRs — o que foi travado, com racional e alternativas |
| [`wiki/disciplina/`](wiki/disciplina/index.md) | Contrato de evidência — todo número carrega rótulo de proveniência |

## Disciplina de evidência

Todo número neste projeto carrega um rótulo: `[MEDIDO]` (rodamos o experimento),
`[LITERATURA]` (reportado por terceiro), `[FONTE-REPO]` (fato lido no código de um
peer clonado), `[ESTIMATIVA]` (derivado por cálculo) ou `[DESCONHECIDO]`. Sem rótulo,
o número não existe. É a vacina contra decidir por benchmark que não transfere.
