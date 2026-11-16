# Sabor da Maria — guia para a conversa com Lucas Rolim & Hildebrando Azevedo

**Glaucia Lemos · ~15 minutos de apresentação + demonstração ao vivo.**
Compartilhe o deck e deixe este guia, o Hermes Desktop e o terminal do operador
na outra tela. A fala de cada slide também está nas notas (tecla **S**). Ela é
um apoio para explicar como o sistema funciona, não um texto para ler.

## Ritmo

| Slide | Janela | Tempo | Ênfase |
|---|---|---|---|
| 1 · Capa | 00:00–00:30 | 30 s | Roteiro da conversa |
| 2 · O que é o desafio? | 00:30–01:45 | 75 s | Planilha, R$ 80, 10% e os 4 pedidos |
| 3 · Qual problema resolve? | 01:45–03:00 | 75 s | Erro aqui vira prejuízo |
| 4 · Solução escolhida | 03:00–04:15 | 75 s | LLM conversa, código valida, ela decide |
| 5 · Por que essa solução? | 04:15–05:45 | 90 s | Caminho óbvio × risco × escolha |
| 6 · Arquitetura | 05:45–07:15 | 90 s | Componentes e canal do operador |
| 7 · Fluxo 1 | 07:15–08:15 | 60 s | Planilha → pesquisa → candidatas |
| 8 · Fluxo 2 | 08:15–09:30 | 75 s | Pergunta antes do aceite; R$ 80 agregado |
| 9 · Fluxo 3 | 09:30–10:45 | 75 s | Proposta, atestação e revalidação |
| 10 · Fluxo 4 | 10:45–12:00 | 75 s | CMV, piso e cenários |
| 11 · Demonstração | 12:00–12:30 | 30 s | Passagem para o Desktop |
| 12 · Melhorias | após a demo | 60 s | Evolução do que existe |
| 13 · Próximos passos | — | 45 s | Rumo a produção |
| 14 · Agradecimentos | — | 30 s | Perguntas |
| A1–A5 · Apêndice | sob demanda | — | Invariantes, persistência, segurança, verificação, trade-offs |

Se o tempo apertar, encurte os slides 5 e 7. Nunca corte os fluxos 2 e 3: eles
respondem ao “coração do desafio” e mostram que o modelo não aprova a si mesmo.

## 1 — Capa · 30 s

**Fala:** “Olá, Lucas e Hildebrando! Obrigada pelo tempo de vocês. Hoje vou apresentar o Sabor da Maria, a solução que desenvolvi para o desafio de Senior AI Engineer.

Vou começar pelo desafio e pelo problema que identifiquei. Depois, explico as principais decisões, a arquitetura e o fluxo da solução. Em seguida, mostro a aplicação funcionando e encerro com as limitações e os próximos passos.”

## 2 — O que é o desafio? · 75 s

**Fala:** “A Dona Maria abre o primeiro delivery. A planilha
`despensa_dona_maria.xlsx` tem duas abas: Despensa, com o estoque, e Precos, com
quanto ela pagou — 37 ingredientes. Ela tem R$ 80 para complementos e a plataforma
cobra 10% sobre a venda. O agente precisa ser o Hermes customizado e fazer quatro
coisas: pesquisar receitas reais, descobrir restrições — que o enunciado chama de
coração do desafio —, comparar com a despensa e o orçamento, e calcular CMV e
preço deixando a decisão com ela.”

**Aponte:** o card 2.2 destacado.

## 3 — Qual problema resolve? · 75 s

**Fala:** “São três perguntas: o que consigo produzir, se tenho condição de
produzir e quanto cobrar. O erro custa dinheiro: comprar e não ter forno, somar
R$ 80 por prato, aplicar a taxa sobre o custo. E há o risco específico de IA:
errar a conta, esquecer um fato ou tratar ‘parece bom’ como aceite. O problema não
é só recomendar; é recomendar de um jeito em que esses erros não passem.”

## 4 — Solução escolhida · 75 s

