# Sabor da Maria — guia para a conversa com Lucas Rolim & Hildebrando Azevedo

**Glaucia Lemos · ~17 minutos de apresentação + demonstração ao vivo.**
Compartilhe o deck e deixe este guia, o Hermes Desktop e o guia interativo, no
modo Demo rápida, na outra tela. A fala de cada slide também está nas notas
(tecla **S**). Ela é um apoio para explicar como o sistema funciona, não um
texto para ler.

## Ritmo

| Slide | Janela | Tempo | Ênfase |
|---|---|---|---|
| 1 · Capa | 00:00–00:30 | 30 s | Roteiro da conversa |
| 2 · O que é o desafio? | 00:30–01:30 | 60 s | Planilha, R$ 80, 10% e as quatro etapas |
| 3 · Qual problema resolve? | 01:30–02:30 | 60 s | Erro vira prejuízo, não só resposta ruim |
| 4 · Solução escolhida | 02:30–03:45 | 75 s | LLM conversa e propõe, domínio garante, ela decide |
| 5 · Por que essa solução? | 03:45–05:00 | 75 s | Caminho rápido × risco × decisão |
| 6 · Arquitetura | 05:00–06:25 | 85 s | Hermes, domínio e aprovação separada |
| 7 · Fluxo 1 · Despensa → candidatas | 06:25–07:30 | 65 s | Planilha → custo unitário → Exa |
| 8 · Fluxo 2 · Elicitação e viabilidade | 07:30–08:50 | 80 s | Descobrir antes de aceitar; R$ 80 compartilhado |
| 9 · Fluxo 3 · Proposta e aprovação | 08:50–10:25 | 95 s | Um exemplo: manifestação, proposta, atestação, revalidação |
| 10 · Fluxo 4 · CMV e preço | 10:25–11:55 | 90 s | CMV, piso de R$ 11,12, cenários, sobra ≠ lucro |
| 11 · Demonstração | 11:55–13:00 | 65 s | Demo rápida REAL em cinco cenas; preço no slide 12 |
| 12 · Ensaio E2E no Desktop | após a demo | 70 s | Evidência SIMULATION e intervenções |
| 13 · O que pode virar melhoria? | após a demo | 80 s | Achados dos testes e evoluções |
| 14 · Próximos passos | após a demo | 65 s | Confiança antes da escala |
| 15 · Agradecimentos | após a demo | 30 s | Frase de síntese e perguntas |
| A1–A5 · Apêndice | sob demanda | — | Invariantes, persistência, segurança, verificação, trade-offs |

Total sugerido: ~17 minutos de fala, mais cerca de 8 minutos da demo rápida após o slide 11. A estimativa considera cerca de 150 palavras por minuto e é uma sugestão, não um requisito do desafio. Sem o slide 12, a fala cai para cerca de 16 minutos.

Priorize os slides 4, 6, 8, 9 e 10, que sustentam a arquitetura. Se o tempo apertar,
resuma o slide 12 em uma frase e encurte os slides 5 e 7. Nunca corte os fluxos 2 e 3.

As linhas em itálico dentro das falas são notas de revisão, não texto para falar.

## 1 — Capa · 30 s

**Fala:**

> Olá, Lucas e Hildebrando. Obrigada pelo tempo de vocês.

> Hoje vou apresentar o Sabor da Maria, a solução que desenvolvi para o desafio de Senior AI Engineer do iFood.

> Vou começar pelo problema e pelas decisões de engenharia. Depois mostro a arquitetura e os fluxos principais.

> Em seguida, faço a demonstração no Hermes Desktop. Para fechar, falo das melhorias e dos próximos passos e abro para perguntas.

> Se quiserem interromper em algum momento, fiquem à vontade. Vamos começar pela Dona Maria.

## 2 — O que é o desafio? · 60 s

**Fala:**

> A Dona Maria está abrindo o primeiro delivery.

> Ela chega com uma planilha de duas abas. Uma mostra o que ela tem em estoque. A outra registra o que ela comprou e quanto pagou. Ao todo, são 37 ingredientes.

> O desafio também traz duas premissas fixas. Ela tem R$ 80 para comprar complementos, e a plataforma cobra 10% sobre o preço de venda.

> O Hermes precisa ajudá-la em quatro etapas.

