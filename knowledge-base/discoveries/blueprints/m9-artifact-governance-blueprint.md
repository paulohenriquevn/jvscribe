---
slug: m9-artifact-governance
version: 1.0
milestone_id: M9
created_at: 2026-07-30
generated_by: discover-execute
source_plan: knowledge-base/discoveries/plans/m9-artifact-governance-plan.md
peer_sha: 116a44e72c5bb631dcdbdb9c176f0304f5fc6fb0
---

# Blueprint: Governança de artefato de modelo, CI e shared kernel

> **Âncora de reprodutibilidade.** Toda citação `arquivo:linha` abaixo refere-se ao clone
> `knowledge-base/references/sherpa-onnx/` no SHA `116a44e72c5bb631dcdbdb9c176f0304f5fc6fb0`
> (2026-07-30). Todas foram abertas e verificadas: a linha citada **exibe** o fato afirmado.

## Context

M9 precisa decidir três coisas de design, e a auditoria de 2026-07-30 mostrou que decidir por
convicção já custou caro neste projeto (dois `model.int8.onnx` com vocabulários de 502 e 503
linhas convivendo sem que nada falhasse). As perguntas: **como um runtime de ASR maduro
declara e valida o contrato do artefato de modelo**, **como um projeto multi-linguagem
estrutura CI sem falso verde**, e **onde o shared kernel pode morar**.

## Objective

Fornecer ao `/to-plan` de M9 evidência `[FONTE-REPO]` citável para cada decisão, em vez de
convicção. Fonte: `sherpa-onnx` — runtime de ASR em produção, C++, que carrega modelos ONNX
com `tokens.txt` a partir de um diretório, com 199 workflows de CI.

## Coverage Corner 1 — Integration Tests

**Q7 — Como testam a fronteira modelo↔decoder sem baixar artefatos grandes no CI?**

`[FONTE-REPO]` **Nenhum dos 22 arquivos `sherpa-onnx/csrc/*-test.cc` referencia arquivo de
modelo.** Verificado por `grep -ln '\.onnx"\|model_config\|LoadModel' sherpa-onnx/csrc/*-test.cc`
→ zero resultados. A amostra lida em profundidade (`context-graph-test.cc`, 5 TESTs;
`cat-test.cc`, 6 TESTs; `circular-buffer-test.cc`, 2 TESTs) confirma: as únicas ocorrências da
string `onnx` são o `#include "sherpa-onnx/csrc/onnx-utils.h"` e o `namespace sherpa_onnx`
(`cat-test.cc:1,5,8,10,254`) — não dependência de artefato.

**A estratégia é separação por camada, não skip condicional:** os testes unitários exercitam
estruturas de dados puras (context graph, buffer circular, concatenação de tensores) com dados
sintéticos escritos no próprio teste. Nada que exija modelo entra no binário de teste unitário.

**Q8 — Que fixture determinística sustenta os testes de decode, e é versionada?**

`[FONTE-REPO]` Não há diretório de fixture para os testes unitários — os dados são construídos
em código. A validação end-to-end com modelo real vive em workflows dedicados
(`.github/workflows/test-*.yaml` — 6+ arquivos: `test-dart.yaml`, `test-go-package.yaml`,
`test-dot-net.yaml`, `test-build-wheel.yaml`…), separados do job de build/teste unitário.

**Lição para M9:** o nosso problema de `SKIP` silencioso existe porque misturamos as duas
camadas no mesmo comando (`cargo test --workspace`). sherpa-onnx não precisa distinguir
executado-vs-pulado porque **nunca pula**: o teste unitário não tem o que pular.

## Coverage Corner 2 — Dependencies

**Q4 — Como fixam versões de dependência de build?**

`[FONTE-REPO]` Padrão em três camadas, em `cmake/googletest.cmake`:

1. **URL com tag imutável** — `:4` → `set(googletest_URL "https://github.com/google/googletest/archive/refs/tags/v1.13.0.tar.gz")`
2. **Mirror de fallback** — `:5` → `set(googletest_URL2 "https://hf-mirror.com/csukuangfj/sherpa-onnx-cmake-deps/resolve/main/googletest-1.13.0.tar.gz")`
3. **Cache local** — `:20-23`, se o tarball já existir em disco, usa-o e zera o mirror

E, decisivo: **verificação de integridade obrigatória** — `:37` → `URL_HASH ${googletest_HASH}`
dentro do `FetchContent_Declare`. O mesmo padrão em `cmake/json.cmake:30` e
`cmake/espeak-ng-for-piper.cmake:42`.

> Correção de leitura registrada: um primeiro grep sem `URL_HASH` sugeriu "pinning sem
> checksum". Estava errado — o `URL_HASH` está a duas linhas do bloco `URL`, fora da janela
> do grep inicial. A afirmação só entrou aqui depois de abrir `cmake/googletest.cmake:30-40`.

**Lição para M9:** três níveis de robustez que nosso `scripts/setup_onnxruntime.sh` **não**
tem — ele baixa `onnxruntime-linux-x64-1.23.0.tgz` do GitHub sem checksum e sem mirror. Um
artefato corrompido ou substituído passa silenciosamente.

