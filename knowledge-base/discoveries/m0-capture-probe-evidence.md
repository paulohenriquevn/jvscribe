# Evidência experimental — captura de dois streams (M0 / Q5)

> Executado em 2026-07-24 no notebook de referência.
> Rotulagem conforme `.claude/rules/asr-evidence-discipline.md` § 1.
> Todos os experimentos restauraram o ambiente ao final.

## Ambiente `[MEDIDO]`

| Item | Valor |
|---|---|
| Servidor de áudio | **PulseAudio nativo** (`/run/user/1001/pulse/native`, protocolo 35) |
| PipeWire | binários presentes (`pw-record`), **daemon não é o servidor ativo** |
| `wireplumber` | **ausente** |
| Sink padrão | `alsa_output.pci-0000_00_1f.3.analog-stereo` — s16le 2ch 44100Hz |
| Source mic | `alsa_input.pci-0000_00_1f.3.analog-stereo` |
| Source loopback | `alsa_output.pci-0000_00_1f.3.analog-stereo.monitor` |

## Hipótese

O áudio do sistema (cliente, no cenário de call center) pode ser capturado
simultaneamente ao microfone (atendente), em dois streams independentes, num único
processo — viabilizando o rótulo de falante por roteamento sem modelo de diarização.

## Experimento 1 — `parec` nos dois streams, ambiente padrão

**Comando:** dois `parec` concorrentes, s16le/16 kHz/mono, 2,2 s.

| Stream | Resultado |
|---|---|
| mic | 58.236 bytes · 1,82 s · sinal presente |
| loopback | **44 bytes (só header WAV) · 0,00 s** |

**Conclusão parcial:** o stream de loopback **abre**, mas não flui amostra. Não é
erro de API.

## Experimento 2 — causa raiz do silêncio

```
Sink:    Mudo: sim | Volume: 0% (-inf dB)
Monitor: Mudo: não | Volume: 100% (0.00 dB)
```

**Conclusão:** o monitor reflete o sinal **pós-volume** do sink. Alto-falante mudo
⇒ monitor captura silêncio legítimo. O mecanismo estava correto; o ambiente é que
estava mudo.

> ⚠ **Consequência de produto (edge case crítico, entra em `PRD.md`):** se o
> atendente mutar a saída de áudio, o loopback captura silêncio e **o cliente deixa
> de ser transcrito**, sem erro visível. O runtime precisa detectar sink mudo /
> volume zero e sinalizar — falha silenciosa é o pior modo de falha aqui.

## Experimento 3 — prova do mecanismo via sink virtual isolado

`module-null-sink` carregado, tom de 440 Hz reproduzido nele, monitor capturado.

| Métrica | Valor |
|---|---|
| Duração | 2,76 s |
| Amplitude máxima | 0,250 |
| RMS | 0,130 |
| **Bin dominante** | **441,4 Hz** (emitido: 440 Hz — erro 0,3%) |

**Conclusão:** captura de loopback funciona e é **fiel em frequência**. Módulo
descarregado; ambiente restaurado.

## Experimento 4 — `cpal 0.16` enumera loopback?

```
input devices: 3
  [mic] default
  [mic] pulse
  [mic] HDA Intel PCH
```

**Conclusão `[MEDIDO]`:** **NÃO.** `cpal` enumera via ALSA no Linux, e `.monitor` é
conceito do PulseAudio — invisível para o ALSA. **`cpal` sozinho não resolve o
loopback.**

## Experimento 5 — `cpal` + `PULSE_SOURCE`

Device `pulse` do cpal com `PULSE_SOURCE=m0probe.monitor`:

```
CONFIG  2ch · 44100 Hz · F32
RESULT  123.476 samples · peak = 0.250000
```

**Conclusão:** funciona, **mas `PULSE_SOURCE` é variável de ambiente do processo** —
não permite duas sources diferentes no mesmo processo. Inviável para M0, que precisa
de mic **e** loopback simultâneos.

## Experimento 6 — `libpulse-simple-binding`, dois streams, mesmo processo ✅

Duas threads, cada uma com `Simple::new(..., Some(&source), ...)` — source
especificada **por stream**, não por processo.

```
RESULT LOOPBACK: samples=48000  peak=0.250000
RESULT MIC:      samples=48000  peak=1.000000
```

**Conclusão `[MEDIDO]` — premissa do M0 provada.** Ambos os streams capturam
simultaneamente, com sources distintas, no mesmo processo, ambos com sinal.
48.000 amostras = 3,0 s @ 16 kHz em cada um.

## Veredito para Q5

| Abordagem | Veredito |
|---|---|
| `cpal` sozinho | ❌ não enumera `.monitor` |
| `cpal` + `PULSE_SOURCE` | ⚠ funciona, mas é por processo — inviável para 2 streams |
| **`libpulse-simple-binding`** | ✅ **solução adotada** — source por stream |
| `parec`/`pw-record` como subprocesso | ⚠ funciona; descartado por acoplar o runtime a processo externo |

**Dependência recomendada:** `libpulse-binding` + `libpulse-simple-binding` 2.28.

## Limites desta evidência

- Medido em **um** ambiente (PulseAudio nativo, Ubuntu, kernel 6.8). Não generaliza para PipeWire nativo, macOS ou Windows — Q-01 e M8 tratam disso.
- `Simple` é API **bloqueante**; adequada a thread dedicada por stream, que é o desenho pretendido. Latência de captura **não medida** — pertence a M1.
- Peak do mic saturou em 1.000000 — ganho de entrada alto. Sem impacto na conclusão (o teste era de mecanismo), mas AGC/normalização é item de M1.
- Sincronia temporal entre os dois streams **não medida** — apenas contagem de amostras igual (48.000 em ambos). Deriva de clock entre streams é risco aberto para o roteamento de falante.
