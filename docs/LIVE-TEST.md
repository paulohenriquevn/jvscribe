# Live test — os 37 entrypoints, executados de verdade

Data: 2026-07-31 · Máquina: i7-1355U, load 5–12 (sessão de trabalho do usuário ativa)
Método: **execução real** com argumentos reais, não `--help`. Onde o dado existia nesta
máquina, o script rodou de ponta a ponta e o resultado foi lido. Onde não existia, o script
foi executado assim mesmo — para registrar **como** ele falha.

## Recursos disponíveis

| tem | não tem |
|---|---|
| `models/current` (M5) e `models/m4-legacy-onnx` | icefall clonado (`/workspace/icefall`) |
| 1.039 wavs do FLEURS + o parquet no cache HF | runtime Rust (removido em 2026-07-30) |
| `sox`, `ffmpeg`, `parec`, mic e monitor do PulseAudio | áudio de call center (local, LGPD) |
| onnxruntime, lhotse, torch, jiwer, faster-whisper | corpus CORAA / TAGARELA |

---

## Placar

| | n |
|---|---|
| **Funcionais, verificados com saída real** | **17** |
| Funcionais, bloqueados por dado ausente nesta máquina (falham claro) | 12 |
| Funcionais mas **superados** — utilidade duvidosa hoje | 3 |
| **Com defeito real encontrado neste teste** | **4** (um quinto foi retirado — era erro meu) |
| Irreproduzíveis por dependência removida do repositório | 2 |

Os grupos se sobrepõem: um script pode ser funcional **e** ter defeito de interface.

---

## 1. Funcionais — rodaram e produziram resultado real

| script | testado | resultado | utilidade |
|---|---|---|---|
| `batch/batch_transcribe.py` | ✅ 4 wavs | transcreveu PT-BR legível, RTFx 24,1× | **alta** — é o caminho de produção offline |
| `realtime/live_transcribe.py` | ✅ 12 s, áudio tocando no alto-falante | **transcreveu ao vivo os dois canais**, com rótulo de falante e timestamps | **alta** — é o produto |
| `realtime/mic_transcribe.py` | ✅ 15 s | transcreveu com display incremental (cinza=tentativo) | **baixa** — ver § 3 |
| `bench/bench_rtfx.py` | ✅ | RTFx 22,9×, p50/p95/p99 | alta |
| `bench/runtime_bench.py` | ✅ 3 reps | tabela pareada com IC95% por configuração | alta |
| `bench/calibrate.py` | ✅ | "janela recomendada: 6 s (66,4% de ocupação)" | alta |
| `bench/stress_test.py` | ✅ 1 min | **`INDETERMINADO (carga)`**, exit 2 | alta — recusou concluir sob load 11,8 |
| `common/artifact.py` | ✅ | regenerou `model_card.json` com fingerprint | alta |
| `eval/cer_from_recogs.py` | ✅ recogs sintético | WER 40,00% / CER | média |
| `eval/bootstrap_wer_ci.py` | ✅ | Δ + IC95% + P(melhora>0) | alta |
| `eval/extract_fleurs_one_wav.py` | ✅ | gravou o wav da fixture | baixa — one-off de proveniência |
| `eval/baseline_fleurs_ptbr.py` | ✅ n=2, faster-whisper small | WER 8,3% [IC95 5,6–12,5] | média — ver § 4 |
| `corpus/run_pipeline.py` | ✅ n=2 | pseudo-label → filtro τ=0,023 → manifest, 1/2 mantidos | alta |
| `probes/blank_penalty_probe.py` | ✅ n=2 | "nulo/inconclusivo (IC inclui 0)" | alta — o nulo é resultado |
| `probes/tta_feature_align_probe.py` | ✅ n=2 | "ALINHAMENTO PIORA" | alta — refutou a hipótese |
| `eval/compare_models.py` | ⚠️ só interface | exige `--refs --hyps-a --hyps-b`; não tinha o par | média |
| `eval/make_telephone_test.py` | ⚠️ só interface | exige um CutSet de entrada | média |

**A prova mais forte** foi o `live_transcribe`: toquei fala pelo alto-falante e ele capturou,
transcreveu e rotulou os dois canais em tempo real. Não é smoke test — é o produto rodando.

```
[ 1.92s] ATENDENTE: ele estava na casa dos vinte anos em uma
[ 4.59s] ATENDENTE: declaração
[ 5.77s] CLIENTE: miber disse que
[ 6.79s] CLIENTE: embora eu não
```

