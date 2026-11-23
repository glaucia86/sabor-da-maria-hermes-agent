# Sabor da Maria — guia para a conversa com Lucas Rolim & Hildebrando Azevedo

**Glaucia Lemos · 17 a 20 minutos de apresentação + 13 a 15 minutos de demonstração ao vivo.**
Compartilhe o deck e deixe este guia, o [roteiro da demo](demo-hermes.md) e o guia
interativo, no modo Demo ao vivo, na outra tela. A fala de cada slide também está nas notas
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
| 11 · Evidências | 11:55–13:25 | 90 s | REAL 19/11 e SIMULATION 17/11 até o preço, com intervenções registradas |
| 12 · O que pode virar melhoria? | 13:25–14:50 | 85 s | Achados de 19/11 e evoluções |
| 13 · Próximos passos | 14:50–15:55 | 65 s | Confiança antes da escala |
| 14 · Demonstração | 15:55–16:40 | 45 s | Transição para a demo ao vivo |
| Demo ao vivo | a partir de 16:40 | 13–15 min | 10 cenas, 6 aprovações ([roteiro](demo-hermes.md)) |
| 15 · Agradecimentos | depois da demo | 30 s | Frase de síntese e perguntas |
| A1–A5 · Apêndice | sob demanda | — | Invariantes, persistência, segurança, verificação, trade-offs |

Reserve **17 min 10 s para os 15 slides**, incluindo os 30 segundos do slide final, e até 2 min 50 s para perguntas durante a exposição. A demo ao vivo ocupa uma janela de 13 a 15 minutos à parte. Use o tempo de cada slide para falar, apontar os elementos do deck e percorrer os exemplos.

