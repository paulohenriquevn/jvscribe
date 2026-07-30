---
slug: m9-artifact-governance
milestone_id: M9
created_at: 2026-07-30
base_sha: 6f3755d
goal: Fechar as lacunas de integridade e reprodutibilidade da auditoria de 2026-07-30, validando identidade de vocabulário (não cardinalidade), instalando CI e consolidando o shared kernel.
---

# Plan: Governança de artefato de modelo, CI e shared kernel (M9)

## Goal

Tornar impossível a transcrição silenciosamente errada por artefato trocado, tornar a suíte
verificável por terceiros, e dar um dono único ao conhecimento hoje replicado — sem excluir
nenhum modelo e sem workaround.

## Context

A auditoria de system design de 2026-07-30 (`system-design-output/final_report.md`, 51
achados, 4 quality gates aprovados) mediu que o produto ocupa 9% dos bytes do repo, que dois
diretórios disputam o nome `model.int8.onnx`, e que a suíte não roda fora da máquina do dono.

O ciclo DISCOVER (`knowledge-base/discoveries/blueprints/m9-artifact-governance-blueprint.md`,
SHIPPABLE 99,4) trouxe o padrão de validação do peer `sherpa-onnx`. **A medição feita durante
o planejamento invalidou a porta ingênua desse padrão** — ver `## Prior Art & Related Work`.

## Baseline Context (deep review of current state)

Estado medido em `6f3755d`.

### Files that will be touched

| Arquivo | LoC | O que faz hoje | Invariants to preserve |
|---|---:|---|---|
| `crates/macaw-asr/src/lib.rs` | 311 | `Vocab::load`, `AsrEngine::load/ctc_logits/transcribe`; erros tipados `AsrError` | Nunca panica; erro sempre tipado com contexto (`error-handling.md` § 2) |
| `crates/macaw-asr/src/decode.rs` | 118 | `ctc_greedy` + `detok`; `vocab` vem do shape da saída | Colapso CTC: remove blank e repetição adjacente |
| `crates/macaw-cli/src/transcribe.rs` | 133 | caller de produção `wav → fbank → transcribe` | Emite métrica de runtime (pilar c do wiring triad) |
| `crates/macaw-cli/src/app.rs` | 526 | dashboard local; `m1_measurements_json` lê diretório removido | Bind só em `127.0.0.1` |
| `crates/macaw-cli/src/main.rs` | 217 | roteamento `fixture/bench/live/transcribe/serve` | `ensure_ort_dylib()` antes de qualquer uso de `ort` |
| `scripts/setup_onnxruntime.sh` | 13 | baixa ORT 1.23.0 sem verificação de integridade | Idempotente (sai cedo se já presente) |
| `.gitignore` | 63 | linhas 57-58 anulam a exceção da linha 17 | Modelos e pesos NUNCA versionados |
| `training/batch/batch_transcribe.py` | 208 | transcrição em lote; `greedy` próprio | RTFx agregado no `transcripts.json` |
| `training/batch/decode_onnx_local.py` | 124 | decode local; `greedy_ctc` próprio | — |
| `training/eval/measure_realcodec.py` | 88 | WER telefônico; `greedy` próprio (detok via `sp.decode`) | Roda em CPU, não toca GPU |
| `training/eval/measure_callcenter.py` | 112 | WER de call center; `greedy` próprio | — |
| `training/scripts/tta_feature_align_probe.py` | 152 | probe fechado; `greedy` próprio | — |
| `scripts/text_normalize_ptbr.py` | 84 | `normalize_ptbr` que **remove** acentos | Determinístico, ordem fixa de passos |
| `training/finetune/prep_icefall.py` | 141 | `normalize_ptbr` que **preserva** acentos | Alvo de treino não perde acento |
| `training/conftest.py` | 14 | injeta as 4 pipelines no `sys.path` | Suíte roda de qualquer cwd |
| `training/tests/test_pipeline_layout.py` | 63 | guarda: sem script solto, sem import cross-pipeline | A guarda não pode ser enfraquecida |
| `README.md` | 66 | 5 de 5 links internos quebrados | Sem claim de "production-ready" (`public-copy.md`) |

### Current callers / dependents

| Símbolo | Callers de produção | Callers de teste |
|---|---|---|
| `AsrEngine::load` | `crates/macaw-cli/src/transcribe.rs:112`, `crates/macaw-cli/src/app.rs:447`, `crates/macaw-cli/src/main.rs:141`, `:221` | `asr_test.rs:16,57`, `forward_pass_test.rs:69`, `real_speech_test.rs:48`, `real_speech_from_wav_test.rs:80`, `transcribe_smoke_test.rs:27`, `vocab_load_test.rs:60` |
| `Vocab::load` | dentro de `AsrEngine` | `vocab_load_test.rs` |
| `ctc_greedy` (Rust) | `AsrEngine::transcribe` | `ctc_decode_test.rs` (7 testes) |
| `greedy` (Python, 5 cópias) | cada pipeline chama a sua | nenhum teste de conformidade entre elas |
| `normalize_ptbr` (5 cópias) | `prep_coraa.py:46`, `prep_tagarela.py:70` importam a de `prep_icefall`; as outras são locais | `test_prep_coraa.py:23`, `test_prep_tagarela.py:82` |

