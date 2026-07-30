# Review — M9 Governança de artefato e reprodutibilidade

- **Slug:** `m9-artifact-governance`
- **Data:** 2026-07-30
- **Escopo:** `99b243a^..HEAD` (16 commits) na branch `workspace`
- **Plano:** `knowledge-base/plans/m9-artifact-governance-plan.md`
- **Contrato:** `.claude/rules/cycle-review.md`

## Veredito

**`NEEDS_FIXES`**

Um BLOCKER: a consolidação do shared kernel (T3.1) introduziu uma regressão de
import que **mata dois scripts de produção** fora do pytest. A suíte não o pega
porque `training/conftest.py` conserta o `sys.path` só sob pytest — é exatamente
a classe de falso verde que M9 foi criado para eliminar, reintroduzida pelo
próprio M9.

Fora isso, o milestone é de qualidade alta e incomum: a medição central foi
re-verificada por mim e bate **exatamente**, os desvios de plano estão declarados
nos commits, e três defeitos pré-existentes reais foram descobertos e corrigidos
no caminho (toolchain falsa, `test_report.sh` verde com build quebrado, teste de
captura flaky).

## Suítes que EU rodei

| Comando | Resultado | Observação |
|---|---|---|
| `cargo test --workspace` | **79 passed, 0 failed, 8 ignored** (exit 0) | 31 binários de teste; zero `SKIP:` impresso |
| `cargo test --workspace -- --ignored` | **8 passed, 0 failed** | com artefatos reais em disco; nenhum escape hatch disparou |
| `python3 -m pytest training/tests scripts/tests -q` | **190 passed** em 67s | |
| `cargo clippy --workspace --all-targets -- -D warnings` | **exit 0** | confirma a alegação de `05a50c8` |
| `python3 training/batch/batch_transcribe.py --help` | **ModuleNotFoundError** | ver BLOCKER B-1 |

## Re-medição independente da alegação central

O commit `86f608e` e o plano afirmam "492 dos 500 ids mapeiam tokens diferentes".
Recomputei do zero sobre os dois `tokens.txt` em disco:

```
linhas runtime: 502 | linhas eval: 503
tokens reais runtime: 500 | eval: 500
ids 0..499 com token DIFERENTE: 492
id 4 runtime: '▁a' | eval: 'r'
```

**Confere exatamente**, inclusive o exemplo do id 4. A justificativa de projeto
para validar identidade em vez de cardinalidade está sustentada por evidência.

## Hard gates (`cycle-review.md:42-48`)

| Gate | Estado |
|---|---|
| Testes falhando na branch | **PASS** — 79 Rust + 190 Python, 0 failed |
| Segredos commitados (`.env`, `credentials*`, `*.pem`, `*.key`) | **PASS** — nenhum arquivo adicionado casa os padrões |
| Commit direto em `main` | **PASS** — HEAD em `workspace`; `main` parada em `2c36f9b` (merge-base) |
| Trailer `Co-Authored-By` | **PASS** — ausente nos 16 commits |
| `CHANGELOG.md` atualizado | **PASS** — atualizado em todos os commits de produção |

## Invariante do dono (inegociável)

**PASS.** `git diff 99b243a^..HEAD --diff-filter=D --name-only` filtrado por
`.onnx|.pt|.ckpt|.bin|.safetensors|tokens.txt|vocab.txt|bpe.model` retorna
**vazio**. Nenhum modelo, peso ou vocabulário foi removido. As 16 deleções são
dumps de texto (`errs-*`, `wer-summary-*`, `train.log`), 2 `examples` Rust e um
state file de loop.

## Achados

