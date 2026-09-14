---
type: Índice
title: Medições
description: Todo número, com hipótese, evidência e limitações separadas. Nenhum sem condição ao lado.
tags: [medicao, evidencia]
timestamp: 2026-07-31T00:00:00Z
---

# Medições

Cada documento separa **hipótese**, **evidência** e **limitações**. Conclusão que excede a
evidência é defeito de severidade máxima — ver [../disciplina/index.md](../disciplina/index.md).

## Por milestone

| documento | o que mediu |
|---|---|
| [m1-harness.md](m1-harness.md) | O instrumento, antes do experimento |
| [m1-baseline.md](m1-baseline.md) | Régua inicial multi-modelo |
| [m2-rtfx-candidatos.md](m2-rtfx-candidatos.md) | Transducer/CTC ~2× mais rápido que AED em CPU |
| [m5-modelo-final.md](m5-modelo-final.md) | O finetune que produziu o modelo entregue |
| [m6-profile-por-operador.md](m6-profile-por-operador.md) | Onde o tempo realmente está |
| [m6-topologia-de-cpu.md](m6-topologia-de-cpu.md) | CPU híbrida, `perf`, e o limite do instrumento |
| [m6-rnf-ao-vivo.md](m6-rnf-ao-vivo.md) | Os critérios de real-time sobre o pipeline completo |
| [m6-soak-30min-rnf04.md](m6-soak-30min-rnf04.md) | O primeiro soak de 30 min — sem vazamento, estado limitado, RNF-04 indeterminado por carga |
| [m10-t1-teto-de-cpu.md](m10-t1-teto-de-cpu.md) | O teto é ~174M, não linear — há 68 ms/s de custo fixo que nenhum modelo menor remove |
| [composicao-do-erro-e-o-que-cada-remedio-alcanca.md](composicao-do-erro-e-o-que-cada-remedio-alcanca.md) | O erro em três terços — e nenhuma intervenção alcança mais que um |
| [e0-instrumento-de-confianca.md](e0-instrumento-de-confianca.md) | O portão custa +0,31% — e o desenho que a execução refutou |
| [e1-portao-de-confianca.md](e1-portao-de-confianca.md) | O portão separa: precisão 55,9% [IC95 49,4; 62,0] contra base 14,3% |
| [e2-correcao-com-portao.md](e2-correcao-com-portao.md) | A correção funciona — 0,27 p.p. — e menos do que eu previ |
| [e4-custo-do-beam.md](e4-custo-do-beam.md) | O custo do beam não é o obstáculo — no lote. No tempo real, desconhecido |
| [e6-preregistro-beam-lm.md](e6-preregistro-beam-lm.md) | Predições e critérios de morte, escritos ANTES da corrida |
| [e6-beam-controle.md](e6-beam-controle.md) | O beam sem LM não move o WER — e era esse o objetivo |
| [e6-beam-lm.md](e6-beam-lm.md) | Beam + LM rende 4,7%, não 10–20%; corpus, ordem e largura saturaram |
| [e7-custo-do-int8.md](e7-custo-do-int8.md) | O int8 não custou acurácia — o orçamento extra não compra por aí |
| [e8-composicao-do-erro-na-regua-corrigida.md](e8-composicao-do-erro-na-regua-corrigida.md) | O split S/D/I, e o balde de inserção que a régua escondia |
| [e9-vies-do-normalizador-contra-modelos-de-forma-falada.md](e9-vies-do-normalizador-contra-modelos-de-forma-falada.md) | A régua erra nos DOIS sentidos; o padrão da área pune forma falada |
| [e10-busca-por-conjunto-desafiador-ptbr.md](e10-busca-por-conjunto-desafiador-ptbr.md) | NURC-SP é o conjunto público difícil; "ruidoso" não prediz dificuldade |
| [e11-banda-e-causa-mas-e-minoria.md](e11-banda-e-causa-mas-e-minoria.md) | Banda é causa do gap, e é ~1/6 dele |
| [e12-realce-de-audio-antes-do-asr-piora.md](e12-realce-de-audio-antes-do-asr-piora.md) | Seis técnicas de realce, seis pioras; banda sintética é pior que ausente |
| [e13-duas-verificacoes-antes-da-gpu.md](e13-duas-verificacoes-antes-da-gpu.md) | O corpus é ~1.413 h; a documentação erra 1,6× |
| [e15-o-vies-de-blank-e-dependente-do-dominio.md](e15-o-vies-de-blank-e-dependente-do-dominio.md) | O viés de blank tem sinal OPOSTO em áudio fácil e difícil — −2,3 p.p. no difícil |
| [e16-o-que-1x-de-rtfx-compra.md](e16-o-que-1x-de-rtfx-compra.md) | Relaxar o RTFx para 1× não compra qualidade — e Whisper small nem cabe |
| [reprodutibilidade.md](reprodutibilidade.md) | O artefato publicado transcreve **e** treina |
| [benchmarks-publicos.md](benchmarks-publicos.md) | FLEURS, CORAA, telefônico — com comando de reprodução |

## O que continua não medido

- **RNF-04** (estabilidade térmica): nenhuma corrida chegou a 30 min
- **RNF-05** (carga concorrente): nenhuma teve softphone ativo
- WER em 8 kHz e em fala espontânea de call center
- Equivalência batch↔streaming
- Piso da frota BYOD (Q-01)