### Domain glossary

| Termo | Definição operacional neste projeto |
|---|---|
| **Token real** | Entrada do `tokens.txt` que o modelo pode emitir — id `< dim de saída`. Exclui símbolos de desambiguação. |
| **Símbolo de desambiguação** | Entradas `#0`, `#1`, `#2`… que o icefall emite no `tokens.txt` para construção do `L.fst`. **Medido:** 2 no artefato do runtime, 3 no de eval. Nunca emitidos pelo modelo. |
| **Fingerprint de vocabulário** | SHA-256 sobre a sequência ordenada `id\ttoken` dos tokens reais. Identidade, não cardinalidade. |
| **Artefato canônico** | O par (modelo, vocabulário) declarado como fonte da verdade em `models/current/`. |
| **Cardinalidade de saída** | Última dimensão de `log_probs`. **Medido:** estática (`['N','T',500]`) — legível na carga, sem inferência. |
| **Falso verde** | Suíte reportando sucesso quando testes degradaram para `SKIP` por falta de ambiente. |

### Architecture boundaries affected

- `macaw-audio` (domínio DSP) — **não é tocado**. A validação vive na fronteira de inferência.
- `macaw-asr` (adapter ONNX) — ganha a validação de identidade. Continua sendo o único que
  conhece `ort` (`architecture.md` § 2, DIP preservado).
- `macaw-cli` (composition root) — só propaga o erro tipado; não decide.
- `training/common/` (**novo**) — shared kernel Python. A guarda de layout passa a permitir
  import cross-pipeline **apenas** a partir dele (`architecture.md` § 3, coesão de módulo).

## Prior Art & Related Work

- **Blueprint M9** (`knowledge-base/discoveries/blueprints/m9-artifact-governance-blueprint.md`)
  — 8 questões, evidência `[FONTE-REPO]` no SHA `116a44e7`.
- **`sherpa-onnx` valida vocabulário** em 3 instâncias, ex.
  `offline-recognizer-canary-impl.h:246` → `if (symbol_table_.NumSymbols() != meta.vocab_size)`.
- **⚠️ A porta ingênua desse padrão NÃO serve aqui `[MEDIDO]`.** Medição feita em
  2026-07-30 sobre os dois artefatos em disco:

  | | `training/results/onnx/` | `models/m5-final-medium-phoneme/` |
  |---|---|---|
  | `log_probs` dim | `['N','T',500]` | `['N','T',500]` |
  | tokens.txt | 502 linhas | 503 linhas |
  | desambiguação | `#0,#1` | `#0,#1,#2` |
  | **tokens reais** | **500** | **500** |
  | **ids com token diferente** | — | **492 de 500** |

  Os dois vocabulários têm **cardinalidade idêntica e conteúdo quase totalmente diferente**
  (id 4 = `▁a` num, `r` no outro). Um check de cardinalidade **passa nos dois** e a
  transcrição continua lixo. Por isso D1 valida **identidade**.
- **`custom_metadata_map` do nosso ONNX `[MEDIDO]`:** contém `model_type`, `model_author`,
  `version`, `comment` — **não contém `vocab_size`**. O caminho do peer (ler vocab do
  metadata) não está disponível; a dimensão vem do shape estático de saída.

## Objective

1. `AsrEngine::load` recusa o par (modelo, vocabulário) incoerente, com erro tipado.
2. `models/current/` declara o artefato canônico, com `model_card.json` contendo o
   fingerprint do vocabulário.
3. CI roda em runner limpo, com job model-free obrigatório separado do job com artefato.
4. `training/common/` hospeda uma única implementação de colapso CTC e de normalização.
5. Nenhum modelo, peso ou vocabulário é removido em nenhuma task.

## ADRs

### D1 — Validar identidade de vocabulário, não cardinalidade

**Decisão:** `AsrEngine::load` valida (a) `tokens_reais == dim_saida_do_modelo` e (b) o
**fingerprint** SHA-256 do vocabulário contra o valor declarado no `model_card.json`, quando
presente. A ausência de `model_card.json` degrada para apenas (a), com aviso.

**Alternativas rejeitadas:** (i) só cardinalidade, como o peer — **medido insuficiente**: os
dois artefatos têm 500 tokens e 492 mapeamentos divergentes; (ii) ler `vocab_size` do
`custom_metadata_map` — **medido indisponível** no nosso export; (iii) validar a cada
`transcribe()` — custo por-utterance sem ganho, já que o par não muda depois da carga.

**Consequência:** o fingerprint tem de ser computado sobre os **tokens reais**, excluindo
símbolos de desambiguação — senão dois lang-dirs equivalentes com nº diferente de `#N`
produziriam fingerprints diferentes por um artefato do FST.

### D2 — Excluir símbolos de desambiguação da contagem

**Decisão:** token cujo símbolo casa `^#\d+$` é excluído da contagem e do fingerprint.

**Alternativas rejeitadas:** (i) contar tudo — quebraria em artefato correto (medido: 502 e
503 linhas para 500 classes); (ii) truncar pelos primeiros N — silencioso e frágil se a
ordem mudar.