> Primeiro, pesquisar receitas reais e ouvir a opinião dela.

> Depois, descobrir se ela tem equipamento, técnica e tempo para preparar o prato. Para mim, esse é o coração do desafio.

> Em seguida, comparar o que ela tem com o que falta, dentro do orçamento.

> Por último, depois que ela aceita um prato, calcular o CMV e apresentar cenários de preço.

> Em todas elas, a escolha final é da Dona Maria. E cada etapa pode dar errado de um jeito caro.

## 3 — Qual problema resolve? · 60 s

**Fala:**

> Por trás do enunciado existem três perguntas. O que ela consegue produzir? Ela tem condições reais de preparar? E quanto deve cobrar para não perder dinheiro?

> Nesse negócio, uma resposta errada vira prejuízo.

> Imagine recomendar uma receita de forno para quem não tem forno. Ela só descobre isso depois de comprar os ingredientes.

> Ou tratar os R$ 80 como verba de cada prato, quando o limite é um só para o cardápio inteiro.

> Na precificação, aplicar os 10% sobre o custo, e não sobre a venda, leva a um preço abaixo do mínimo.

> Com LLMs existe ainda outra classe de risco. O modelo pode errar uma conta, esquecer um fato ou entender um “parece bom” como aceite.

> Por isso, eu não queria apenas um recomendador que acertasse na maioria das vezes. Queria impedir que erros do modelo virassem decisões de negócio.

> Essa ideia orientou a solução que escolhi.

## 4 — Solução escolhida · 75 s

**Fala:**

> A decisão central foi separar o que o LLM pode fazer do que a aplicação precisa garantir.

> O Hermes conversa, pesquisa e propõe. Ele fala com a Dona Maria em linguagem simples, faz as perguntas sobre a cozinha e explica os números.

> Para orientar esse atendimento, escrevi um arquivo de contexto, o `.hermes.md`, e uma skill. Também criei dois plugins. Um limita as ferramentas que o modelo pode chamar. O outro pesquisa receitas pelo Exa, sem exigir chave de API.

> As regras de negócio não ficam no prompt. Elas estão num serviço Python, que o Hermes acessa por MCP via stdio.

> É esse serviço que valida viabilidade, orçamento e preço, com tipos estritos e cálculos em Decimal.

> O SQLite guarda o estado do negócio. Fatos, receitas, decisões e auditoria ficam no banco, e uma nova sessão retoma o atendimento sem depender da memória do modelo.

> E quem decide continua sendo a Dona Maria. O Hermes só registra propostas. Quem aplica é um processo local independente, que o modelo não enxerga.

> Na prática, isso me permite testar cada regra sem chamar nenhum LLM. Essa separação nasceu de algumas escolhas bem conscientes.

## 5 — Por que essa solução? · 75 s

**Fala:**

> Para cada decisão, comparei o caminho mais rápido com o risco que ele traria.

> O mais rápido seria deixar o modelo fazer as contas. Mas basta uma regra esquecida para o preço ficar abaixo do mínimo. Por isso os cálculos estão em Python, cobertos por testes que não dependem de LLM.

> O mesmo raciocínio vale para o estado. A memória do agente ajuda a conversa, mas não é confiável para guardar orçamento ou aceite. Desliguei a memória automática, e o estado vem sempre do SQLite.

> Nos valores, troquei float por Decimal. O preço é arredondado para cima, no centavo, para nunca cair abaixo do piso.

> A escolha que mais pesou foi separar proposta de aprovação. Se o agente pudesse confirmar a própria decisão, um “parece bom” viraria aceite.

> Na pesquisa, o modelo não envia consulta livre nem URL. Ele escolhe entre termos liberados, e cada fonte fica registrada com a referência original.

> Por último, mantive tudo local. Foi uma decisão de escopo. Ela facilita a reprodução, mas ainda não atende vários restaurantes.

> No conjunto, troquei um pouco de flexibilidade por garantias que eu consigo testar. Agora vou mostrar como essas peças se organizam.

## 6 — Arquitetura · 85 s

**Fala:**

> O desenho segue o caminho de uma conversa.

> À esquerda, a Dona Maria fala com o Hermes Desktop. O contexto e a skill definem como a consultora se comporta.

