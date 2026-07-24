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

**Benigno.** Um offset fixo de partida:

1. Não acumula — não degrada ao longo de uma chamada de horas.
2. É calibrável — pode ser alinhado no início da captura.
3. Em produção, ambos os streams iniciam juntos no começo da chamada; o offset é
   um alinhamento único, não um erro crescente.

**R1 do plano é resolvido:** não há necessidade de âncora temporal contínua. Basta,
se necessário, descartar a janela de warmup no início.

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