### D3 — Dois jobs de CI, não contagem de SKIP

**Decisão:** job `test-model-free` (obrigatório, falha o build) e job `test-with-artifact`
(separado, roda só quando o artefato está disponível).

**Alternativas rejeitadas:** (i) CI que falha se o nº de SKIPs sobe — trata o sintoma e
mantém a ambiguidade; (ii) baixar 27 MB de modelo em todo job — encarece e acopla o CI a um
artefato não versionado.

**Racional `[FONTE-REPO]`:** nenhum dos 22 `*-test.cc` do sherpa-onnx toca modelo; o falso
verde é eliminado por design.

### D4 — Checksum obrigatório no download do ONNX Runtime

**Decisão:** `setup_onnxruntime.sh` verifica SHA-256 antes de extrair.

**Alternativa rejeitada:** confiar na URL com tag — o peer usa `URL_HASH` mesmo com URL
imutável (`cmake/googletest.cmake:37`), e o modo de falha aqui (40× de lentidão) já custou
uma investigação inteira.

## Drawbacks & Risks

| # | Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|---|
| R1 | A validação de identidade quebra fluxos que hoje passam em silêncio com o par errado | Alta | Médio — falha alto em script que ninguém sabia estar quebrado | Fingerprint é opcional quando não há `model_card.json`; T1.3 gera o card para o artefato canônico antes de T1.2 endurecer |
| R2 | Consolidar as 5 cópias de `greedy` muda sutilmente um número já publicado | Média | Alto — invalidaria WER do CHANGELOG/paper | T3.1 escreve **primeiro** um teste de equivalência entre as 5 cópias sobre a mesma entrada; só consolida se forem equivalentes, e registra a divergência se não forem |
| R3 | O CI expõe quantos testes fazem SKIP e o número é desconfortável | Alta | Baixo — é informação, não regressão | D3 separa os jobs: o número deixa de ser ambíguo |
| R4 | Mover o artefato para `models/current/` quebra script com caminho hard-coded | Média | Médio | T1.3 usa **symlink** e mantém o caminho antigo funcionando; nenhum arquivo é movido ou removido |
| R5 | `#N` de desambiguação pode não ser a única classe de token não-emitível | Baixa | Alto — falso negativo na validação | T1.1 assere a regra sobre os **dois** artefatos reais em disco, não sobre um |

## Unresolved Questions

- Q1 — O export do icefall pode ser instruído a gravar `vocab_size` no `custom_metadata_map`?
  Se sim, uma versão futura pode simplificar D1. **Não bloqueia M9** (o shape estático basta).
- Q2 — As 5 implementações de `greedy` são realmente equivalentes? T3.1 mede antes de
  consolidar; se divergirem, a consolidação vira decisão de qual está certa, com evidência.
- Q3 — Runner de CI: GitHub-hosted basta para `cargo test --workspace`? O build do `ort` com
  `load-dynamic` precisa do dylib em `vendor/`, baixado por script. Resolve-se em T2.3.

## Dependency Graph

```
T1.1 (fingerprint + contagem real)
  └─> T1.2 (validação no load)   ──┐
  └─> T1.3 (model_card + current) ─┴─> Fase 1 completa
T2.1 (.gitignore)  ─> T2.3 (CI)   [T2.1 antes de T2.3: sem fixture, o CI falha]
T2.2 (checksum)    ─> T2.3
T2.4 (LICENSE/toolchain) ─> T2.3
T3.1 (equivalência + common/ctc.py) ─> T3.2 (common/text.py) ─> T3.3 (guarda)
T4.1..T4.3 (limpeza) — dependem de T2.3 (CI verde como rede)
```

## Phase 1: Integridade do artefato

### T1.1 — `Vocab` expõe tokens reais e fingerprint

#### Objective
Separar, em `Vocab`, os tokens emitíveis dos símbolos de desambiguação, e derivar um
fingerprint estável de identidade.

#### Why this step (action + reasoning)

**O que faz:** adiciona a `Vocab` (em `crates/macaw-asr/src/lib.rs`) os métodos
`real_len()` — contagem excluindo `^#\d+$` — e `fingerprint()` — SHA-256 sobre a sequência
ordenada `id\ttoken` dos tokens reais.

**Por que agora:** T1.2 não pode validar nada sem uma definição operacional de "tamanho do
vocabulário" que sobreviva aos artefatos reais. A medição registrada em
`## Prior Art` mostra 502 e 503 linhas para 500 classes: contar linhas é errado por
construção. D2 fixa a regra; esta task a implementa e a prova nos dois artefatos.

#### Evidence
`[MEDIDO]` 2026-07-30: `training/results/onnx/tokens.txt` tem 502 linhas, ids 0..501, com
`#0 500` e `#1 501`; `models/m5-final-medium-phoneme/tokens.txt` tem 503 linhas com
`#0,#1,#2`. Ambos os modelos: `log_probs` shape `['N','T',500]`.

#### Files to edit
```
crates/macaw-asr/src/lib.rs — Vocab::real_len(), Vocab::fingerprint()
crates/macaw-asr/tests/vocab_load_test.rs — RED tests primeiro
```

