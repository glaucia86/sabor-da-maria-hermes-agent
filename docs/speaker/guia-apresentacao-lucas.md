# Sabor da Maria — guia para a conversa com Lucas Rolim & Hildebrando Azevedo

**Glaucia Lemos · ~17 minutos de apresentação + demonstração ao vivo.**
Compartilhe o deck e deixe este guia, o Hermes Desktop e o terminal do operador
na outra tela. A fala de cada slide também está nas notas (tecla **S**). Ela é
um apoio para explicar como o sistema funciona, não um texto para ler.

## Ritmo

| Slide | Janela | Tempo | Ênfase |
|---|---|---|---|
| 1 · Capa | 00:00–00:30 | 30 s | Roteiro da conversa |
| 2 · O que é o desafio? | 00:30–01:35 | 65 s | Planilha, R$ 80, 10% e os 4 pedidos |
| 3 · Qual problema resolve? | 01:35–02:40 | 65 s | Erro aqui vira prejuízo |
| 4 · Solução escolhida | 02:40–04:00 | 80 s | LLM conversa, código valida, ela decide |
| 5 · Por que essa solução? | 04:00–05:30 | 90 s | Caminho óbvio × risco × escolha |
| 6 · Arquitetura | 05:30–06:50 | 80 s | Componentes e processo separado de aprovação |
| 7 · Fluxo 1 · Despensa → candidatas | 06:50–07:50 | 60 s | Planilha → Exa → candidatas |
| 8 · Fluxo 2 · Elicitação e viabilidade | 07:50–09:05 | 75 s | Pergunta antes do aceite; R$ 80 agregado |
| 9 · Fluxo 3 · Proposta e aprovação | 09:05–10:25 | 80 s | Manifestação × proposta × aprovação |
| 10 · Fluxo 4 · CMV e preço | 10:25–11:40 | 75 s | CMV, piso, cenários; sobra ≠ lucro |
| 11 · Demonstração | 11:40–12:35 | 55 s | Passagem para o Desktop e o guia |
| 12 · Ensaio E2E no Desktop | após a demo | 95 s | Resultados SIMULATION e intervenções |
| 13 · O que pode virar melhoria? | após a demo | 60 s | Evolução a partir do ensaio |
| 14 · Próximos passos | após a demo | 50 s | Rumo a produção |
| 15 · Agradecimentos | após a demo | 40 s | Ideia central e perguntas |
| A1–A5 · Apêndice | sob demanda | — | Invariantes, persistência, segurança, verificação, trade-offs |

Total sugerido: ~17 minutos de fala, mais até 10 minutos de demonstração após o slide 11. A estimativa considera cerca de 145 palavras por minuto; é uma sugestão, não um requisito do desafio.

Se o tempo apertar, encurte os slides 5 e 7. Nunca corte os fluxos 2 e 3: eles
respondem ao “coração do desafio” e mostram que o modelo não aprova a si mesmo.
Não corte o slide 12: é onde as intervenções do ensaio ficam explícitas.

## 1 — Capa · 30 s

**Fala:**

> Olá, Lucas e Hildebrando. Obrigada pelo tempo de vocês.

> Vou apresentar o Sabor da Maria: uma consultora de cardápio e preço que eu construí sobre o Hermes Agent para o desafio de Senior AI Engineer.

> Dividi a conversa em três partes. Primeiro, o problema e as decisões de arquitetura. Depois, a demonstração no Hermes Desktop e o que o ensaio completo mostrou. No final, limitações, próximos passos e perguntas.

> Se quiserem interromper em algum ponto, fiquem à vontade.

## 2 — O que é o desafio? · 65 s

**Fala:**

> Começando pelo enunciado. A Dona Maria está abrindo o primeiro delivery e chega com uma planilha de duas abas: uma com o que ela tem em estoque e outra com o que comprou e quanto pagou. São 37 ingredientes. Essa planilha original está no repositório e é a entrada padrão da instalação.

> Há duas premissas fixas: R$ 80 para complementos e uma taxa de 10% sobre o preço de venda.

> O agente precisa acompanhá-la em quatro etapas: pesquisar receitas reais e ouvir o que ela acha; descobrir se ela tem equipamento, técnica e tempo para o prato; comparar o que tem com o que falta, dentro do orçamento; e, só depois do aceite, calcular o CMV e propor cenários de preço.

