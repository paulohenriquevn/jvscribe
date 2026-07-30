# ADR-0004 — Remover o runtime Rust; jvscribe passa a ser Python-only

- Status: aceito
- Data: 2026-07-30
- Decisor: dono do projeto

## Contexto

O repositório mantinha dois runtimes: um motor de inferência em Rust (3 crates, 4.042 LoC,
79 testes) e as pipelines Python de corpus, treino e avaliação. O PRD escopava o repositório
como "o modelo **e** o motor de inferência".

A decisão foi motivada por **colaboração**: cientistas de dados trabalham em Python, e manter
um segundo runtime em outra linguagem cobra imposto de contexto em toda mudança.

## A medição que precedeu a decisão

Uma medição preliminar sugeriu que o binário Rust entregava RTFx 5,8× — abaixo do piso de 6×
do RNF-07 — enquanto o harness Python reportava 41–90×. **Essa comparação era inválida** e foi
corrigida antes de decidir: confrontava o RTFx do Rust (pipeline completo — fbank + inferência
+ decode) com o do `bench_rtfx.py` (só inferência). É a falácia § 3 #11 da
`asr-evidence-discipline.md`.

Comparação justa `[MEDIDO]` 2026-07-30, mesma clip de 17,76 s, mesmo pipeline, 2 threads,
i7-1355U:

| Runtime | RTFx | Mediana |
|---|---|---|
| Python (`batch_transcribe.py`) | 5,7 · 6,3 · 6,7 · 7,5 · 8,0 | **6,7×** |
| Rust (binário, com teto de threads) | 3,0 · 3,6 · 4,9 · 8,8 · 11,3 · 14,7 | **6,9×** |

**Indistinguíveis.** A decisão NÃO foi tomada por performance — foi por foco de time. Registrar
isso importa: se alguém no futuro reabrir a questão achando que o Rust era lento, o dado diz
o contrário.

## Alternativas consideradas

1. **Manter os dois** — rejeitada: imposto de contexto em toda mudança.
2. **Arquivar em branch/tag em vez de apagar** — **adotada em conjunto com a remoção.** O motor
   está em `rust-runtime-archive-v0.8.0`; recuperável com
   `git switch -c rust-restore rust-runtime-archive-v0.8.0`.
3. **Remover sem substituir a captura dual** — rejeitada: teria eliminado uma capacidade de
   produto sem aviso (ver Consequências).

## Consequências

### A capacidade que precisou ser reimplementada

O Rust capturava mic + loopback com **seleção de source por stream** via libpulse — é o que
separa atendente (microfone) de cliente (áudio da placa) numa ligação. Sem isso não há
rotulagem de falante.

`sounddevice` **não serve**: verificado em 2026-07-30, `sd.query_devices()` nesta máquina lista
8 entradas e **zero** monitor sources. É o mesmo motivo que levou o ADR D2 a escolher libpulse
em vez de cpal.

Solução adotada: `training/realtime/dual_capture.py`, um processo `parec --device=<source>` por
stream. Mesma capacidade, mesmo mecanismo do libpulse, via subprocesso. **Provado em execução**
por `training/tests/test_dual_capture.py` — 6 testes, incluindo captura simultânea real dos dois
streams e verificação de que nenhum processo fica órfão.

### O que se perdeu

- Extração de fbank com **zero alocação no caminho quente** (`features.rs` tinha teste com
  `stats_alloc` provando a propriedade). O Python usa `lhotse.Fbank`; a garantia não existe mais.
- Erros **tipados** de captura em nível de compilador; o Python usa exceções.
- O golden test cross-language do `kaldi_fbank` contra o lhotse — sem o lado Rust, não há o que
  comparar.

### O que ficou mais simples

- Um runtime, uma linguagem, uma suíte. CI sem toolchain Rust, sem `libpulse-dev`, sem
  `ORT_DYLIB_PATH`.
- Cientistas de dados alteram o caminho de inferência sem aprender Rust.

## Nota de identidade

O produto se chama **jvscribe**. As referências a "Macaw Voice" e aos crates `macaw-*` eram
resquício e foram corrigidas nos documentos vivos. Registros históricos (ADRs anteriores,
`training/results/*.md`, medições) **não** foram reescritos: eles documentam o que era verdade
quando foram escritos, e reescrevê-los falsificaria evidência.
