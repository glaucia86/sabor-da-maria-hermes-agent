# Complementos: pesquisa, confirmação e orçamento

Leia `get_business_state`, a candidata interessada e o plano completo. Se houver
identidade pendente, siga [ingredientes](ingredientes.md) e use o ID devolvido
pelo servidor. Uma adaptação da receita exige revisão explícita da candidata.

Pesquise oferta real com busca e extração disponíveis no Hermes. Registre
URL, título, trecho e horário efetivamente observado. Snippet ou memória não
comprovam embalagem, preço, disponibilidade nem frete. Faça no máximo duas
reformulações automáticas por intenção; depois explique a limitação e aguarde.
Pesquisa sem resultado não autoriza inventar uma oferta.

Use `register_complement_quote` com `CommandMeta` e `quote` contendo:

- `ingredient_id`, `description`, `supplier` e `source` WEB;
- `package_quantity={value,unit}` na base `g`, `ml` ou `un`;
- `package_price` e `purchase_extra_total` como texto decimal;
- `extra_conditions` sustentando os encargos, inclusive ausência/isenção;
- `availability=AVAILABLE|UNAVAILABLE|UNKNOWN` e `availability_context`;
- `max_packages` e `valid_until` somente quando informados pela oferta.

Quando tamanho, preço ou encargos não forem conhecidos, envie o campo `null`
e seu `<campo>_gap` com a lacuna real. Disponibilidade não informada é UNKNOWN,
com contexto explicando a ausência. Frete não encontrado não vale `0.00`.
Massa e volume não são intercambiáveis sem conversão sustentada.

O registro devolve ID/versão e status ESTIMATED, sem confirmação. Para revisar
a mesma oferta, use `quote_id` e `expected_quote_version`; preserve a origem.
Não envie `status`, `confirmation`, pacotes calculados ou outros derivados.

Após mostrar a oferta e receber escolha explícita, use `set_production_plan`
com todos os itens/lotes e `quote_selections=[{ingredient_id,quote_id,quote_version}]`.
O plano é substituído integralmente; não omita outros itens ou seleções ativos.
Selecione uma oferta por ingrediente, sem escolher fornecedor pela pessoa.
Revisão da oferta exige seleção da versão atual. Não divida compras entre fornecedores.

Chame `evaluate_purchase_plan` e explique apenas seus resultados: faltantes,
pacotes inteiros, desembolso integral, sobra planejada, custo dos ingredientes
consumidos e encargos separados. Sobra planejada não é estoque físico. Oferta
insuficiente pede outra oferta ou quantidade; faltante zero não provoca compra.
O limite agregado é R$ 80,00, incluindo os encargos informados.

Quando `is_simulation=true` ou `purchase_status=PENDING`, apresente tudo como
estimativa e exponha as lacunas. Pergunte pela confirmação específica de
embalagem, preço, encargos e disponibilidade; encerre o turno aguardando.
Uma cotação pesquisada não é consentimento. Não use `accept_recipe` para
contornar pendências e não efetue compras.

Com a oferta completa, receba uma fala humana específica antes de chamar
`confirm_complement_quote`. Envie `quote_id`, `quote_version`, `evidence`
(`turn_ref`, fala literal e `captured_at` real do turno) e `scope` contendo:
`package_quantity`, `package_price`, `purchase_extra_total`, `extra_conditions`,
`supplier`, `availability_context` e `packages` (limite de pacotes confirmados).
Os dados devem corresponder à versão atual registrada. Dados novos exigem
revisar a oferta e selecionar sua nova versão antes da confirmação.

O guard aceita uma manifestação explícita completa, por exemplo:
“Confirmo 1 pacote de 1000 g a R$ 20,00 por pacote, encargos R$ 0,00,
Retirada gratuita, disponível em Fornecedor: Retirada hoje.”
Use os valores e condições reais da oferta; peça esclarecimento se a fala não
cobrir esse escopo. Nunca reescreva uma fala parcial como confirmação completa.

Reavalie após confirmar: R$ 80,00 é permitido; R$ 80,01 ou mais retorna
`OVER_BUDGET`. Explique desembolso, saldo/diferença e aguarde a pessoa decidir
sobre redução ou outra oferta. Não escolha a solução por ela.
Somente avaliação confirmada e viabilidade elegível permitem pedir o aceite
do prato; depois siga [precificação](precificacao.md) e aguarde escolha de preço.

A confirmação vale por no máximo 24 horas, ou até o vencimento comercial
anterior. Esse prazo operacional não é garantia do fornecedor. Expiração,
mudança da oferta ou mais pacotes que os confirmados exigem nova confirmação.
Na retomada, aceite/cálculo/preço antigos podem estar invalidados; não os
apresente como vigentes nem repita decisões humanas automaticamente.
Estoque histórico é alocado primeiro, com seu custo; o complemento usa seu
próprio preço. Encargos aparecem no desembolso e ficam separados do CMV de
ingredientes. Confirmar não compra, congela preço nem baixa estoque físico.
