# Jornada E2E assistida no Hermes Desktop — 17/11/2026

Ensaio conversacional completo no Hermes Desktop, em um workspace `SIMULATION`
separado e com planilha sintética. O registro distingue o que o Hermes executou
na conversa do que exigiu intervenção operacional. **Não homologa o perfil REAL
com a planilha original**, que continua sendo o [percurso oficial do avaliador](../README.md#executar).

## Ambiente

| Item | Valor |
| --- | --- |
| Sistema | Windows |
| Host | Hermes Desktop, Hermes 0.23.1, commit `3b421578588243f920886e6fe79a6faa87ea026e` |
| Modelo | `openai/gpt-6.1-sol`, escolhido no seletor do Hermes |
| Aplicação | Conteúdo equivalente ao commit `9a07573`; as alterações ainda não estavam commitadas durante o ensaio |
| Contexto | Workspace `SIMULATION` novo, perfil exclusivo, contexto `.hermes.md` + skill incorporado à pasta de conversa |
| Planilha | Sintética: arroz, alho, cebola, azeite, sal e água, todos com estoque e preço |
| Pesquisa | Exa anônimo, um termo liberado (`arroz branco simples ingredientes`) |
| Sessão | Uma conversa contínua, das 03:14 às 03:59 (BRT) |

## Resultado persistido

Confirmado por `get_business_state` no mesmo perfil, após a última aprovação:

| Item | Estado |
| --- | --- |
| Receita | Adaptação hipotética da receita web, versão 3, selecionada no cardápio (`MENU_SELECTED`) |
| Fonte | [Receita de arroz branco simples e rápido](https://revistacasaejardim.globo.com/gastronomia/noticia/2024/09/receita-de-arroz-branco-simples-e-rapido.ghtml), extraída na conversa; a receita web original permaneceu intacta |
| Plano | 1 lote, 2 porções de acompanhamento |
| Viabilidade e compras | `ELIGIBLE`; compras `CONFIRMED`, desembolso R$ 0,00, saldo R$ 80,00 |
| Aceite | Aplicado após aprovação local |
| Preço | Cenário M30, R$ 2,03 por porção; CMV R$ 1,218; taxa R$ 0,20; sobra após taxa e ingredientes R$ 0,61 |
| Custos operacionais | Embalagem, gás/energia e trabalho não informados; lucro líquido não calculado |
| Contexto | `SIMULATION`, rótulo hipotético preservado; nenhuma proposta pendente |

## O que o Hermes executou na conversa

| Ferramenta | Chamadas |
| --- | --- |
| `get_business_state` | 26 |
| `get_inventory_snapshot` | 1 |
| `search_culinary_sources` / `extract_culinary_source` | 1 / 1 |
| `propose_user_change` | 14 (12 propostas criadas, 2 recusadas) |
| `evaluate_recipe_feasibility` / `evaluate_purchase_plan` | 2 / 2 |
| `calculate_pricing_scenarios` | 1 |

O Hermes consultou a despensa e pesquisou e extraiu a fonte. Também propôs os fatos
da cozinha, a receita web, a adaptação `USER_SIMULATION`, o plano, o interesse,
o aceite e a escolha do preço. Explicou os três cenários e aguardou a escolha.
Nenhuma ferramenta fora do catálogo foi usada para aprovar ou gravar.

| Propostas | Origem | Resultado |
| --- | --- | --- |
| Fatos da cozinha (3) | Hermes | 2 aplicadas, 1 expirada e substituída |
| Receita web e adaptação (3) | Hermes | 2 aplicadas, 1 expirada e substituída |
| Plano na versão anterior da receita (1) | Hermes | Expirada; não reutilizada após a revisão da receita |
| Rendimento/requisitos e revisão das categorias (2) | **Operação**, pelo mesmo `propose_user_change` | 2 aplicadas |
| Plano, interesse, aceite e preço (5) | Hermes | 4 aplicadas; 1 aceite recusado e expirado |

## Intervenções operacionais

1. **Preparação do perfil.** O workspace foi criado com os passos de `prepare`,
   usando a planilha sintética, e o perfil, com `configure`. O onboarding não
   configura pesquisa em `SIMULATION`. Por isso, plugin, termos e configuração
   de pesquisa equivalentes aos do REAL foram acrescentados manualmente, e os
   plugins desse perfil foram recarregados no gateway.
2. **Aprovações humanas.** As 10 propostas aplicadas foram inspecionadas e
   aprovadas no terminal com `review approve` e `ATESTO <hash>`. O agente não
   aprovou nada.
3. **Revisão da receita.** Duas chamadas do Hermes para atualizar rendimento e
   requisitos da receita foram recusadas com `SOURCE_NOT_LINKED`. Uma fonte
   `WEB` só é herdada no mesmo índice e com o mesmo conteúdo do requisito; as
   chamadas deslocaram três requisitos web e reescreveram seus `reason`. As duas
   propostas corretivas foram preparadas pela operação, fora da conversa, pelo
   mesmo tool MCP e binding, depois de ensaiadas em uma cópia descartável do
   banco. Por decisão humana, as ressalvas das lacunas declaradas foram movidas
   para o contexto operacional.
4. **Aceite.** A primeira aprovação do aceite foi recusada com
   `USER_CONFIRMATION_REQUIRED`, porque o interesse pela receita não havia sido
   registrado. Após orientação na conversa, o Hermes propôs o interesse e um
   novo aceite.
5. **Leitura antes do commit.** Uma consulta do Hermes ocorreu 8 segundos antes
   da gravação da escolha do preço e mostrou a proposta como `PENDING`. A nova
   consulta mostrou o estado correto; não houve cache nem outro banco.

## Limites

- Dados `SIMULATION` e planilha sintética; não comprova a planilha original nem
  o perfil REAL.
- Todos os ingredientes estavam na despensa: o orçamento foi conferido com
  desembolso zero, sem cotação ou compra de complemento.
- Uma receita, um modelo, um termo de pesquisa e uma conversa contínua; a
  retomada em nova sessão não foi exercitada.
- A etapa de revisão da receita exigiu propostas preparadas pela operação.
  Reproduzir este ensaio exige a configuração manual descrita no item 1.

## Observações para os próximos ensaios

- Ao adaptar uma receita, preserve os requisitos `WEB` na mesma posição e com
  o mesmo `reason`, e acrescente os novos depois deles.
- Envie `category_reviews` em uma revisão separada, sem mudar ingredientes,
  método, rendimento, requisitos ou contexto; caso contrário, a aprovação as
  descarta.
- Lacunas em `declared_gaps` mantêm a viabilidade `PENDING`.
- Registre o interesse antes de propor o aceite.
- Volte ao Desktop somente depois de `ok: true` na aprovação.

Banco, perfil, transcrição e diagnósticos permanecem em `artifacts/private/` e
no diretório do Hermes, fora do Git.
