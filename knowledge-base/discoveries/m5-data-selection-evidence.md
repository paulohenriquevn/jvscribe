# M5 — Evidência para a estratégia de dado (filtro por concordância de pseudo-rótulo)

Nota de evidência `[LITERATURA]` que sustenta a decisão de **como** intervir no dado se o
run atual de M5 platôar acima de ≤25% WER. Não é blueprint nem ADR — é o lastro empírico
citável para o eixo "dado é o gargalo, não a arquitetura" (ver `CLAUDE.md § Contexto que
evita erros repetidos` e o diagnóstico de overfitting medido em M5).

## Fonte

**Rangappa, Carofilis, Kumar, Villatoro-Tello, Motlicek et al. (Idiap Research Institute)** —
*"Efficient Data Selection for Domain Adaptation of ASR Using Pseudo-Labels and Multi-Stage
Filtering"*. Fornecido pelo dono em 2026-07-29. `[LITERATURA]` — não reproduzido por nós.

## Por que é a evidência mais relevante que temos (setup quase idêntico)

| Rangappa et al. | M5 (nós) |
|---|---|
| Zipformer ~70M, pré-treinado (Gigaspeech) | Zipformer 64M, encoder do M4 (161h PT-BR) |
| RTX 3090, ScaledAdam, warmup+decay, RNN-T+CTC, 30 épocas, peak LR 5e-2 | RTX 3090, ScaledAdam, warmup+decay, CTC+fonema, base-lr 0,03 |
| Fine-tune de pseudo-rótulos **Whisper** em call-center (Wow, 7500h, sem GT) | Fine-tune de pseudo-rótulos **Whisper** (TAGARELA ~1110h, sem GT) |

Mesma família de arquitetura, mesma GPU, mesmo regime (pseudo-rótulo Whisper de call-center).

## Achado central `[LITERATURA]` (condições do experimento original)

Condições: Zipformer 70M, decode/WER no test **com** ground-truth (Wow test 18h; Fisher 3h).

| Fine-tune em | WER Zipformer (Wow) | WER Zipformer (Fisher) |
|---|---|---|
| Pré-treinado (sem fine-tune) | 15,6 | 16,2 |
| **Todas** as 7500h/1878h pseudo (baseline) | 14,3 | 15,4 |
| Random 100h (1,4%) | 14,8 (**pior que baseline**) | 15,9 |
| WER-classifier low-WER 100h | 14,6 | 15,5 |
| **CER-agreement < 5% (100h)** | **13,3** (**melhor que o dataset todo**) | **14,6** |

**Conclusão dos autores:** *"what kind of data is selected matters more than the quantity."*
Um subconjunto de ~1,4% dos pseudo-rótulos, filtrado por **concordância inter-ASR (CER médio
< 5% entre Whisper/Zipformer/Parakeet)**, **iguala ou supera** o fine-tune no conjunto completo.
Random selection piora; a qualidade (concordância) é o que importa.

## Mapeamento à nossa decisão

1. **Confirma empiricamente o nosso diagnóstico `[MEDIDO]`** (overfitting ao pseudo-rótulo
   ruidoso do TAGARELA — train ≈ val no melhor ponto de cada época, val sobe dentro da época).
   Treinar no conjunto ruidoso inteiro é subótimo; filtrar por concordância remove o ruído
   que o modelo estava decorando.
2. **Método concreto (substitui o vago "menos TAGARELA"):** decodar TAGARELA com um 2º/3º
   ASR (o Zipformer do M4 + os pseudo-rótulos Whisper já existentes; opcional 3º), computar
   CER par-a-par, manter segmentos com CER médio < τ (~5-8%). Reutiliza a infra de "filtro por
   concordância" do M3 (Regra 9).
3. **Ganho duplo — qualidade E compute:** eles retêm ~15-20% das horas (bin CER 0-5); para
   nós, ~150-220h limpas de TAGALERA + 171h humano CORAA em vez de 1281h ruidosas → épocas
   ~5-6× mais rápidas e teto de WER mais alto.

## Caveats de proveniência (não superinterpretar)

- **WER absoluto NÃO transfere:** eles em 12-14%, nós em ~32%. Eles partem de Gigaspeech
  (inglês, milhares de horas de pré-treino) num idioma com muito mais recurso. O que transfere
  é o achado **relativo** (subconjunto filtrado > conjunto ruidoso), agnóstico a língua/arquitetura.
- **Prep exige GPU** (decodar TAGARELA com um 2º sistema) → roda **depois** que o treino atual
  liberar a GPU; não paralelizável barato agora.
