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

**Fala:** “Olá, Lucas e Hildebrando! Obrigada pelo tempo de vocês. Este é o Sabor da Maria, que desenvolvi para o desafio de Senior AI Engineer. Primeiro vou mostrar o problema e as decisões de engenharia. Depois, a arquitetura e a jornada do agente. Em seguida, teremos dez minutos para a demonstração ao vivo e, no final, comento as melhorias e os próximos passos.”

## 2 — O que é o desafio? · 75 s

**Fala:** “A Dona Maria está abrindo seu primeiro delivery. Ela tem uma planilha com 37 ingredientes: uma aba informa o estoque; a outra, os preços que pagou. O desafio traz duas restrições financeiras: oitenta reais para comprar complementos e uma taxa de dez por cento sobre a venda. A missão do Hermes customizado é ajudar em quatro momentos: pesquisar receitas reais e ouvir a opinião dela; descobrir se tem equipamentos, técnicas e condições para cozinhar; avaliar o que falta dentro do orçamento; e calcular o custo do prato e cenários de preço. O ponto mais importante é o segundo: gostar de uma receita não significa conseguir prepará-la.”

## 3 — Qual problema resolve? · 75 s

**Fala:** “O problema se resume a três perguntas: o que ela consegue cozinhar, se tem condições reais de produzir e quanto pode cobrar sem perder dinheiro. O risco não é abstrato. O agente pode recomendar um prato que exige forno quando ela não tem forno, tratar os oitenta reais como orçamento para cada receita ou calcular a taxa sobre o custo, em vez da venda. E existe o risco específico do modelo: errar uma conta ou interpretar um simples “parece bom” como aceite definitivo. Por isso, não bastava criar um recomendador de receitas. Eu precisava construir um fluxo em que essas decisões fossem verificadas antes de virar compromisso para o negócio.”

## 4 — Solução escolhida · 75 s

**Fala:** “A solução parte de uma separação de responsabilidades. O Hermes cuida da conversa: pesquisa, pergunta sobre a cozinha e explica as alternativas para a Dona Maria. Mas o modelo não é a autoridade sobre o negócio. Ele usa ferramentas MCP para consultar um serviço Python, que verifica viabilidade, orçamento e precificação com regras testáveis. O SQLite persiste os fatos e as decisões, então uma nova sessão não depende da memória automática do agente. E a Dona Maria continua decidindo. Quando ela manifesta uma escolha, o Hermes registra uma proposta; uma pessoa operadora revisa e atesta essa manifestação num terminal separado. Em resumo: o modelo conversa, o código valida e a decisão é humana.”

## 5 — Por que essa solução? · 90 s

**Fala:** “Para chegar a essa solução, comparei caminhos mais simples com seus riscos. Deixar o LLM fazer as contas pelo prompt seria rápido, mas uma regra esquecida poderia gerar prejuízo. Por isso, os cálculos e as validações estão em Python, com testes. Também desativei a memória automática do Hermes para o estado de negócio ficar no SQLite. Nos valores financeiros, usei Decimal e arredondamento para cima, em centavos, para não ficar abaixo do preço mínimo. Outra escolha foi separar proposta de aprovação: o modelo não pode confirmar sozinho o que a Dona Maria decidiu. Na web, a pesquisa usa termos previamente liberados, reduzindo exposição de dados e riscos de conteúdo malicioso. Por fim, optei por MCP local e SQLite. Não havia motivo para introduzir infraestrutura distribuída neste desafio; os limites dessa escolha entram nos próximos passos.”

## 6 — Arquitetura · 90 s

**Fala:** “Este desenho mostra como distribuí essas responsabilidades. À esquerda, a Dona Maria conversa com o Hermes. O arquivo de contexto e a skill orientam o atendimento; o plugin de política limita as ferramentas que ele pode chamar. A pesquisa na web acontece por um plugin separado, com termos autorizados. Para consultar estoque, avaliar receitas ou calcular preços, o Hermes chama seis ferramentas de atendimento por MCP via stdio. O MCP é a interface do mesmo serviço Python local, onde Pydantic valida os dados e Decimal apoia os cálculos. O SQLite guarda estado e histórico. Na parte inferior está outro caminho: o operador humano importa a planilha pelo setup-real e revisa propostas pela CLI, fora do alcance do modelo. A seta vermelha tracejada representa uma manifestação feita na conversa, não uma conexão técnica direta com o operador. Assim, conversa, validação, persistência e atestação ficam separadas.”

**Aponte:** a caixa do serviço local e a seta tracejada, que representa o fluxo lógico, não uma chamada entre pessoas.

## 7 — Fluxo 1 · Despensa → candidatas · 60 s

**Fala:** “Agora, olhando a jornada, tudo começa com a planilha. O operador a importa, e o sistema cruza duas informações diferentes: o estoque determina a quantidade disponível; a quantidade comprada e o preço pago determinam o custo unitário. Se um preço ou uma conversão estiver ausente, o sistema registra a pendência, não inventa zero. O snapshot fica no SQLite. Durante a conversa, o Hermes consulta esses dados e pesquisa receitas com os termos públicos liberados. Ele recupera o conteúdo a partir do identificador do resultado e mantém a referência da fonte. A Dona Maria também pode sugerir uma receita própria. Nesse momento, o agente apresenta candidatas e pede opinião. Interesse ainda não é aceite: é o começo da avaliação de viabilidade.”

