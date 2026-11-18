# Jornada REAL no Hermes Desktop — 17/11/2026

Ensaio conversacional no Hermes Desktop com o **perfil REAL** e a **planilha
original do desafio** (`doc-specs/despensa_dona_maria.xlsx`). A jornada foi
da despensa até a avaliação de viabilidade e parou, por decisão do domínio,
antes do aceite e da precificação: faltavam dados que ninguém havia medido e
que não seriam inventados.

A jornada REAL completa até o preço, de 19/11/2026, está em
[verification-desktop-real-complete.md](verification-desktop-real-complete.md).

O registro separa o que a avaliadora relatou do que foi **conferido no banco
por leitura** (`mode=ro`, sem propostas nem aprovações), depois da sessão.
Preço e cardápio finalizados existem somente no [ensaio
`SIMULATION`](verification-desktop-e2e.md); os dois resultados não se misturam.

## Ambiente

| Item | Valor |
| --- | --- |
| Sistema | Windows |
| Host | Hermes Desktop, Hermes 0.23.1, commit `3b421578588243f920886e6fe79a6faa87ea026e` |
| Modelo | `openai/gpt-6.1-sol`, provedor `nous`, escolhido no seletor do Hermes |
| Perfil | `sabor-real-…`, criado por `onboarding configure`; seis tools MCP + duas de pesquisa |
| Planilha | Original: 37 ingredientes, total histórico R$ 663,39, orçamento de complementos R$ 80,00 |
| Pesquisa | Exa anônimo; cinco termos liberados: arroz, feijão, frango, batata, macarrão |
| Verificações prévias | `check`, `verify-profile` e `check-research` em PASS |
| Sessões | Uma conversa longa e uma segunda conversa nova sobre o mesmo banco |

## O que aconteceu