**Fala:** “Separei três papéis. O Hermes conversa, com context file, skill e dois
plugins — política e pesquisa. O que precisa ser verdade passa pelo Python via
MCP stdio, com seis tools: viabilidade, orçamento e preço com Decimal. O estado
fica no SQLite, então retomar não depende da memória do modelo. E toda decisão
vira proposta, aprovada num terminal que o modelo não enxerga.”

**Frase-chave:** “Regra no código, não no prompt: um teste prova a regra sem LLM.”

## 5 — Por que essa solução? · 90 s

**Fala:** percorra a tabela da esquerda para a direita, uma linha por vez:
caminho óbvio, risco e o que foi feito. Feche com: “Não coloquei infraestrutura
distribuída porque o problema é local; o custo dessa escolha está nos próximos passos.”

**Corte:** se o tempo apertar, comente só as linhas de memória, aprovação e busca.

## 6 — Arquitetura · 90 s

**Fala:** “Da esquerda para a direita: a Dona Maria conversa com o Hermes. Dentro
dele, context file e skill definem o papel; o plugin de política mantém uma lista
fechada de tools e usa hooks para recusar o resto; o plugin de pesquisa é o único
caminho para a web. Para negócio, o Hermes chama o MCP; banco e workspace são
fixados pelo operador. O domínio valida com Pydantic, calcula com Decimal e grava
no SQLite com auditoria. Embaixo, o canal do operador: o `setup-real` importa a
planilha e a CLI de aprovação lista, inspeciona e atesta o que ela decidiu.”

**Aponte:** a seta tracejada “manifesta a decisão” — é a ponte humana.

## 7 — Fluxo 1 · Despensa → candidatas · 60 s

**Fala:** “O operador importa a planilha. Estoque diz o que está disponível;
quantidade comprada e preço pago dizem o custo unitário. Ausente não vira zero.
Na conversa, o Hermes consulta o inventário e pesquisa com termos liberados —
não monta consulta livre —, depois extrai a página pelo ID do resultado, guardando
URL, horário e hash. Ela também pode trazer receita própria. Gostar ainda não é
aceite: é a entrada do próximo fluxo.”

## 8 — Fluxo 2 · Elicitação e viabilidade · 75 s

**Fala:** “Cada requisito — equipamento, técnica, operação, ingredientes — é
comparado com fatos confirmados. Confirmado segue; desconhecido vira pergunta;
impeditivo exige rever o plano. A resposta dela não vai direto para o banco: vira
proposta e passa pela aprovação. Depois, `evaluate_recipe_feasibility` diz se é
elegível, e `evaluate_purchase_plan` soma o que falta em todos os pratos, conta o
pacote inteiro e o frete, e só usa ofertas confirmadas, válidas por até 24 horas.
Acima de R$ 80 é OVER_BUDGET.”

## 9 — Fluxo 3 · Proposta e aprovação · 75 s

**Fala:** “Vale para fatos, receitas, cotações, aceite e preço. O Hermes chama
`propose_user_change`: a proposta fica pendente, com resumo, hash e dez minutos de
prazo; o negócio não muda. No terminal, o operador inspeciona o conteúdo exato e
atesta. Isso não é uma tool do modelo. A aplicação revalida revisão, prazo e
regras; se tudo bate, efeito e auditoria entram na mesma transação; senão, nada é
aplicado pela metade. Repetir a operação devolve o resultado já gravado.”

## 10 — Fluxo 4 · CMV e preço · 75 s

**Fala:** “Só depois do aceite. O CMV por porção é a soma da quantidade usada vezes
o custo da origem, dividido pelo rendimento. O pacote pesa no orçamento inteiro,
mas o CMV usa só o que a receita consome. Piso é CMV ÷ 0,90; para margem m, CMV ÷
(0,90 − m). Com CMV de R$ 10, o piso é R$ 11,12 — R$ 11,11 ficaria abaixo do custo,
por isso arredondo para cima. O enunciado chama a sobra de lucro; eu explico como
sobra após ingredientes e taxa. Ela escolhe um cenário ou preço próprio acima do
piso, com a mesma aprovação.”

## 11 — Demonstração · 30 s

**Fala:** “Agora a aplicação: Hermes Desktop para conversar, terminal para
aprovar, planilha original. Se faltar um dado, o comportamento correto é perguntar
ou bloquear, e vou mostrar isso também.” Siga o [roteiro da demo](demo-hermes.md).

