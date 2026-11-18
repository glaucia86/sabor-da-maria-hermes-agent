# Jornada REAL completa no Hermes Desktop — 19/11/2026

Ensaio no Hermes Desktop com um **perfil REAL novo** e a **planilha original do
desafio** (`doc-specs/despensa_dona_maria.xlsx`), da pesquisa à escolha do
preço. As falas da Dona Maria foram interpretadas por quem conduziu o ensaio,
com dados de demonstração declarados na conversa: quantidades, rendimento,
tempo e condições da cozinha são declarações, não medições físicas.

Cada proposta teve o conteúdo conferido por leitura antes da atestação local
no terminal (`ATESTO <hash>`). O modelo não aprovou nada. A jornada anterior,
que parou na viabilidade, está em [Jornada REAL — 17/11/2026](verification-desktop-real.md).

## Ambiente

| Item | Valor |
| --- | --- |
| Sistema | Windows |
| Host | Hermes Desktop, Hermes 0.23.1, commit `3b4215785882` |
| Modelo | `openai/gpt-6.1-sol`, provedor `nous` |
| Perfil | `sabor-real-…`, criado por `setup-real` e `configure` em pasta nova |
| Planilha | Original: 37 ingredientes, total histórico R$ 663,39, orçamento R$ 80,00 |
| Pesquisa | Exa anônimo; termos liberados: `frango acebolado` e `frango` |
| Verificações prévias | `verify-profile` e `check-research` em PASS, depois de `hermes gateway restart` |

## O que aconteceu