#### TDD

```
test_real_len_exclui_simbolos_de_desambiguacao:
  Given um tokens.txt com 3 tokens reais e 2 entradas "#0 3" / "#1 4"
  When  Vocab::load
  Then  assert_eq!(vocab.real_len(), 3) e assert_eq!(vocab.len(), 5)

test_fingerprint_e_estavel_para_mesmo_conteudo:
  Given dois tokens.txt idênticos em arquivos distintos
  Then  assert_eq!(a.fingerprint(), b.fingerprint())

test_fingerprint_difere_quando_um_id_mapeia_token_diferente:
  Given dois vocabulários de MESMO tamanho com um id trocado
  Then  assert_ne!(a.fingerprint(), b.fingerprint())

test_fingerprint_ignora_diferenca_apenas_em_desambiguacao:
  Given dois vocabulários com os mesmos tokens reais e nº diferente de #N
  Then  assert_eq!(a.fingerprint(), b.fingerprint())
```

#### Acceptance criteria
- [ ] `cargo test -p macaw-asr --test vocab_load_test` reporta `4 passed; 0 failed`
- [ ] `Vocab::real_len()` retorna exatamente `500` para `training/results/onnx/tokens.txt` e para `models/m5-final-medium-phoneme/tokens.txt`
- [ ] `Vocab::fingerprint()` produz valores diferentes para os dois `tokens.txt` reais — `assert_ne!` no teste, cobrindo os 492 ids divergentes medidos

### T1.2 — `AsrEngine::load` recusa par incoerente

#### Objective
Falhar alto na carga quando o vocabulário não corresponde à saída do modelo.

#### Why this step (action + reasoning)

**O que faz:** lê a última dimensão de `log_probs` do type-info da sessão (disponível sem
inferência) e compara com `Vocab::real_len()`; havendo `model_card.json`, compara também o
fingerprint. Falha com `AsrError::VocabModelMismatch` contendo os dois números.

**Por que agora:** é o item que mata o risco R2 da auditoria — transcrição silenciosamente
errada. Depende de T1.1 (a definição de `real_len`) e precede tudo o mais: sem ele, qualquer
número medido depois é suspeito.

#### Evidence
`crates/macaw-asr/src/lib.rs:286` já lê `let vocab = shape[2] as usize` — mas só **durante**
a inferência. `[MEDIDO]` o shape é estático (`['N','T',500]`), logo legível na carga.
`[FONTE-REPO]` o peer falha alto no mesmo ponto: `offline-recognizer-canary-impl.h:246-247`.

#### Files to edit
```
crates/macaw-asr/src/lib.rs — variante AsrError::VocabModelMismatch + checagem em load()
crates/macaw-asr/tests/vocab_load_test.rs — RED test primeiro
```

#### TDD

```
test_load_falha_quando_vocab_nao_bate_com_saida_do_modelo:
  Given o model.int8.onnx real (500 classes) e um tokens.txt com 499 tokens reais
  When  AsrEngine::load
  Then  assert!(matches!(err, AsrError::VocabModelMismatch { model_dim: 500, vocab_real: 499, .. }))
  And   a mensagem contém os dois números

test_load_aceita_o_artefato_canonico_real:
  Given training/results/onnx (500 classes, 502 linhas com 2 desambiguações)
  Then  AsrEngine::load retorna Ok  // prova que a regra D2 não gera falso positivo
```

#### Acceptance criteria
- [ ] `cargo run -p macaw-cli -- transcribe tests/fixtures/tone_440hz_16k.wav` sai com código `0` usando `training/results/onnx/`
- [ ] Com `tokens.txt` de 499 tokens reais, `AsrEngine::load` retorna `Err(AsrError::VocabModelMismatch)` — asserção no teste
- [ ] `format!("{err}")` contém as substrings `model_dim=500` e `vocab_real=499`

### T1.3 — `models/current/` canônico + `model_card.json`

#### Objective
Declarar um artefato canônico, sem mover nem remover nenhum peso.

#### Why this step (action + reasoning)

**O que faz:** cria `models/current` como **symlink** para o diretório vigente e gera
`model_card.json` com sha256 do modelo, fingerprint do vocabulário, `real_len`, WER medido e
data. Introduz `MACAW_MODEL_DIR` lido pelo Rust e pelo Python.

**Por que agora:** T1.2 só pode validar fingerprint se houver onde declará-lo. E o symlink
(R4) preserva todo caminho hard-coded existente — nada quebra.

#### Evidence
Auditoria: `training/batch/eval_public_hf.py:15` usa caminho absoluto
`/home/paulo/Projetos/jvscribe/models/m5-final-medium-phoneme`. `crates/macaw-cli/src/main.rs:46`
aponta para `training/results/onnx`.

#### Files to edit
```
scripts/make_model_card.py — gera o card (novo)
models/current — symlink (não versionado; criado pelo script)
crates/macaw-asr/src/lib.rs — leitura opcional do model_card.json
training/batch/eval_public_hf.py — MACAW_MODEL_DIR em vez de caminho absoluto
scripts/tests/test_make_model_card.py — RED test primeiro
```

#### TDD

