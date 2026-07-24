# Evidência — sincronia entre streams (R1 / T5.2)

> Executado em 2026-07-24 no notebook de referência (i7-1355U, Ubuntu 22.04,
> PulseAudio nativo). Rotulagem conforme `.claude/rules/asr-evidence-discipline.md` § 1.

## Hipótese

O blueprint (`m0-walking-skeleton-blueprint.md` § R-M0-1) deixou aberto se a
diferença entre os dois streams é **offset de startup** (uma vez, benigno) ou
**drift contínuo** (acumula, quebra RF-05). A minha medição inicial confirmou
apenas contagem de amostras — insuficiente para distinguir os dois.

## Experimento

`crates/macaw-audio/examples/probe_drift.rs`: captura mic + monitor de um
null-sink por N segundos, com tom contínuo, e reporta a diferença de contagem de
amostras. Rodado em durações crescentes — se a diferença **absoluta** for
constante, é offset; se crescer, é drift.

```
cargo run -p macaw-audio --example probe_drift -- <segundos>
```

## Resultado `[MEDIDO]`

| Duração | mic | monitor | diff_abs (amostras) | diff (s) | pct |
|---|---|---|---|---|---|
| 4 s | 63.488 | 41.472 | 22.016 | 1,38 | 34,7% |
| 8 s | 127.488 | 104.448 | 23.040 | 1,44 | 18,1% |
| 16 s | 255.488 | 232.448 | **23.040** | **1,44** | 9,0% |

## Conclusão

**É offset de startup, não drift contínuo.** A diferença absoluta estabiliza em
**23.040 amostras (1,44 s)** e **não cresce** de 8 s para 16 s — idêntica. A
porcentagem cai (34,7% → 9,0%) apenas porque o offset fixo vira fração menor de um
total maior.

Em regime, os dois streams avançam à **mesma taxa — drift ≈ 0**. O gap é a latência
de partida do monitor de um null-sink recém-criado, ~1,44 s maior que a do mic de
hardware.

### Consequência para RF-05 (roteamento de falante)

**Benigno na janela medida — com um limite importante de validade.**

O que a evidência sustenta, restrito ao que foi medido (≤ 16 s, mic de hardware vs
monitor de **null-sink de software**):

1. O offset de partida é constante (~1,44 s) e não cresce entre 4 s, 8 s e 16 s.
2. É calibrável — pode ser alinhado descartando a janela de warmup inicial.

**O que a evidência NÃO sustenta** — e a análise anterior extrapolou
indevidamente:

- A afirmação de que o offset "não degrada ao longo de uma chamada de horas" era
  **extrapolação de 16 s para horas** — a falácia #4 (benchmark curto). Deriva de
  crystal é ppm: indetectável em 16 s, acumulável em horas.
- Pior: o arranjo **estruturalmente não pode** medir deriva entre dois relógios de
  hardware. O monitor de um null-sink **não tem crystal independente** — é dirigido
  pelo mesmo timer do servidor que serve o mic. O experimento mede a **consistência
  de resample do servidor**, não o caso de produção (loopback de um dispositivo de
  playback real, com seu próprio clock).

**Deriva de hardware entre mic e loopback numa chamada longa é `[DESCONHECIDO]`** e
precisa ser medida em M1 (harness sustentado ≥ 10 min) contra dois clocks reais.

**R1 do plano é parcialmente endereçado:** o offset de *partida* está caracterizado
e é benigno; a deriva de *hardware em regime prolongado* segue aberta.

### Consequência para o teste de integração

O teste `test_two_captures_run_simultaneously_without_interference` originalmente
media a diferença de **contagem total desde o spawn**, o que conflaciona offset de
startup com paridade de taxa — metodologicamente incorreto. Reescrito para medir
**paridade de taxa em regime** (após warmup de 3 s), que é a propriedade física
relevante e que esta evidência mostra ser ~0.

## Limites

- Medido com null-sink como fonte de loopback; um sink de hardware real pode ter
  offset diferente. A **taxa** em regime não deve mudar (mesma crystal do servidor).
- Um ambiente PipeWire pode diferir — Q-01 / M8.