| # | Sev | Arquivo:linha | Achado |
|---|---|---|---|
| B-1 | **BLOCKER** | `training/batch/batch_transcribe.py:24` | `import ctc` no topo do módulo mata o script fora do pytest |
| B-2 | **BLOCKER** | `training/eval/measure_callcenter.py:60` | mesmo import, dentro de `greedy()` — falha diferida ao decode |
| H-1 | HIGH | `ROADMAP.md:332` | DoD "Teste de conformidade CTC cross-language" não entregue |
| H-2 | HIGH | `training/tests/test_ctc_equivalence.py:39,66` | o teste de equivalência nunca exercita o shared kernel |
| H-3 | HIGH | `.claude/rules/cycle-review.md:11-12` | pré-condições do ciclo não satisfeitas (sem implementation log, sem audit de code-quality) |
| H-4 | HIGH | `training/common/text.py:25` | T3.2 não consolidou nada: as 5 `normalize_ptbr` continuam, e o módulo novo **adiciona** uma 6ª cópia |
| H-5 | HIGH | `.github/workflows/ci.yml` | o CI **nunca executou**; o critério T2.3 exige evidência de execução |
| M-1 | MEDIUM | `crates/macaw-asr/src/lib.rs:288` | `output_vocab_dim()` é export público órfão |
| M-6 | MEDIUM | `training/tests/test_pipeline_layout.py:113-115` | a guarda de T3.3 é vacuamente verde sobre as 2 cópias que seu próprio docstring cita |
| M-7 | MEDIUM | `README.md:17,26,65` | tabela de milestones diverge do ROADMAP (critério T4.3 não cumprido) |
| M-2 | MEDIUM | `crates/macaw-asr/tests/vocab_load_test.rs:122-125` | escape hatch + CI = falso verde no teste de aceite central de T1.1 |
| M-3 | MEDIUM | `knowledge-base/plans/…-plan.md:691` | `training/smoke/` não removido; omissão não declarada |
| M-4 | MEDIUM | `crates/macaw-cli/src/transcribe.rs:47-58` | wiring triad pilar (c): a saída não registra qual artefato a produziu |
| M-5 | MEDIUM | `ROADMAP.md:331` | DoD diz "consolidando as 7 implementações"; 2 de 5 migradas |
| L-1 | LOW | `CHANGELOG.md:16,36` | duas seções `### Added` dentro de `[Unreleased]` |
| L-2 | LOW | `knowledge-base/plans/…-plan.md:721` | critério "o diretório original some do HEAD" não cumprido |
| L-3 | LOW | `crates/macaw-cli/src/app.rs:507` | `Err(_)` descarta o `io::ErrorKind` |
| L-4 | LOW | `training/results/m4-pilot-fleurs-results.md:27` | cita `train.log`, agora fora do HEAD |
| L-5 | LOW | `crates/macaw-asr/src/lib.rs:466-471` | parsing manual de JSON por `split` |

---

### B-1 / B-2 — BLOCKER: a consolidação do shared kernel quebrou dois scripts de produção

**Uma causa-raiz, dois sítios, um fix.**

`training/batch/batch_transcribe.py:24`:

```python
import ctc  # shared kernel (training/common)
```

O módulo `ctc` vive em `training/common/`. Ele só é importável porque
`training/conftest.py:13` insere esse diretório no `sys.path` — e `conftest.py`
**é carregado exclusivamente pelo pytest**. Executado como o CLI que ele é:

```
$ python3 training/batch/batch_transcribe.py --help
Traceback (most recent call last):
  File "training/batch/batch_transcribe.py", line 24, in <module>
    import ctc  # shared kernel (training/common)
ModuleNotFoundError: No module named 'ctc'
```

O script está **integralmente morto** fora do pytest. Antes de `2e3db56` ele
tinha a própria `greedy` e funcionava.

`training/eval/measure_callcenter.py:60` tem o mesmo import dentro de `greedy()`,
o que é pior: `--help` funciona, o script carrega modelo e áudio, e só então
morre. Provado sem pytest:

```
$ python3 -c "import sys; sys.path.insert(0,'training/eval'); import measure_callcenter as m; ..."
FALHOU: ModuleNotFoundError No module named 'ctc'
```

**Por que a suíte não pega.** Nenhum teste invoca esses scripts como subprocesso.
`training/tests/test_batch_transcribe.py:7` faz `from batch_transcribe import
greedy, segment, SR` — in-process, sob o `sys.path` já corrigido pelo conftest. O
"smoke ponta-a-ponta" que o CHANGELOG anuncia nunca cruza a fronteira do processo.
Os 190 testes verdes dão **zero** sinal sobre o entry point real.

A ironia é o achado: `.github/workflows/ci.yml:5-11` descreve o falso verde como
o problema que M9 resolve, e T3.1 o reintroduziu numa forma nova.

