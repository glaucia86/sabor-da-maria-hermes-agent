# Esclarecer identidade e medida

Leia a candidata, suas linhas e a fotografia do workspace. Nomes normalizados
preservam qualificadores: carne moída de patinho não é qualquer carne e feijão
preto não é carioquinha. Não confirme equivalência por semelhança textual.

Se a identidade estiver ambígua, pergunte. Após fala humana inequívoca, use
`resolve_recipe_ingredient` com receita/versão/linha, identidade existente e
`UserEvidence` literal. A resposta fornece nova versão da receita. Reconfirme
o plano quando a versão material mudar.

Se o ingrediente não existir na fotografia nem nas identidades complementares
de `get_business_state`, use `new_ingredient={name,dimension}` em vez de
`existing_ingredient_id`, com evidência da identidade. Use exatamente um ramo.
O servidor fornece o ID; nunca invente UUID nem altere a planilha. Colisão de
nome pede esclarecimento e o ID existente. A disponibilidade zero significa
somente ausência na fotografia; pergunte sobre estoque adicional antes de comprar.
Para pesquisar o faltante e simular pacotes, siga [complementos](compras.md).

`UNIT_CONVERSION_REQUIRED` pede medida sustentada e pausa, sem custo zero.
Uma embalagem de cobertura registrada como `1 un` não informa gramas. Pergunte
se o conteúdo informado também corresponde à embalagem comprada na fotografia.
Não suponha peso por ovo, densidade, xícara, colher ou rendimento cru/cozido.
Os outros ingredientes válidos continuam disponíveis para avaliação.

Use `record_ingredient_conversion` com fator decimal textual positivo,
ingrediente, unidades, contexto e evidência específica. `RECIPE_MEASURE`
exige receita/versão/linha e corresponde à medida original daquela linha.
`from_preparation_basis` identifica RAW ou COOKED da fonte; o fator produz
equivalente RAW para a despensa. Medida sem quantidade continua pendente.

`HISTORICAL_PACKAGE` exige fala humana que sustente a embalagem comprada.
O fator parte da unidade base da fotografia (`g`, `ml` ou `un`) e produz a
unidade indicada. Uma medida da receita ou embalagem atual não autoriza mudar
o denominador histórico. O XLSX e o snapshot original permanecem intactos;
quantidades/custos efetivos aparecem na avaliação do plano.

Conflito exige esclarecimento e `replaces_conversion_id` da conversão vigente;
nunca substitua silenciosamente. Consulte histórico em `get_business_state`.
Depois da escrita, avalie novamente e apresente o resumo atual. Aceites e
preços invalidados exigem novas manifestações humanas; restaurar fator antigo
não restaura decisões. Evidência registrada é trilha auditável, não autenticação.