```
test_model_card_contem_fingerprint_e_sha256:
  Given um diretório com model.int8.onnx e tokens.txt
  When  make_model_card
  Then  o JSON tem chaves sha256, vocab_fingerprint, vocab_real_len, generated_at
  And   vocab_real_len == 500 no artefato real

test_model_card_nunca_remove_arquivo:
  Given o diretório do artefato
  When  make_model_card roda duas vezes
  Then  o conjunto de arquivos antes == depois  // invariante de modelo
```

#### Acceptance criteria
- [ ] `jq -r .vocab_fingerprint models/current/model_card.json` é igual ao valor de `Vocab::fingerprint()` no teste
- [ ] `find models -type f | sort | sha256sum` é idêntico antes e depois de rodar `scripts/make_model_card.py`
- [ ] `grep -c '/home/paulo' training/batch/eval_public_hf.py` retorna `0`

## Phase 2: Rede de segurança

### T2.1 — Corrigir `.gitignore` e provar que as fixtures voltam

#### Objective
Restaurar a proteção das fixtures determinísticas.

#### Why this step (action + reasoning)

**O que faz:** remove as linhas 57-58 (`*.wav`, `*.f32`) que anulam a exceção da linha 17, e
adiciona um teste que falha se uma fixture nova for ignorada.

**Por que agora:** é pré-requisito de T2.3 — sem fixture versionada, o CI não roda os testes
determinísticos. E é o item nº 1 da ordem de execução da auditoria: um `git add` em massa
hoje perde as fixtures em silêncio.

#### Evidence
`[MEDIDO]` `git check-ignore --no-index -v tests/fixtures/nova.wav` →
`.gitignore:57:*.wav`; e `crates/macaw-audio/tests/fixtures/kaldi_fbank80_golden.f32` →
`.gitignore:58:*.f32`. Cinco arquivos de teste dependem dessas fixtures.

#### Files to edit
```
.gitignore — remover linhas 57-58
scripts/tests/test_gitignore_fixtures.py — RED test primeiro
```

#### TDD

```
test_fixture_wav_nova_nao_e_ignorada:
  Given o .gitignore do repo
  When  git check-ignore --no-index tests/fixtures/__probe.wav
  Then  assert exit_code != 0   // não ignorado

test_golden_f32_nao_e_ignorado:
  When  git check-ignore --no-index crates/macaw-audio/tests/fixtures/__probe.f32
  Then  assert exit_code != 0
```

#### Acceptance criteria
- [ ] `pytest scripts/tests/test_gitignore_fixtures.py` reporta `2 passed`
- [ ] `git check-ignore models.zip models/m0-borrowed/x.onnx` sai com código `0` para ambos

### T2.2 — Checksum no download do ONNX Runtime

#### Objective
Impedir que um artefato corrompido ou substituído passe silenciosamente.

#### Why this step (action + reasoning)

**O que faz:** adiciona verificação SHA-256 ao `setup_onnxruntime.sh`, abortando antes de
extrair.

**Por que agora:** o modo de falha (lib errada → 40× mais lento) já custou uma investigação
em M6, e o CI de T2.3 vai depender deste script.

#### Evidence
`scripts/setup_onnxruntime.sh` (13 linhas) baixa e extrai sem verificação.
`[FONTE-REPO]` o peer usa `URL_HASH` obrigatório em `cmake/googletest.cmake:37`.

#### Files to edit
```
scripts/setup_onnxruntime.sh — verificação sha256sum -c antes do tar
scripts/tests/test_setup_onnxruntime.py — RED test primeiro
```

#### TDD

```
test_setup_aborta_com_checksum_invalido:
  Given um tarball falso com conteúdo arbitrário
  When  a função de verificação roda
  Then  exit code != 0 e a mensagem cita o hash esperado e o obtido

test_setup_e_idempotente_quando_ja_presente:
  Given vendor/onnxruntime-linux-x64-1.23.0 já existe
  Then  o script sai 0 sem baixar nada
```

#### Acceptance criteria
- [ ] `grep -c 'sha256sum' scripts/setup_onnxruntime.sh` retorna `>= 1` e o hash esperado do 1.23.0 está literal no script
- [ ] Rodar `./scripts/setup_onnxruntime.sh` duas vezes sai `0` nas duas e imprime `já presente` na segunda

### T2.3 — CI com dois jobs

#### Objective
Tornar a suíte verificável por terceiros, sem falso verde.

#### Why this step (action + reasoning)

**O que faz:** cria `.github/workflows/ci.yml` com job `test-model-free` (obrigatório:
`cargo test --workspace`, `pytest training/tests scripts/tests`) e job `test-with-artifact`
(condicional, roda os testes `#[ignore]` quando o artefato existir).

**Por que agora:** é a rede que protege as fases 3 e 4. Sem CI, a consolidação do CTC (T3.1)
não teria como provar ausência de regressão para um terceiro.

#### Evidence
`[FONTE-REPO]` `.github/workflows/linux.yaml:66,68,70` — matriz nomeada por eixo.
Auditoria: `scripts/test_report.sh` existe justamente porque o falso verde é real.

#### Files to edit
```
.github/workflows/ci.yml — novo
```

#### TDD

