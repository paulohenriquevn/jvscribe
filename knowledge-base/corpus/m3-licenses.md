# M3 — Licenças das fontes de corpus, volume e Q-09

**Data:** 2026-07-25 · **Fonte:** blueprint `m3-corpus` § Corner 2/Q5 (SHIPPABLE 99,1).
Cada linha carrega o rótulo de proveniência (`asr-evidence-discipline § 1`).

## Decisão de risco (dono do projeto)

**Paulo (dono), 2026-07-25, registrado explicitamente:** o risco de licença dos
datasets/repos — incluindo o **TAGARELA `CC-BY-NC-SA-4.0`** (não-comercial) e a
contradição TAGARELA-NC vs modelo-CC-BY — é **assumido pelo dono**. Consequência: as
8.972 h de TAGARELA e o professor parakeet-TAGARELA ficam **liberados** como
fonte/professor. O **fato** (TAGARELA é NC-SA) permanece registrado abaixo por
honestidade; o que muda é a postura de risco, não a proveniência do fato.

## Tabela de licenças e veredito comercial

| Fonte | Licença | Uso comercial | Rótulo |
|---|---|---|---|
| **FLEURS** (google/fleurs pt_br) | CC-BY-4.0 | **Sim** (com atribuição) | `[FONTE-REPO]` card local `datasets--google--fleurs/.../README.md:113,17129` |
| **MLS-PT** (Multilingual LibriSpeech, ~161 h PT) | CC-BY-4.0 | **Sim** (com atribuição) | `[LITERATURA]` HF card `facebook/multilingual_librispeech` |
| **Common Voice (pt)** | CC0-1.0 | **Sim** (domínio público) — re-verificar termos na Mozilla Data Collective (migração out/2025) | `[LITERATURA]` |
| **parakeet-TAGARELA (modelo)** | CC-BY-4.0 (card) | card diz sim (derivado de dados NC-SA — risco assumido) | `[LITERATURA]` |
| **TAGARELA (dataset, 8.972 h)** | **CC-BY-NC-SA-4.0** | **NÃO — non-commercial** (risco assumido pelo dono) | `[LITERATURA]` `huggingface.co/datasets/freds0/TAGARELA` |
| **Cem Mil Podcasts** (Spotify, >76.000 h) | research-only (sem licença comercial pública) | **NÃO confirmável** (Q-09) | `[DESCONHECIDO]` |

## Volume declarado

| Camada | Fontes | Volume | Uso |
|---|---|---|---|
| Comercialmente limpo | FLEURS + MLS-PT + Common Voice | ~ centenas de h (CC-BY/CC0) | base segura sem depender do risco assumido |
| Com risco assumido pelo dono | + TAGARELA (8.972 h, NC-SA) | **8.972 h** | o volume principal que ataca o risco dominante do corpus |
| Upside a negociar | + Cem Mil Podcasts (>76.000 h) | `[DESCONHECIDO]` | Q-09 — negociação humana |

O volume utilizável **com a decisão de risco** é dominado pelas 8.972 h de TAGARELA;
sem ela, cai para as fontes CC-BY/CC0 (ordem de centenas de h). Isto quantifica o
risco dominante: o corpus é o gargalo, e a decisão de risco do dono é o que o afrouxa.

## Q-09 — acesso ao Cem Mil Podcasts bruto

**Resposta honesta `[DESCONHECIDO]` com os termos publicados:**

- **Termos `[LITERATURA]`:** Cem Mil Podcasts (Spotify Research, arXiv:2209.11871) =
  123.054 episódios / 16.131 shows / **>76.000 h** PT (BR + EU), "released for academic
  research purposes". A página do Spotify Research **não detalha licença comercial,
  restrição, nem processo formal de acesso**. TAGARELA (8.972 h ≈ 12% dos 76k) é a
  derivação já pública, mas CC-BY-NC-SA-4.0.
- **O que falta para saber (negociação humana — `technical-program-lead`):** (1)
  contatar Spotify Research diretamente (eles controlam a distribuição); (2) obter o
  data license agreement do bruto; (3) esclarecer se há caminho comercial pago.
- **Conclusão para o DoD:** acesso ao bruto **não confirmável autonomamente**; a via
  pública (TAGARELA) está disponível e, com o risco assumido pelo dono, **utilizável**.
  Segue como upside negociável, não como bloqueio.