## Coverage Corner 3 — Tools

**Q5 — Qual a forma do CI multi-linguagem?**

`[FONTE-REPO]` `.github/workflows/linux.yaml` (529 linhas) usa `strategy.matrix` (`:68,70`)
com três eixos — `build_type`, `shared_lib`, `with_tts` — e o nome do job é derivado da
matriz (`:66` → `name: ${{ matrix.build_type }} shared-${{ matrix.shared_lib }} tts-${{ matrix.with_tts }}`).
A taxonomia dos 199 workflows é **por prefixo de propósito**: `build-*`, `test-*`, `apk-*`,
`aarch64-*`, `android-*`. Um workflow por combinação plataforma × propósito, não um monolito.

**Q6 — O CI distingue teste executado de teste pulado por falta de artefato?**

`[FONTE-REPO]` **Asserção negativa, com escopo nomeado (checkpoint EC-3):** varri
`.github/workflows/linux.yaml` (26 ocorrências de `if:`, zero de `continue-on-error`) e rodei
`grep -rl GTEST_SKIP sherpa-onnx/csrc/` → **nenhum arquivo**. Não existe mecanismo de
distinção skip-vs-run porque **não existe skip condicional nos testes unitários** (ver Corner 1).

Os 26 `if:` do `linux.yaml` são condicionais de *plataforma e de release* (matriz, upload de
artefato), não de disponibilidade de modelo.

**Lição para M9 — a mais importante do blueprint:** nosso `scripts/test_report.sh` é um
paliativo excelente para um problema que sherpa-onnx **eliminou por design**. Contar SKIPs é
tratar o sintoma; a cura é separar as camadas de teste.

## Coverage Corner 4 — Techniques

**Q1 — O contrato do "diretório de modelo" e onde a ausência é detectada**

`[FONTE-REPO]` `sherpa-onnx/csrc/offline-model-config.cc:67` define
`bool OfflineModelConfig::Validate() const`, que checa em ordem:

- `:79` — `num_threads > 0`, com mensagem que **inclui o valor recebido**
- `:104-105` — `if (!FileExists(tokens))` → `SHERPA_ONNX_LOGE("tokens: '%s' does not exist", tokens.c_str())`
- `:113-114` — idem para `bpe_vocab`
- `:120-167` — **despacha** para o `Validate()` da família de modelo concreta
  (`paraformer`, `nemo_ctc`, `whisper`, `zipformer_ctc:140`, `sense_voice`, `canary`…)

O contrato é: **um config validável, com `tokens` obrigatório, e validação polimórfica por
família de arquitetura**. A mensagem de erro sempre carrega o caminho recebido.

**Q2 — Validação vocabulário × dimensão de saída do modelo — o achado central**

`[FONTE-REPO]` **Sim, existe, e é exatamente o padrão que M9 precisa.** Três instâncias
independentes:

| Local | Verificação |
|---|---|
| `offline-recognizer-canary-impl.h:246` | `if (symbol_table_.NumSymbols() != meta.vocab_size)` → `:247` `SHERPA_ONNX_LOGE("number of lines in tokens.txt %d != %d (vocab_size)", ...)` |
| `offline-ct-transformer-model.cc:93-94` | `if (static_cast<int32_t>(tokens.size()) != vocab_size)` → LOGE com os dois números |
| `offline-recognizer-transducer-nemo-impl.h:267,272-273` | valida **duas** invariantes: `symbol_table_["<blk>"] == vocab_size - 1` **e** `NumSymbols() == vocab_size` |

E o `vocab_size` **não vem de um arquivo à parte** — vem do metadata embutido no ONNX (ver Q3).
Ou seja: o modelo carrega sua própria dimensão, e o `tokens.txt` é conferido contra ela.

Complementarmente, `offline-recognizer-ctc-impl.h:183-192` exige que o `tokens.txt` contenha
`<blk>`, `<eps>` ou `<blank>` e **aborta o processo** (`SHERPA_ONNX_EXIT(-1)`) se não contiver
— fail-fast literal, não degradação.

**Q3 — Como os metadados são transportados**

`[FONTE-REPO]` **Embutidos no próprio arquivo ONNX**, lidos via a API de metadata customizado
do ONNX Runtime: `sherpa-onnx/csrc/onnx-utils.cc:113` →
`meta_data.LookupCustomMetadataMapAllocated(key.get(), allocator)`, e os wrappers em `:429` e
`:432`. Os headers `offline-*-model-meta-data.h` são apenas as *structs* que recebem os
valores lidos.

**Trade-off que isso resolve:** metadata embutido **não pode se separar do modelo**. Um
`model_card.json` ao lado do `.onnx` pode ser copiado sem o par, ou ficar defasado — que é
precisamente o modo de falha que produziu os dois `model.int8.onnx` divergentes neste projeto.

## Cross-cutting Comparison

