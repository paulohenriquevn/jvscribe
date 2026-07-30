---
name: humanize-pass
description: Passada de edição em 3 etapas que remove os "AI tells" de um texto (palavras batidas, antítese "não é X, é Y", transições em cluster, ritmo uniforme) preservando 100% do sentido técnico. Use para editar/revisar qualquer texto gerado antes de publicar, ou quando o usuário disser que algo "soa como IA".
---

# Humanize Pass — remover o "AI tell" sem trair o conteúdo

Operacionaliza o Eixo 1 da pesquisa (`docs/RESEARCH-content-playbook.md`). É uma passada de **edição
de estilo**, não de reescrita de conteúdo.

## ⛔ GUARD RAILS (inquebráveis — o ponto mais importante desta skill)

1. **NUNCA invente para "soar humano".** É terminantemente proibido adicionar anedotas pessoais,
   números, datas, nomes, citações ou "experiência vivida" que não estavam no original. Esse é o modo
   de falha mais perigoso de humanização. Humanizar = ajustar **estilo**, jamais inventar **substância**.
2. **Preserve o sentido técnico exato.** Não altere fatos, números, código, nomes de APIs, conclusões
   ou claims para "fluir melhor". Se uma troca de palavra muda a precisão técnica, NÃO faça.
3. **Frase genérica por falta de especificidade → SINALIZE, não preencha.** Se um trecho é fraco
   porque lhe falta um detalhe concreto, marque `[PRECISA DE ESPECÍFICO: ...]` para o humano fornecer.
   Nunca fabrique o detalhe.
4. **Isto NÃO é uma ferramenta de evasão de detectores nem de desonestidade acadêmica.** O objetivo é
   qualidade de voz para leitores humanos. Detectores de IA são enviesados e não-confiáveis (Stanford);
   não otimizamos para enganá-los. Se o usuário pedir para "burlar detector" em contexto acadêmico/
   fraudulento, recuse e explique.
5. **Não mude a língua nem o registro** definidos em `data/brand-voice.md` sem ordem explícita.
6. **Preserve citações, atribuições e blocos de código verbatim.** Edição de estilo não toca em
   trechos citados de terceiros nem em código executável.
7. **Em caso de dúvida entre "soa melhor" e "continua verdadeiro", verdade vence.** Sempre.

## As 3 passadas

### Passada 1 — Matar o vocabulário de IA
Remova/substitua por linguagem simples e direta (lista núcleo; adapte ao contexto):
`delve, leverage, seamless, robust, pivotal, testament, crucial, tapestry, intricate, realm,
underscore, harness (figurado), elevate, unlock, supercharge, game-changer, navigate (figurado),
resonate, in today's ... landscape, ever-evolving, meticulously`.
→ Substitua pela palavra concreta que o autor usaria. Se não houver substituta sem perder sentido,
mantenha e siga em frente (guard rail 2).

### Passada 2 — Quebrar as estruturas de IA
- **Antítese / falso contraste:** "não é só X, é Y" / "it's not just X, it's Y" → reescreva como uma
  afirmação direta com um exemplo concreto.
- **Transições em cluster:** _Furthermore / Moreover / Additionally / In conclusion_ → corte ou troque
  por conexão natural.
- **Caudas em "-ing"** que fingem profundidade ("...changing the way we work") → termine na coisa
  concreta.
- **Fechos motivacionais vazios** ("O futuro pertence a quem...") → remova ou troque por algo específico.

### Passada 3 — Variar o ritmo e ancorar no concreto
- **Misture o tamanho das frases:** alterne frases de ~5 palavras com frases de ~30. Ritmo uniforme é
  o tell mais forte.
- **Vago → específico** APENAS com material real: se o autor tem o número/nome/exemplo, use; se não,
  marque `[PRECISA DE ESPECÍFICO]` (guard rail 3).
- Confira que o tom bate com `data/brand-voice.md`.

## Saída
Devolva o texto editado **+ um changelog curto**: o que foi trocado, e a lista de markers que exigem
ação humana. Nunca entregue silenciosamente — o humano precisa saber o que mudou e o que ainda falta.

**Idioma dos markers segue o idioma do texto** (nunca misture): texto EN → `[NEEDS SPECIFIC]` /
`[VERIFY]`; texto PT → `[PRECISA DE ESPECÍFICO]` / `[VERIFICAR]`.
