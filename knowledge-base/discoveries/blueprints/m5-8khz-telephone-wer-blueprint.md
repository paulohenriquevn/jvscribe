# Blueprint — WER 8 kHz telefônico (call center BR) para Zipformer-CTC 64M em CPU

**Origem:** deep research (2026-07-29) de 2 cientistas do time (`speech-data-scientist`,
`asr-chief-scientist`) após o fracasso medido da continuação D2. Disciplina de evidência
`.claude/rules/asr-evidence-discipline.md`: todo número rotulado.

## Contexto (o problema)

- Deliverable M5 = Zipformer-CTC medium 64M + fonema, int8 ONNX. **Wideband 23,31% WER
  [MEDIDO]**, RTFx 34× CPU. **Telefônico-proxy 8 kHz (bandpass) 31,97% [MEDIDO]** — não bate
  o alvo DoD#3 ≤25%.
- Tentativa D2 (fine-tune full com augmentação telefônica on-the-fly, base-lr 0,006, fp32,
  warm-start de checkpoint médio) **colapsou o modelo** para near-blank (WER ~98% em wideband
  **e** telefônico) `[MEDIDO]`. Verificado que não é ambiente/harness/features: `avg_124_112`
  no mesmo ambiente = 22,09% `[MEDIDO]`.

## Causa-raiz do colapso D2 (evidência)

CTC tem atrator trivial para `blank` (peaky behavior, arXiv:2105.14849 `[LITERATURA]`). Um
modelo convergido vive numa solução peaky; o choque de augmentação religada de golpe + LR
alto o empurra para a bacia de blank. Agravantes medidos/documentados:
- `base-lr 0,006` **acima** do recomendado — icefall manda ~1/10 do LR de treino ≈ 0,0045
  `[FONTE-REPO]` (`references/icefall/docs/source/recipes/Finetune/from_supervised/finetune_zipformer.rst`).
- Warm-start de **checkpoint médio** (`--avg`) + scheduler Eden reinicia em batch=0 → LR
  efetivo volta ao **pico** com warmup curto `[FONTE-REPO]` (`egs/librispeech/ASR/zipformer/optim.py:841-900`).
- Augmentação aplicada a ~100% do batch (sem âncora de alinhamento limpo) `[FONTE-REPO]`
  (`scripts/corpus/telephone_channel_transform.py`).
- Assinatura: `ctc_output.norm` 245→108, near-blank `[MEDIDO]`.

## Causa-raiz do platô telefônico (31,97%)

A augmentação atual usa **G.711 A-law fixo** `[FONTE-REPO]` (`scripts/corpus/telephone_channel.py`).
A literatura (APSIPA 2019, 27 codecs FFmpeg `[LITERATURA]`) classifica **G.711 como o codec
mais inócuo** (quase não degrada ASR); os que transferem para telefonia real são os agressivos
(GSM-FR, AMR-NB, G.729, Opus baixo-bitrate). O modelo treinado no codec brando não generaliza
para o canal real. Trocar por **pool de codecs realistas** rende **7,28–12,78 pp absolutos**
no paper.

## Ativo descoberto: dev/test 8 kHz REAL