| Etapa | O que o Hermes fez | Resultado |
| --- | --- | --- |
| 1. Pesquisa | A primeira busca retornou `DATA_SOURCE_UNAVAILABLE` duas vezes. O agente mostrou a despensa, não inventou receita e pediu uma fonte. A pedido, tentou de novo | [Frango acebolado, TudoGostoso](https://www.tudogostoso.com.br/receita/1487-frango-acebolado.html), 4 porções. Apontou sobrecoxa × peito e os ingredientes ausentes |
| 2. Receita própria | Propôs `register_recipe_candidate` com origem `USER_PROVIDED` e, no mesmo turno, os fatos da cozinha | Receita aprovada: 5 ingredientes `RAW`, 4 porções, 6 requisitos e as 3 categorias revisadas, sem lacunas |
| 3. Cozinha | A proposta de fatos ficou desatualizada após a receita; a pedido, foi refeita | 6 fatos aprovados, incluindo 60 min por cozinhada para 40 min exigidos |
| 4. Interesse e plano | Propôs o interesse e, sem confirmação da quantidade, também o plano | Interesse aprovado. O plano antecipado não foi atestado; depois de "Confirmo 1 lote, 4 porções", foi refeito e aprovado |
| 5. Compras | Consultou `evaluate_purchase_plan` | `CONFIRMED`: tudo em estoque, desembolso R$ 0,00, saldo R$ 80,00 |
| 6. Aceite | "Aceito este prato conforme este resumo." | Aprovado; viabilidade `ELIGIBLE` e custo `READY` |
| 7. Preço | `calculate_pricing_scenarios` e explicação da conta | Tabela abaixo, com M10, M20 e M30 |
| 8. Escolha | "Escolho o cenário M20." | A primeira proposta expirou (`AUTHORIZATION_EXPIRED`) por demora na aprovação; refeita e aprovada |
| 9. Retomada | "Como ficou meu cardápio?" | Recuperou o prato, R$ 3,46 por porção, sobra e saldo |

## CMV e cenários

| Ingrediente | Conta | Custo no lote |
| --- | --- | ---: |
| Peito de frango | 600 g × R$ 0,014/g | R$ 8,40 |
| Cebola | 200 g × R$ 0,004/g | R$ 0,80 |
| Alho | 10 g × R$ 0,020/g | R$ 0,20 |
| Óleo de soja | 30 ml × R$ 0,009/ml | R$ 0,27 |
| Sal | 6 g × R$ 0,00185/g | R$ 0,0111 |
| **Lote (4 porções)** | | **R$ 9,6811** |

CMV por porção: R$ 9,6811 ÷ 4 = R$ 2,420275. Preço mínimo: R$ 2,420275 ÷ 0,90
= R$ 2,69.

| Cenário | Preço | Taxa de 10% | Sobra após taxa e ingredientes |
| --- | ---: | ---: | ---: |
| M10 | R$ 3,03 | R$ 0,30 | R$ 0,31 |
| **M20 (escolhido)** | **R$ 3,46** | R$ 0,35 | **R$ 0,69** |
| M30 | R$ 4,04 | R$ 0,40 | R$ 1,22 |

A sobra não é lucro líquido: embalagem, gás/energia, trabalho e entrega não
foram informados.

## Conferência no banco (leitura, após a sessão)

- `context_mode: REAL`, sem dependência de simulação.
- Receita versão 1 com 5 ingredientes; 6 fatos da cozinha; aceite `VALID`.
- Cálculo `VALID`: CMV R$ 2,420275, mínimo R$ 2,69, cenários R$ 3,03, R$ 3,46 e R$ 4,04.
- Cardápio: M20, R$ 3,46, `VALID`.
- 6 aprovações locais (`LOCAL_APPROVAL`) e 3 propostas superadas ou expiradas, sem efeito.
- 1 observação de pesquisa registrada.

## Observações

| Observação | Efeito | Encaminhamento |
| --- | --- | --- |
| O gateway compartilhado do Hermes subiu antes do perfil novo | `verify-profile` recusou com "Plugins não registrados no gateway" | `hermes gateway restart` após `configure`; registrado no [guia](setup.md#problemas) |
| Com o termo `frango`, o primeiro resultado é uma lista de receitas acima do limite de extração | Pesquisa indisponível | Liberar um termo de prato, como `frango acebolado` |
| O Exa anônimo oscilou | Uma falha antes do sucesso | Pedir nova tentativa; sem fallback para busca livre |
| Duas propostas no mesmo turno | Só a primeira aprovada vale; a outra fica desatualizada | Aprovar uma e pedir que o agente refaça a outra |
| Plano proposto antes da confirmação da quantidade | A atestação local impediu a aplicação | Reforçar na skill: confirmar antes de propor |
| Aprovação expirada termina com "use outra pasta nova" | Mensagem enganosa; a pasta estava íntegra | Mensagem específica para `AUTHORIZATION_EXPIRED` |

## Ensaio pelo Hermes CLI (19/11)

Antes da sessão no Desktop, a mesma jornada foi executada pelo Hermes CLI, em
outra pasta REAL criada por `setup-real` e `configure`, com o mesmo modelo, a
mesma skill e as mesmas tools. Cada fala foi enviada por
`onboarding chat --query "…"` e as seguintes por `--resume <session_id>`, na
mesma sessão. A atestação foi delegada por quem conduziu o ensaio; cada proposta
foi conferida por leitura antes do `ATESTO <hash>`.

| Etapa | Resultado |
| --- | --- |
| Pesquisa | `receita frango acebolado` → TudoGostoso, extraída na primeira tentativa |
| Receita | **Recusada** na primeira proposta: a fala só dizia "cru" para o frango, e o agente deixou corretamente a base de cebola, alho, óleo e sal como `UNKNOWN`, sem revisão de categorias. Com o complemento ("todas as quantidades são cruas" e as três categorias), a nova proposta foi aprovada |
| Fatos e interesse | Propostos no mesmo turno; o interesse ficou desatualizado (`STALE_REVISION`) e foi refeito e aprovado |
| Plano, aceite e preço | Aprovados; compras `CONFIRMED`, R$ 0,00 e saldo R$ 80,00 |
| Cálculo | CMV R$ 2,420275, mínimo R$ 2,69, cenários R$ 3,03, R$ 3,46 e R$ 4,04 |
| Escolha | O CLI não exibiu os códigos dos cenários; a fala "Escolho o preço de R$ 3,46" gerou a proposta `M20`, aprovada |

Foram 6 aprovações, 1 recusa e 1 proposta desatualizada sem efeito. A retomada
("Como ficou meu cardápio?") devolveu o prato a R$ 3,46 por porção. O ensaio
motivou o roteiro do Desktop: dizer na fala da receita que todas as quantidades
são cruas e já descrever as três categorias.

## Limites

- Falas de demonstração, sem cozinheira real nem medição física independente.
- Uma sessão, um modelo, um sistema operacional.
- Receita sem água; receitas com água incorporada continuam exigindo identidade
  e custo sustentados.
- Banco, perfil e transcrição permanecem em `artifacts/private/` e no diretório
  do Hermes, fora do Git.