(Mic e loopback captam o mesmo alto-falante aqui, daí o eco entre os dois papéis. Num 1:1
real são fontes distintas.)

---

## 2. Funcionais, bloqueados por dado que não existe nesta máquina

Todos falharam **como deveriam**: mensagem que diz o que falta. Não são defeitos.

| script | o que falta | como falha |
|---|---|---|
| `finetune/prep_finetune.py` | icefall clonado | `FALHA: train.py nao encontrado em /workspace/icefall/…` |
| `finetune/prep_phoneme_head.py` | idem | `FALHA: …/zipformer não existe` |
| `finetune/prep_augment_datamodule.py` | idem | `FALHA: asr_datamodule.py nao encontrado` |
| `finetune/prep_coraa.py` | corpus CORAA | `FileNotFoundError: metadata do CORAA não encontrado` |
| `finetune/prep_tagarela.py` | shards TAGARELA | `nenhum .parquet encontrado sob /x — rode download_…` |
| `finetune/download_tagarela_subset.py` | rede + HF token | `CalledProcessError` do `curl` |
| `finetune/gen_phonemes.py` | corpus | interface ok |
| `eval/measure_realcodec.py` | icefall | mensagem com `--icefall-root` / `ICEFALL_ROOT` |
| `bench/finetune_smoke.py` | checkpoint + bpe | argparse exige os obrigatórios |
| `eval/measure_callcenter.py` | áudio local (LGPD) | ver § 4 |
| `audit/coraa_speaker_overlap.py` | metadados CORAA | ver § 4 |
| `audit/tagarela_coraa_leak_check.py` | os dois corpora | ver § 4 |

---

## 3. Funcionais mas superados — utilidade real duvidosa

### `realtime/mic_transcribe.py` — **um canal, e o canal errado**

Transcreve ao vivo, mas usa `sounddevice`. `[MEDIDO]` neste teste: o `sounddevice` enxerga
**zero monitor sources** nesta máquina. O `CLAUDE.md` registra o mesmo fato e é por isso que
`live_transcribe.py` usa `parec`.

Consequência: `mic_transcribe` **só captura o microfone, nunca o loopback** — não consegue o
lado do cliente, que é metade do produto. E seu `--device N` documenta "ver
`sd.query_devices()`", uma lista onde o monitor não aparece.

**Veredito: superado por `live_transcribe.py`.** Serve como versão de um canal para depuração;
não serve ao caso 1:1.

### `eval/extract_fleurs_one_wav.py` — one-off de proveniência

Funciona, mas regenera uma fixture derivada que já existe. Utilidade: manter a reprodutibilidade
da fixture. Rodar mais de uma vez não agrega.

### `eval/eval_runtime_wer.py` · `eval/analyze_error_composition.py` — órfãos de um runtime removido

O `main()` dos dois exige o binário Rust, **removido do repositório em 2026-07-30**. Falham com
a mensagem certa (dizem qual commit e o que usar no lugar), mas **não há como executá-los aqui**.
Continuam no repositório porque são a proveniência do WER de runtime publicado e porque seus
helpers são importados por outros módulos.

---

## 4. Defeitos REAIS encontrados por este teste — **todos corrigidos**

### D1 — `baseline_fleurs_ptbr.py` sobrescreve um documento VERSIONADO da wiki

Rodei com `n=2` e ele **substituiu `wiki/medicoes/m1-baseline.md`** — o baseline real de M1,
de 12 utterances e 3 modelos — por uma corrida de duas utterances. Tive de restaurar via git.

Não há flag de saída: o destino é fixo no código. Um teste rápido destrói uma medição publicada.
**Causa: fui eu quem apontou o script para a wiki** ao corrigir o `NameError` do `REPO` numa
sessão anterior; o destino anterior (`jvscribe/results/`) tinha sido removido. Troquei um bug
por outro.

`corpus/run_pipeline.py` e `eval/baseline_minds14.py` tinham o mesmo padrão (o segundo ainda
apontando para `jvscribe/results/`, removida).

**✅ Corrigido.** `common/metrics.escrever_relatorio` recusa sobrescrever um relatório existente;
`JVSCRIBE_REPORT` aponta outro destino e `JVSCRIBE_REPORT_FORCE=1` autoriza a substituição
deliberada. Verificado: a mesma corrida `n=2` que apagou o baseline agora imprime o relatório
e recusa gravar — md5 do arquivo publicado **inalterado**.

