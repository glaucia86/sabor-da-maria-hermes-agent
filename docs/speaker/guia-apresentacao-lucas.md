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

**Fala:**

> Olá, Lucas e Hildebrando! Obrigada pelo tempo de vocês.

> Hoje vou apresentar o Sabor da Maria, a solução que desenvolvi para o desafio de Senior AI Engineer do iFood.

> Vou começar pelo problema e pelas decisões de engenharia. Depois mostro a arquitetura e os fluxos da solução.

> Em seguida, teremos a demonstração prática. Para encerrar, apresento as limitações, os próximos passos e abro espaço para perguntas.

## 2 — O que é o desafio? · 75 s

**Fala:**

> O desafio apresenta a Dona Maria, que está abrindo seu primeiro delivery.

> Ela fornece uma planilha com duas abas: uma mostra o estoque e a outra registra as compras e os preços pagos. Ao todo, são 37 ingredientes.

> Temos também R$ 80 para comprar complementos e uma taxa de plataforma de 10% sobre o preço de venda.

> O Hermes Agent precisa ajudá-la em quatro etapas.

> Primeiro, pesquisar receitas reais na internet e ouvir a opinião dela.

> Depois, descobrir se ela tem equipamentos, técnicas e condições para preparar o prato. Para mim, esse é o coração do desafio.

> Em seguida, comparar ingredientes, identificar o que falta e verificar o orçamento.

> Por último, após o aceite de um prato, calcular o CMV e apresentar cenários de preço.

> Mas a escolha final continua sendo da Dona Maria.

## 3 — Qual problema resolve? · 75 s

**Fala:**

> Por trás do enunciado existem três perguntas: o que ela consegue produzir, se tem condições reais de preparar e quanto deve cobrar.

> Uma resposta errada pode trazer prejuízo.

> Imagine recomendar uma receita que exige forno quando ela não tem esse equipamento.

> Ou tratar os R$ 80 como orçamento individual de cada prato, em vez de um limite compartilhado.

> Na precificação, aplicar a taxa sobre o custo, e não sobre a venda, também pode gerar um preço abaixo do mínimo.

> Com LLMs há outros riscos: um cálculo errado, um fato esquecido ou até um “parece bom” interpretado como aprovação.

> Por isso, não quis construir apenas um recomendador.

> Separei a conversa do Hermes das regras determinísticas em Python. E mantive a aprovação humana fora do controle do modelo.

## 4 — Solução escolhida · 75 s

**Fala:**

> Aqui está uma das principais decisões de arquitetura: separar o que o modelo pode fazer do que a aplicação precisa garantir.

> O Hermes conduz a conversa com a Dona Maria, pesquisa receitas e faz perguntas sobre a cozinha.

> Para orientar esse atendimento, configurei um arquivo de contexto, uma skill e dois plugins: um para a política de ferramentas e outro para a pesquisa mediada.

> Mas as regras de negócio não ficam no prompt.

> O Hermes acessa, por MCP via stdio, um serviço Python com seis ferramentas de atendimento. É ali que verifico viabilidade, orçamento e precificação.

> Uso Pydantic para validar dados, Decimal nos cálculos financeiros e SQLite para persistir fatos, receitas e decisões.

> Assim, o negócio não depende da memória automática do agente.

> E a Dona Maria continua decidindo. O Hermes propõe, mas um operador humano atesta a manifestação dela por um canal separado.

> Em resumo: o modelo conversa, o Python valida e a decisão é humana.

## 5 — Por que essa solução? · 90 s

**Fala:**

> Para chegar a essa solução, avaliei alguns caminhos e os riscos de cada um.

> O mais simples seria deixar o LLM fazer as contas. Mas uma regra esquecida ou um arredondamento errado pode trazer prejuízo.

> Por isso, coloquei as validações em Python, com testes automatizados.

> Também desliguei a memória automática do Hermes e passei a guardar o estado do negócio no SQLite.

> Nos cálculos financeiros, usei Decimal e arredondamento para cima, em centavos, para não cobrar abaixo do preço mínimo.

> Outra escolha foi separar proposta de aprovação. O agente pode sugerir, mas não confirma a própria decisão.

> Na pesquisa, uso apenas termos públicos autorizados para reduzir riscos de prompt injection e exposição da despensa.

> Por fim, mantive tudo local. Infraestrutura distribuída não era necessária para o escopo do desafio, embora essa escolha tenha limitações.