Priorize os slides 4, 6, 8, 9, 10 e 11. Se o tempo apertar, encurte os slides 5, 7 e 12, preservando os fluxos de viabilidade e aprovação e os resultados de REAL e SIMULATION. Use os atalhos de tempo da demo previstos no [roteiro](demo-hermes.md#se-o-tempo-apertar).

Para as perguntas, comece pelo controle já implementado, diga que evidência o sustenta e explique o custo da escolha antes de propor uma evolução.

## 1 — Capa · 30 s

**Fala:**

> Olá, Lucas e Hildebrando. Obrigada pelo tempo de vocês. Hoje apresento o Sabor da Maria, desenvolvido para o desafio de Senior AI Engineer do iFood.

> Minha tese é separar a conversa da decisão. O modelo pode errar, e o domínio impede que uma proposta fora das regras altere o negócio.

> Vou mostrar o problema, a arquitetura, os fluxos, as evidências e os próximos passos. No fim, faço a demonstração ao vivo no Hermes Desktop, da pesquisa ao preço. Fiquem à vontade para interromper.

## 2 — O que é o desafio? · 60 s

**Fala:**

> A Dona Maria está abrindo o primeiro delivery. Recebemos uma planilha com duas abas, estoque e preços, e 37 ingredientes. O desafio fixa R$ 80 para complementos e uma taxa de 10% sobre a venda.

> A jornada tem quatro etapas. Primeiro, pesquisar receitas reais e ouvir o feedback. Depois, descobrir se ela consegue produzir e comparar os faltantes com o orçamento. Após o aceite, calcular o CMV e apresentar cenários de preço.

> O coração do desafio é a viabilidade real da cozinha. A decisão final continua sendo da Dona Maria.

## 3 — Qual problema resolve? · 60 s

**Fala:**

> Uma resposta errada aqui pode virar prejuízo. Recomendar uma receita de forno para quem não tem forno, tratar os R$ 80 como verba por prato ou calcular a taxa sobre o custo são erros com efeito financeiro.

> O modelo também pode confundir interesse com aceite. Os controles impedem que essa interpretação, por si só, altere o estado do negócio.

## 4 — Solução escolhida · 75 s

**Fala:**

> O Hermes era um requisito do desafio. Aproveitei seu runtime, skills, plugins e MCP para concentrar a engenharia no domínio.

> O agente conversa, pesquisa e propõe. Um serviço Python, exposto por MCP via stdio, valida viabilidade, orçamento e preço. SQLite persiste fatos, receitas, decisões e auditoria.

> A Dona Maria decide. A operadora confere a proposta e a atesta em um processo separado, e o domínio revalida antes de aplicar. Essa divisão de autoridade me permite testar as regras sem chamar uma LLM.

## 5 — Por que essa solução? · 75 s

**Fala:**

> Os cálculos seguem regras determinísticas, usam Decimal e arredondam o piso para cima. A memória automática do Hermes fica desligada. O estado de negócio vem do SQLite e pode ser retomado em outra sessão.

> O catálogo fechado, a pesquisa por termos liberados e a aprovação externa limitam o efeito de erros do modelo. A fonte original fica registrada para conferência.

> Mantive a execução local para tornar o protótipo reproduzível. A aprovação externa acrescenta etapas e a pesquisa restrita reduz a flexibilidade. Em troca, consigo testar os limites do que o agente pode aplicar.

## 6 — Arquitetura · 85 s

**Fala:**

> À esquerda, a Dona Maria conversa com o Hermes Desktop, orientado pelo `.hermes.md` e pela skill. Dentro do host, um plugin controla o catálogo e confere se a ferramenta pedida é a executada. O outro expõe duas ferramentas de pesquisa via Exa.

> No centro, seis ferramentas MCP dão acesso ao serviço Python. O domínio valida as regras e o SQLite guarda o estado.

> A faixa de baixo mostra o caminho da operadora. Um processo separado importa a planilha e atesta pela CLI, sem passar pelo MCP. A linha tracejada indica a manifestação no chat. O agente não possui ferramenta de aprovação.

> Em produção, eu usaria uma interface autenticada com confirmação enviada diretamente ao backend, fora do alcance do modelo.

**Aponte:** o diagrama da esquerda para a direita e depois a faixa de baixo. A aprovação é outro processo, sem tool para o modelo.

## 7 — Fluxo 1 · Despensa → candidatas · 65 s

**Fala:**

> O `setup-real` importa os 37 ingredientes e relaciona estoque e preço para calcular custos unitários. Cinco quilos de arroz por R$ 24,90 dão cerca de meio centavo por grama. Preço ou conversão ausente vira pendência.

> O Hermes consulta a despensa e pesquisa pelo Exa com termos liberados. A fonte original fica registrada e o conteúdo externo é tratado como dado não confiável.

> Se uma página tentar induzir o modelo a ignorar os R$ 80, o catálogo restrito, a validação do orçamento e a aprovação externa limitam o efeito. A resposta do modelo ainda pode ser enganosa. Por isso, confiro a fonte e o resultado das ferramentas.

## 8 — Fluxo 2 · Elicitação e viabilidade · 80 s

**Fala:**

> A receita exige equipamento, técnica, tempo e condições de operação na escala do plano. Para uma receita que pede uma panela de três litros, uma panela sem capacidade informada deixa o requisito `UNKNOWN`. Se ela tem dois litros, o requisito fica `BLOCKED`. O primeiro caso pede esclarecimento. O segundo exige adaptação ou outra receita.

> Só com os requisitos confirmados a receita pode ficar `ELIGIBLE`. Em seguida, o domínio soma os faltantes de todos os pratos, considerando pacotes inteiros e frete. Os R$ 80 são um teto compartilhado.

> O aceite exige viabilidade e compras confirmadas. A conversa é adaptativa porque as próximas perguntas dependem dos dados que ainda faltam.

**Aponte:** o exemplo da panela. Desconhecido vira pergunta, impeditivo bloqueia o aceite.

## 9 — Fluxo 3 · Proposta e aprovação · 95 s

**Fala:**

> Quando a Dona Maria diz que aceita um prato, o Hermes registra a manifestação com `propose_user_change`. A proposta fica pendente com hash e revisão esperada. O estado ainda não muda.

> A operadora confere se a proposta corresponde ao que a Dona Maria disse e atesta pela CLI. O domínio revalida o conteúdo, o prazo de dez minutos, a revisão e as regras de negócio.

> No REAL, a operadora deixou sem atestação um plano proposto antes de a Dona Maria confirmar a quantidade. Na SIMULATION, o domínio recusou o primeiro aceite porque faltava o interesse. São duas barreiras diferentes.

> Quando a proposta passa, decisão e auditoria são gravadas na mesma transação. Idempotência e revisão evitam efeitos duplicados e a aplicação de propostas desatualizadas. Uma interface autenticada pode simplificar a confirmação mantendo essa fronteira fora do agente.

**Destaque:** percorra as quatro etapas do diagrama e indique onde cada recusa aconteceu. A operadora atesta a manifestação da Dona Maria e o domínio revalida antes de aplicar.

## 10 — Fluxo 4 · CMV e preço · 90 s

**Fala:**

> O orçamento considera o pacote inteiro comprado. No CMV entra a quantidade de ingredientes que cada porção consome. Se compro um quilo e uso duzentos gramas na receita, são duzentos gramas no custo do lote.

> A taxa de 10% incide sobre a venda. O piso é o CMV dividido por 0,90, arredondado para cima. Com CMV de R$ 10, o piso é R$ 11,12. Após a taxa e os ingredientes, sobra um centavo.

> Os cenários M10, M20 e M30 ficam em R$ 12,50, R$ 14,29 e R$ 16,67. A sobra ainda precisa cobrir embalagem, gás, energia e mão de obra.

> A Dona Maria escolhe um cenário ou informa um preço próprio a partir do piso. A escolha passa pela mesma aprovação.

**Aponte:** percorra o diagrama da compra ao preço. Mostre onde entra o pacote inteiro, faça a conta do piso e compare a sobra nele com a dos três cenários.

## 11 — Evidências · Jornadas completas · 90 s

**Fala:**

> À esquerda está o REAL de 19 de novembro, com a planilha original, no Desktop e no CLI. Após a pesquisa pelo Exa, registrei uma receita própria com os ingredientes crus e as três categorias revisadas. A receita ficou elegível e o estoque cobriu tudo. O desembolso foi zero e o saldo ficou em R$ 80.

> Depois do aceite, o CMV foi de R$ 2,42 por porção, o piso de R$ 2,69 e a escolha M20 de R$ 3,46. Foram seis aprovações locais em cada ensaio. Eu interpretei a cozinheira com dados de demonstração. No Desktop, pedi nova pesquisa quando o Exa oscilou e solicitei que o agente refizesse propostas.

> À direita está a SIMULATION de 17 de novembro, com planilha sintética. O CMV foi de R$ 1,218, e o M30 de R$ 2,03 por porção ficou gravado. A operação preparou duas correções após `SOURCE_NOT_LINKED` e configurou a pesquisa manualmente. Os bancos são separados.

> A regressão documentada de 19 de novembro registrou 998 testes aprovados e 4 ignorados. Os 18 Agent Evals em CLI assistido verificam as ferramentas chamadas e o estado persistido. Ainda falta comparar modelos em condições controladas.

**Aponte:** compare os dois resultados gravados e as intervenções em cada coluna. [REAL de 19/11](../verification-desktop-real-complete.md), [SIMULATION de 17/11](../verification-desktop-e2e.md) e [regressão local](../testing.md).

## 12 — O que pode virar melhoria? · 85 s

**Fala:**

> No REAL, o agente criou propostas na mesma revisão e antecipou o plano. A prioridade é propor uma decisão por vez, depois da confirmação. No ensaio no Desktop, uma proposta expirou e a CLI de aprovação exibiu uma mensagem que dificultou a recuperação.

> Para a pesquisa, eu usaria termos de prato e avaliaria trazer duas ou três candidatas com os mesmos controles. Na SIMULATION, duas correções de adaptação exigiram intervenção. Quero melhorar o contrato da ferramenta e a skill para preservar o vínculo com a fonte.

> Também incluiria custos operacionais no preço. Nos evals, compararia modelos com perfis variados, dados contraditórios e tentativas de prompt injection. Mediria conclusão, violações de regras, afirmações sem evidência, latência e custo.

## 13 — Próximos passos · 65 s

**Fala:**

> Começaria por identidade e autorização. A confirmação autenticada por restaurante iria direto ao backend, preservando expiração, revisão, idempotência e auditoria.

> Depois, isolaria dados por restaurante e reavaliaria SQLite e MCP local. Instrumentaria chamadas, abandono e custo por jornada, e levaria os evals de conversa à CI. Só então integraria a publicação de cardápios e preços.

> Também compararia a conversa adaptativa com um formulário guiado. Mediria conclusão, tempo até um cardápio válido, abandono e custo para escolher a interface.

**Aponte:** avance pelas cinco etapas da linha do tempo e explique por que cada uma vem antes da publicação de cardápios.

## 14 — Demonstração · 45 s + demo ao vivo (13–15 min)

**Fala:**

> Agora vou abrir um atendimento REAL novo, preparado com a planilha original. Faço o papel da Dona Maria no Desktop e o da operadora no terminal.

> Em 10 cenas e 13 a 15 minutos, vamos da pesquisa à escolha do preço, com seis aprovações locais. Confiro cada proposta antes de atestar e verifico o resultado no estado gravado.

> Se a pesquisa ou o modelo oscilar, vou explicar o que aconteceu e seguir o plano de recuperação do roteiro.

**Demo ao vivo:** siga o [roteiro da demo](demo-hermes.md) ou o modo **Demo ao vivo** do [guia interativo](../demo/hermes-desktop-walkthrough.html). São 10 cenas, 6 aprovações e 13 a 15 minutos. Ao fim, volte ao slide 15.

## 15 — Agradecimentos · 30 s

**Fala:**

> O modelo conversa, pesquisa e propõe. O domínio valida as regras, a Dona Maria decide, e só decisões confirmadas alteram o negócio.

> O repositório reúne a implementação, as evidências e os limites da solução. Lucas e Hildebrando, obrigada pela conversa. Fico à disposição para as perguntas.

### Apêndice

> Estes slides ficam como apoio para as perguntas. Eu abro só o que for útil para a discussão.

> São cinco temas: invariantes, persistência, segurança, verificação e trade-offs.

### A1 — Invariantes

> Estas são as regras que nenhuma conversa contorna, porque estão no domínio e não no prompt.

> Os R$ 80 são um teto único para todos os pratos, contando pacote inteiro e encargos. A taxa de 10% incide sobre a venda. É premissa do desafio, não uma afirmação sobre contratos reais do iFood. E os cálculos usam Decimal, com o preço sempre arredondado para cima em centavos.

> Informação ausente não vira zero. Desconhecido gera pergunta, impeditivo bloqueia o aceite, e custo incompleto impede aceite e preço definitivos. Se uma premissa muda, como a receita ou o rendimento, as decisões que dependiam dela deixam de valer.

> Por fim, REAL e SIMULATION ficam em bancos separados. Foi isso que permitiu fazer o ensaio com dados hipotéticos sem nenhuma chance de eles virarem fato real.

### A2 — Domínio e persistência

> A unidade de consistência é o workspace: o conjunto de receitas, plano, fatos e escolhas que dividem o mesmo orçamento e o mesmo estoque.

> Toda alteração declara a revisão de estado que espera encontrar. Se outra decisão mudou o estado antes, a operação é recusada. É isso que impede aplicar uma proposta desatualizada. A alteração e a auditoria entram na mesma transação, então não existe gravação pela metade.

> Também há idempotência. A mesma operação com o mesmo conteúdo devolve o resultado já gravado. Já o mesmo identificador com conteúdo diferente é tratado como conflito.

> A planilha importada nunca é reescrita. Correções viram versões e camadas, preservando a origem de cada dado, como aconteceu com a receita web e a adaptação no ensaio.

> SQLite resolve bem o protótipo local. Com vários operadores e acesso remoto, eu reavaliaria o armazenamento.

### A3 — Segurança

> Em segurança, a ideia foi reduzir o que o modelo consegue fazer e validar tudo no ponto onde a ação teria efeito.

> No Hermes, o catálogo é fechado: seis ferramentas MCP e duas de pesquisa. Durante o desenvolvimento, encontrei um risco no reparo de nomes de ferramentas do host: uma chamada proibida podia acabar redirecionada para uma ferramenta permitida. Por isso, o plugin de política compara o nome pedido com o executado e bloqueia a divergência. Memória automática e perfil de usuário ficam desligados.

> No Python, banco e workspace são fixados pelo operador, os schemas recusam campos extras e a aprovação não existe como ferramenta do modelo.

> Na pesquisa, o Exa é chamado pelo endpoint anônimo, com um resultado por busca e sem fallback para outro provedor. Não há consulta nem URL livre, e a extração tem limites de redirect, de volume e de destino. Na planilha, há limites de tamanho, e as células são sempre tratadas como dados.

> A limitação que eu deixo explícita: um perfil isolado do Hermes não é uma sandbox do sistema operacional. Em produção, eu reforçaria identidade e permissões por processo.

### A4 — Verificação

> Em 19 de novembro, a regressão registrou 998 testes aprovados e 4 ignorados. Pytest e Hypothesis cobrem regras, limites, persistência e concorrência, e os testes de integração exercitam o MCP real por stdio.

> Nos 18 Agent Evals, a execução foi assistida pela CLI e a revisão foi delegada. A verificação inclui as ferramentas chamadas e o estado persistido.

> O REAL de 19 de novembro chegou ao preço no Desktop e no CLI, com a planilha original e seis aprovações locais por ensaio. As falas da cozinheira eram de demonstração. Em 17 de novembro, o REAL ficou em `PENDING` por falta de dados confirmados. Nesse mesmo dia, a SIMULATION assistida chegou ao preço com planilha sintética.

> A CI passou em Windows, Ubuntu e macOS no commit `95a0e51`, com cobertura do núcleo e do MCP. O Hermes e o modelo são verificados nos ensaios assistidos.

### A5 — Trade-offs

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
| Por que não LangGraph/Pydantic AI? | Hermes era requisito. Seu runtime, MCP, skills e plugins deixaram a engenharia concentrar-se no domínio. A recuperação após `SOURCE_NOT_LINKED` exigiu intervenção. LangGraph permitiria explicitar transições e novas tentativas, com mais código e manutenção. Em produção, eu decidiria pelos requisitos e evals. Aqui Pydantic valida contratos. |
| Como tratar preço faltante com alimento em estoque? | Disponibilidade e custo são independentes; readiness financeiro bloqueia a decisão definitiva. [cost_readiness.py](../../src/dona_maria/cost_readiness.py). |
| Uma nova sessão esquece as restrições? | A abertura consulta o mesmo workspace; revisão e decisões vêm do SQLite. Memória do LLM não é autoridade. [business_state.py](../../src/dona_maria/business_state.py). |
| Como escalar para multiusuário? | Começaria com confirmação autenticada na interface, enviada diretamente ao backend. Preservaria revisão, expiração, idempotência, transação e auditoria. A operação exige autorização e isolamento por restaurante, armazenamento concorrente, observabilidade e gestão de segredos. |
| Qual modelo teve melhor resultado? | Não há comparação controlada suficiente para declarar vencedor. Registre modelo/provider/versão e assistência de cada execução; não derive ranking de uma demo. |
| Por que fazer a jornada inteira ao vivo? O que pode falhar? | Porque é a prova mais direta de que o fluxo funciona com a planilha original e de que cada decisão passa pela aprovação local. Pode falhar a pesquisa (Exa anônimo oscila), o modelo pode demorar ou criar duas propostas juntas, e uma proposta pode expirar em 10 minutos. O roteiro trata cada caso; nada é completado de memória. [Roteiro](demo-hermes.md). |
| O que ainda não está homologado? | Uma jornada com cozinheira real e medições físicas; outros modelos e sistemas operacionais no Hermes; receitas com água incorporada no REAL. A jornada REAL completa de 19/11 usou falas de demonstração. CI não instala o Hermes nem um modelo. [Jornada REAL completa](../verification-desktop-real-complete.md). |
| Por que o REAL de 17/11 parou? | Base cru/cozido `UNKNOWN` nas 9 linhas (o plano só soma linhas `RAW`), água sem custo, quatro lacunas declaradas na receita (tempo, peso da porção, requisitos, base) e interesse não registrado. Nenhum desses dados podia ser inventado. [planning.py](../../src/dona_maria/planning.py). |
| Por que o agente não mostrou o saldo de R$ 80? | No REAL de 17/11, a demanda incompleta deixou `remaining_budget` como `null`. Mostrar R$ 80 como saldo confirmado teria presumido compras zero. No REAL de 19/11, o domínio confirmou compras de R$ 0 e saldo de R$ 80. [REAL de 17/11](../verification-desktop-real.md), [REAL de 19/11](../verification-desktop-real-complete.md). |
| Quanto deu o prato REAL? | No frango acebolado de 19/11, a ferramenta calculou depois do aceite: lote de R$ 9,6811 (600 g de frango × R$ 0,014 + 200 g de cebola × R$ 0,004 + 10 g de alho × R$ 0,02 + 30 ml de óleo × R$ 0,009 + 6 g de sal × R$ 0,00185), CMV de R$ 2,420275 por porção, piso de R$ 2,69 e M20 de R$ 3,46, com sobra de R$ 0,69, que não é lucro. |
| Como você avalia o agente, e não só o código? | Agent Evals com cenário, tools chamadas e estado persistido; a resposta escrita sozinha não aprova. Falhas e tentativas ficam preservadas. O próximo passo é rodar os mesmos casos em outros modelos e na CI. [evals/README.md](../../evals/README.md). |
| E custo e latência? | Não medi de forma controlada. A arquitetura reduz o que o modelo precisa fazer (a matemática e as regras ficam no Python), mas o agente consulta o estado muitas vezes: 26 `get_business_state` no ensaio SIMULATION. Eu instrumentaria tokens, chamadas por etapa e tempo até a decisão. |
| Como observar isso em produção? | Logs estruturados já registram tool, resultado e duração por chamada MCP, sem dados privados. Faltam traces por atendimento, métricas de travamento por etapa e custo por conversa. |
| O que faria com mais duas semanas? | Repetir o REAL com uma cozinheira real; fazer a skill propor uma decisão por vez; simplificar o contrato de revisão de receita, que causou as recusas `SOURCE_NOT_LINKED`; trazer duas ou três candidatas por busca; comparar modelos nos evals; trocar o terminal por uma revisão autenticada. |
| O E2E foi autônomo? | Não. No REAL de 19/11, as falas da cozinheira foram minhas, pedi nova pesquisa quando o Exa falhou, propostas desatualizadas foram refeitas a pedido e o plano antecipado não foi atestado. Na SIMULATION, duas propostas corretivas foram preparadas pela operação depois de recusas `SOURCE_NOT_LINKED`, o primeiro aceite foi recusado por falta de interesse e a pesquisa do perfil foi configurada manualmente. Todas as aprovações foram locais. [REAL 19/11](../verification-desktop-real-complete.md), [SIMULATION](../verification-desktop-e2e.md#intervenções-operacionais). |
| As falas da Dona Maria são reais? | Não. Eu interpretei a cozinheira com dados de demonstração declarados na conversa. O que é real é a planilha original, a pesquisa Exa, o modelo, as tools, o banco REAL e as aprovações locais. O sistema registra essas falas como declarações (`USER_PROVIDED`), não como medições. |
| Por que agente em vez de formulário? | A elicitação é adaptativa: perguntas dependem das lacunas de cada cozinha. Ainda não há comparação controlada. Mediria taxa de conclusão, tempo até cardápio válido, abandono e custo por jornada; escolheria o formulário se entregar melhores resultados. |
| Como comprovar redução de alucinação? | Não há taxa comparativa medida. Os testes demonstram controles de domínio, não ausência de alucinação. Criaria dataset com diferentes perfis, contradições, dados ausentes e ataques; repetiria execuções por modelo e mediria afirmações sem evidência, precisão de tools, conclusão e violações de regras. |
| E se uma receita web mandar ignorar o orçamento? | Conteúdo externo é dado não confiável; pesquisa e catálogo restritos, validação determinística do teto agregado e ausência de tool de aprovação limitam o impacto mesmo com o modelo enganado. Riscos residuais: recomendações falsas ou persuasivas e falhas fora dos contratos. Complementaria com adversarial evals e regressão. |
