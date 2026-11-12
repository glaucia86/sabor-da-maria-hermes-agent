# CMV, cenários e escolha

Depois de `accept_recipe` confirmado, use `calculate_pricing_scenarios` com
`recipe_id`, `acceptance_id`, revisão observada e um novo `operation_id`.
É uma escrita técnica: registra o cálculo, sem escolher pela pessoa.

Explique primeiro o CMV por porção, o mínimo e as três opções M10/M20/M30
fornecidas pelo MCP. O mínimo não é um dos cenários. Margens de 10/20/30%
são política didática sobre a venda após taxa e ingredientes, não markup
nem regra de repasse da plataforma. Mostre preço, taxa, recebimento,
resultado aproximado e margem efetiva da ferramenta, sem refazer contas.

Se a pessoa quiser detalhes, mostre a memória: produção total, lote médio,
porção vendável, lotes/rendimento e parcelas de ingredientes com quantidade,
unidade, preço de aquisição, denominador e origem. Preserve notas sobre
diferenças de arredondamento. O resultado não é lucro líquido: gás,
embalagem e mão de obra sem dados não estão incluídos.

Aguarde a escolha humana. A forma conservadora aceita “Escolho M20”,
“Escolho o cenário M20” ou “Escolho o preço de R$ 15,00”, também com
“Confirmo”. A evidência deve corresponder exatamente à opção/preço enviado.
Se a fala for ambígua, peça esclarecimento; nunca reescreva a fala original
para passar no guard. Referência e horário da fala precisam ser observáveis.

`captured_at` é o horário da fala humana citada, não o horário do cálculo,
aceite ou leitura da ferramenta. Não reutilize `calculated_at`, `accepted_at`
ou `decided_at` como horário da fala. Se a referência do turno e seu horário
não estiverem disponíveis no host ou fornecidos pela pessoa, pergunte e pause.

Use `save_menu_decision` com receita, aceite e cálculo atuais, exatamente um
de `scenario_id` ou `custom_price`, e a evidência literal. Preço personalizado
é string decimal com ponto e no máximo duas casas. Abaixo do mínimo, explique
a recusa e aguarde outra escolha; não substitua por um cenário automaticamente.

Só diga “registrado” após sucesso confirmado da ferramenta. Falha de cálculo
ou MCP exige informar o problema e aguardar, sem cálculo textual alternativo.
Resultado incerto exige leitura e replay do mesmo comando/ID. Uma mudança
material exige novo resumo, aceite e cálculo; não reutilize a fala antiga.

Na retomada, `get_business_state` fornece cálculos, histórico de escolhas e
`menu` com decisões vigentes. Preserve estoque e orçamento; não importe de
novo. Estado PRICED pede escolha; MENU_SELECTED indica escolha já registrada.