## 6 — Arquitetura · 90 s

**Fala:**

> Este é o desenho da solução. A ideia principal foi separar bem as responsabilidades.

> A Dona Maria conversa com o Hermes, orientado pelo arquivo de contexto e pela skill.

> Dentro dele, o plugin de política restringe as ferramentas disponíveis. E a pesquisa na web acontece por um plugin separado, com termos autorizados.

> Quando precisa consultar estoque, avaliar receitas ou calcular preços, o Hermes usa seis ferramentas MCP, por stdio.

> O MCP e as regras de negócio fazem parte do mesmo serviço Python local. Nele, Pydantic valida dados e Decimal apoia os cálculos. O SQLite guarda o estado e o histórico.

> Na parte inferior, temos o canal do operador humano, fora do alcance do modelo.

> É por esse canal que a planilha é importada e que as decisões manifestadas pela Dona Maria são revisadas e atestadas.

> A seta tracejada representa o fluxo lógico dessa manifestação, não uma conexão técnica direta entre pessoas.

> Ou seja: o Hermes conversa, o Python valida, o SQLite guarda e a aprovação humana acontece separadamente.

**Aponte:** MCP e domínio são o mesmo serviço Python; a seta tracejada é fluxo lógico.

## 7 — Fluxo 1 · Despensa → candidatas · 60 s

**Fala:**

> Agora vou mostrar como a solução funciona na prática, começando pela despensa da Dona Maria.

> Primeiro, o operador importa a planilha com o comando setup-real.

> O sistema cruza as duas abas para identificar quais ingredientes estão disponíveis, suas quantidades e o custo unitário.

> Se faltar um preço ou uma conversão de medida, ele registra a pendência. Não assume um valor qualquer.

> Essas informações ficam no SQLite.

> A partir daí, o Hermes consulta o inventário e pesquisa receitas reais na internet, usando somente termos autorizados e mantendo a referência das fontes.

> A Dona Maria também pode sugerir uma receita própria.

> Com essas opções, o Hermes pergunta o que ela achou.

> Mas aqui está um detalhe importante: gostar de uma receita ainda não significa conseguir prepará-la.

> E é isso que verificamos no próximo fluxo.

## 8 — Fluxo 2 · Elicitação e viabilidade · 75 s

**Fala:**

> Agora chegamos ao que considero o coração do desafio: descobrir se a Dona Maria realmente consegue preparar uma receita antes de recomendar compras.

> O sistema avalia não apenas os ingredientes, mas também equipamentos, técnicas e condições da cozinha, como tempo, gás e espaço para armazenamento.

> Se alguma informação ainda não foi confirmada, o Hermes precisa perguntar em vez de presumir.

> Por exemplo, ela pode dizer que tem forno, mas apenas uma assadeira.

> Essa informação vira proposta, passa pela atestação humana e então o sistema reavalia a viabilidade.

> Se existir um impedimento, precisamos adaptar o planejamento ou considerar outra receita.

> Depois, o serviço verifica os ingredientes que faltam e calcula as compras, incluindo embalagens inteiras e frete.

> Os R$ 80 são compartilhados entre todos os pratos.

> Só quando a receita é viável e o planejamento cabe no orçamento é que ela pode seguir para a decisão da Dona Maria.

> E é esse processo de aprovação que mostro no próximo slide.

**Aponte:** desconhecido vira pergunta; impeditivo bloqueia o aceite.

## 9 — Fluxo 3 · Proposta e aprovação · 75 s

**Fala:**

> Agora chegamos a uma das decisões mais importantes da arquitetura: impedir que o agente aprove as próprias propostas.

> Isso vale para fatos sobre a cozinha, aceite de receitas e escolha de preços.

> Quando a Dona Maria manifesta uma decisão, o Hermes registra uma proposta pendente. Isso não significa que ela já foi aplicada.

> Nesse momento, entra o operador humano.

> Em uma CLI, num terminal separado, ele verifica se a proposta corresponde ao que a Dona Maria decidiu e atesta essa manifestação. O operador não escolhe por ela.

> A aprovação acontece fora das ferramentas disponíveis para o modelo.

> Antes de aplicar a alteração, o serviço verifica o prazo de dez minutos, a revisão do estado e as regras de negócio.

> Se algo mudou ou não está válido, ele bloqueia a operação.

> Se tudo estiver correto, a decisão e a auditoria são registradas juntas no SQLite.

