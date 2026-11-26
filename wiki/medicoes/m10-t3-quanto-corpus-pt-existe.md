---
type: Medição
title: T3/Q-12 e Q-13 — quanto corpus pt-BR existe, medindo a variedade
description: >-
  YODAS pt tem 262 h, não 15–25 mil. O volume está no VoxPopuli, que é 3,8% brasileiro. A maior
  fonte pt-BR é o TAGARELA, já em casa e usado a 13%.
tags: [medicao, m10, t3, corpus, granary, yodas, voxpopuli, q12, q13]
timestamp: 2026-09-14T15:00:00Z
---

# T3/Q-12 — o inventário real das fontes abertas `[MEDIDO]`

Data: 2026-09-14 · leitura direta dos manifestos e metadados no Hugging Face, sem baixar áudio.

## A pergunta

O plano M10 assumiu que o YODAS-Granary pt oferecia **15–25 mil horas** `[ESTIMATIVA]`, derivadas
do card do dataset ("5.898.764 amostras, 1,5 TB") e de uma duração média suposta. A meta de
25.000 h do T3 dependia inteiramente desse número. Q-12 pedia medi-lo antes de assumir.

## Evidência

### YODAS pt — medido por duas vias independentes

**Via 1, amostragem dos parquets.** 2.084 arquivos `data/pt*/asr_only/*.parquet`; 10 sorteados
com semente fixa, lidos na coluna `duration`:

| | valor |
|---|---|
| linhas por parquet | 337 (194–616) |
| duração por segmento | média **1,36 s**, mediana **0,98 s** (n=3.368) |
| extrapolação | 701.891 segmentos → **265 h** |

**Via 2, os manifestos do `nvidia/Granary`.** Os cinco `pt/yodas/pt_asr_pt*.jsonl` trazem
`duration` preenchida e podem ser somados sem amostragem:

| shard | linhas | horas |
|---|---|---|
| pt000 | 49.667 | 19 |
| pt100 | 178.917 | 64 |
| pt101 | 182.307 | 66 |
| pt102 | 179.285 | 64 |
| pt103 | 138.962 | 50 |
| **total** | **729.138** | **262** |

As duas vias concordam em **1%** (265 contra 262 h). O número é 262 h.

**O card do dataset erra por ~8×** ao anunciar 5,9M amostras: o manifesto soma 729 mil.

### As outras fontes do Granary pt

| fonte | linhas | horas | proveniência |
|---|---|---|---|
| YouTube-Commons (`ytc`) | 254.656 | **959 h** | `[MEDIDO]` — `duration` preenchida |
| VoxPopuli | 2.282.501 | **~12.700 h** | `[ESTIMATIVA]` — ver abaixo |
| YODAS | 729.138 | **262 h** | `[MEDIDO]` |

**O VoxPopuli não pôde ser medido**: o campo `duration` é a string literal `'None'` em **todas** as
2.282.501 linhas. A estimativa vem da contagem de palavras — 114.463.884 palavras, média de 54,0
por linha — dividida por uma taxa de fala:

| taxa | horas |
|---|---|
| 2,2 palavras/s | 14.453 |
| **2,5 palavras/s** | **12.718** |
| 2,8 palavras/s | 11.356 |

## As duas conclusões, e a segunda é pior

### 1. O volume existe, mas não onde o plano procurava

Granary pt soma **~13.900 h**, o que torna a meta de 25.000 h plausível somando as fontes
existentes. Mas **91% desse volume está no VoxPopuli**, e ele é o único que não pôde ser medido.

### 2. A fonte dominante é do domínio errado — responde parcialmente Q-13

**VoxPopuli é o Parlamento Europeu.** Português europeu, fala preparada, registro formal,
vocabulário institucional. O alvo do projeto é **call center brasileiro**: espontâneo, coloquial,
telefônico, com disfluência e sobreposição.

`e11` já mediu que a banda explica **~1/6** do gap de domínio, e que os outros cinco sextos são
espontaneidade, sotaque e conteúdo — exatamente os eixos em que o VoxPopuli está mais longe do
alvo do que o corpus que o projeto já tem.

Um corpus de 25.000 h dominado por parlamento europeu moveria o WER de FLEURS sem mover o de call
center brasileiro. **Volume não é a mesma coisa que corpus.**

### 3. A granularidade do YODAS é um segundo problema

Segmentos com mediana de **0,98 s** são quase palavras isoladas. Um modelo streaming com chunk de
1120 ms (ADR-006) precisa de utterances mais longas que o próprio chunk para aprender a usar
contexto. As 262 h do YODAS pt entram como dado de baixa utilidade para o regime escolhido.