**Fix sugerido:** tornar `training/common/` um pacote importável de verdade
(`from common import ctc` com `training/` no path via `pyproject`/`setup.cfg` ou
um `sys.path` bootstrap explícito no topo de cada entry point), e adicionar **um**
teste que rode cada script como subprocesso (`subprocess.run([sys.executable,
script, "--help"])`) — é o único teste que teria pego isto.

---

### H-1 — DoD "Teste de conformidade CTC cross-language" não entregue

`ROADMAP.md:332` exige:

> - [ ] **Teste de conformidade CTC cross-language** entre `common/ctc.py` e `macaw-asr::ctc_greedy`, no mesmo padrão do golden `kaldi_fbank_golden_test.rs`

A Coverage Matrix do plano mapeia esse bullet para T3.1, e o bloco `#### TDD` de
T3.1 nomeia `test_common_ctc_equivale_ao_decoder_rust`. **Esse teste não existe.**
Nenhum arquivo em `training/tests/` ou `scripts/tests/` compara saída Python de
CTC contra a implementação Rust; não há invocação de binário Rust em teste Python.

O único teste cross-language do milestone é
`scripts/tests/test_make_model_card.py:20`
(`test_fingerprint_python_reproduz_o_do_rust`) — que valida o **fingerprint**, não
o **decoder CTC**. `CHANGELOG.md:17` descreve esse teste como "teste de
conformidade cross-language", o que pode ser lido como se o bullet do DoD
estivesse coberto. Não está.

---

### H-2 — O teste de equivalência CTC nunca exercita o shared kernel

`training/tests/test_ctc_equivalence.py` não importa `common/ctc.py` em nenhum
ponto (imports nas linhas 44, 58, 59: `decode_onnx_local`, `batch_transcribe`,
`measure_callcenter`). O módulo criado por T3.1 não tem teste de comportamento
próprio — a única referência a ele em toda a suíte é
`training/tests/test_pipeline_layout.py:79`, que é a guarda de layout, não um
teste de decode.

Três problemas concretos:

1. **`test_colapso_das_implementacoes_concorda_na_mesma_entrada` (linha 39)** — o
   nome diz "as implementações"; o corpo exercita **uma** (`decode_onnx_local.
   greedy_ctc`) contra `_collapse_reference`, uma função definida no próprio
   arquivo de teste. O plano prometia as 5.
2. **`test_divergencia_conhecida_de_detokenizacao_esta_documentada` (linhas 66-79)**
   — é asserção de substring em código-fonte: `assert "sp.decode(toks)" in src`.
   Não roda `measure_realcodec.greedy`. Passaria com a função completamente
   quebrada.
3. **`training/scripts/tta_feature_align_probe.py`** — quinta cópia, nunca
   exercitada por nenhum teste.

O mesmo padrão de teste-por-substring aparece em
`scripts/tests/test_setup_onnxruntime.py:47`
(`assert "já presente" in src and "exit 0" in src`) e na linha 42, cujo
`subprocess.run(["sha256sum", "-c", ...])` testa o **coreutils**, não
`setup_onnxruntime.sh` — passaria com o script deletado. Atenuante honesto: o
commit `262366b` registra validação manual em sandbox dos dois caminhos, e a
linha 28 (`i_check < i_tar`) verifica a ordem real no fonte.

---

### H-3 — Pré-condições do `cycle-review` não satisfeitas

`.claude/rules/cycle-review.md:11-12` exige, antes deste ciclo:

- `knowledge-base/implementations/{slug}-implementation.md` — **não existe**
  (diretório vazio)
- `knowledge-base/audits/{slug}-code-quality-*.md` com verdict ∈ {PASS,
  PASS_WITH_CAVEATS} — **não existe** (diretório vazio)

Isto não é burocracia: o achado M-1 abaixo é exatamente da classe que
`/code-quality` detecta automaticamente (`dead_code_unallowlisted_rust`), e o
commit `05a50c8` mostra que rodar o gate funcionou antes — ele pegou `fingerprint()`
órfã. Depois desse commit o gate não foi re-executado, e um novo órfão passou.

---

### H-4 — T3.2 não consolidou `normalize_ptbr`; adicionou mais uma cópia

O critério de aceite de T3.2 é literal e executável:

> - [ ] `grep -rn 'def normalize_ptbr' scripts training | wc -l` retorna `0`

**Rodei. Retorna `5`:**

