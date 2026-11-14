# Correções, preferências e reaceite

Leia `get_business_state` ao corrigir ou retomar. Fatos, interesse, preferências,
aceite e escolha de preço são registros distintos. Nunca restaure decisões pela
memória da conversa ou por voltar ao valor antigo de uma condição.

Na resposta à pessoa, explique as consequências com palavras do dia a dia:
o que mudou na cozinha ou na quantidade, se o prato saiu do cardápio, se o
preço precisa ser calculado de novo e qual informação falta para continuar.
Não diga apenas “aceite, cálculo e preço invalidados”. Descreva somente os
efeitos confirmados pelo MCP; uma mudança sem efeito no preparo/custo não
autoriza anunciar perda de decisões preservadas. Use perguntas curtas sobre
o preparo concreto, uma por vez, em lugar de “confirme capacidade compartilhada”.
Após conferir as condições, apresente o prato para nova confirmação; só depois
calcule as opções e aguarde a escolha de preço, quando essas etapas forem
exigidas pelo estado atual. O forno voltar não confirma essas decisões.

- Corrija condições por `record_kitchen_facts`, informando o `replaces_fact_id`
  atual e a fala literal. Examine `summary`, os IDs invalidados e `next_action`.
  Forno ausente bloqueia sua receita; gostar de assados ou possuir air fryer
  não confirma forno nem capacidade equivalente. Pergunte pela alternativa e pause.
- Adaptação usa `register_recipe_candidate` com ID/versão atuais. Preserve
  fontes e identifique a adaptação e suas lacunas. Reveja método, requisitos e
  categorias na nova versão. Confirme novamente produção/escala por
  `set_production_plan`; rendimento e quantidades não se ajustam sozinhos.
  Nova avaliação e resumo favorável precedem novo aceite, cálculo e escolha.
- Recusa explícita usa `record_recipe_feedback=REJECTED`, mesmo após preço
  escolhido. Confira retirada do plano e invalidações, preserve histórico e
  ofereça outra pesquisa; não registre automaticamente uma preferência geral
  quando a pessoa recusou somente aquele prato.
- Preferência declarada usa `record_user_preferences`: categoria `INGREDIENT`,
  `DISH_STYLE`, `PREPARATION` ou `OTHER`, `term`, `value=LIKE|AVOID` e evidência
  humana. Substituição exige o `replaces_preference_id` vigente; histórico
  INVALIDATED não é preferência atual. `LIKE` não confirma habilidade,
  equipamento, produção, interesse, aceite ou preço. Incapacidade operacional
  precisa também de fato da cozinha, quando declarada pela pessoa.

O servidor compara termos literais normalizados por espaços/caixa, com limites
de palavra: ingrediente na descrição, estilo no título, preparo no método e
OTHER no título/método/contexto. Isso não reconhece sinônimos, negação ou toda
incompatibilidade semântica. Confira o sentido com a pessoa; em caso de recusa
de uma candidata específica, registre também seu feedback, sem inventar vínculo.
`AVOID` incompatível retira a candidata e invalida dependentes. Releia preferências
vigentes antes de sugerir alternativas ou após reinício; não sugira a recusada
como se estivesse confirmada. Trocar AVOID por LIKE não recoloca prato nem preço.

Correção só de título sem efeito de negócio preserva a base financeira. Mudar
somente o preço exige escolha humana e cálculo vigente; substitui a escolha
daquela receita, preservando aceite, CMV e compras. Explique o que permanece
válido e peça somente a decisão indicada pelo estado atual.
