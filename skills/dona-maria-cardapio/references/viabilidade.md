# Viabilidade e aceite

1. Leia o estado atual. Registre a manifestação de interesse ou recusa por
   `record_recipe_feedback`, sem confundir interesse com aceite. Recusa retira
   o item do plano e permite buscar outra candidata.
2. Reveja `EQUIPMENT`, `SKILL` e `OPERATION` conforme o método. Identifique
   requisitos críticos; categoria sem requisito precisa de justificativa
   fundamentada. Use revisão de `register_recipe_candidate` para completar
   rendimento por lote, unidade vendável, categorias e dados sustentados.
3. Pergunte somente pelos fatos necessários e aguarde. Registre respostas
   por `record_kitchen_facts`: chave/categoria do requisito, booleano para
   disponibilidade/habilidade, decimal textual e unidade para capacidade/tempo,
   ou texto controlado correspondente à condição explícita. Uma substituição
   informa `replaces_fact_id` atual. Nunca envie status `CONFIRMED`.
   Em `EXPLICIT_CONDITION`, confira o `value` esperado no requisito: um texto
   confirmado exige esse mesmo texto controlado, sem trocar por `true`.
   A evidência preserva a fala humana original, separada do valor tipado.
   Reutilize chaves de requisitos já existentes; não crie fatos com chaves
   desconectadas, pois o avaliador pode não associar sinônimos. Preserve uma
   limitação parcial como tal: pouca experiência com massas não equivale a
   `SKILL_KNOWN=false` para toda técnica de massa. Registre em lote os fatos
   independentes; serialize escritas que compartilham a revisão do workspace.
   Ao final, releia fatos, preferências e interesse no estado para verificar
   a persistência e os efeitos antes de resumi-los à cliente.
4. Apresente lotes e porções antes de `set_production_plan`. A lista substitui
   o plano inteiro, incluindo rascunhos. Peça confirmação inequívoca da produção;
   a forma conservadora suportada começa com “Confirmo ...”. Para pedido de
   12 porções com rendimento 5, explique 3 lotes, 15 porções e sobra de 3 e
   aguarde confirmação desses três números. Não altere para 2,4 lotes.
5. Vários lotes/pratos exigem perguntar sobre sequência, recursos compartilhados
   e tempo. O arranjo suportado é sequência explicitamente confirmada: fato
   `OPERATION`, chave `production_arrangement`, valor `SEQUENTIAL`, contexto
   `<id do plano>:<versão>`, com a fala específica da pessoa. Capacidade é
   conferida por lote; mínimos de tempo com mesma chave/unidade são somados
   na sequência. Isso não garante a duração da fonte. Outro arranjo fica
   pendente, sem presumir paralelismo. Mudança de plano exige reconfirmação.
6. Antes de chamar `evaluate_recipe_feasibility`, confira se existe plano e
   `plan_item_id` real da receita na versão atual. Sem esse pré-requisito,
   não invente IDs nem crie um plano apenas para liberar a ferramenta.
   Explique a limitação e faça uma comparação preliminar entre o método
   pesquisado e os fatos confirmados, identificando-a como análise, não como
   status formal retornado pelo MCP. Pergunte primeiro como a meta diária se
   distribui entre pratos e entregas; depois proponha lotes para confirmação.
   Havendo plano confirmado, consulte `evaluate_recipe_feasibility` para cada
   item e `evaluate_purchase_plan` para o conjunto. Desconhecido gera `PENDING` e
   pergunta; impedimento confirmado gera `BLOCKED` e oferta de alternativa ou
   adaptação a validar. Identidade, medida ou base cru/cozido sem suporte não
   demonstram suficiência. Não invente conversões, estoque ou compras.
7. Somente quando todo o plano for elegível e os ingredientes forem suficientes,
   apresente o resumo vigente: pratos, fontes, condições, lotes/porções/sobras,
   demanda/estoque/faltantes, desembolso e saldo. Sem compra necessária, o
   desembolso pode ser zero. Um rascunho inviável precisa sair do plano antes
   do aceite de outro prato. Aguarde a resposta humana ao resumo.
8. Use `accept_recipe` com item, receita, `evaluation_id` atuais e evidência
   literal do aceite. Formas suportadas incluem “Aceito este prato”, “Aceito
   esta receita” e “Sim, aceito”. “Parece bom” exige esclarecimento. Uma frase
   explícita não dispensa os guards. Erro de avaliação antiga exige releitura,
   novo resumo e nova confirmação, sem reutilizar a fala anterior.

Toda escrita usa revisão observada e `operation_id`; replay conserva comando/ID.
`UserEvidence` contém `turn_ref`, `statement` e `captured_at` textual com timezone,
referentes à fala humana exata. Não fabrique referências, horários nem respostas.
O contrato depende da fidelidade do host/modelo; esses campos não autenticam
consentimento. Fonte web nunca confirma fato, produção ou aceite.

## Capacidade e adaptações antes do aceite

Avalie a janela de trabalho pelo processo completo: separação e higiene,
cortes e eventual descongelamento, cocção, montagem, embalagem, conservação
até a entrega e limpeza. Não converta número de bocas em paralelismo garantido
para uma pessoa nem extrapole o tempo publicado para uma escala maior.
Confirme volume útil das panelas, bancada, tamanho das porções e o que entra
na janela de tempo; proponha teste cronometrado sem tratá-lo como já realizado.
Pergunte se a saída será logo após o preparo ou depois de armazenamento, pois
pouca refrigeração muda a operação; ausência de freezer não impede por si só
uma produção para saída imediata, mas não dispensa conservação segura.

Ao propor adaptação, explicite a etapa retirada ou alterada e a consequência
no produto, como perder o gratinado ao retirar o forno. Não apresente o método
adaptado como se fosse o da fonte original. Mantenha rendimento, tempo,
quantidades, utensílios e conservação como pendências até haver suporte e
validação; não substitua ingredientes ou revise a receita silenciosamente.
Siga `correcoes.md` para registrar a versão adaptada quando ela for definida.

Aceite não compra, não debita estoque físico e não escolhe preço. Se faltar
insumo, explique a pendência; cotação e preço dependem de ferramentas próprias.
Após aceite vigente, siga [CMV e escolha de preço](precificacao.md) quando as
ferramentas estiverem disponíveis; caso contrário, explique a limitação e aguarde.