- Falácia §3 evitada: não uso o 13,3% deles como se fosse nosso número (arquiteturas com
  parentesco mas pré-treino/idioma distintos).

## 2ª fonte convergente — OLMoASR (AllenAI, Ngo et al. 2025) `[LITERATURA]`

*"OLMoASR: Open Models and Data for Training Robust Speech Recognition Models"* (Allen AI /
UW / Stanford). Fornecido pelo dono em 2026-07-29. Cenário diferente (treina Whisper-style
**do zero** em web-data inglês, 3M→1M h curadas), mas o achado de **curadoria de dado** é um
experimento **controlado** (mesma arquitetura/recipe/tokenizer, só o dado muda) e **converge**
com o Rangappa por outro caminho.

Ablações de filtragem de texto (short-form WER médio, 14 sets):

| Filtro | WER | Δ | % removido |
|---|---|---|---|
| Sem filtro de qualidade | 37,2 | — | — |
| **Remover linhas repetidas** | 22,7 | **−14,4pp** | 40% |
| Remover caixa anômala (só maiúsc./minúsc.) | 32,4 | −4,8pp | 32% |
| **Comparação texto manual×máquina (WER > τ; τ_doc=0,5, τ_seg=0,7)** | 20,7 | **−16,5pp** | 55% |

Achados que importam para nós:
- **Filtrar pseudo-rótulo/transcrição-automática ruidosa é a alavanca dominante** (mesma
  mensagem do Rangappa, experimento independente).
- **"Remover linhas repetidas" ataca o modo de falha do Whisper** (loops de alucinação em
  áudio não-fala) — e é **text-only, sem GPU**. TAGARELA é Whisper-pseudo → provável alvo.
- **Quantidade satura:** 20× mais horas → só **+2,1pp** short-form. Reforça que **caçar Q-09
  (76k h) rende pouco perto de limpar o que já temos** (qualidade > quantidade, com número).

**Lacuna concreta no nosso pipeline:** `training/prep_tagarela.py::is_hallucinated_text` filtra
**char-runs** (CHAR_RUN_MAX=6) e palavras longas (MAX_WORD_LEN=30) — mas **não** filtra
**repetição de frase/linha**, que é o filtro de −14pp do OLMoASR.

### Medição própria `[MEDIDO]` — o lever de texto barato tem prêmio PEQUENO aqui (2026-07-29)

Auditoria (`tagarela_noise_audit.py`, amostra 150k cuts / 394h do TAGARELA já filtrado, vs baseline
CORAA humano): fração de segmentos com assinatura de loop do Whisper (palavra ≥3× consecutiva,
n-grama repetido, unique-ratio baixo):

| Sinal | TAGARELA | CORAA humano |
|---|---|---|
| qualquer flag de repetição | **3,37%** (4,1% das horas) | 1,28% |
| n-grama em loop | 2,85% | 0,74% |

**Conclusão que corrige o otimismo sobre o OLMoASR:** alucinação grosseira **não** é o problema
dominante no nosso TAGARELA (só ~3-4%, contra os 40% de dados que o OLMoASR remove em web-scraping
cru). Nosso filtro atual + qualidade do Whisper-medium já limpam o lixo óbvio. Portanto o lever de
texto barato rende **pouco** (~4% dos dados), **não** os −14pp do ablation deles. O overfitting
medido é a **erro sutil do pseudo-rótulo** (palavra errada/faltando, estilo ≠ humano), que só o
**filtro por concordância CER (Rangappa, precisa de GPU)** pega — ou é limite de **capacidade** do
64M (referência de viabilidade ≤25% é 600M). Falácia §3 evitada: não transferir o −14pp do OLMoASR
(cenário/ruído distintos) para o nosso caso; medimos o nosso e o prêmio é menor.

## Sequência de decisão (mesma espinha; 1º passo de dado agora mais barato)

1. Terminar o run atual + averaging + beam/LM → medir (grátis; run é init warm-start útil).
2. Se ≤25%: validar DoDs → review → release.
3. Se platôar acima, **na ordem de custo**:
   - (a) **Filtro text-only, sem GPU** — reforçar `is_hallucinated_text` com remoção de
     linha/frase repetida + caixa anômala (OLMoASR, ~−14pp no ablation deles); re-mux;
     continuação warm-start. Barato e rápido.
   - (b) **Filtro por concordância CER** (Rangappa) — decodar TAGARELA com 2º/3º ASR, manter
     CER médio < τ. Maior lift, mas precisa de GPU (pós-run).
   - Quantidade (Q-09) é **última** prioridade (satura, per OLMoASR).