O VoxPopuli é o oposto: 54 palavras por linha, cerca de 22 s por utterance — boa forma para
contexto longo, domínio errado.

## Q-13 respondida — a variedade, medida em vez de suposta

Não há rótulo de variedade em nenhum manifesto. O que há é texto, e pt-BR e pt-PT divergem em
itens lexicais de alta frequência e em **duas construções gramaticais**: o gerúndio brasileiro
(`está fazendo`) contra o infinitivo preposicionado europeu (`está a fazer`). Contando marcadores
exclusivos por milhão de palavras:

| fonte | palavras | léxico BR | gramática BR | veredito |
|---|---|---|---|---|
| **VoxPopuli pt** | 21,4 M | 22,3% | **3,8%** | **pt-PT** |
| YouTube-Commons pt | 8,5 M | 98,3% | **96,7%** | **pt-BR** |
| YODAS pt | 1,1 M | 98,2% | **95,3%** | **pt-BR** |
| TAGARELA (1 shard) | 11,5 k | 98,2% | **95,2%** | **pt-BR** |

O sinal gramatical é mais limpo que o lexical porque alguns marcadores lexicais são ambíguos
(`fato` é "terno" em pt-PT mas palavra comum em pt-BR; `meia` idem). No VoxPopuli o `a + infinitivo`
aparece **1.807 vezes por milhão** contra 72 do gerúndio — razão de 25 para 1.

## O inventário que importa: horas de pt-BR, não de "pt"

| fonte | horas | % BR | **horas pt-BR** | licença | estilo |
|---|---|---|---|---|---|
| **TAGARELA** | 8.972 | 95,2% | **~8.540** | **CC-BY-NC-SA-4.0** | podcast espontâneo |
| VoxPopuli pt | ~12.700 `[EST]` | 3,8% | ~480 | CC0 | parlamento europeu |
| YouTube-Commons pt | 959 | 96,7% | ~927 | CC-BY | YouTube |
| YODAS pt | 262 | 95,3% | ~250 | CC-BY-3.0 | YouTube, fragmentado |

**Duas conclusões que mudam T3:**

1. **O TAGARELA é 84% de todo o pt-BR disponível** — e o projeto usou **1.139 h dele, 13%**
   (`e13`). A maior fonte não é nova: está identificada, baixável e subutilizada.
2. **A escala e a licença estão em lados opostos.** O TAGARELA é `CC-BY-NC-SA-4.0` — **não
   comercial** — e o produto é para operação de call center de empresa. Somando apenas fontes de
   licença comercialmente limpa, o pt-BR disponível cai para **~1.660 h**.

O risco de licença do TAGARELA já está registrado no `ROADMAP.md` § Constraints como "assumido em
2026-07-24". Esta medição mostra o tamanho do que se assumiu: **sem o TAGARELA o corpus pt-BR é
seis vezes menor.**

O TAGARELA traz ainda uma coluna `accent`, que permite estratificar por sotaque — algo que nenhuma
outra fonte oferece e que o teste de call center vai exigir.

## Q-09 respondida — a fonte bruta é do Spotify, e o acesso está fechado

O `ROADMAP.md` marca Q-09 — acesso às ~76.000 h brutas do *Cem Mil Podcasts* — como **risco
dominante de M3**. A cadeia foi rastreada até a origem:

1. O card e o paper do TAGARELA (`arXiv:2603.15326`, ICASSP 2026) declaram que o corpus foi
   **"collected from the Cem Mil Podcasts repository"**, descrito como *"a massive corpus offering
   over 76,000 hours of diverse, multi-dialect Portuguese audio"*, entregue como **áudio bruto com
   transcrição automática de qualidade variável**.
2. A referência [8] do paper é: Garmash, Tanaka, Clifton, Correia, Jat, Zhu, Jones e Karlgren
   (2023), *"Cem mil podcasts: a spoken Portuguese document corpus…"*, CLEF / LNCS,
   DOI `10.1007/978-3-031-42448-9_5`.
3. **Clifton, Jones e Karlgren são os autores de *"100,000 Podcasts: A Spoken English Document
   Corpus"*** (COLING 2020) — o Spotify Podcast Dataset. O Cem Mil Podcasts é o análogo português,
   do mesmo grupo.
4. **O canal de distribuição não responde.** `podcastsdataset.byspotify.com` devolve resposta
   vazia; `research.atspotify.com/datasets/` redireciona para o blog de engenharia, sem página de
   datasets.