> Eu destaquei a segunda etapa porque, para mim, é o coração do desafio: é ali que uma boa recomendação vira problema na cozinha. E, em todas as etapas, quem decide é a Dona Maria.

## 3 — Qual problema resolve? · 65 s

**Fala:**

> Quando eu traduzo o enunciado, sobram três perguntas: o que ela consegue produzir, se tem condições reais de preparar e quanto cobrar sem perder dinheiro.

> O que me chamou atenção é que, aqui, uma resposta errada não é só uma resposta ruim; é prejuízo. Recomendar uma receita de forno para quem não tem forno, e ela descobrir isso depois de comprar. Tratar os R$ 80 como verba de cada prato, quando é um limite único. Aplicar os 10% sobre o custo, e não sobre a venda, e cobrar abaixo do mínimo.

> E existe uma classe de erro que é própria de LLM: errar uma conta, esquecer algo que ela contou dez mensagens atrás ou entender um “parece bom” como aceite.

> Esses riscos definiram a arquitetura. Eu não queria um recomendador que acerta na maioria das vezes; queria que esses erros não conseguissem virar estado de negócio. É isso que o próximo slide resume.

## 4 — Solução escolhida · 80 s

**Fala:**

> Esta é a decisão central do projeto: separar o que o modelo pode fazer do que a aplicação precisa garantir.

> O Hermes é a interface e o orquestrador. Ele conversa em linguagem simples, escolhe qual ferramenta chamar, pesquisa receitas e explica os números. Para orientar esse atendimento, configurei um arquivo de contexto, uma skill e dois plugins: um de política, que fecha o catálogo de ferramentas, e um de pesquisa, que consulta o Exa pelo endpoint anônimo, sem chave de API.

> As regras não ficam no prompt. Ficam num serviço Python que o Hermes acessa por MCP via stdio, com seis ferramentas de negócio. Ali, Pydantic valida a entrada, Decimal faz as contas e as invariantes são conferidas antes de qualquer gravação. O SQLite guarda fatos, receitas, decisões e auditoria, então retomar o atendimento não depende do que o modelo lembra.

> E a decisão continua humana. O Hermes só consegue criar propostas; quem aplica é um processo local separado, que não aparece no catálogo do modelo.

> O ganho prático é que cada regra pode ser provada por um teste, sem chamar nenhum LLM. Mas eu não cheguei aqui direto; avaliei outros caminhos.

## 5 — Por que essa solução? · 90 s

**Fala:**

> Cada linha desta tabela é um caminho que eu considerei e descartei, junto com o risco que ele traria.

> O mais rápido seria deixar o LLM fazer as contas no prompt. Funciona na demo e falha no dia em que ele esquece uma regra ou arredonda para baixo. Por isso, regras e cálculos estão em Python, com testes que não dependem de modelo.

> Também não uso a memória do agente como estado de negócio. Desliguei a memória automática do Hermes; o estado vem do SQLite pelo `get_business_state`, inclusive numa sessão nova. Nos valores, Decimal em vez de float, e o preço sobe para o centavo seguinte, para nunca ficar abaixo do piso.

> O ponto que mais pesou foi a aprovação. Se o agente pode confirmar a própria decisão, um “parece bom” vira aceite. Então ele propõe, e a aprovação acontece fora dele.

> Na pesquisa, o modelo não envia consulta nem URL livre: escolhe entre termos públicos liberados, e a extração é feita pelo ID do resultado registrado. Isso reduz a superfície para prompt injection e evita mandar a despensa para fora.

> Por fim, mantive tudo local: um backend distribuído traria complexidade que o desafio não pede, com o custo de ainda não atender vários restaurantes. Vamos ver como as peças se encaixam.

## 6 — Arquitetura · 80 s

**Fala:**

> Aqui estão as mesmas responsabilidades, agora como componentes.

> À esquerda, a Dona Maria conversa com o Hermes no Desktop. O Hermes recebe o `.hermes.md` e a skill, que definem papel, linguagem e condução, e usa o modelo escolhido no perfil. Dentro do host há dois plugins: o de política mantém a allowlist e hooks que comparam a ferramenta pedida com a executada; o de pesquisa expõe só duas ferramentas e fala com o Exa usando os termos liberados.