| Dimensão | sherpa-onnx (`116a44e7`) | Macaw Voice hoje | Delta para M9 |
|---|---|---|---|
| Validação vocab × modelo | 3 instâncias, fail-fast com os dois números na mensagem | **Nenhuma** — `AsrEngine::load` só abre a sessão | Implementar; o padrão está pronto para copiar |
| Origem do `vocab_size` | metadata embutido no ONNX | não lido | Preferir embutido; `model_card.json` como complemento humano, não como fonte |
| Ausência de arquivo | `FileExists` + mensagem com o caminho | erro tipado `ModelNotFound` já existe | Já alinhado |
| Blank id | validado contra o vocabulário, aborta se ausente | `ICEFALL_BLANK_ID = 0` **constante hard-coded** | Validar em vez de assumir |
| Checksum de dependência baixada | `URL_HASH` obrigatório | `setup_onnxruntime.sh` sem checksum | Adicionar |
| Skip em teste unitário | não existe — testes são model-free | 22 testes degradam com `SKIP` silencioso | Separar camadas; `test_report.sh` vira rede, não cura |
| Forma do CI | matriz por plataforma × propósito, 1 workflow por combinação | nenhum CI | Começar com 1 workflow, 1 matriz |

## ADRs

### D1 — `vocab_size` embutido no ONNX é a fonte da verdade; `model_card.json` é complemento

**Decisão:** M9 deve ler `vocab_size` do **metadata embutido no ONNX** e validar o
`tokens.txt` contra ele, como sherpa-onnx faz em `offline-recognizer-canary-impl.h:246`. O
`model_card.json` previsto no DoD permanece — mas como documento **humano** (proveniência,
WER medido, data), nunca como fonte de verdade para validação de dimensão.

**Alternativa rejeitada:** `vocab_size` declarado no `model_card.json` e validado contra ele.
Rejeitada porque um arquivo ao lado pode se separar do modelo ou defasar — exatamente o modo
de falha que criou os dois `model.int8.onnx` divergentes neste projeto.

**Risco residual:** se o export do icefall **não** gravar `vocab_size` no metadata, o fallback
é derivar a dimensão da saída do próprio grafo (`log_probs.shape[-1]`), que é sempre
verificável. Isso deve ser confirmado no `/to-plan` antes de virar task.

### D2 — Separar camadas de teste em vez de contar SKIPs

**Decisão:** o CI de M9 roda **dois jobs distintos** — testes model-free (obrigatórios,
falham o build) e testes que exigem artefato (job separado, explicitamente marcado). O
`scripts/test_report.sh` permanece como rede de segurança local, não como o mecanismo
principal.

**Racional `[FONTE-REPO]`:** sherpa-onnx não precisa distinguir executado-vs-pulado porque
nenhum dos 22 `*-test.cc` toca modelo. O falso verde é eliminado por design, não detectado por
relatório.

**Alternativa rejeitada:** fazer o CI falhar quando o nº de SKIPs sobe. Trata o sintoma e
mantém a ambiguidade estrutural.

### D3 — Checksum obrigatório para artefato baixado

**Decisão:** `scripts/setup_onnxruntime.sh` passa a verificar o SHA-256 do tarball, no padrão
`URL_HASH` de `cmake/googletest.cmake:37`.

**Racional:** hoje o script baixa 1.23.0 do GitHub sem verificação. Um artefato corrompido
produz o modo de falha de 40× de lentidão já documentado no `CLAUDE.md` — que custou uma
investigação inteira em M6.

## Recommendations

Ordenadas por (impacto × evidência ÷ esforço):

1. **Validação `vocab_size` no `AsrEngine::load`** — o padrão está pronto para copiar de
   `offline-recognizer-canary-impl.h:246`. Mata o risco R2 da auditoria (transcrição
   silenciosamente errada).
2. **Validar o blank id em vez de assumi-lo** — `ICEFALL_BLANK_ID = 0` é hard-coded;
   sherpa-onnx valida contra o vocabulário e aborta se ausente
   (`offline-recognizer-ctc-impl.h:183-192`).
3. **Dois jobs de CI** (model-free obrigatório / com-artefato separado), conforme D2.
4. **Checksum no setup do ONNX Runtime**, conforme D3.
5. **`model_card.json` como documento humano** — proveniência e WER medido, sem papel de
   validação.

## O que NÃO foi investigado (limites honestos)

- **Apenas 1 dos 8 peers** foi lido (D1 do plano). As decisões acima apoiam-se numa única
  implementação; onde isso for arriscado, o `/to-plan` deve marcar como hipótese a validar.
- **Fase A com `ast-grep` não foi executada** — as questões se resolveram com `grep` + `Read`
  dirigidos, dentro do orçamento. Nenhuma questão ficou `blocked` por isso, mas o mapa de
  hotspots por AST que o plano previa não existe.
- **Nenhum workflow `test-*.yaml` foi lido em profundidade** — sabe-se que existem e que são
  separados do build; *como* obtêm o modelo não foi verificado.
- **Nenhum número de performance** foi medido ou citado nesta investigação.
- **Shared kernel:** as fontes web da allowlist não foram consultadas; a pergunta de onde o
  `training/common/` deve morar foi respondida por analogia estrutural, não por prior art
  externo. Tratar como `[ESTIMATIVA]` no plano.