> Depois, o Hermes pode consultar o estado atualizado e informar o resultado.

> Ou seja: o agente propõe e explica. Quem decide é a Dona Maria.

**Destaque:** a Dona Maria decide; o operador atesta, sem substituí-la.

## 10 — Fluxo 4 · CMV e preço · 75 s

**Fala:**

> Depois que a Dona Maria aceita um prato, chegamos à precificação.

> Primeiro, o serviço calcula o CMV, que significa Custo da Mercadoria Vendida. Aqui, consideramos o custo dos ingredientes usados em cada porção.

> Existe uma diferença importante.

> Se ela compra um pacote inteiro, o valor total entra no orçamento de compras. Mas o CMV considera apenas a quantidade consumida no prato.

> Também precisamos considerar a taxa de 10% cobrada sobre o preço de venda.

> Por exemplo, com CMV de R$ 10, o piso é R$ 11,12, arredondado para cima.

> Nesse preço, a sobra depois da taxa e dos ingredientes é de aproximadamente um centavo. Não é R$ 1,12 de lucro.

> A partir daí, o sistema mostra três cenários, com margens de 10%, 20% e 30%.

> Esses valores ainda não representam lucro líquido: faltam despesas como embalagem, gás e mão de obra.

> A Dona Maria escolhe um cenário ou outro preço acima do piso. E essa decisão passa pela aprovação humana.

## 11 — Demonstração · 30 s

**Fala:**

> Agora vou mostrar a solução funcionando no Hermes Desktop, usando os dados da planilha original.

> As decisões são atestadas por um operador humano, numa CLI em terminal separado.

> Essa interface foi uma escolha para o protótipo. Em produção, eu a substituiria por uma experiência mais amigável, mantendo a aprovação fora do alcance do modelo.

> Vamos acompanhar a jornada: consulta à despensa, pesquisa de receitas, perguntas sobre a cozinha, orçamento, aceite e precificação.

**Tempo:** a demonstração tem até dez minutos, separados da apresentação.

## 12 — O que pode virar melhoria? · 60 s

**Fala:**

> Depois de implementar essa jornada, identifiquei algumas oportunidades de evolução.

> Na pesquisa, hoje trabalhamos com termos autorizados e uma candidata por busca. Eu ampliaria para duas ou três opções, mantendo os controles.

> A aprovação também poderia sair do terminal e ganhar uma interface mais amigável, sem dar ao modelo permissão para aprovar.

> Na precificação, incluiria embalagem, gás, energia e mão de obra para estimar o resultado do negócio com mais precisão.

> Na avaliação do agente, já existe uma matriz com 18 casos integrados em execução assistida por CLI.

> Mas isso ainda não é uma comparação controlada entre modelos, nem uma homologação do Desktop.

> O próximo passo seria executar evals por modelo, comparando qualidade, latência e custo.

> Também evoluiria a interpretação de preferências. Se a Dona Maria disser que evita fritura, o agente poderia relacionar isso a pratos empanados e confirmar a preferência.

> São melhorias para transformar o protótipo em uma experiência mais útil e simples de operar.

## 13 — Próximos passos · 45 s

**Fala:**

> Pensando em transformar o protótipo em produto, eu seguiria cinco etapas.

> A primeira é identidade e autorização. Precisamos autenticar a Dona Maria e quem atesta suas decisões.

> Depois, eu prepararia a solução para vários restaurantes.

> Minha proposta seria uma plataforma multi-tenant: cada estabelecimento teria um consultor personalizado, com seus próprios dados e restrições, mas compartilhando a mesma arquitetura e governança.

> Nesse cenário, avaliaria MCP remoto, isolamento por restaurante e PostgreSQL, conforme a necessidade de escala e concorrência.

> A terceira etapa seria observabilidade, para acompanhar ferramentas, falhas, qualidade e custo.

> A quarta seria integrar os evals de conversa com Hermes ao pipeline de CI.

> E a quinta, conectar a solução à operação do delivery para publicar cardápios e preços aprovados.

> A evolução seria gradual, preservando as regras de negócio e os controles de segurança.

## 14 — Agradecimentos · 30 s

**Fala:**

> Bom, pessoal, essa foi a solução que desenvolvi para o desafio Sabor da Maria.

> Lucas e Hildebrando, muito obrigada pelo tempo e pela oportunidade de apresentar o projeto.

> O repositório está público, com o código, as decisões de arquitetura e as instruções para executar a aplicação.