> Os dois plugins ficam dentro do host. O de política fecha o catálogo e confere se a ferramenta executada é a mesma que o modelo pediu. O de pesquisa expõe apenas duas ferramentas e consulta o Exa.

> No centro está o serviço Python. O MCP é só a porta de entrada. Atrás dele, o domínio cuida de inventário, planejamento, cotações e preço. Tudo que vale para o negócio passa por esse domínio e termina no SQLite.

> Na parte de baixo fica o caminho da operadora. É um processo separado, que importa a planilha e revisa as propostas pela CLI. Ele grava no mesmo banco, mas não passa pelo MCP, e o modelo não tem nenhuma ferramenta para aprovar.

> A linha tracejada representa a manifestação da Dona Maria, e não uma conexão técnica. A manifestação acontece no chat. A aprovação acontece fora dele.

> Hoje essa aprovação usa um terminal, o que basta para o protótipo. Em produção, eu levaria isso para uma interface de revisão autenticada, ainda fora do alcance do modelo.

> Com as peças no lugar, vamos seguir a jornada, começando pela despensa.

**Aponte:** o diagrama da esquerda para a direita e depois a faixa de baixo. A aprovação é outro processo, sem tool para o modelo.

## 7 — Fluxo 1 · Despensa → candidatas · 65 s

**Fala:**

> A jornada começa antes da conversa. A operadora importa a planilha original com o `setup-real`, e os 37 ingredientes entram no banco.

> O importador relaciona as duas abas pelo nome do ingrediente. O estoque diz quanto ela tem. A aba de preços diz quanto ela pagou e por qual quantidade, e é dela que sai o custo unitário.

> Cinco quilos de arroz por R$ 24,90, por exemplo, dão cerca de meio centavo por grama.

> Quando falta um preço ou uma conversão de medida, o sistema registra uma pendência. Ele nunca completa com zero.

> Na conversa, o Hermes consulta esse inventário e pesquisa receitas reais pelo Exa, com os termos liberados.

> Cada receita extraída guarda a fonte original. O conteúdo da página é tratado como dado não confiável. Se o site trouxer alguma instrução, ela não muda o que o agente pode fazer.

> A Dona Maria vê as opções e diz o que achou. Só que gostar de uma receita ainda não significa conseguir prepará-la.

## 8 — Fluxo 2 · Elicitação e viabilidade · 80 s

**Fala:**

> Chegamos ao ponto que o desafio coloca no centro.

> O agente precisa descobrir se a Dona Maria consegue preparar o prato antes de permitir que ela o aceite.

> Cada receita tem requisitos. Equipamento, técnica, tempo, gás ou energia, espaço e ingredientes na quantidade do plano. Para cada requisito, o domínio procura um fato confirmado sobre a cozinha dela.

> Pense numa receita que pede uma panela de pelo menos três litros. Se ela disse apenas que tem panela, a capacidade ainda é desconhecida. O requisito fica UNKNOWN, e o agente precisa perguntar. Ele não pode supor.

> Se ela responde que a panela tem dois litros, a restrição está confirmada. O requisito vira BLOCKED, e o caminho é adaptar a receita ou escolher outra.

> Quando todos os requisitos estão confirmados, a receita fica ELIGIBLE.

> Depois vem o orçamento. O serviço soma os faltantes de todos os pratos, considera pacotes inteiros e frete e compara com os R$ 80. O limite é compartilhado. Ele não se renova a cada receita.

> O aceite só fica disponível com a receita elegível e as compras confirmadas.

> Em todos esses passos, a resposta da Dona Maria só vira fato depois de uma aprovação. Esse é o mecanismo do próximo slide.

**Aponte:** o exemplo da panela. Desconhecido vira pergunta, impeditivo bloqueia o aceite.

## 9 — Fluxo 3 · Proposta e aprovação · 95 s

**Fala:**

> Imagine que a Dona Maria escreva no chat: “Aceito este prato.” Essa é a manifestação dela. É a vontade dela, mas ainda não é uma decisão válida no sistema.

> O Hermes transforma essa frase numa proposta, pela ferramenta `propose_user_change`. A proposta fica pendente no banco, com um hash do conteúdo e a revisão do estado em que foi criada. Nada muda no negócio ainda.