```
test_workflow_declara_dois_jobs_distintos:
  Given .github/workflows/ci.yml
  Then  o YAML parseia e contém jobs test-model-free e test-with-artifact
  And   test-model-free não referencia nenhum caminho de modelo

// validação real: o job precisa passar em runner limpo — evidência é a execução, não o arquivo
```

#### Acceptance criteria
- [ ] `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"` sai com código `0`
- [ ] `grep -cE 'models/|results/onnx' <bloco do job test-model-free>` retorna `0`
- [ ] Execução real registrada: URL do run do GitHub Actions **ou** saída de `act -j test-model-free` com `Job succeeded`

### T2.4 — LICENSE e toolchain fixada

#### Objective
Sustentar o que os 3 crates já declaram.

#### Why this step (action + reasoning)

**O que faz:** adiciona `LICENSE` Apache-2.0 na raiz e `rust-toolchain.toml` fixando 1.75.

**Por que agora:** entra junto com o CI porque é o mesmo eixo — o que um terceiro vê e
verifica. Custo: dois arquivos.

#### Evidence
`Cargo.toml:7` → `license = "Apache-2.0"`; nenhum arquivo `LICENSE` existe.
`workspace.package.rust-version = "1.75"` sem `rust-toolchain.toml`.

#### Files to edit
```
LICENSE — novo
rust-toolchain.toml — novo
```

#### TDD

```
test_licenca_declarada_tem_arquivo:
  Given Cargo.toml declara license = "Apache-2.0"
  Then  existe LICENSE na raiz e seu texto contém "Apache License"
```

#### Acceptance criteria
- [ ] `head -2 LICENSE | grep -c 'Apache License'` retorna `1` e `grep -c 'Apache-2.0' Cargo.toml` retorna `>= 1`
- [ ] `grep -c '1.75' rust-toolchain.toml` retorna `1`

## Phase 3: Shared kernel

### T3.1 — Provar equivalência e consolidar o colapso CTC

#### Objective
Uma implementação de colapso CTC em Python, com equivalência provada contra a de Rust.

#### Why this step (action + reasoning)

**O que faz:** escreve primeiro um teste que roda as 5 implementações Python sobre a mesma
matriz de log-probs e compara as saídas; só então cria `training/common/ctc.py` e migra os
callers. Adiciona teste de conformidade contra `macaw-cli transcribe`.

**Por que agora:** R2 diz que consolidar pode mudar um número publicado. A ordem
teste-primeiro é o que transforma esse risco em evidência: se divergirem, sabemos qual e por
quê antes de mudar qualquer coisa.

#### Evidence
Auditoria: 7 implementações (5 Python + 1 Rust + 1 em `smoke/`), 4 nomes diferentes, zero
teste de conformidade. Divergência conhecida: `measure_realcodec.py:48` detokeniza com
`sp.decode`, as outras com `join(pieces).replace("▁")`.

#### Files to edit
```
training/common/__init__.py — novo
training/common/ctc.py — implementação única
training/tests/test_ctc_equivalence.py — RED test primeiro (as 5 vs a nova)
training/batch/batch_transcribe.py — passa a importar de common
training/batch/decode_onnx_local.py — idem
training/eval/measure_realcodec.py — idem
training/eval/measure_callcenter.py — idem
training/conftest.py — expõe common/ ao sys.path
```

#### TDD

```
test_as_cinco_implementacoes_concordam_na_mesma_entrada:
  Given uma matriz de log_probs determinística (seed fixa) e um id2tok sintético
  When  cada uma das 5 implementações roda
  Then  assert todas produzem a mesma sequência de ids colapsada
  And   se divergirem, o teste falha nomeando qual e em que entrada

test_common_ctc_equivale_ao_decoder_rust:
  Given a mesma matriz de log_probs
  When  common.ctc.greedy roda e macaw-cli transcribe roda sobre o mesmo wav
  Then  assert as sequências de token coincidem
```

#### Acceptance criteria
- [ ] `pytest training/tests/test_ctc_equivalence.py -v` roda e seu resultado (passou / divergiu em qual entrada) fica registrado no log da task
- [ ] `pytest training/tests scripts/tests -q` reporta `0 failed` (baseline medido: 157 testes)
- [ ] `training/results/*.md` sem diff de número; se houver, o antes/depois é registrado no CHANGELOG

### T3.2 — `common/text.py` com nomes que expõem o contrato

#### Objective
Eliminar a ambiguidade das 5 `normalize_ptbr`.

#### Why this step (action + reasoning)

**O que faz:** move as duas semânticas para `training/common/text.py` como
`normalize_for_wer_compare` (remove acento) e `normalize_train_target` (preserva), migrando os
callers.

**Por que agora:** enquanto duas funções incompatíveis compartilharem um nome, todo WER do
projeto carrega ambiguidade sobre qual régua foi usada. Depende de T3.1 ter criado `common/`.

#### Evidence
`scripts/text_normalize_ptbr.py:52` remove acentos (NFKD + descarta combining);
`training/finetune/prep_icefall.py:49` preserva (NFC + classe de caracteres com `áàâãéêíóôõúçü`).