```
training/smoke/prep_fleurs.py:33
training/scripts/analyze_error_composition.py:37
training/finetune/prep_icefall.py:49
scripts/text_normalize_ptbr.py:52
training/scripts/eval_runtime_wer.py:37
```

Nenhuma das cinco delega para `training/common/text.py`. E `common/text.py` tem
**zero callers de produção** — o único import do módulo em todo o repositório
fora de testes é ele importando outra coisa (`text.py:45`).

Pior: `training/common/text.py:25` (`normalize_train_target`) **re-implementa** os
passos de `training/finetune/prep_icefall.py:49` — `NFC` + `re.sub(_TRAIN_KEEP)` +
colapso de espaço — em vez de importá-los. É uma 6ª cópia da semântica que
preserva acento, criada pela própria task cuja meta declarada era eliminar cópias.
Só `normalize_for_wer_compare` (`text.py:37`) delega de fato, e na direção
inversa: `common/` → `scripts/text_normalize_ptbr.py`.

O plano listava em T3.2 `#### Files to edit`: "`scripts/text_normalize_ptbr.py` —
passa a delegar" e "`training/finetune/prep_icefall.py` — passa a delegar".
Nenhum dos dois delega, e a mensagem de `ead3b7f` não declara essa omissão —
declara apenas a delegação de `normalize_for_wer_compare`, que é verdadeira e
isolada.