> Em seguida entra a operadora, num processo separado. Ela abre a proposta pela CLI, lê o resumo e confere se aquilo corresponde ao que a Dona Maria disse. Se corresponder, ela atesta usando o hash.

> A operadora não decide pela Dona Maria. Ela confirma que o registro é fiel à manifestação.

> Mesmo atestada, a proposta volta ao domínio. Ele verifica se o prazo de dez minutos expirou, se o estado mudou desde a proposta e se as regras de negócio continuam válidas. No ensaio em SIMULATION, um aceite chegou sem o interesse registrado, e o domínio recusou.

> Se algo falha, nada é aplicado. Se tudo está certo, a decisão e a auditoria são gravadas na mesma transação.

> Esse caminho vale para todas as decisões, dos fatos da cozinha à escolha do preço.

> O custo é operacional, porque cada decisão exige uma ida ao terminal. Eu aceitei esse custo porque, com ele, o modelo nunca aprova a si mesmo. Com o prato aceito, o próximo passo é o preço.

**Destaque:** a Dona Maria decide. A operadora atesta, sem substituí-la. O domínio revalida antes de aplicar.

## 10 — Fluxo 4 · CMV e preço · 90 s

**Fala:**

> Com o aceite aplicado, o sistema pode calcular o preço.

> O primeiro número é o CMV, o custo dos ingredientes de cada porção.

> Existe uma diferença importante. Se ela compra um pacote de um quilo e a receita usa duzentos gramas, o pacote inteiro conta no orçamento de compras. No CMV entram só os duzentos gramas.

> Depois vem a taxa. Os 10% incidem sobre o preço de venda, não sobre o custo. Ela recebe 90% do que cobra, e por isso o preço mínimo é o CMV dividido por 0,90.

> Com CMV de R$ 10, a divisão dá R$ 11,111. O sistema arredonda para cima e chega a R$ 11,12.

> Nesse preço, a taxa fica em R$ 1,11. Depois dos ingredientes e da taxa, sobra um centavo. O preço está R$ 1,12 acima do custo, mas quase nada fica com ela.

> A partir do piso, o sistema mostra três cenários, com margens de 10, 20 e 30% sobre a venda. Com o mesmo CMV, os preços ficam em R$ 12,50, R$ 14,29 e R$ 16,67.

> Eu evito chamar essa diferença de lucro. Ela ainda precisa pagar embalagem, gás, energia e mão de obra, que não estão na planilha.

> A Dona Maria escolhe um cenário ou um preço próprio acima do piso, e essa escolha passa pela mesma aprovação. Agora quero mostrar como tudo isso aparece na prática.

## 11 — Demonstração · 65 s

**Fala:**

> Até aqui, mostrei as decisões de arquitetura e os controles do sistema. Agora quero mostrar como isso aparece para a Dona Maria, que não precisa saber o que é MCP, SQLite ou hash.

> No Hermes Desktop, eu sou a Dona Maria. Vou seguir a demo rápida do guia interativo, com cinco cenas só de consulta sobre o perfil REAL, preparado antes com a planilha original. Não vou criar propostas nem aprovar nada ao vivo.

> Vamos ver a despensa, a fonte Exa registrada, a adaptação com o plano, a viabilidade que ainda está pendente e as decisões que passaram pela aprovação externa.

> Um esclarecimento sobre as evidências. A receita REAL ainda não foi aceita nem precificada, e a jornada REAL completa vai passar por uma nova validação de ponta a ponta. Preço e cardápio aparecem no próximo slide, como resultado do ensaio em SIMULATION. Durante a demonstração, vou confirmar cada passo pelo estado gravado, e não pela resposta do modelo.

> Vamos começar pela despensa.

*Revisar após a validação REAL: substituir o esclarecimento sobre as evidências pelo resultado comprovado.*

**Demo rápida (~8 min, somente leitura):** abra o guia pelo link do slide, no modo Demo rápida. Cenas: 1 · despensa e orçamento (1:30) · 2 · fonte Exa registrada (1:30) · 3 · adaptação e plano (1:45) · 4 · viabilidade pendente (1:30) · 5 · aprovação humana externa (1:45). Sem comandos no terminal, sem novas propostas e sem aprovações. Ao fim da cena 5, volte ao slide 12 para preço e cardápio do ensaio SIMULATION.

## 12 — Ensaio E2E no Desktop · 70 s