#### Files to edit
```
training/common/text.py — novo
scripts/text_normalize_ptbr.py — passa a delegar
training/finetune/prep_icefall.py — passa a delegar
training/tests/test_text_normalization.py — RED test primeiro
```

#### TDD

```
test_normalize_for_wer_compare_remove_acento:
  Given "coração"
  Then  assert resultado == "coracao"

test_normalize_train_target_preserva_acento:
  Given "coração"
  Then  assert resultado == "coração"

test_as_duas_funcoes_diferem_em_entrada_acentuada:
  Then  assert normalize_for_wer_compare(s) != normalize_train_target(s)
```

#### Acceptance criteria
- [ ] `grep -rn 'def normalize_ptbr' scripts training | wc -l` retorna `0`
- [ ] `pytest training/tests/test_prep_coraa.py training/tests/test_prep_tagarela.py -q` reporta `0 failed`

### T3.3 — Guarda de layout permite `common/`

#### Objective
Tornar a regra mais forte, não mais fraca.

#### Why this step (action + reasoning)

**O que faz:** altera `test_pipeline_layout.py` de "nenhum import cross-pipeline" para
"cross-pipeline apenas a partir de `common/`", e estende a guarda para falhar quando um `.py`
de pipeline aparecer fora de `training/{finetune,batch,realtime,eval,common}`.

**Por que agora:** sem isso, T3.1 e T3.2 violariam a guarda existente. E a extensão fecha o
buraco por onde as cópias escaparam para `models/`.

#### Evidence
Auditoria: `models/m5-final-medium-phoneme/{decode_onnx_local,mic_transcribe}.py` são cópias
byte-idênticas fora do alcance da guarda.

#### Files to edit
```
training/tests/test_pipeline_layout.py — regra atualizada + novo caso
```

#### TDD

```
test_import_de_common_e_permitido:
  Given batch/batch_transcribe.py importando de common.ctc
  Then  a guarda passa

test_import_cross_pipeline_direto_continua_proibido:
  Given eval/x.py importando de batch/y.py
  Then  a guarda falha

test_py_de_pipeline_fora_da_arvore_e_detectado:
  Given uma cópia de um módulo de pipeline em models/
  Then  a guarda falha nomeando o arquivo
```

#### Acceptance criteria
- [ ] `pytest training/tests/test_pipeline_layout.py -q` reporta `0 failed` com os 3 casos novos
- [ ] Criar um `training/__probe.py` temporário faz `pytest training/tests/test_pipeline_layout.py` falhar

## Phase 4: Limpeza com rede

### T4.1 — Endpoint `/m1` morto

#### Objective
Eliminar erro engolido em produção.

#### Why this step (action + reasoning)

**O que faz:** remove `m1_measurements_json` e sua rota, ou a repõe apontando para fonte viva
— decidido pela existência ou não de destino. Hoje ela lê um diretório removido e devolve
`200 OK` vazio.

**Por que agora:** é o único caso em que a deriva documental virou defeito de runtime, e
viola `error-handling.md` § 2 (erro engolido).

#### Evidence
`crates/macaw-cli/src/app.rs:498-506` → `.join("../../knowledge-base/measurements")` com
`unwrap_or_default()`. `dashboard.html:233-240` renderiza o placeholder.

#### Files to edit
```
crates/macaw-cli/src/app.rs — remover ou repontar
crates/macaw-cli/src/dashboard.html — ajustar
crates/macaw-cli/tests/server_concurrency_test.rs — ajustar se referenciar a rota
```

#### TDD

```
test_rota_m1_nao_devolve_200_vazio_silencioso:
  Given o servidor no ar
  When  GET /m1
  Then  ou a rota não existe (404), ou devolve conteúdo real
  And   nunca 200 com payload vazio
```

#### Acceptance criteria
- [ ] `grep -c 'read_to_string.*unwrap_or_default' crates/macaw-cli/src/app.rs` retorna `0`
- [ ] `cargo test -p macaw-cli` reporta `0 failed`

### T4.2 — Grupo A da remoção

#### Objective
Remover 89.874 linhas sem caller, preservando toda evidência.

#### Why this step (action + reasoning)

**O que faz:** executa o Grupo A de `system-design-output/target_architecture.md` § 4 — dumps
`errs-*` cujo `recogs-*` par existe, `train.log` já ignorado pelo `.gitignore`,
`training/smoke/`, `wer-summary-*`, os 2 `examples` Rust, a dep duplicada no `Cargo.toml`, e
as 2 cópias byte-idênticas em `models/`.

**Por que agora:** depende de T2.3 (CI verde como rede). É a última fase por isso.

#### Evidence
Auditoria, com prova de ausência de caller item a item. **Invariante:** nenhum arquivo de
modelo, peso ou vocabulário entra nesta lista — verificado: dos 21 achados de remoção, zero
tocam `.onnx/.pt/tokens.txt`.

#### Files to edit
```
(remoções listadas em target_architecture.md § 4 Grupo A)
training/results/m4-pilot-fleurs/ — ARQUIVAR, não remover (Grupo B: sem recogs par)
```

#### TDD