`callcenter/texto.mp3` = chamada real **8 kHz, ~9 min, transcrição HUMANA timestampada,
PII mascarada** `[MEDIDO]`. É a semente do **dev/test real** do DoD#3 (o único jeito honesto
de medir — proxy bandpass é falácia § 3 #6). LGPD: uso **local**, nunca versionar. Um call de
9 min tem IC largo (§ 3 #12) → precisa ≥20-30 min de fala humana para número travável.

## Ranking unificado de alavancas (impacto WER 8 kHz × custo/risco)

| # | Alavanca | Impacto esperado | Custo/risco | Fonte |
|---|---|---|---|---|
| **1** | **n-gram LM + prefix-beam no decode** | ~10–15% rel (→ ~27–29%) | Baixíssimo — zero treino, zero colapso, cabe no CPU | `[FONTE-REPO]` LibriSpeech RESULTS.md; `[ESTIMATIVA]` transfere p/ 8k por analogia "difícil" |
| **2** | **Pool de codecs realistas** (GSM/AMR/G.729/Opus), p=0,5, curriculum, substituindo G.711-fixo | +7–13 pp | Baixo — ffmpeg/torchaudio AudioEffector on-the-fly, zero dado novo | `[LITERATURA]` APSIPA 2019 |
| **3** | **Dev/test 8 kHz real** (`callcenter/` humano) + coletar mais | Alto p/ validade da medição | Baixo-médio — LGPD local-only, precisa ≥20 min | `[MEDIDO]` |
| **4** | **8 kHz-nativo** (fbank sr=8000, fmax~3600, ~64 mel), re-treino no mesmo encoder | Maior teto (nativo 28,98% vs wideband-em-8k 71,23%) | Médio — re-extrair features + treino novo (muda dim entrada; novo ADR); sem risco de colapso | `[LITERATURA]` Li et al./Microsoft ICASSP 2013 |
| **5** | **Mixed-bandwidth FT** (16k ∪ 8k-upsampled, `--use-mux 1`, LR 0,002, warmup 4000, aug em rampa, single-ckpt) | Médio-alto (8k 29,33% mantendo 16k 28,27%) | Médio — colapso mitigado pela receita gentil | `[LITERATURA]` Li et al. |
| **6** | **Adapter/LoRA de canal** (encoder congelado) | Médio — adaptação gentil | Baixo — 1,15% params, recipe pronta; LoRA merge-able (custo CPU zero) | `[FONTE-REPO]` `references/icefall/egs/librispeech/ASR/zipformer_{adapter,lora}/` |
| **7** | Pseudo-label de call real (transcritores heterogêneos + filtro CER) → só treino | Médio-alto | Médio — LGPD (voz=biométrico, jurídico), Whisper alucina em 8k | `[LITERATURA]` Distil-Whisper |
| **8** | Q-09 Cem Mil Podcasts (wideband) como volume sob augmentação #2 | Alto p/ WER geral | Alto — acesso/ToS pendente | `[DESCONHECIDO]` |
| ✗ | **Bandwidth-extension (neural upsampling)** | Baixo/negativo — "never improvements over native" | Alto (rede extra no CPU) | `[LITERATURA]` Li et al. — **DESCARTADA** |

## Sequência recomendada (valor/custo)

1. **#1 n-gram LM** (grátis, primeiro) → medir no dev real → **novo piso** antes de qualquer re-treino.
2. Em paralelo: **#3 dev/test real** + **#2 pool de codecs** (prepara o dado para qualquer FT).
3. Se ainda >25%: **#5 mixed-bandwidth FT corrigido** (a "D2 do jeito certo") **ou** **#6 adapter/LoRA** — baratos, FT-compatíveis.
4. Maior teto se preciso: **#4 8 kHz-nativo** (novo ADR de features — o produto É 8 kHz).
5. Diagnóstico barato em paralelo: repetir D2 mudando **uma** variável (LR / single-ckpt / rampa) para isolar o gatilho do colapso.

## ⚠️ Divergência entre cientistas (registrada, não dissolvida — regra do projeto)

**Sobre a alavanca #4 (8 kHz-nativo):** os cientistas DISCORDAM, e a evidência mais forte
inverte a recomendação.
- `asr-chief-scientist` recomendou features **8 kHz-nativas** (menos mel bins, fmax~3600) como
  maior teto, citando Li et al./Microsoft 2013 (nativo 28,98% vs wideband-em-8k 71,23%)
  `[LITERATURA]`.
- `audio-dsp-engineer` **refuta o mecanismo** com evidência `[FONTE-REPO]` mais atual e do nosso
  próprio toolkit: icefall (`egs/swbd/ASR/local/compute_fbank_swbd.py:108`) **e** ESPnet
  (`egs2/swbd/asr1`) — ambos em SWBD (corpus 8 kHz nativo) — **fazem `.resample(16000)` ANTES
  do `Fbank(80 bins)`**, i.e. upsample 8k→16k e reusam o extrator wideband. Construir extrator
  nativo com menos bins é a convenção **pré-E2E (GMM-HMM) abandonada** (Kaldi mfcc_hires 40 bins).
  **Nossa config atual (80 bins @16 kHz + resample) já É a convenção SOTA.**

**Reconciliação:** o *objetivo* (casar treino ao canal) está certo; o *mecanismo* "extrator
nativo fewer-bins" está desatualizado. O casamento moderno se faz por **upsample + augmentação
de codec realista (#2) + bandwidth-embedding (abaixo)** — NÃO por um 2º pipeline de features.
**Alavanca #4 rebaixada** para "não fazer sem piloto de contra-experimento"; nossa feature atual
está correta. Experimento que resolve: piloto pequeno nativo-fewer-bins vs upsample-atual no
mesmo test set 8 kHz real — só investir se o nativo ganhar.

## Alavancas adicionais do 3º cientista (DSP/canal)

| # | Alavanca | Impacto | Custo | Fonte |
|---|---|---|---|---|
| **9** | **Bandwidth-embedding auxiliar** (1 feature extra "é telefônico" concatenada ao input) | +13% rel em NB sem degradar WB `[LITERATURA]` (arXiv:1909.02667) | **~zero CPU** (1 canal) | candidata cheap de alto valor p/ o gap DoD#3 |
| **10** | **AMR-NB tandem** (origem celular→G.711 no gateway) no simulador — o path físico mais comum em call center BR, hoje 100% ausente | Alto `[ESTIMATIVA]` | Baixo (offline); requer `ffmpeg` + `libavcodec-extra` (encode AMR não está no build padrão) `[MEDIDO]` | refina a alavanca #2 |
| ✗ | **Front-end de inferência (AGC/NS/dereverb)** | incerto, **risco de PIORAR o WER** (processing distortion) `[LITERATURA]` arXiv:2311.11599 | — | **não adicionar sem A/B de WER**; robustez vem da augmentação de TREINO, não do front-end |

**Nota de arquitetura (DSP):** no caso 1:1 o cliente vem por telefonia (degradar o stream de
loopback) mas o mic do atendente é VoIP local (talvez sem degradação) — **decidir se a augmentação
de canal se aplica por-stream** antes da próxima rodada com dado real. Questão em aberto.

## 🧪 Testes de mesa (2026-07-29) e decisões PhD-level

Dois desk-checks sobre o baseline real de 40,13%, mais correção de método (evidência mandou):

**TM#1 — decomposição S/D/I `[MEDIDO]`** (`analyze_errors.py`, modelo entregue, call real):
`hits 65,0% · substitutions 23,7% (DOMINA) · deletions 11,4% · insertions 5,1%`.
- **Hipótese "mistura de 2 falantes infla via deleção" → REFUTADA** (deleções só 11,4%; ~5 pp
  de inflação, não a maioria). O erro é **confusão acústica (substituição)**, não perda de fala.
- O modelo **acerta 2/3 das palavras** num áudio real difícil — base decente; gap fechável.
- Consequência: erro substituição-dominante é (a) parcialmente corrigível por **LM** e (b)
  principalmente pela **augmentação de codec realista** (o modelo confunde porque nunca viu o
  canal real). A alavanca acústica é a principal; o LM é complemento barato.

**TM#2 — sensibilidade a codec `[MEDIDO]`** (ffmpeg tandem sobre o call real):
`mp3 40,13% · μ-law 39,35% · GSM-FR 41,90%`. Deltas pequenos (±2 pp) mas na ordem da literatura
(μ-law inócuo, GSM pior) — **abafados** porque o áudio já é mp3 8 kHz (tandem muda pouco). O teste
limpo de codec exige áudio **limpo mono-falante** (CORAA, na instância). Valida a ferramenta.

**Correção de método (a decisão mais importante):** produção é **1:1 com canais SEPARADOS**
(mic=atendente VoIP-local, loopback=cliente 8 kHz) → **cada stream é MONO-FALANTE**. O 40,13% foi
medido em **mono-misto (2 falantes)** — condição mais difícil e **diferente** da produção. O alvo
honesto do DoD#3 é **mono-falante real-codec 8 kHz** (stream do cliente).

### Decisões travadas
| # | Decisão | Base |
|---|---|---|
| D1 | **Métrica âncora = CORAA humano + pool de codecs realistas (mono-falante, N grande, IC estreito).** 40,13% (mono-misto) vira upper-bound de stress; 31,97% (bandpass) é lower-bound otimista. | correção de método + TM#1 |
| D2 | **Alavanca principal = FT gentil corrigido com codec-pool** (single-ckpt, LR 0,002, warmup 4000, codec p=0,5 em rampa, `--use-mux 1`, + bandwidth-embedding). Precisa de GPU. | substituição domina (TM#1) + APSIPA + recipe icefall |
| D3 | **LM n-gram (shallow fusion) = complemento barato**, avaliado sobre o modelo melhorado, não isolado primeiro. | substituições são LM-addressable, mas menor que a acústica |
| D4 | **Augmentação por-stream**: degradar só o stream do cliente; o mic do atendente pode ficar wideband. | arquitetura 1:1 |
| D5 | **CPU-agora (instância pausada): implementar+testar o transform de codec-pool** (prerequisito do D2, GPU-free). Re-provisionar GPU só quando a ferramenta estiver pronta. | parsimônia + não desperdiçar GPU |

## ADRs a registrar quando decidir

- Se #4 virar produto: **novo ADR de features 8kHz-nativo** (muda dim de entrada; ≠ artefato exportado hoje).
- Trocar canal de augmentação (#2): documentar em `scripts/corpus/telephone_channel.py` + CHANGELOG.

## Limites honestos deste blueprint

- Nenhum WER 8 kHz de melhoria é `[MEDIDO]` nosso — são `[LITERATURA]` (Li et al./CD-DNN-HMM;
  APSIPA) ou `[FONTE-REPO]` (LibriSpeech). O fator telefônico BR real (§ 3 #6) e o IC (§ 3 #12)
  só saem de medição no dev/test real.
- Não decide arquitetura/tamanho (ADR 0003 fixou medium 64M).

## Fontes

- Peaky/blank: arXiv:2105.14849 · Less-peaky priors arXiv:2406.02560
- Mixed-bandwidth: Li, Yu, Huang & Gong (Microsoft, ICASSP 2013)
- Codec-aug: APSIPA 2019 http://www.apsipa.org/proceedings/2019/pdfs/216.pdf · Channel-Aware arXiv:2211.01669
- Pseudo-label: Distil-Whisper arXiv:2311.00430 · Self-Taught Recognizer arXiv:2405.14161
- Peers locais `[FONTE-REPO]`: `references/icefall/egs/librispeech/ASR/{zipformer/finetune.py,zipformer/optim.py,zipformer_adapter/,zipformer_lora/,RESULTS.md}`, `references/icefall/docs/source/recipes/Finetune/`, `references/lhotse/lhotse/features/kaldi/extractors.py`
