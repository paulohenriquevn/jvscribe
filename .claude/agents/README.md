# Agents — Macaw Voice ASR PT-BR

Doze agents especialistas cobrindo as cinco capacidades centrais do projeto:
pesquisa em ASR, dados e linguística PT-BR, inferência em CPU, sistemas/áudio/Rust,
e avaliação experimental reproduzível.

> **Estado do projeto: discover contínuo.** Encoder, decoder, tokenização e tamanho
> seguem `⏸ PENDENTE` (`PRD.md` § 8.1). Todo agent opera sob
> `.claude/rules/asr-evidence-discipline.md` § 0: o default é **investigar e medir**,
> não escolher.

## Contrato compartilhado

Todos os agents leem `.claude/rules/asr-evidence-discipline.md` antes de concluir.
Ela define a rotulagem obrigatória de números (`[MEDIDO]` / `[LITERATURA]` /
`[ESTIMATIVA]` / `[DESCONHECIDO]`), a separação hipótese/evidência/conclusão, e as
12 falácias que invalidam um artefato — os "sinais negativos" convertidos em gates.

## O time

| Agent | Papel (codinome) | Milestones |
|---|---|---|
| `asr-chief-scientist` | Chief Scientist — arquitetura ASR ("Helena Costa") | M2, M4, M5 |
| `streaming-asr-scientist` | Streaming ASR de baixa latência ("Rafael Nunes") | M2, M4, M6 |
| `speech-data-scientist` | Corpus, pseudo-labeling, augmentação ("Camila Prado") | M3, M5 |
| `ptbr-phonetics-scientist` | Fonética computacional PT-BR, G2P, BPE ("Thiara Almeida") | M4, M7 |
| `cpu-inference-engineer` | Otimização de inferência em CPU ("Lucas Ferraz") | M2, M6 |
| `rust-runtime-engineer` | Runtime Rust ("Beatriz Rocha") | M0, M1, M6 |
| `audio-dsp-engineer` | DSP de telefonia e VoIP ("André Martins") | M0, M1, M3 |
| `decoding-biasing-engineer` | Decodificação e hotwords ("Eduardo Salles") | discover agora; implementação pós-M2 |
| `ml-infra-engineer` | Infra de treino e reprodutibilidade ("Sofia Mendonça") | M4, M5 |
| `evaluation-scientist` | Métricas, protocolo e significância ("Gustavo Reis") | M1, M4, M5, M8 |
| `hardware-validation-engineer` | Hardware BYOD e piso da frota ("Renata Vieira") | M8, Q-01 |
| `technical-program-lead` | Coordenação científico-engenharia ("Marcelo Paiva") | M0-M8 |

## Alocação por fase

**Núcleo inicial (Fases 0, 0.5 e 1 — M0/M1/M2):** `asr-chief-scientist`,
`streaming-asr-scientist`, `evaluation-scientist`, `rust-runtime-engineer`,
`audio-dsp-engineer`, `hardware-validation-engineer`, `technical-program-lead`.

**Núcleo de dados e piloto (Fase 2 — M3/M4):** entram `speech-data-scientist`,
`ptbr-phonetics-scientist`, `ml-infra-engineer`, `decoding-biasing-engineer`,
`cpu-inference-engineer`.

## Bloqueios de fase que os agents respeitam

| Liberado hoje (independente de arquitetura) | Bloqueado pelo ADR de M2 |
|---|---|
| Captura mic + loopback, VAD, ring buffers, log-mel, afinidade de threads | Decoder |
| Harness de medição dos RNFs | Hotwords / word spotter |
| Corpus, augmentação, manifests (M3, paralelo) | Backend do encoder |
| Test set de call center e protocolo de avaliação | Formato de estado/cache do modelo |

Fonte: `PRD.md` § 8.2 e § 9. Um agent que receba pedido de item bloqueado recusa e
sinaliza — não protótipa "para adiantar".

## Modelo por agent

`opus` nos papéis onde uma conclusão errada custa semanas ou milhares de dólares
(chief scientist, streaming, dados, CPU, avaliação, program lead); `sonnet` nos
papéis mais executórios. É uma linha no frontmatter (`model:`) — ajuste livremente.

## Como invocar

Os agents são acionados pelo nome via Task/Agent, ou automaticamente quando o
contexto casa com a `description` do frontmatter. Divergência entre dois agents é
resultado de valor: registre-a e nomeie o experimento que a resolve — não a dissolva
por senioridade.