**Consequência:** ir à fonte bruta não afrouxa a licença — aperta. O TAGARELA
(`CC-BY-NC-SA-4.0`) é **o acesso mais permissivo que existe àquele áudio**, e já está em casa. As
76.000 h não são uma alavanca disponível; são o corpus do qual alguém já extraiu, curou e
publicou os 12% que o projeto pode usar.

Q-09 deixa de ser risco em aberto e passa a ser **restrição conhecida**: o teto de pt-BR em
podcast é o TAGARELA, não o Cem Mil Podcasts.

> Não verifiquei se existe canal de solicitação individual ao Spotify Research, nem se o corpus
> circula por acordo institucional. O que está verificado é que **a via pública saiu do ar**.

## O TAGARELA é ~1,9× maior do que o próprio card declara `[MEDIDO]`

O card declara três números que **não fecham entre si**: 8.972 h, 7.111.196 exemplos no split
`train`, e duração média de 9,30 ± 5,49 s. Os dois últimos dão **18.371 h**, não 8.972.

Medição direta, quatro shards lidos por inteiro (16.125 segmentos, 100% de cada shard):

| shard | segmentos | média | horas |
|---|---|---|---|
| 100 | 4.032 | 10,96 s | 12,28 |
| 600 | 4.031 | 7,20 s | 8,06 |
| 1200 | 4.031 | 8,67 s | 9,71 |
| 1700 | 4.031 | 7,52 s | 8,42 |

Agregado: média **8,59 s**, mediana 7,52 s, p10 2,80 s, p90 16,56 s.

Duas vias independentes convergem:

| via | total |
|---|---|
| horas por shard × 1.764 shards | **16.965 h**, IC95% [13.661; 20.269] |
| 7.111.196 exemplos × 8,59 s medidos | **16.968 h** |

**O número de exemplos e a duração média do card estão corretos; o total de horas não.** O corpus
tem cerca de **17.000 h**, não 8.972 — e a ~92% de pt-BR, isso são **~15.600 h de português
brasileiro**, quase o dobro do que o [ADR-0006](../decisoes/0006-tagarela-como-corpus-principal.md)
assumiu ao aceitar o risco de licença.

A variância entre shards é alta (7,20 a 10,96 s de média) **porque cada shard é um show**, e shows
têm estilos diferentes. Por isso o IC é largo: 4 de 1.764 shards é 0,23% de amostra.

## A estrutura do corpus, lida do path

```
podcasts_segmented_enhanced_vocos_16khz_flac/1/X/show_1xbd6Gfk8xiL6YpYdpQL3k/
  0BZA2JUaMiVp2r7Kwe6rlg_<hash>_782.58_800.28-0001.flac
```

Três coisas que o path entrega:

1. **Um shard é um show.** Todos os 4.031 segmentos do shard 882 vêm de
   `show_1xbd6Gfk8xiL6YpYdpQL3k`. Com 1.764 shards para 2.094 shows, é quase um para um — o que
   **valida o amostrador estratificado** que já existe em `finetune/download_tagarela_subset.py`.
   O caveat honesto do docstring ("a estratificação é por posição, não por show") é, na prática,
   por show.
2. **O ID é do Spotify**, confirmando por uma terceira via a origem rastreada em Q-09.
3. ⚠️ **O áudio já passou por realce neural** — `enhanced_vocos`, um vocoder. O `e12` deste projeto
   mediu **"seis técnicas de realce, seis pioras"** e registrou que *"o reconhecedor lida melhor
   com informação faltando do que com informação inventada"*. Treinar em áudio revocodado ensina o
   modelo a esperar artefatos que o áudio real do call center não terá. **Não é bloqueante, mas
   precisa ser verificado antes do treino de escala**: existe versão não-realçada?

## O realce por vocoder: medido, e a conclusão inverte a preocupação `[MEDIDO]`

Não existe versão não-realçada. O paper (§3.5) diz que o Vocos foi **repurposed como denoiser**,
treinado num dataset privado para remover ruído de fundo, hiss e reverberação leve; o que eles
publicam para reprodutibilidade é **o denoiser**, não o áudio cru.

Perfil espectral, metodologia do `e11` com a remoção de DC que aquela medição registrou como
indispensável (mediana por corpus):

| corpus | banda 90% | **banda 99%** | SNR proxy | energia > 7 kHz |
|---|---|---|---|---|
| **TAGARELA** (denoised) | 822 Hz | **3.080 Hz** | 4,4 dB | 0,04% |
| FLEURS pt (natural) | 774 Hz | **5.276 Hz** | 8,7 dB | 0,21% |
| `leitura` (atendimento simulado) | 946 Hz | 1.988 Hz | 7,4 dB | 0,00% |