Consequência para o DoD: `ROADMAP.md:331` ("consolidando ... as 5
`normalize_ptbr`") não pode ser marcado `[x]`.

O mérito real da task permanece e não é pequeno: `test_text_normalization.py`
**mediu** que existem duas semânticas incompatíveis sob o mesmo nome, e nomeou-as.
O diagnóstico está certo; a consolidação é que não aconteceu.

---

### H-5 — O CI nunca executou; o DoD "CI verde" não tem evidência

O próprio plano antecipou isto no bloco `#### TDD` de T2.3:

> `// validação real: o job precisa passar em runner limpo — evidência é a execução, não o arquivo`

E o critério de aceite pede: *"Execução real registrada: URL do run do GitHub
Actions **ou** saída de `act -j test-model-free` com `Job succeeded`"*.

```
$ gh run list --workflow=ci.yml
HTTP 404: workflow ci.yml not found on the default branch
  (https://api.github.com/repos/usetheodev/jvscribe/actions/workflows/ci.yml)
```

O remote existe (`git@github.com:usetheodev/jvscribe.git`), os commits de M9 não
foram pushados, e não há registro de `act` em lugar nenhum do repositório. O
workflow **nunca rodou, em runner nenhum**.

Isso importa além do checkbox: o grafo de dependências do plano (linha 190) diz
`T4.1..T4.3 (limpeza) — dependem de T2.3 (CI verde como rede)`. A limpeza de
89 mil linhas foi executada sem a rede que o plano exigia. Na prática a rede foi
a suíte local, que — como B-1 demonstra — não cobre os entry points.

O DoD `ROADMAP.md` "CI verde ... rodando em runner limpo" não pode ser marcado
`[x]`. Mitigação barata: `act -j test-model-free` localmente, ou pushar a branch
e colar a URL do run.

---

### M-1 — `output_vocab_dim()` é export público órfão

`crates/macaw-asr/src/lib.rs:288`:

```rust
pub fn output_vocab_dim(&self) -> Option<usize> {
```

Zero callers em todo o workspace — nem produção, nem teste (`grep -rn
"output_vocab_dim()" --include="*.rs" .` excluindo a definição retorna vazio). Por
`code-quality-golden-rule.md` § 2 isso é `dead_code_unallowlisted_{language}`,
cap **FAIL_HARD (49)**. É a mesma lacuna que `05a50c8` corrigiu para
`fingerprint()`; esta ficou.

Fix: remover o getter, ou dar-lhe um caller/teste.

---

### M-2 — Escape hatch + CI produzem falso verde no teste de aceite central de T1.1

`crates/macaw-asr/tests/vocab_load_test.rs:122-125`:

```rust
if !runtime.exists() || !eval.exists() {
    eprintln!("SKIP: artefatos ausentes ({runtime:?} / {eval:?})");
    return;
}
```

Um `return` cedo faz o teste **passar** sem asserir nada. Isso interage mal com o
CI: o job `test-with-artifact` popula apenas `training/results/onnx` (`ci.yml`,
`tar xzf ... -C training/results/onnx`) e nunca
`models/m5-final-medium-phoneme/`, que a linha 121 exige. Logo, no CI, o teste
que prova a alegação central do milestone — os 492 ids divergentes — reporta
"ok" sem executar uma asserção.

Há 15 escape hatches desse tipo nos testes Rust. Na minha máquina os 8 `#[ignore]`
rodaram de verdade (nenhum `SKIP:` impresso), então o problema é estritamente do
ambiente de CI.

Fix: trocar o `return` por `panic!` quando o job é o de artefato (ou fazer o CI
buscar os dois diretórios). Um teste que precisa de artefato e não o acha deve
falhar, não passar.

---

### M-3 — `training/smoke/` não foi removido, e a omissão não está declarada

O plano T4.2 (`knowledge-base/plans/m9-artifact-governance-plan.md:691`) lista
`training/smoke/` no Grupo A. `git ls-files training/smoke/` retorna 5 arquivos
ainda rastreados. A mensagem de `c89865d` enumera o que removeu e **não menciona**
`training/smoke/` — não é desvio declarado, é omissão silenciosa.

Relevante para M-5: `smoke/decode_ctc.py` é a 7ª implementação de colapso CTC que
o DoD manda consolidar.

---

### M-6 — A guarda de T3.3 é vacuamente verde sobre as cópias que a motivaram

`training/tests/test_pipeline_layout.py:104-107`, docstring do teste novo:

> *"Cópias byte-idênticas de `decode_onnx_local.py` e `mic_transcribe.py` foram
> parar em `models/m5-final-medium-phoneme/` — invisíveis para ela."*

Linhas 113-115, o escopo escolhido:

```python
tracked = subprocess.run(
    ["git", "ls-files", "*.py"], cwd=repo, ...
```

E `.gitignore:50` ignora `models/`. Logo o teste **não enxerga os dois arquivos
que seu próprio docstring nomeia como motivação**. Verifiquei que continuam em
disco e que `cmp models/m5-final-medium-phoneme/decode_onnx_local.py
training/batch/decode_onnx_local.py` retorna idêntico.

A justificativa de escopo no comentário (linhas 112-113: "diretórios gitignored
são artefatos locais do operador") é defensável em si. O problema é a combinação:
o teste declara fechar um buraco, e o escopo escolhido o mantém aberto. E a
mesma dupla estava no Grupo A de T4.2 para remoção (`plan:691`, "as 2 cópias
byte-idênticas em `models/`") — não foram removidas nem declaradas como puladas.

O CHANGELOG afirma que a varredura "passou a cobrir todo arquivo versionado" —
verdadeiro e uma melhora real, mas não fecha o buraco enunciado.

---

### M-7 — README diverge do ROADMAP; o critério de T4.3 não é cumprido

Critério: *"A tabela de milestones do README lista os mesmos estados
`[x]/[~]/[ ]` que `grep '^### M' ROADMAP.md`"*.

`ROADMAP.md` → M0-M4 `[x]`, M5 `[~]`, M6-M9 `[ ]`. O README mapeia corretamente
M0-M8, e então `README.md:26`:

```
| M9 — Governança de artefato e reprodutibilidade | 🔄 em curso |
```

`🔄 em curso` é um **quarto estado** sem contrapartida no ROADMAP (onde M9 é
`[ ]`, mapeado para `⏳` nas outras linhas) — e isso logo abaixo de
`README.md:22`, que afirma "A tabela reflete o `ROADMAP.md`, que é a fonte da
verdade".

Além disso, `README.md:17` ("Progresso por milestones (`ROADMAP.md`, M0–M8)") e
`README.md:65` ("Milestones M0–M8 com Definition of Done") ficaram desatualizados
— M9 existe no ROADMAP e na própria tabela acima.

`test_readme_links.py` não pega isto: ele valida resolução de links, não
consistência de estado. O commit `6c46b35` conserta a tabela para M0-M8 com
cuidado real; a linha do próprio M9 é que escapou.

---

### M-4 — Wiring triad pilar (c): a transcrição não registra qual artefato a produziu

`crates/macaw-cli/src/transcribe.rs:47-58` — `TranscribeMetrics` expõe
`n_frames`, `audio_secs`, `decode_ms`, `rtfx`, `tokens`. Nenhum campo identifica o
artefato: nem `model_dir`, nem `vocab_fingerprint`, nem `model_sha256`.

M9 existe porque dois diretórios disputam o nome `model.int8.onnx` e produzem
transcrições incompatíveis. A validação agora impede o par **errado**, mas a saída
continua sem dizer qual par **certo** foi usado — a ambiguidade que originou o
milestone permanece nos dados de saída. `cycle-implement.md` exige pilar (c),
métrica de runtime, para toda feature nova.

Fix barato: incluir `vocab_fingerprint` (já computado na linha 121) em
`TranscribeMetrics`.

---

### M-5 — O DoD afirma consolidação das 7 implementações; foram 2 de 5

`ROADMAP.md:331` diz "consolidando as 7 implementações de colapso CTC". Estado
real: `batch_transcribe.py` e `measure_callcenter.py` migradas;
`training/batch/decode_onnx_local.py:31` mantém `def greedy_ctc` própria;
`measure_realcodec.py` e `tta_feature_align_probe.py` idem; `smoke/decode_ctc.py`
intocado (M-3).

A parcialidade **está declarada** em `2e3db56` ("batch_transcribe e
measure_callcenter migrados") — isso é honestidade e não conta como defeito. O
defeito é o bullet do DoD ficar factualmente falso se marcado `[x]` no release.
O mesmo bullet cobre as 5 `normalize_ptbr`, onde a situação é pior (H-4).

## Critérios de aceite do plano que EU executei

Rodei literalmente os critérios mecanizáveis. Resultado:

| Task | Critério (comando do plano) | Esperado | Obtido | |
|---|---|---:|---:|---|
| T1.3 | `grep -c '/home/paulo' training/batch/eval_public_hf.py` | 0 | 0 | PASS |
| T2.2 | `grep -c 'sha256sum' scripts/setup_onnxruntime.sh` | ≥1 | 2 | PASS |
| T2.4 | `head -2 LICENSE \| grep -c 'Apache License'` | 1 | 1 | PASS |
| T2.4 | `grep -c '1.75' rust-toolchain.toml` | 1 | 3 | desvio declarado¹ |
| T3.2 | `grep -rn 'def normalize_ptbr' scripts training \| wc -l` | 0 | **5** | **FAIL (H-4)** |
| T4.1 | `grep -c 'read_to_string.*unwrap_or_default' app.rs` | 0 | 0 | PASS |
| T4.2 | `--diff-filter=D` sem `.onnx`/`tokens.txt` | vazio | vazio | PASS |
| T4.2 | "o diretório original some do HEAD" (m4-pilot-fleurs) | some | 3/4 rastreados | FAIL (L-2) |
| T4.3 | `pytest training/tests/test_readme_links.py -q` | 0 failed | 0 failed | PASS |
| T2.3 | evidência de execução real do CI (URL ou `act`) | registrada | **inexistente** | **FAIL (H-5)** |
| T2.2 | hash esperado **literal no script** | literal | em `.sha256` à parte | FAIL parcial (L-7) |
| T2.4 | `head -2 LICENSE \| grep -c 'Apache License'` | 1 | 1 | PASS (proxy fraco — L-6) |
| T4.3 | estados do README == `grep '^### M' ROADMAP.md` | iguais | M9 diverge | FAIL parcial (M-7) |
| T4.2 | `training/smoke/` + 2 cópias em `models/` removidas | removidas | **presentes** | **FAIL (M-3, M-6)** |

¹ `rust-toolchain.toml:14` fixa `channel = "1.88"`, não 1.75. O commit `1ca6fdb`
declara e justifica a correção (o piso real do `ort` 2.0.0-rc.12 é 1.88, e o
`1.75` do `Cargo.toml` era falso). Desvio declarado — o critério do plano é que
ficou obsoleto. As 3 ocorrências de "1.75" são comentários explicando a correção.

---

### LOW

- **L-1** `CHANGELOG.md:16` e `CHANGELOG.md:36` — duas seções `### Added` dentro
  do mesmo `[Unreleased]`. Keep a Changelog / Regra 6 admite uma por categoria.
- **L-2** `plan:721` exige "o diretório original some do HEAD" para
  `m4-pilot-fleurs`. `git ls-files` mostra 3 dos 4 arquivos ainda rastreados, e o
  tarball `training/results/archive/m4-pilot-fleurs-raw.tar.gz` duplica conteúdo
  versionado. O commit declara "ARQUIVADO, NAO APAGADO" com justificativa sólida
  (dado por-utterance irrecuperável), então é desvio declarado — mas o critério
  de aceite continua formalmente não cumprido.
- **L-3** `crates/macaw-cli/src/app.rs:507` — `Err(_) => { missing.push(name); … }`
  descarta o `io::ErrorKind`. Um `EACCES` é reportado como "relatórios ausentes".
  A correção do erro engolido é real e boa; falta só distinguir a causa.
- **L-4** `training/results/m4-pilot-fleurs-results.md:27` cita o `train.log` como
  proveniência de "41,9s ± 1,3 / época". O arquivo saiu do HEAD; num clone limpo a
  citação não resolve. A linha 40 do mesmo arquivo foi repontada para o tarball; a
  27 não.
- **L-6** `LICENSE` tem **17 linhas** e termina em `Full text:
  https://www.apache.org/licenses/LICENSE-2.0.txt` (`LICENSE:17`) — é o *boilerplate
  de cabeçalho* da Apache-2.0, não o texto da licença (~202 linhas). A própria
  Apache-2.0 § 4(a) exige entregar uma cópia da licença a quem recebe o trabalho.
  O critério do plano (`head -2 LICENSE | grep -c 'Apache License'` → 1) **passa**,
  porque mede as duas primeiras linhas — é um proxy que não distingue stub de texto
  completo. Fix: `curl -o LICENSE https://www.apache.org/licenses/LICENSE-2.0.txt`.
- **L-7** O critério de T2.2 pede o hash "literal no script"; ele vive em
  `scripts/onnxruntime-1.23.0.sha256` e o script o consome via `sha256sum -c`.
  **Design melhor** que o critério (separa dado de lógica, permite `-c` nativo) —
  registro apenas porque o critério, como escrito, não é cumprido.
- **L-5** `crates/macaw-asr/src/lib.rs:466-471` — extração de `vocab_fingerprint`
  por `split("\"vocab_fingerprint\"")`. Defensável pela escada de parcimônia
  (`serde` não é dependência do workspace hoje), e o campo é gerado por script
  próprio. Frágil se o card ganhar um campo cujo *valor* contenha esse literal.

### INFO

- **TDD RED→GREEN não é rastreável no histórico.** Em `86f608e`, `773fa24`,
  `262366b`, `ead3b7f` o teste e a implementação chegam no **mesmo commit**. As
  mensagens afirmam "RED->GREEN" e não tenho motivo para duvidar, mas a ordem não é
  verificável a partir do artefato.
- `models/current` é symlink **gitignored** (`.gitignore:50`). O `model_card.json`
  versionado vive em `training/results/onnx/`. Num clone limpo o symlink não
  existe até rodar `scripts/make_model_card.py`. Consistente com o invariante de
  não versionar pesos.

## O que verifiquei e está saudável

- **Invariante do dono**: zero arquivos de modelo/peso/vocabulário removidos.
  Verificado por `--diff-filter=D` em todo o range.
- **A medição que sustenta o design**: 492/500 ids divergentes, 500 tokens reais
  em ambos, id 4 = `▁a` vs `r` — recomputado do zero, bate exatamente.
- **Wiring pilar (a) da validação de identidade**:
  `crates/macaw-cli/src/transcribe.rs:121` chama
  `validate_against_model_card` em produção. E é cobertura **completa**:
  `Vocab::load` tem exatamente um caller de produção em todo o workspace
  (`transcribe.rs:115`), então não há caminho de transcrição sem validação.
- **`validate_vocab` no ponto certo**: `lib.rs:435` valida **antes** da inferência,
  não depois — fail-fast real, custo O(1) (dimensão lida na carga, `real_len`
  cacheado em `Vocab::load`).
- **Mensagens de erro tipadas com contexto**: `AsrError::VocabModelMismatch` cita
  `model_dim=500 vocab_real=499`; `VocabFingerprintMismatch` cita os dois hashes.
  Ambas explicam a consequência ("transcrição seria silenciosamente errada").
  Atendem `error-handling.md` § 2.
- **Nenhum `unwrap`/`expect`/`unwrap_or_default` novo em caminho de produção** —
  `git diff` sobre `crates/*/src/*.rs` filtrado por esses padrões retorna vazio. O
  único `unwrap_or_default()` existente foi **removido** (T4.1).
- **Desvio de T1.2 declarado**: `773fa24` explica que `load()` recebe só o caminho
  do modelo, que o par só se forma em `transcribe(&vocab)`, e move a validação
  para lá. Honestidade, não defeito.
- **`test_report.sh`** (`scripts/test_report.sh`): a correção é real e boa — captura
  `$?` de `cargo test`, aborta com as últimas 20 linhas, e trata zero testes como
  erro. O commit é honesto sobre a ferramenta anti-falso-verde ter produzido falso
  verde.
- **Três defeitos pré-existentes achados e corrigidos no caminho** (`1ca6fdb`):
  `rust-version = "1.75"` era falso (piso real 1.88, lido do `Cargo.toml` do `ort`);
  `capture_test` flaky medido em 2/5 execuções e corrigido para 0/8; `test_report.sh`
  verde com build quebrado. Descobrir e declarar isso é o oposto de esconder.
- **Referências órfãs pós-remoção**: varredura sistemática dos 16 arquivos
  deletados (basename + path, todos os tipos de arquivo, excluindo
  `knowledge-base/references/`) achou **uma** só (L-4). `probe_load`, `probe_drift`,
  `errs-test-*`, `wer-summary-*` não têm referência viva; a dep duplicada removida
  do `Cargo.toml` era só a de `[dev-dependencies]`, e `macaw-audio` continua em
  `[dependencies]`.
- **`public-copy.md`**: `README.md` sem nenhum termo proibido
  (`production-ready`, `battle-tested`, etc.). Claims numéricos com link de
  evidência e caveat honesto sobre a magnitude "~2×" (linhas 54-56).
- **`clippy -D warnings` limpo** — re-executado, exit 0.
- **CI model-free é genuinamente model-free**: nenhuma referência a `models/`,
  `results/onnx`, `.onnx` no job obrigatório (guardado por
  `scripts/tests/test_ci_workflow.py`).

## Caminho para `READY_TO_MERGE`

1. **B-1/B-2** — consertar o import do shared kernel e adicionar um teste que rode
   cada entry point como subprocesso. Sem isso, dois scripts de produção estão
   quebrados no HEAD.
2. **H-1** — implementar o teste de conformidade CTC cross-language, ou rebaixar
   explicitamente o bullet do DoD com justificativa (não marcar `[x]` em silêncio).
3. **H-2** — fazer `test_ctc_equivalence.py` importar e exercitar `common/ctc.py`;
   trocar a asserção de substring da linha 78 por execução real.
4. **H-3** — rodar `/code-quality` e gerar o implementation log antes de re-submeter.
5. **H-4** — migrar os callers para `common/text.py` (e fazer
   `normalize_train_target` delegar em vez de copiar), ou reescopar o bullet do
   DoD com honestidade.
6. **H-5** — rodar o CI de fato (`act -j test-model-free` ou push + URL do run).
   É barato e é a rede que as fases 3 e 4 já consumiram sem ter.
7. **M-1** — remover ou wirear `output_vocab_dim()`.
8. **M-2..M-7, L-1..L-7** — endereçar ou documentar; nenhum bloqueia isoladamente.
   `L-6` (LICENSE stub) é o de menor custo e maior consequência externa.

## Nota de método sobre esta revisão

Rodei as quatro suítes e todos os critérios de aceite mecanizáveis eu mesmo; não
aceitei número de mensagem de commit sem re-medir. Duas varreduras auxiliares
(referências órfãs pós-remoção; matriz completa de 32 critérios) foram delegadas a
subagentes, e **cada achado que elas trouxeram foi re-verificado por mim** antes de
entrar neste relatório — `LICENSE` lido na íntegra, `gh run list` re-executado,
`cmp` rodado nas cópias de `models/`, `README.md`/`ROADMAP.md` comparados linha a
linha. Nenhum achado aqui repousa em relato de terceiro.

> **Nota de método.** Não marcar `[x]` nos bullets de DoD `ROADMAP.md:331-332` no
> release enquanto H-1 e H-4 estiverem abertos. O milestone tem o hábito, visível
> em vários commits, de medir antes de afirmar — vale mantê-lo aqui.