### D2 — `audit/tagarela_noise_audit.py` tem interface posicional não documentada

```python
MANIFEST = sys.argv[2] if len(sys.argv) > 2 else "…"
SAMPLE   = int(sys.argv[1]) if len(sys.argv) > 1 else 120000
```

A ordem é `[amostra] [manifesto]` — contraintuitiva, sem `argparse`, sem `--help`, e **parseada
em nível de módulo**: importar o arquivo já dispara a leitura de `sys.argv`. Passar o caminho
primeiro dá `ValueError: invalid literal for int()`.

**✅ Corrigido.** `--manifest` / `--amostra` com `argparse`, parse dentro de `main()`, e
fail-fast que diz de onde vem o manifest.

### D3 — quatro scripts falham com exceção crua, não com erro de domínio

`error-handling.md § 2` exige mensagem que diga o que fazer. Estes dão o traceback da lib:

| script | o que aparece |
|---|---|
| `eval/measure_callcenter.py` | `FileNotFoundError: [Errno 2] … '/x'` |
| `eval/make_callcenter_cuts.py` | `soundfile.LibsndfileError: Error opening '/x'` |
| `audit/coraa_speaker_overlap.py` | `FileNotFoundError: … '/x/metadata_train…'` |
| `audit/tagarela_coraa_leak_check.py` | `FileNotFoundError: … '/x'` |

Compare com os que fazem certo: *"recipe do icefall não encontrada em … Passe `--icefall-root`
ou exporte `ICEFALL_ROOT`"*.

**✅ Corrigido** nos quatro — validação na fronteira, com a instrução do que buscar:

```
áudio do call center não encontrado: /x
O dado de call center é LOCAL por LGPD — não é versionado neste repositório.
```

### D4 — `live_transcribe.py` emite veredito de RNF sem registrar a carga

O relatório marcou **RNF-02 ❌ (p99 722 ms)** com a máquina em load 11,8. É a mesma classe de
defeito que corrigi no `stress_test.py`, que hoje diz `INDETERMINADO (carga)`. O relatório
declara que RNF-04/05 são condições, mas trata p99 como resultado.

### D5 — ❌ **RETIRADO: era erro meu, não do script**

Reportei que `prep_icefall.py` recusava `--splits`. Ele recusa mesmo — porque **nunca teve
essa flag**. A palavra `splits` só aparece no arquivo como chave de config interna. Eu a
inventei ao copiar a linha de comando do `gen_phonemes.py`, que tem `--splits`.

A interface real é `--sources --lang --out --num-jobs --limit`, e o `--help` a mostra
corretamente. Fica registrado porque um relatório de teste que acusa o alvo errado é pior que
um que não acusa nada.

---

## 5. O que não foi testado, e por quê

| script | motivo |
|---|---|
| `batch/eval_public_hf.py` | roda, mas leva ~15 min por corrida; validado numa sessão anterior (WER 15,83%) |
| `batch/decode_onnx_local.py` | exige um manifest Lhotse que eu teria de fabricar; o caminho de decode já é exercitado por `batch_transcribe` |
| `eval/baseline_minds14.py` | dataset MINDS-14 ausente do cache |
| `finetune/patch_ctc_decode.py` | patcher de arquivo do icefall; sem icefall não há o que patchar |

---

## 6. Conclusão honesta

**Ruído praticamente não há.** Dos 37, apenas `mic_transcribe.py` é claramente supérfluo hoje —
e mesmo ele funciona; o problema é que `live_transcribe.py` faz o mesmo e mais. Os dois órfãos
do runtime Rust são proveniência de medição, não código morto.

**O que este teste comprou** que a suíte de 397 testes não cobria:

1. A prova de que o produto **transcreve fala ao vivo** pelos dois canais — nenhum teste
   unitário demonstra isso.
2. Cinco defeitos de interface e de efeito colateral que só aparecem na execução real, sendo
   um deles **destrutivo** (sobrescreve medição versionada) e introduzido por mim.
3. A confirmação medida de que `sounddevice` não vê monitor sources nesta máquina — o fato que
   justifica o desenho com `parec`.

**O que ele NÃO prova:** nada sobre WER, RTFx sustentado ou RNF. A máquina esteve sob load 5–12
o tempo todo, e `asr-evidence-discipline.md § 5` é explícito: máquina sob carga não mede.
Os números de RTFx acima são de execução, não de medição.