> No centro está o serviço Python. MCP e domínio rodam no mesmo processo local: o adaptador recebe a chamada por stdio, os serviços de inventário, planejamento, cotação e preço validam as regras, e o SQLite guarda snapshot, estado, histórico e auditoria.

> Embaixo, o canal do operador, que é outro processo. É por ele que a planilha entra com o `setup-real` e que as propostas são listadas, inspecionadas e atestadas. A CLI chama o serviço de aprovação direto em Python e grava no mesmo banco; não passa pelo MCP, e o modelo não tem nenhuma ferramenta de aprovação.

> A seta tracejada é só o fluxo lógico: a Dona Maria manifesta na conversa, mas a atestação acontece fora dela. Agora, os fluxos.

**Aponte:** MCP e domínio são o mesmo serviço Python; a aprovação roda em outro processo, sem tool para o modelo; a seta tracejada é fluxo lógico.

## 7 — Fluxo 1 · Despensa → candidatas · 60 s

**Fala:**

> O primeiro fluxo começa antes da conversa. O operador importa a planilha com o `setup-real`; com a original, são 37 itens.

> O importador cruza as duas abas: o estoque diz o que está disponível, e a compra diz o custo unitário. Cinco quilos de arroz por R$ 24,90 viram cerca de meio centavo por grama. Preço ou conversão ausente vira pendência, nunca zero, e o snapshot fica imutável no SQLite.

> Na conversa, o Hermes consulta o inventário e pesquisa no Exa só com os termos liberados. A extração é feita pelo ID do resultado, com fonte, hash e horário registrados, e o texto da página é tratado como dado. A Dona Maria também pode trazer uma receita própria.

> Com as candidatas na mesa, ela dá a opinião. Mas gostar de uma receita não é conseguir prepará-la, e é isso que o próximo fluxo verifica.

## 8 — Fluxo 2 · Elicitação e viabilidade · 75 s

**Fala:**

> Este é o fluxo que eu considero o coração do desafio.

> Cada receita traz requisitos de preparo: equipamento, técnica, operação e ingredientes na escala do plano. Para cada requisito, o serviço procura um fato confirmado sobre a cozinha da Dona Maria. Se esse fato não existe, o estado é UNKNOWN, e o comportamento correto é perguntar, não presumir. Ter fogão não confirma que a panela comporta o lote, nem que ela tem tempo livre antes da entrega.

> A resposta dela vira proposta, passa pela aprovação local, e só então o `evaluate_recipe_feasibility` reavalia. Se um requisito está confirmado como ausente, o resultado é BLOCKED, e o caminho é adaptar a receita ou trocar de candidata.

> Depois vêm as compras. O `evaluate_purchase_plan` soma os faltantes de todos os pratos, considera pacote inteiro e frete e compara com os R$ 80 agregados. Só ofertas confirmadas entram, e a confirmação vale por no máximo 24 horas.

> O aceite só passa com viabilidade ELIGIBLE e compras CONFIRMED. E como uma decisão dessas chega ao banco é o assunto do próximo slide.

**Aponte:** desconhecido vira pergunta; impeditivo bloqueia o aceite.

## 9 — Fluxo 3 · Proposta e aprovação · 80 s

**Fala:**

> Este é o controle que mais influenciou a arquitetura. Eu separo três momentos que costumam se misturar.

> O primeiro é a manifestação. A Dona Maria diz “aceito este prato” ou “escolho o M30”. É a vontade dela, mas ainda não é uma decisão válida no sistema.

> O segundo é a proposta. O Hermes transforma essa fala num comando tipado e chama `propose_user_change`. O que vai para o banco é uma proposta pendente, com hash e a revisão de estado esperada. O negócio não muda.

> O terceiro é a aprovação operacional. Num processo local separado, o operador inspeciona um resumo determinístico e atesta, com o hash, que aquele conteúdo exato corresponde ao que ela disse. Ele não decide por ela; confirma a manifestação. Mesmo assim, o Python revalida o prazo de dez minutos, a revisão do estado e as regras. Se falhar, recusa sem efeito parcial. Se passar, efeito e auditoria entram na mesma transação.