**O TAGARELA tem 42% menos banda que o FLEURS**, e cinco vezes menos energia acima de 7 kHz. O
vocoder cortou o topo do espectro — é o que um denoiser neural faz, porque é lá que mora o ruído
que ele foi treinado a remover.

**E isso aproxima o corpus do alvo, não o afasta.** Colocando na régua do `e11`, que mediu banda
como a causa acústica do gap de domínio:

```
leitura 1.988 Hz  <  TAGARELA 3.080 Hz  <  LapsBM 4.405 Hz  <  FLEURS 5.276 Hz
   (alvo)              (corpus)                                  (o que temos hoje)
```

O canal telefônico corta em ~3.400 Hz. **O TAGARELA cai praticamente em cima disso**, enquanto o
FLEURS está 55% acima. Treinar em áudio cuja banda já se parece com a do alvo é vantagem, não
defeito — e explica por que o `e12` não se aplica aqui: aquela medição testou **realce aplicado na
inferência**, criando divergência entre treino e teste. Aqui o realce está no **treino**, e move o
corpus *na direção* do domínio de teste.

**O risco que permanece, e não é medido por este instrumento:** o vocoder pode ter introduzido
artefatos sintéticos que o modelo aprenda a esperar. Perfil espectral agregado não os enxerga.
Separar "banda menor porque podcast" de "banda menor porque vocoder" exigiria o áudio cru, que não
existe publicamente. **A mitigação é a cadeia de augmentação que o M3 já construiu** — devolver
ruído e reverberação ao áudio limpo restaura variabilidade acústica e reduz a chance de o modelo
se especializar no artefato.

## Limitações

1. **O VoxPopuli é `[ESTIMATIVA]`.** A taxa de 2,5 palavras/s é típica de fala preparada, mas não
   foi verificada contra este áudio. O intervalo de 11.356 a 14.453 h reflete só a incerteza da
   taxa, não a de segmentação ou silêncio.
2. **Nada foi baixado em áudio.** Todos os números vêm de manifesto e metadado. Se houver
   divergência entre manifesto e o que os arquivos contêm, ela não aparece aqui.
3. **A variedade foi medida no TEXTO, não no áudio.** Marcadores lexicais e gramaticais separam
   os corpora de forma inequívoca (razão de 25:1 no VoxPopuli), mas um falante brasileiro citando
   forma europeia — ou o inverso — conta como o que escreveu, não como o que é. Para um corpus
   inteiro o viés se dilui; para um shard específico, não.
4. **O TAGARELA foi medido em UM shard** (11,5 k palavras de 1.857). A concordância com as outras
   fontes brasileiras dá confiança, mas a distribuição de sotaque entre shards não foi verificada —
   e a coluna `accent` existe justamente para isso.
5. **A amostragem do YODAS usou 10 de 2.084 parquets.** A concordância com o manifesto (1%) dá
   confiança, mas não é censo.

## Consequência para o plano

A premissa de T3 — "YODAS-Granary pt resolve o volume" — **está refutada**, e a fonte que a
substitui já estava em casa.

**O pt-BR disponível soma ~10.200 h**, das quais **~8.540 h são TAGARELA** — identificado,
baixável, com coluna de sotaque, e usado a 13% da sua extensão. A expansão de T3 não depende de
descobrir corpus novo; depende de **escalar o uso do que já foi escolhido em M3**.

Isso reordena as prioridades de T3:

1. **Escalar o TAGARELA de 1.139 h para a faixa de 5.000–8.500 h.** É a alavanca maior, e a mais
   barata: o amostrador estratificado (`finetune/download_tagarela_subset.py`) já existe e é
   auditável. Mas os rótulos são pseudo-Whisper — **é preciso re-rotular com professor adaptado**
   (ADR-003), porque foi ao ruído desses rótulos que M5 fez overfitting.
2. **Somar as ~1.180 h de YouTube** (`ytc` + YODAS), que são pt-BR medido e de licença limpa.
3. **Descartar o VoxPopuli pt** como fonte principal. 3,8% de pt-BR significa que 96% do maior
   volume disponível treina a variedade errada. Pode entrar como dado de pré-treino genérico, nunca
   como corpus de domínio.
4. **A meta de 25.000 h não se sustenta** com fontes abertas em pt-BR. Ou se revisa para a faixa
   de 10.000 h, ou Q-09 (Cem Mil Podcasts, ~76 k h) deixa de ser risco e passa a ser pré-requisito.

E a tensão que T3 tem de resolver antes de T5: **a escala e a licença estão em lados opostos.**