| Etapa | O que o Hermes fez | Resultado persistido |
| --- | --- | --- |
| 1. Despensa | Consultou estado e despensa | 37 ingredientes com custo unitário; nenhuma proposta |
| 2. Pesquisa | Buscou e extraiu fontes pela pesquisa mediada | 8 buscas registradas, 1 resultado por busca, 6 extrações completas. Escolhida a [Receita de Arroz com Frango, Receitas Nestlé](https://www.receitasnestle.com.br/receitas/receita-arroz-frango): 4 porções e 30 min publicados |
| 3. Receita original | Propôs `register_recipe_candidate` com fonte WEB | Receita 1, versão 1, proveniência WEB por campo; sem aceite |
| 4. Cozinha | Propôs `record_kitchen_facts` | 17 fatos: fogão a gás de 4 bocas, panela de 5 L com tampa, frigideira, utensílios, água potável, habilidades declaradas, janela de 60 min, **sem forno** |
| 5. Adaptação | Propôs a versão da Maria (sem o tempero industrializado) e, depois, a revisão das categorias | Receita 2, derivada da 1, versão 2. A receita WEB continua intacta |
| 6. Plano | Calculou 1 lote, 4 porções e 0 excedentes; propôs `set_production_plan` após confirmação explícita | Plano de 1 lote e 4 porções, vinculado à receita 2 |
| 7. Viabilidade | Chamou `evaluate_recipe_feasibility` | **`PENDING`**. O agente pediu, uma pergunta por vez: tempo efetivo do lote, base cru/cozido, capacidade útil da panela e peso final da porção |

A adaptação usa 400 g de frango, 300 g de arroz, 600 ml de água, 80 g de
cebola, 10 g de alho, 20 ml de óleo, 6 g de sal, 2 g de cúrcuma e 5 g de
salsinha para 4 porções. Oito desses nove ingredientes foram associados a
itens da planilha original, com o custo unitário derivado das duas abas. A
água não existe na planilha.

Os 30 minutos publicados pela fonte **não** foram tratados como tempo medido
na cozinha. Os fatos da cozinha são declarações feitas no ensaio, atestadas
localmente; não são medições físicas independentes.

## Decisões humanas

| Proposta | Origem | Situação |
| --- | --- | --- |
| Receita original (`register_recipe_candidate`) | Hermes | Aprovada no terminal |
| Fatos da cozinha (`record_kitchen_facts`) | Hermes | Aprovada |
| Adaptação (`register_recipe_candidate`) | Hermes | Aprovada |
| Revisão das categorias (`register_recipe_candidate`) | Hermes | Aprovada |
| Plano de produção (`set_production_plan`) | Hermes | Aprovada |
| Base cru/cozido (`register_recipe_candidate`) | Hermes | Não aprovada; expirou após dez minutos |

As cinco aprovações foram feitas com `review list`, `inspect` e `approve` e a
atestação `ATESTO <hash>`, fora do catálogo do modelo. O agente não aprovou
nada. Uma tentativa de revisão foi recusada pelo domínio sem alterar o estado
e foi corrigida na conversa.

## Retomada em conversa nova

Em uma conversa nova, no mesmo perfil e banco, o Hermes recuperou equipamentos,
habilidades, as receitas 1 e 2, o plano, as pendências de viabilidade e a
ausência de aceite e de preço, sem depender do histórico anterior. Ele também
informou que não conseguia confirmar o saldo disponível. Esse comportamento é
correto: `remaining_budget` fica `null` enquanto o plano não tem demanda
completa, porque um valor ausente não vira R$ 80,00 nem zero.

## Conferência no banco (leitura, após a sessão)

- `context_mode: REAL`, 37 itens, sem dependência de simulação.
- Receita 1 `DISCOVERED`; receita 2 `FEASIBILITY_PENDING`, interesse `UNDECIDED`.
- Plano com 1 lote e 4 porções; 17 fatos da cozinha; menu vazio.
- Propostas: 5 `APPLIED_HISTORICAL` e 1 `EXPIRED`.
- `evaluate_recipe_feasibility`: `PENDING`. `evaluate_purchase_plan`: `PENDING`,
  desembolso e saldo `null`.

## Por que a jornada parou antes do aceite

| Bloqueio | Origem no domínio | Como resolver sem inventar |
| --- | --- | --- |
| Base cru/cozido `UNKNOWN` nas 9 linhas | O plano só soma demanda de linhas `RAW` ([planning.py](../src/dona_maria/planning.py)) | Revisar a receita declarando que as quantidades são de ingredientes crus, se for verdade |
| Água sem identidade e sem custo | A água incorporada compõe o CMV; não está na planilha | Informar a fonte de custo real (conta de água) ou registrar a lacuna |
| Quatro lacunas declaradas na receita | `declared_gaps` mantêm a viabilidade `PENDING` | Medir ou declarar tempo e peso da porção, sempre rotulados como declaração |
| Interesse não registrado | O aceite exige interesse `INTERESTED` | Manifestação explícita da cozinheira |

Com esses dados, a sequência restante é: plano de compras (estoque cobre os
oito ingredientes da planilha), aceite, cálculo dos três cenários e escolha
do preço, cada decisão com proposta e aprovação local.

## Melhoria encontrada e corrigida

Na consulta de compras, a projeção do atendimento usava a mensagem "esclarecer a
medida e a unidade" para os oito ingredientes, quando a causa real era a base
cru/cozido. A pergunta induzia a Dona Maria a responder outra coisa. A
projeção passou a perguntar se a quantidade é do ingrediente cru ou já
preparado, com teste dedicado em
[test_attendance.py](../tests/unit/test_attendance.py). A regra de negócio
não mudou.

## Limites

- A jornada REAL não chegou ao aceite, ao CMV do prato nem à escolha do preço.
- Um modelo, um sistema operacional e uma avaliadora no papel de Dona Maria e
  de operadora.
- As chamadas de ferramenta não foram contabilizadas nesta sessão; a tabela
  acima descreve os efeitos persistidos, não uma contagem de chamadas.
- Banco, perfil, transcrição e diagnósticos permanecem em `artifacts/private/`
  e no diretório do Hermes, fora do Git.