> Isso vale para fatos da cozinha, receitas, plano, interesse, cotações, aceite e preço. O custo é operacional: cada decisão exige uma ida ao terminal. Aceitei esse custo porque, assim, o modelo nunca autoriza a si mesmo.

**Destaque:** a Dona Maria decide; o operador atesta, sem substituí-la; o Python revalida antes de aplicar.

## 10 — Fluxo 4 · CMV e preço · 75 s

**Fala:**

> Com o aceite aplicado, entra a precificação. O `calculate_pricing_scenarios` só roda com aceite vigente; ele grava o cálculo, mas não escolhe preço.

> O CMV aqui é o custo dos ingredientes consumidos por porção: quantidade usada vezes o custo unitário de cada origem, dividido pelo rendimento do lote. O pacote inteiro conta no orçamento de compras, mas no CMV entra só o que o prato consome.

> A taxa de 10% incide sobre a venda. Ela recebe 90% do preço, então o piso é o CMV dividido por 0,90. Com CMV de R$ 10, o piso é R$ 11,12, arredondado para cima, e a sobra nesse ponto é um centavo, não R$ 1,12.

> Os cenários M10, M20 e M30 são margens sobre a venda. O enunciado pede dois ou três; os percentuais foram escolha minha. E eu evito a palavra lucro: essa sobra ainda precisa pagar embalagem, gás e trabalho, que não estão na planilha.

> A Dona Maria escolhe um cenário ou um preço acima do piso, e essa escolha passa pelo mesmo fluxo de aprovação. Isso fecha a arquitetura; agora quero mostrar como ela aparece na prática.

## 11 — Demonstração · 55 s

**Fala:**

> Até aqui, mostrei as decisões de arquitetura e os controles do sistema. Agora quero mostrar como isso aparece para a Dona Maria, que não precisa saber o que é MCP, SQLite ou hash de proposta.

> Vou usar o perfil REAL, com a planilha original, seguindo o guia interativo do repositório: prompts em primeira pessoa, em linguagem natural, com a explicação do que o agente faz em cada etapa. Vocês podem usar o mesmo guia para testar.

> No Desktop, eu sou a Dona Maria; no terminal, sou a operadora que atesta as propostas. Vou avisar quando trocar de papel.

> Uma transparência: a jornada completa que registrei no Desktop foi um ensaio em SIMULATION; o percurso REAL completo ainda não está homologado. Se algo travar, mostro o estado alcançado e a pendência, sem completar com hipótese.

**Tempo:** a demonstração tem até dez minutos, separados da apresentação. Abra o guia pelo link do slide.

## 12 — Ensaio E2E no Desktop · 95 s

**Fala:**

> Antes de hoje, fiz um ensaio completo no Hermes Desktop, em 17 de novembro, num workspace SIMULATION com uma planilha sintética de seis itens. Quero mostrar o que ele comprovou e o que não comprovou.

> Numa conversa contínua de uns 45 minutos, o Hermes consultou a despensa, pesquisou no Exa e extraiu uma receita real de arroz branco. A receita web ficou intacta, e a adaptação entrou como versão separada, marcada como `USER_SIMULATION`, para nunca ser confundida com fato real. Depois vieram as condições da cozinha, o plano de 1 lote e 2 porções, viabilidade ELIGIBLE e compras CONFIRMED sem complemento. Interesse e aceite passaram pela aprovação local.

> O CMV ficou em R$ 1,218 por porção. A escolha foi o M30, e o preço persistido é R$ 2,03. Tirando a taxa simplificada de 10% e os ingredientes, sobram uns 61 centavos, que não são lucro líquido: embalagem, gás e trabalho não foram informados. No fim, o cardápio ficou em MENU_SELECTED, com saldo de R$ 80,00 e nenhuma proposta pendente.

> O que não foi autônomo: duas tentativas do Hermes de revisar a adaptação foram recusadas porque perdiam o vínculo com a fonte web, e as propostas corretivas foram preparadas pela operação, fora da conversa. O primeiro aceite também foi recusado, porque o interesse ainda não estava registrado. Os controles funcionaram; a experiência ainda precisa melhorar.