## 12 — O que pode virar melhoria? · 60 s

**Fala:** “Pesquisa com termos derivados da despensa e mais candidatas; aprovação
na própria interface, ainda fora do modelo; lucro real com embalagem, gás e
trabalho; os mesmos 18 evals integrados em outros modelos; e preferências semânticas com
confirmação.”

## 13 — Próximos passos · 45 s

**Fala:** “Identidade da cozinheira e do operador; serviço MCP remoto com Postgres
e isolamento por restaurante; observabilidade de tools, jornadas e custo de LLM;
host Hermes e evals no CI; e integração com a plataforma de delivery.”

## 14 — Agradecimentos · 30 s

**Fala:** “Obrigada. O repositório está público, com README e guia de instalação.
Tenho apêndices sobre invariantes, persistência, segurança, verificação e
trade-offs, se quiserem aprofundar.”

## Apêndice · sob demanda

Use **Esc** para a visão geral e pule direto para o slide da pergunta:
A1 Invariantes, A2 Persistência, A3 Segurança, A4 Verificação, A5 Trade-offs.

## Perguntas difíceis — respostas ancoradas no código

| Pergunta | Resposta técnica e evidência |
|---|---|
| O hash impede um modelo malicioso? | Não sozinho. O modelo não recebe approve; a CLI exige atestação e o serviço revalida hash, revisão, prazo e guards. [approvals.py](../../src/dona_maria/approvals.py), [approval_cli.py](../../src/dona_maria/approval_cli.py). |
| E duas aprovações concorrentes? | A transação e a operação persistida evitam duplicar efeitos; concorrência/replay têm testes próprios. Não é uma garantia de exactly-once para sistemas externos. [test_local_approval.py](../../tests/unit/test_local_approval.py). |
| Pydantic impede prompt injection? | Não. Rejeita estrutura indevida. Allowlist, binding, pesquisa restrita e aprovação local limitam os efeitos. [mcp_server.py](../../src/dona_maria/mcp_server.py), [hermes_policy](../../src/dona_maria/hermes_policy/__init__.py). |
| E se o modelo inventar um ID de fonte? | O backend busca o resultado e segmento vinculados; dados fabricados não materializam uma fonte válida. [research.py](../../src/dona_maria/research.py). |
| A busca não pode vazar dados? | Só aceita IDs de termos públicos liberados. A extração controla destinos. O provider ainda tem comportamento próprio, documentado como limite. [research_network.py](../../src/dona_maria/research_network.py). |
| Por que não LangGraph/Pydantic AI? | A orquestração já pertence ao Hermes; adicionar outro orquestrador não resolve um requisito deste recorte. O projeto usa Pydantic para contratos, não Pydantic AI. |
| Como tratar preço faltante com alimento em estoque? | Disponibilidade e custo são independentes; readiness financeiro bloqueia a decisão definitiva. [cost_readiness.py](../../src/dona_maria/cost_readiness.py). |
| Uma nova sessão esquece as restrições? | A abertura consulta o mesmo workspace; revisão e decisões vêm do SQLite. Memória do LLM não é autoridade. [business_state.py](../../src/dona_maria/business_state.py). |
| Como escalar para multiusuário? | Seria outra fronteira: autenticação, autorização por recurso, armazenamento concorrente, observabilidade e gestão de segredos. Não alegar que trocar SQLite por PostgreSQL resolve tudo. |
| Qual modelo teve melhor resultado? | Não há comparação controlada suficiente para declarar vencedor. Registre modelo/provider/versão e assistência de cada execução; não derive ranking de uma demo. |
| Por que não mostrar tudo do zero em dez minutos? | A jornada exige várias manifestações e atestações. O roteiro prepara fatos no ensaio humano e mostra uma decisão nova ao vivo; sem preparo, o resultado correto é uma demo parcial explicitamente rotulada. |
| O que ainda não está homologado? | A jornada completa no Desktop com a planilha original e o perfil final precisa do ensaio humano; CI não instala o Hermes nem um modelo. |