**Fala:**

> De volta aos slides, quero mostrar rapidamente o que o ensaio em SIMULATION deixou registrado. É nele que aparecem o preço e o cardápio que a demo REAL não mostrou. É uma evidência separada da demonstração, com dados sintéticos.

> Numa conversa contínua, o Hermes pesquisou uma receita real pelo Exa, preservou a versão original e registrou a adaptação como hipótese. O plano ficou com um lote de duas porções, a receita ficou elegível e as compras foram confirmadas sem complemento.

> No preço, o CMV foi de R$ 1,218 por porção. A escolha foi o M30, e o valor gravado foi R$ 2,03. Depois da taxa e dos ingredientes, sobram uns 61 centavos, que também não são lucro líquido.

> O que não foi autônomo precisa ser dito. Duas correções na receita adaptada foram preparadas pela operação, fora da conversa. O primeiro aceite foi recusado porque faltava o interesse. E a pesquisa desse perfil foi configurada manualmente.

> Os controles funcionaram. A experiência ainda tem pontos a melhorar, e é por eles que começo o próximo slide.

*Revisar após a validação REAL: avaliar mover este slide para o apêndice e trazer os resultados REAL para a apresentação principal.*

**Cuidado:** números de SIMULATION com planilha sintética. Não os apresente como resultado da planilha original nem chame a sobra de lucro.

## 13 — O que pode virar melhoria? · 80 s

**Fala:**

> Separei as melhorias em dois grupos. Algumas apareceram nos testes. Outras são evoluções que eu já planejava.

> Nos testes, ao adaptar uma receita, o Hermes tentou uma revisão que perdia o vínculo com a fonte web. O domínio recusou, como deveria, mas o modelo não conseguiu se corrigir sozinho. Eu melhoraria o contrato da ferramenta e as orientações da skill para que essa correção não dependa da operação.

> A aprovação pela CLI também mostrou atrito. Ela evoluiria para uma interface de revisão segura, ainda fora do catálogo do modelo.

> Entre as evoluções, a pesquisa traria duas ou três candidatas por busca, e não apenas uma, com os mesmos controles.

> No preço, faltam embalagem, gás, energia e mão de obra para chegar a um lucro de verdade.

> Nos evals, existem 18 casos integrados. Eles foram executados de forma assistida pela CLI, com dados sintéticos e revisão delegada. Ainda não comparam modelos, e esse é o próximo passo, medindo qualidade, latência e custo.

> Por fim, as preferências. Hoje a correspondência é literal. Se ela disser “não gosto de fritura”, o agente deveria perguntar se isso inclui empanados, em vez de presumir.

> Para transformar o protótipo em produto, porém, a prioridade é outra.

## 14 — Próximos passos · 65 s

**Fala:**

> Pensando em produto, eu não começaria pela escala. Começaria pela confiança.

> O primeiro passo é identidade e autorização. Hoje a atestação é local e não autentica a cozinheira. Antes de escalar, o sistema precisa saber quem pode decidir.

> Depois vem o suporte a vários restaurantes. Cada um teria dados, restrições e histórico isolados, sobre as mesmas regras de domínio. Essa é uma proposta de evolução, e ela levaria a reavaliar o SQLite e o MCP local.

> Com mais restaurantes, a observabilidade passa a ser essencial. Quero ver onde a jornada trava, quais ferramentas falham e quanto cada atendimento custa em modelo.

> Em seguida, os evals de conversa entram na CI. Hoje a CI cobre o núcleo e o MCP, mas não o agente.

> Só depois disso faria sentido integrar com o delivery, publicando cardápios e preços aprovados.

> Em todas as etapas, o contrato continua o mesmo. O modelo propõe, e o domínio decide o que pode virar estado.

## 15 — Agradecimentos · 30 s

**Fala:**

> Se eu tivesse que resumir o projeto numa frase, seria esta. O LLM pesquisa, conversa e propõe, mas é o domínio que valida as regras, e só decisões confirmadas alteram o estado do negócio.

> O repositório tem a implementação, a documentação e os materiais para reproduzir a jornada.

> Lucas e Hildebrando, obrigada pela conversa. Fico à disposição para as perguntas.

### {{icon book-open}}Apêndice — 