**Cuidado:** números de SIMULATION com planilha sintética; não os apresente como resultado da planilha original nem chame a sobra de lucro.

## 13 — O que pode virar melhoria? · 60 s

**Fala:**

> Juntando o desenvolvimento e o ensaio, estas são as melhorias que eu priorizaria.

> A primeira veio do E2E. O domínio recusou corretamente uma adaptação que perdia o vínculo com a fonte, mas o Hermes não se corrigiu sozinho. Eu deixaria o contrato da ferramenta e a skill mais explícitos, para isso não depender da operação.

> Na pesquisa, traria duas ou três candidatas por busca, com os mesmos controles. A aprovação poderia ir para uma tela de revisão, ainda fora do catálogo do modelo. No preço, entrariam embalagem, gás, energia e trabalho.

> Nos evals, há 18 casos no recorte CLI, mas um único modelo observado; o próximo passo é comparar modelos em qualidade, latência e custo. E as preferências deixariam de ser literais: “não gosto de fritura” deveria levar a perguntar sobre empanados.

> Isso é evolução do protótipo. Para virar produto, a ordem é outra.

## 14 — Próximos passos · 50 s

**Fala:**

> Pensando em produto, eu seguiria esta sequência, e a ordem importa.

> Primeiro, identidade. Hoje a atestação é local e não autentica a cozinheira; antes de escalar, preciso saber quem pode decidir.

> Depois, multiusuário: cada restaurante com seus dados e restrições sobre as mesmas regras, com MCP remoto, isolamento por tenant e PostgreSQL quando a concorrência justificar.

> Em seguida, observabilidade: tracing das ferramentas, métricas da jornada e custo de LLM. Depois, levar o Hermes e os evals de conversa para a CI, que hoje cobre só o núcleo e o MCP. E, por último, integrar ao delivery para publicar cardápio e preço aprovados.

> Em todas as etapas, o contrato continua o mesmo: o modelo propõe, e o domínio valida o que pode ser persistido.

## 15 — Agradecimentos · 40 s

**Fala:**

> Para fechar, a ideia que guiou o projeto: o Hermes pode raciocinar, pesquisar, conversar e propor, mas quem aplica as regras e decide o que pode ser persistido é a aplicação Python. Uma manifestação só vira decisão depois de passar por uma aprovação fora do modelo.

> O repositório está público, com a planilha original, o passo a passo de instalação, o guia interativo e o registro do ensaio, incluindo as intervenções.

> Obrigada, Lucas e Hildebrando. Deixei um apêndice sobre invariantes, persistência, segurança, verificação e trade-offs, se quiserem aprofundar. Fico à disposição.

### {{icon book-open}}Apêndice — 

> Estes slides ficam como apoio para as perguntas. Eu abro só o que for útil para a discussão.

> São cinco temas: invariantes, persistência, segurança, verificação e trade-offs.

### {{icon lock}}A1 — Invariantes

> Estas são as regras que nenhuma conversa contorna, porque estão no domínio e não no prompt.

> Os R$ 80 são um teto único para todos os pratos, contando pacote inteiro e encargos. A taxa de 10% incide sobre a venda; é premissa do desafio, não uma afirmação sobre contratos reais do iFood. E os cálculos usam Decimal, com o preço sempre arredondado para cima em centavos.

> Informação ausente não vira zero. Desconhecido gera pergunta, impeditivo bloqueia o aceite, e custo incompleto impede aceite e preço definitivos. Se uma premissa muda, como a receita ou o rendimento, as decisões que dependiam dela deixam de valer.

> Por fim, REAL e SIMULATION ficam em bancos separados. Foi isso que permitiu fazer o ensaio com dados hipotéticos sem nenhuma chance de eles virarem fato real.

### {{icon database}}A2 — Domínio e persistência

> A unidade de consistência é o workspace: o conjunto de receitas, plano, fatos e escolhas que dividem o mesmo orçamento e o mesmo estoque.

> Toda alteração declara a revisão de estado que espera encontrar. Se outra decisão mudou o estado antes, a operação é recusada; é isso que impede aplicar uma proposta desatualizada. A alteração e a auditoria entram na mesma transação, então não existe gravação pela metade.

> Também há idempotência. A mesma operação com o mesmo conteúdo devolve o resultado já gravado; o mesmo identificador com conteúdo diferente é tratado como conflito.