## 8 — Fluxo 2 · Elicitação e viabilidade · 75 s

**Fala:** “Este é o coração do desafio: descobrir o que a Dona Maria realmente consegue preparar, antes de recomendar uma compra ou aceitar um prato. Cada receita tem requisitos de equipamentos, técnica, tempo, energia, armazenamento e ingredientes. O serviço compara esses requisitos com os fatos confirmados. Se algo é desconhecido, o agente precisa perguntar. Se existe um impedimento, o plano tem que mudar. Por exemplo, ela pode dizer que tem forno, mas apenas uma assadeira. Essa informação vira proposta, passa pela revisão local e depois a viabilidade é reavaliada. Em seguida, o planejamento soma os ingredientes que faltam para todos os pratos, incluindo pacotes inteiros e frete. Os oitenta reais são um orçamento compartilhado, não um limite por receita. Só quando as pendências são resolvidas o prato pode seguir para o aceite.”

**Aponte:** desconhecido → pergunta; impeditivo → bloqueio.

## 9 — Fluxo 3 · Proposta e aprovação · 75 s

**Fala:** “Aqui está o mecanismo que impede o agente de aprovar as próprias decisões. Quando a Dona Maria manifesta uma escolha, o Hermes chama propose_user_change. O serviço grava uma proposta pendente, com resumo e hash. Isso ainda não altera a decisão de negócio. Num terminal separado, o operador humano consulta a proposta, verifica o conteúdo e atesta apenas se corresponde ao que ela disse. Ele não escolhe no lugar dela. Antes de aplicar, o serviço revalida o prazo de dez minutos, a revisão do estado e as regras do negócio. Se houver divergência, recusa a operação. Se estiver tudo certo, o efeito e a auditoria são gravados na mesma transação. Essa separação vale para fatos da cozinha, receitas, cotações, aceite e escolha do preço.”

**Destaque:** o operador atesta a manifestação da Dona Maria; não decide por ela.

## 10 — Fluxo 4 · CMV e preço · 75 s

**Fala:** “Depois do aceite válido, chegamos à precificação. O serviço calcula o CMV por porção a partir das quantidades consumidas e do custo unitário de cada ingrediente. Uma distinção importante: comprar um pacote inteiro entra no orçamento de compras, mas o custo do prato considera só a parte utilizada. Como a plataforma retém dez por cento da venda, o preço mínimo é o CMV dividido por zero vírgula noventa. Por exemplo, se o CMV é dez reais, o piso arredondado para cima é onze reais e doze centavos. O sistema também apresenta cenários de margem de dez, vinte e trinta por cento. Eu chamo o resultado de sobra após ingredientes e taxa, não lucro líquido, porque ainda faltam custos como embalagem, energia e trabalho. A Dona Maria escolhe; a confirmação passa pela mesma aprovação local.”

## 11 — Demonstração · 30 s

**Fala:** “Agora vamos à demonstração. Vou usar o Hermes Desktop para conversar com a Dona Maria e um terminal separado para revisar as decisões. A ideia é percorrer a despensa, a pesquisa de receitas, as perguntas sobre viabilidade, o orçamento e a precificação. Se faltar alguma informação, espero que o sistema pergunte ou bloqueie, em vez de inventar uma resposta.”

**Tempo:** a demonstração tem até dez minutos, separados dos quinze da apresentação.

## 12 — O que pode virar melhoria? · 60 s

**Fala:** “Depois da jornada, ficam claras algumas oportunidades de melhoria. A pesquisa hoje é restrita a termos liberados e um resultado por busca; eu ampliaria as candidatas sem abrir mão dos controles. A aprovação por terminal é verificável, mas poderia virar uma experiência mais fluida na interface, ainda fora do alcance do modelo. Também acrescentaria embalagem, energia e mão de obra para estimar lucro de forma mais completa. Na qualidade do agente, a matriz S19 reúne dezoito casos integrados no recorte assistido por CLI. Eles não equivalem a uma comparação controlada entre modelos nem homologam o Desktop. O próximo passo é repetir avaliações por modelo, medindo qualidade, latência e custo. E eu evoluiria a compreensão de preferências semânticas, sempre com confirmação.”

## 13 — Próximos passos · 45 s

**Fala:** “Para transformar o protótipo em produto, eu priorizaria cinco etapas. Primeiro, identidade e autorização: hoje a atestação é local e não autentica fortemente a cozinheira. Depois, suporte a vários restaurantes, com isolamento dos dados e um serviço remoto — o que também justificaria reavaliar o SQLite. Na sequência, observabilidade da jornada, das ferramentas e dos custos de modelo; execução dos evals conversacionais com Hermes no CI; e, por último, integração com a operação de delivery para publicar o cardápio aprovado. O ponto é evoluir a infraestrutura quando houver necessidade, sem perder as garantias que já estão no domínio.”

## 14 — Agradecimentos · 30 s

**Fala:** “Obrigada, Lucas e Hildebrando. O código e a documentação estão no repositório, incluindo o passo a passo para executar localmente. Deixei material de apoio sobre segurança, persistência, testes e trade-offs para aprofundarmos nas perguntas. Fico à disposição.”

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