> Estes slides ficam como apoio para as perguntas. Eu abro só o que for útil para a discussão.

> São cinco temas: invariantes, persistência, segurança, verificação e trade-offs.

### {{icon lock}}A1 — Invariantes

> Estas são as regras que nenhuma conversa contorna, porque estão no domínio e não no prompt.

> Os R$ 80 são um teto único para todos os pratos, contando pacote inteiro e encargos. A taxa de 10% incide sobre a venda. É premissa do desafio, não uma afirmação sobre contratos reais do iFood. E os cálculos usam Decimal, com o preço sempre arredondado para cima em centavos.

> Informação ausente não vira zero. Desconhecido gera pergunta, impeditivo bloqueia o aceite, e custo incompleto impede aceite e preço definitivos. Se uma premissa muda, como a receita ou o rendimento, as decisões que dependiam dela deixam de valer.

> Por fim, REAL e SIMULATION ficam em bancos separados. Foi isso que permitiu fazer o ensaio com dados hipotéticos sem nenhuma chance de eles virarem fato real.

### {{icon database}}A2 — Domínio e persistência

> A unidade de consistência é o workspace: o conjunto de receitas, plano, fatos e escolhas que dividem o mesmo orçamento e o mesmo estoque.

> Toda alteração declara a revisão de estado que espera encontrar. Se outra decisão mudou o estado antes, a operação é recusada. É isso que impede aplicar uma proposta desatualizada. A alteração e a auditoria entram na mesma transação, então não existe gravação pela metade.

> Também há idempotência. A mesma operação com o mesmo conteúdo devolve o resultado já gravado. Já o mesmo identificador com conteúdo diferente é tratado como conflito.

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

> Os testes determinísticos cobrem regras, limites, persistência e concorrência. O Hypothesis gera sequências de operações para achar casos extremos. A última regressão completa foi em 16 de novembro, com 804 aprovados. Depois da troca para o Exa, rodei 77 testes direcionados de pesquisa, não a suíte inteira. Os testes de integração exercitam o servidor MCP real por stdio.

> Nos evals do agente, eu não olho só a resposta escrita: confiro as ferramentas chamadas e o estado persistido. São 18 casos no recorte CLI assistido, com a revisão delegada declarada.

> Em 17 de novembro, preparei o REAL com a planilha original até o `check`, e fiz o ensaio completo no Desktop em SIMULATION. A conversa REAL completa no Desktop ainda falta, e eu não a apresento como feita.

> A CI roda o núcleo em Windows, Ubuntu e macOS, mas não instala o Hermes nem um modelo.

### {{icon scale}}A5 — Trade-offs

> Escolhi uma arquitetura local porque o desafio não pedia backend distribuído, outro orquestrador ou uma interface própria. Isso trouxe simplicidade e me deixou testar as regras sem depender do LLM.

> Os custos também são claros. A aprovação externa adiciona passos, e o ensaio mostrou isso. A pesquisa por termos liberados dá menos liberdade. A integração depende da versão do Hermes e dos hooks, e por isso o plugin recusa outra versão. O Exa anônimo evita pedir chave ao avaliador, mas tem cota e disponibilidade que eu não controlo, e eu preferi falhar de forma explícita a cair numa busca livre.

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
| Por que não mostrar tudo do zero em oito minutos? | A jornada completa exige várias manifestações e atestações e, no ensaio, levou mais de uma hora. A demo rápida consulta um atendimento REAL preparado antes, sem novas propostas nem aprovações ao vivo. A jornada completa continua no guia interativo para validação técnica. |
| O que ainda não está homologado? | A jornada completa no Desktop com a planilha original no perfil REAL. O ensaio completo de 17/11 foi em `SIMULATION`, com planilha sintética; a preparação REAL foi conferida até `check`. CI não instala o Hermes nem um modelo. [Registro E2E](../verification-desktop-e2e.md). |
| O E2E foi autônomo? | Não. Duas propostas corretivas da adaptação foram preparadas pela operação, fora da conversa, depois de recusas `SOURCE_NOT_LINKED`; o primeiro aceite foi recusado por falta de interesse registrado; a pesquisa do perfil `SIMULATION` foi configurada manualmente. Nenhuma aprovação foi feita pelo agente. [Intervenções](../verification-desktop-e2e.md#intervenções-operacionais). |