```
test_nenhum_arquivo_de_modelo_foi_removido:
  Given a lista de arquivos antes da remoção
  When  o Grupo A é executado
  Then  assert todo arquivo com extensão .onnx/.pt/.ckpt/.bin/tokens.txt continua presente

test_suite_continua_verde_apos_remocao:
  Then  cargo test --workspace e pytest continuam passando
```

#### Acceptance criteria
- [ ] `find models training/results -name '*.onnx' -o -name 'tokens.txt' | sort` idêntico antes e depois — diff vazio
- [ ] `ls training/results/archive/m4-pilot-fleurs-raw.tar.gz` sai `0` e o diretório original some do HEAD
- [ ] `cargo test --workspace` e `pytest training/tests scripts/tests -q` reportam `0 failed` após a remoção

### T4.3 — README e citações mortas

#### Objective
Consertar a porta de entrada.

#### Why this step (action + reasoning)

**O que faz:** reescreve a tabela "Como navegar" apontando para o que existe (agora que
`PRD.md`, `ROADMAP.md` e os ADRs foram restaurados, a maioria dos links volta a resolver), e
varre as citações remanescentes.

**Por que agora:** por último porque depende do estado final da árvore após T4.2.

#### Evidence
Auditoria: 5/5 links do README quebrados; 50 citações mortas em 34 arquivos. **Nota:** a
restauração feita em `99b243a` já reparou parte disso — a task deve **re-medir** antes de agir.

#### Files to edit
```
README.md — tabela "Como navegar" + estado dos milestones
(demais arquivos conforme a re-medição)
```

#### TDD

```
test_todos_os_links_internos_do_readme_resolvem:
  Given cada link markdown relativo do README.md
  Then  assert o caminho existe em disco
```

#### Acceptance criteria
- [ ] `pytest training/tests/test_readme_links.py -q` reporta `0 failed` — todo link relativo resolve em disco
- [ ] A tabela de milestones do README lista os mesmos estados `[x]/[~]/[ ]` que `grep '^### M' ROADMAP.md`

## Coverage Matrix

Todo bullet do DoD de M9 mapeado para ≥ 1 task.

| DoD do M9 (ROADMAP.md) | Task(s) |
|---|---|
| Artefato canônico declarado com `model_card.json` | T1.3 |
| Fail-fast de vocabulário | T1.1, T1.2 |
| `MACAW_MODEL_DIR` nos dois lados | T1.3 |
| `training/common/` consolidando CTC e `normalize_ptbr` | T3.1, T3.2 |
| Teste de conformidade CTC cross-language | T3.1 |
| `.gitignore` corrigido | T2.1 |
| CI verde | T2.3 |
| `LICENSE` + `rust-toolchain.toml` | T2.4 |
| Grupo A executado, Grupo B arquivado | T4.2 |
| README e citações mortas | T4.3 |
| *(derivado de D4 — não estava no DoD original)* checksum do ORT | T2.2 |
| *(derivado da auditoria)* endpoint `/m1` morto | T4.1 |

**Cobertura: 10/10 bullets do DoD mapeados (100%)** + 2 tasks derivadas do DISCOVER.

## Dependencies

M9 **não adiciona nenhuma dependência nova** (parsimony ladder, rung 4).

| Ecossistema | Dependência | Versão | Já instalada? | Rule 9 |
|---|---|---|---|---|
| Rust | `sha2` | 0.10 | **Não** — necessária para o fingerprint (T1.1) | Crate padrão de facto para SHA-256; reimplementar seria violação direta |
| Python | nenhuma nova | — | — | `hashlib` da stdlib cobre o fingerprint (rung 2) |

> `sha2` é a única adição. Alternativa avaliada: usar `ring` (mais pesado, traz crypto que não
> precisamos) ou implementar SHA-256 à mão (proibido pela Regra 9). `sha2` é a escolha mínima.

## Failure scenarios (external I/O)

| Cenário | Onde | Comportamento exigido |
|---|---|---|
| Download do ORT falha (rede) | `setup_onnxruntime.sh` | Sai != 0 com mensagem; não deixa `vendor/` pela metade |
| Checksum do ORT não bate | `setup_onnxruntime.sh` | Aborta **antes** de extrair; cita esperado vs obtido |
| `tokens.txt` ausente | `AsrEngine::load` | `AsrError::VocabNotFound` com o caminho (já existe) |
| `model_card.json` ausente | `AsrEngine::load` | Degrada para validação de cardinalidade, com aviso — não falha |
| `models/current` aponta para diretório inexistente | `AsrEngine::load` | `AsrError::ModelNotFound` com o caminho resolvido do symlink |
| CI sem artefato de modelo | `test-with-artifact` | Job não roda; **não** marca o build como verde por isso |

## Global Definition of Done

- [ ] Todos os 10 bullets do DoD do M9 no `ROADMAP.md` com evidência de execução
- [ ] `cargo test --workspace` verde; `pytest training/tests scripts/tests` verde
- [ ] `/code-quality` ∈ {PASS, PASS_WITH_CAVEATS}
- [ ] `/review` = READY_TO_MERGE
- [ ] **Invariante:** zero arquivos de modelo/peso/vocabulário removidos, verificado por
      listagem antes/depois
- [ ] CHANGELOG atualizado