> Também deixei slides técnicos complementares sobre segurança, persistência e testes, caso queiram aprofundar algum ponto.

> Agora fico à disposição para as perguntas.

## Apêndice · sob demanda

Use **Esc** para a visão geral e abra apenas o slide relacionado à pergunta da banca.

### A1 — Invariantes

> Aqui estão algumas regras que a conversa não pode contornar.

> Os R$ 80 são um orçamento único para todos os pratos. Não podemos tratar esse valor como se estivesse disponível novamente para cada receita.

> A taxa de 10% também incide sobre o preço de venda. É uma regra do desafio, não uma afirmação sobre contratos reais do iFood.

> Quando falta um preço ou uma medida, o sistema não inventa zero. Informação desconhecida gera pergunta. Um impeditivo bloqueia o aceite.

> E, se mudar alguma premissa, como a receita ou o rendimento, as decisões dependentes precisam ser reavaliadas.

> Por último, separo dados reais e de simulação em bancos diferentes. O modelo não transforma uma hipótese em fato real só porque alguém pediu na conversa.

### A2 — Domínio e persistência

> O SQLite guarda as decisões que fazem parte do mesmo planejamento. Esse conjunto é o que chamamos de workspace.

> Cada alteração indica a revisão de estado que espera encontrar.

> Se outra decisão mudou o estado antes, a operação é recusada. Isso evita aplicar uma proposta desatualizada.

> Também uso transações: a alteração e seu registro de auditoria são gravados juntos.

> E existe idempotência. Se a mesma operação for repetida com o mesmo conteúdo, o sistema devolve o resultado já registrado. Se o identificador vier com conteúdo diferente, trata como conflito.

> A planilha original não é reescrita. Correções e esclarecimentos ficam em camadas separadas, preservando a origem.

> SQLite atende ao protótipo local. Para vários operadores e acesso remoto, eu reavaliaria o armazenamento.

### A3 — Segurança

> Aqui a ideia foi reduzir o que o modelo consegue fazer e validar tudo no ponto em que uma ação teria efeito.

> No Hermes, configurei uma lista fechada de ferramentas permitidas.

> Identifiquei também um risco no reparo de nomes de ferramentas pelo host. Uma chamada originalmente proibida podia acabar direcionada para uma ferramenta permitida.

> Por isso, o plugin compara a chamada original com a que será executada e bloqueia divergências.

> No serviço Python, o banco e o workspace são fixados pelo operador, e a aprovação não está disponível como ferramenta do modelo.

> A pesquisa não aceita consultas ou URLs livres. E a importação da planilha impõe limites de tamanho e trata as células como dados.

> Existe uma limitação importante: um perfil isolado do Hermes não equivale a uma sandbox do sistema operacional.

> Em produção, eu reforçaria também as identidades e as permissões de cada processo.

### A4 — Verificação

> Para avaliar a solução, separei as evidências por camada.

> Primeiro, os testes determinísticos em Python verificam regras de negócio, persistência e concorrência. O Hypothesis também gera variações de operações para explorar casos extremos.

> Depois, os testes de integração exercitam o servidor MCP real por stdio.

> Já os evals do agente analisam jornadas. Não verifico apenas a resposta escrita: também confiro as ferramentas chamadas e o estado persistido.

> Na matriz S19, são 18 casos do fluxo assistido por CLI, com a revisão humana delegada explicitamente.

> Isso não significa 18 execuções novas da mesma versão, nem validação completa do Hermes Desktop.

> A CI executa o núcleo em Windows, Ubuntu e macOS, mas não instala o Hermes nem um modelo real.

> Por isso, ainda precisamos validar a jornada completa no Desktop, com a planilha original.

### A5 — Trade-offs

> Escolhi uma arquitetura local porque o desafio não exigia um backend distribuído, um ORM adicional ou outra interface.

> Isso trouxe simplicidade e facilitou testar as regras independentemente do LLM.

> Mas os custos dessas decisões são claros.

> A aprovação por terminal exige mais passos. A pesquisa com termos autorizados tem menos flexibilidade. E a integração depende da versão do Hermes e de seus hooks.

> O SQLite facilita a execução local, mas não resolve sozinho as necessidades de uma plataforma multiusuário.

> Eu só migraria para outra infraestrutura quando os requisitos de concorrência, isolamento e acesso remoto justificassem.

> A ideia é evoluir sem abrir mão dos contratos e controles que já estão funcionando.

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