> A planilha importada nunca é reescrita. Correções viram versões e camadas, preservando a origem de cada dado, como aconteceu com a receita web e a adaptação no ensaio.

> SQLite resolve bem o protótipo local. Com vários operadores e acesso remoto, eu reavaliaria o armazenamento.

### {{icon shield-check}}A3 — Segurança

> Em segurança, a ideia foi reduzir o que o modelo consegue fazer e validar tudo no ponto onde a ação teria efeito.

> No Hermes, o catálogo é fechado: seis ferramentas MCP e duas de pesquisa. Durante o desenvolvimento, encontrei um risco no reparo de nomes de ferramentas do host: uma chamada proibida podia acabar redirecionada para uma ferramenta permitida. Por isso, o plugin de política compara o nome pedido com o executado e bloqueia a divergência. Memória automática e perfil de usuário ficam desligados.

> No Python, banco e workspace são fixados pelo operador, os schemas recusam campos extras e a aprovação não existe como ferramenta do modelo.

> Na pesquisa, o Exa é chamado pelo endpoint anônimo, com um resultado por busca e sem fallback para outro provedor. Não há consulta nem URL livre, e a extração tem limites de redirect, de volume e de destino. Na planilha, há limites de tamanho, e as células são sempre tratadas como dados.

> A limitação que eu deixo explícita: um perfil isolado do Hermes não é uma sandbox do sistema operacional. Em produção, eu reforçaria identidade e permissões por processo.

### {{icon flask-conical}}A4 — Verificação

> Eu separei as evidências por camada, porque cada uma prova uma coisa diferente.

> Os testes determinísticos cobrem regras, limites, persistência e concorrência; o Hypothesis gera sequências de operações para achar casos extremos. A última regressão completa foi em 16 de novembro, com 804 aprovados. Depois da troca para o Exa, rodei 77 testes direcionados de pesquisa, não a suíte inteira. Os testes de integração exercitam o servidor MCP real por stdio.

> Nos evals do agente, eu não olho só a resposta escrita: confiro as ferramentas chamadas e o estado persistido. São 18 casos no recorte CLI assistido, com a revisão delegada declarada.

> Em 17 de novembro, preparei o REAL com a planilha original até o `check`, e fiz o ensaio completo no Desktop em SIMULATION. A conversa REAL completa no Desktop ainda falta, e eu não a apresento como feita.

> A CI roda o núcleo em Windows, Ubuntu e macOS, mas não instala o Hermes nem um modelo.

### {{icon scale}}A5 — Trade-offs

> Escolhi uma arquitetura local porque o desafio não pedia backend distribuído, outro orquestrador ou uma interface própria. Isso trouxe simplicidade e me deixou testar as regras sem depender do LLM.

> Os custos também são claros. A aprovação externa adiciona passos, e o ensaio mostrou isso. A pesquisa por termos liberados dá menos liberdade. A integração depende da versão do Hermes e dos hooks; por isso o plugin recusa outra versão. O Exa anônimo evita pedir chave ao avaliador, mas tem cota e disponibilidade que eu não controlo, e eu preferi falhar de forma explícita a cair numa busca livre.

> O SQLite atende a execução local, mas não resolve sozinho uma plataforma multiusuário. Eu só trocaria a infraestrutura quando concorrência, isolamento e acesso remoto justificassem, sem abrir mão dos contratos que já estão funcionando.
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
| O que ainda não está homologado? | A jornada completa no Desktop com a planilha original no perfil REAL. O ensaio completo de 17/11 foi em `SIMULATION`, com planilha sintética; a preparação REAL foi conferida até `check`. CI não instala o Hermes nem um modelo. [Registro E2E](../verification-desktop-e2e.md). |
| O E2E foi autônomo? | Não. Duas propostas corretivas da adaptação foram preparadas pela operação, fora da conversa, depois de recusas `SOURCE_NOT_LINKED`; o primeiro aceite foi recusado por falta de interesse registrado; a pesquisa do perfil `SIMULATION` foi configurada manualmente. Nenhuma aprovação foi feita pelo agente. [Intervenções](../verification-desktop-e2e.md#intervenções-operacionais). |
