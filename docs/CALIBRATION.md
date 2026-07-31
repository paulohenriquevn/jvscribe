# Runbook — calibrar o runtime ao trocar de CPU

**Quando rodar:** ao levar o jvscribe para uma máquina diferente, ao trocar de modelo, ou ao
mudar o número de canais simultâneos.

**Por que existe:** parte das otimizações deste projeto é portável e parte **não é**. Herdar
um número medido noutra máquina é pior que não ter número, porque parece calibrado.

---

## O que é portável e o que precisa ser remedido

| otimização | portável? | por quê |
|---|---|---|
| `FeatureCache` — fbank incremental | **sempre** | elimina trabalho redundante; independe de hardware |
| dreno do `DualCapture.read()` | **sempre** | era defeito de encanamento (1 chunk por chamada contra ~30/s produzidos) |
| teto do `committed` | **sempre** | era estado sem limite (2.128 entradas em 3 min) |
| backpressure | **sempre** | propriedade de sistema de tempo real, não de CPU |
| arena de memória ON + `inter_op` | **provavelmente** | config de runtime; medido −17,1% aqui, mas não verificado noutra CPU |
| **`intra_op_num_threads`** | **não** | sai da topologia (P-cores vs E-cores) — já é dinâmico, mas a heurística `metade dos lógicos rápidos` é de uma máquina |
| **janela de decode** | **não** | sai da ocupação de CPU medida |

**NÃO é calibração:** ativar afinidade de CPU. Foi tentado, medido e revertido — `sched_setaffinity`
é herdado pelos processos filhos e os `parec` da captura passavam a disputar os mesmos núcleos
com a inferência, derrubando o RTFx de 4,60× para 2,33×. Há teste de regressão contra isso.

---

## Procedimento

### 0. Deixe a máquina ociosa

Não é formalidade. Medido: a **mesma** configuração deu RTFx 3,51× / 2,90× / 2,82× / 2,50× com
a máquina em load 3–4. A dispersão engole qualquer diferença que se queira medir. Feche
navegador, IDE e o que mais estiver rodando; confira com `uptime`.

O `calibrate.py` avisa quando o load average passa de 1,0 — o aviso não é decorativo.

### 1. Verifique a topologia detectada

```bash
python3 -c "
import sys; sys.path.insert(0,'jvscribe/common')
from cpu_topology import detectar; import json; print(json.dumps(detectar().como_dict(), indent=2))"
```

Confira se `hibrida` bate com o hardware. Falso positivo de hibridez fatiaria a máquina à toa;
falso negativo deixaria threads esperando núcleo lento. A tolerância de 15% em frequência
existe para que boost por núcleo **não** conte como hibridez.

### 2. Meça a curva de custo e obtenha a janela

```bash
python3 jvscribe/tools/calibrate.py \
    --audio <um wav de 16 kHz> --canais 2 --hop 0.5 --json config-<maquina>.json
```

Saída: o custo de decode por tamanho de janela, a ocupação de CPU resultante e a **maior
janela que cabe** no teto de 80%.

Janela **maior é melhor** — mais contexto para o LocalAgreement-2 confirmar palavra. A busca é
pelo teto que ainda cabe, não pelo mais rápido.

Se a saída for `NENHUMA janela cabe`, a máquina não aguenta o caso de uso com esse número de
canais. Isso é a resposta correta, não uma falha da ferramenta: as opções são menos canais,
hop maior ou hardware com mais folga.

### 3. Confirme os parâmetros de sessão do ONNX

```bash
python3 jvscribe/tools/runtime_bench.py --audio <wav> --janela <a do passo 2> --reps 25
```

Compara arena, `inter_op`, contagem de threads e nível de otimização de grafo com **bootstrap
pareado**. Só declara vencedor quando o IC95% do delta não cruza zero — se sair
`inconclusivo`, a diferença é ruído e a config atual serve.

> Neste i7, baixar `graph_optimization_level` para `BASIC` **piora** +6,6%. Não assuma que
> menos otimização é mais previsível.

### 4. Valide sob carga sustentada

```bash
python3 jvscribe/tools/stress_test.py \
    --audio-dir <pasta de wavs> --minutos 30 --canais 2 --threads <do passo 1>
```

Trinta minutos é o mínimo do RNF-04: um chip U de 15 W não sustenta turbo, e um benchmark de
30 s mede o turbo e mente. A saída traz RTFx e p99 **minuto a minuto** — o que interessa é a
razão entre o último minuto e o primeiro (alvo ≥ 0,80), não a média.

**Com um softphone rodando em paralelo**, este mesmo comando cobre o RNF-05.

### 5. Valide de ponta a ponta

```bash
python3 jvscribe/realtime/live_transcribe.py \
    --window <passo 2> --hop 0.5 --threads <passo 1> --duracao 60 --relatorio evidencia.md
```

⚠️ Use isto para **validar**, não para comparar configurações. O harness ao vivo depende de
alto-falante, microfone e timing de reprodução; a dispersão para config idêntica é de ~1,0× de
RTFx. Comparação de config sai do passo 3 (pareado) ou do 4 (determinístico).

---

## Interpretando os números

| sintoma | causa provável | onde olhar |
|---|---|---|
| ocupação > 100% em toda janela | modelo grande demais para a CPU | reduzir canais, ou modelo menor |
| RTFx cai ao longo do soak | throttling térmico (RNF-04) | curva minuto a minuto do passo 4 |
| p99 alto com RTFx bom | os canais decodificam **em série**; a latência tem piso `hop + decode(própria) + decode(do outro)` | reduzir janela, ou o streaming causal de M6 |
| backlog crescendo sem parar | consumidor mais lento que a produção | já corrigido no `read()`; se voltar, é regressão |
| tudo inconclusivo no passo 3 | máquina não estava ociosa | voltar ao passo 0 |

---

## Se o número mudar muito

Um resultado muito diferente do registrado aqui é informação, não erro. Registre em
`jvscribe/results/` com a condição de medição ao lado — CPU, load average, número de
repetições. Um número sem condição não é comparável com nada.

Referência desta máquina (i7 híbrido, 2 P-cores a 5,0 GHz + 8 E-cores a 3,7 GHz):

| janela | custo (intra=2, arena ON) | ocupação com 2 canais @ 0,5 s |
|---|---|---|
| 2 s | 26,7 ms | 10,7% |
| 6 s | 112,2 ms | 44,9% |
| 10 s | 158,7 ms | 63,5% |
| 12 s | 270,4 ms | 108,2% — satura |

Antes das otimizações de sessão, a janela de 6 s custava 172 ms e a de 10 s pedia 104,9%.

---

## O que a calibração NÃO resolve

O modelo **não é streaming** — é não-causal, e cada hop reprocessa a janela inteira. Medido:
121 ms para reprocessar 6 s contra 11 ms de processar só os 0,5 s novos, **10,6× de
retrabalho**. Nenhuma calibração remove esse termo; ele sai com treino causal e reexport com
tensores de estado. Ver `docs/ARCHITECTURE.md`.

## Referências cruzadas

| assunto | onde |
|---|---|
| Como o modelo e o motor funcionam | `docs/ARCHITECTURE.md` |
| Profile por operador e prior art | `jvscribe/results/m6-runtime-profile-2026-07-31.md` |
| Topologia, afinidade e o limite do instrumento | `jvscribe/results/m6-cpu-topology-2026-07-31.md` |
| Envelope medido ao vivo | `jvscribe/results/m6-live-dual-channel.md` |
| Critérios RNF-01..08 | `PRD.md` § 6 |
