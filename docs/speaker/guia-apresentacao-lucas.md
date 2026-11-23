# Sabor da Maria — guia para a conversa com Lucas Rolim & Hildebrando Azevedo

**Glaucia Lemos · meta de 17–20 minutos de fala + demonstração ao vivo.**
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

Total sugerido: cerca de 17 minutos de fala (meta máxima de 20 minutos), mais cerca de 8 minutos da demo rápida após o slide 11. As janelas são referências, não requisitos do desafio. Use as falas como pontos de ancoragem, sem repetir todo o texto do slide. Reserve o restante para perguntas e apêndice.

Priorize os slides 4, 6, 8, 9, 10 e 12, que sustentam arquitetura e evidências. Se o tempo apertar, encurte os slides 5 e 7, mas preserve a distinção REAL/SIMULATION e os fluxos 2 e 3. Abra o apêndice só se solicitado. Nas perguntas, comece pelo controle já implementado, explique o motivo e o trade-off, e só então descreva a evolução proposta.

As linhas em itálico dentro das falas são notas de revisão, não texto para falar.

## 1 — Capa · 30 s

**Fala:**

> Olá, Lucas e Hildebrando. Obrigada pelo tempo de vocês. Hoje apresento o Sabor da Maria, desenvolvido para o desafio de Senior AI Engineer do iFood.

> Minha tese é separar a conversa da decisão: o modelo pode errar, mas não deve conseguir aplicar uma decisão que viole as regras do negócio.

> Vou mostrar o problema, a arquitetura, os fluxos, uma demonstração no Hermes Desktop e as evidências. Depois, abrimos para perguntas. Fiquem à vontade para interromper.

## 2 — O que é o desafio? · 60 s

**Fala:**

> A Dona Maria está abrindo o primeiro delivery. Recebemos uma planilha com duas abas, estoque e preços, e 37 ingredientes. O desafio fixa R$ 80 para complementos e uma taxa de 10% sobre a venda.

> A jornada tem quatro etapas: pesquisar receitas reais e ouvir o feedback; descobrir se ela consegue produzir; comparar faltantes com o orçamento; e, depois do aceite, calcular o CMV e apresentar cenários de preço.

> O coração do desafio é a viabilidade real da cozinha. A decisão final continua sendo da Dona Maria.

## 3 — Qual problema resolve? · 60 s

**Fala:**

> Uma resposta errada aqui pode virar prejuízo. Recomendar uma receita de forno para quem não tem forno, tratar os R$ 80 como verba por prato ou calcular a taxa sobre o custo são erros com efeito financeiro.

> Com uma LLM, há ainda o risco de confundir um interesse com um aceite. Em vez de tentar garantir que o modelo nunca erre, construí controles para impedir que erros desse tipo alterem indevidamente o estado do negócio.

## 4 — Solução escolhida · 75 s

**Fala:**

> O Hermes era um requisito do desafio. Aproveitei seu runtime, skills, plugins e MCP para concentrar a engenharia no domínio.

> O agente conversa, pesquisa e propõe. Um serviço Python, exposto por MCP via stdio, valida viabilidade, orçamento e preço. SQLite persiste fatos, receitas, decisões e auditoria.

> A Dona Maria decide; um processo independente aplica as propostas autorizadas. Assim consigo testar as regras sem chamar uma LLM. A separação é de autoridade, não apenas de componentes.

## 5 — Por que essa solução? · 75 s

**Fala:**

> Escolhi regras determinísticas para os cálculos, Decimal para dinheiro e arredondamento para cima no piso. A memória automática do Hermes fica desligada: o estado de negócio vem do SQLite, não do contexto conversacional.

> Restringi a pesquisa e as ferramentas e separei proposta de aprovação. Isso reduz a superfície de ação do modelo, sem prometer eliminar alucinações.

> Mantive a execução local para tornar o protótipo reproduzível. O trade-off é menos flexibilidade e mais atrito operacional, em troca de invariantes verificáveis.

## 6 — Arquitetura · 85 s

**Fala:**

> À esquerda, a Dona Maria conversa com Hermes Desktop, orientado pelo arquivo .hermes.md e pela skill. Dentro do host, dois plugins controlam o catálogo e a pesquisa Exa. O plugin de política também verifica se a ferramenta pedida é a executada.

> No centro, seis tools MCP dão acesso ao serviço Python; duas tools de pesquisa completam o catálogo. O domínio valida as regras e o SQLite guarda o estado.

> Na parte de baixo, a CLI importa a planilha e atesta propostas sem passar pelo MCP. A linha tracejada indica a manifestação no chat, não uma conexão técnica. O agente não possui ferramenta de aprovação.

> Em produção, substituiria o terminal por uma interface autenticada no chat, com a confirmação enviada diretamente ao backend, fora da LLM.

**Aponte:** o diagrama da esquerda para a direita e depois a faixa de baixo. A aprovação é outro processo, sem tool para o modelo.

## 7 — Fluxo 1 · Despensa → candidatas · 65 s

**Fala:**

> O setup-real importa os 37 ingredientes, relacionando estoque e preço para calcular custos unitários. Preço ou conversão ausente vira pendência, nunca zero.

> O Hermes consulta a despensa e pesquisa pelo Exa com termos liberados. A fonte original fica registrada e o conteúdo externo é tratado como dado não confiável.

> Mesmo se uma página tentar instruir o modelo a ignorar os R$ 80, o catálogo restrito, o guard de orçamento e a aprovação externa limitam o efeito. Uma recomendação enganosa ainda é possível; por isso segurança não se resume ao prompt.

## 8 — Fluxo 2 · Elicitação e viabilidade · 80 s

**Fala:**

> A receita exige equipamento, técnica, tempo e condições de operação na escala do plano. Uma panela sem capacidade informada é UNKNOWN; se ela é menor que a exigida, o requisito é BLOCKED. O primeiro caso pede esclarecimento; o segundo exige adaptação ou outra receita.

> Só com os requisitos confirmados a receita pode ficar ELIGIBLE. Em seguida, o domínio soma os faltantes de todos os pratos, considerando pacotes inteiros e frete. Os R$ 80 são um teto compartilhado.

> O aceite exige viabilidade e compras confirmadas. Esse fluxo demonstra por que uma conversa adaptativa pode ajudar: as próximas perguntas dependem dos dados que ainda faltam.

**Aponte:** o exemplo da panela. Desconhecido vira pergunta, impeditivo bloqueia o aceite.

## 9 — Fluxo 3 · Proposta e aprovação · 95 s

**Fala:**

> Se a Dona Maria disser que aceita um prato, o Hermes registra a manifestação via propose_user_change. A proposta fica pendente com hash e revisão esperada; o estado ainda não muda.

> A operadora confere a fidelidade à manifestação e atesta pela CLI. Ela não decide pela Dona Maria. O domínio revalida o conteúdo, a expiração de dez minutos, a revisão e as regras de negócio.

> Se algo falha, nada é aplicado. Se passa, decisão e auditoria são gravadas na mesma transação. Idempotência e revisão protegem contra replay e concorrência. Na SIMULATION, o primeiro aceite foi recusado por falta de interesse registrado.

> O custo é a fricção da confirmação externa; o benefício é impedir a autoaprovação do agente. Uma interface autenticada pode remover a operadora intermediária sem remover essa fronteira de confiança.

**Destaque:** a Dona Maria decide. A operadora atesta, sem substituí-la. O domínio revalida antes de aplicar.

## 10 — Fluxo 4 · CMV e preço · 90 s

**Fala:**

> O CMV é o custo dos ingredientes consumidos por porção; o orçamento considera o pacote inteiro comprado. São grandezas diferentes.

> A taxa de 10% incide sobre a venda. Portanto, o piso é CMV dividido por 0,90. Com CMV de R$ 10, o piso arredondado para cima é R$ 11,12.

> Os cenários M10, M20 e M30 ficam em R$ 12,50, R$ 14,29 e R$ 16,67. Não chamo a sobra de lucro líquido porque faltam embalagem, energia e mão de obra.

> A Dona Maria escolhe o cenário ou um preço próprio acima do piso; a escolha passa pela mesma aprovação.

## 11 — Demonstração · 65 s

**Fala:**

> Agora vou mostrar cinco cenas, somente de consulta, no perfil REAL preparado com a planilha original: despensa, fonte Exa, adaptação e plano, viabilidade e aprovações externas.

> No ensaio REAL de 17 de novembro, cinco decisões foram aprovadas e uma nova sessão retomou o estado. A receita permaneceu PENDING porque ainda faltavam informações necessárias. Não inventei esses dados para forçar o aceite.

> Vou conferir o estado persistido, não apenas o texto do agente. A jornada completa até o preço é uma evidência distinta, em SIMULATION, que veremos no próximo slide. Vamos à demo.

**Demo rápida (~8 min, somente leitura):** abra o guia pelo link do slide, no modo Demo rápida. Cenas: 1 · despensa e orçamento (1:30) · 2 · fonte Exa registrada (1:30) · 3 · adaptação e plano (1:45) · 4 · viabilidade pendente (1:30) · 5 · aprovação humana externa (1:45). Sem comandos no terminal, sem novas propostas e sem aprovações. Ao fim da cena 5, volte ao slide 12 para preço e cardápio do ensaio SIMULATION.

## 12 — Ensaio E2E no Desktop · 70 s

**Fala:**

> Na SIMULATION de 17 de novembro, com planilha sintética, o agente percorreu pesquisa, adaptação, viabilidade, compras e preço. O resultado persistido foi M30, R$ 2,03 por porção, com CMV de R$ 1,218.

> Foi uma jornada assistida: duas correções de adaptação exigiram intervenção operacional após SOURCE_NOT_LINKED; o primeiro aceite foi recusado e a pesquisa foi configurada manualmente. Não é evidência de autonomia geral.

> Além desse ensaio, a regressão documentada registra 948 testes aprovados e dois ignorados, com CI em três sistemas operacionais. Há também 18 casos de Agent Evals em CLI assistido, auditando ferramentas e estado. Cada camada verifica algo diferente; ainda não medi uma taxa de alucinação nem comparei modelos de forma controlada.

**Cuidado:** números de SIMULATION com planilha sintética. Não os apresente como resultado da planilha original nem chame a sobra de lucro.

## 13 — O que pode virar melhoria? · 80 s

**Fala:**

> Os testes revelaram duas prioridades: melhorar a recuperação do agente quando o domínio rejeita uma adaptação sem fonte, e tornar a elicitação mais clara. Já corrigi a mensagem de compras que confundia base cru/cozido com unidade.

> Também reduziria o atrito da aprovação, ampliaria as candidatas da pesquisa e incluiria os custos operacionais na precificação. Preferências semânticas exigem confirmação, não suposição.

> Nos evals, compararia modelos e estratégias com perfis variados, dados contraditórios e ataques de prompt injection. Mediria conclusão da tarefa, violações de regras, afirmações sem evidência, latência e custo.

## 14 — Próximos passos · 65 s

**Fala:**

> Para produção, começaria por identidade e autorização: confirmação autenticada por restaurante, enviada diretamente ao backend. Preservaria expiração, idempotência, concorrência e auditoria.

> Depois, isolamento multi-tenant e reavaliação de SQLite e MCP local. Instrumentaria traces de ferramentas, pontos de abandono e custo por jornada; colocaria os evals de conversa na CI. Só então integraria a publicação de cardápios e preços.

> Validaria também o valor do agente contra um formulário guiado: taxa de conclusão, tempo até cardápio válido, abandono e custo. Se o formulário for superior, não insistiria na IA conversacional.

## 15 — Agradecimentos · 30 s

**Fala:**

> Para resumir: o modelo pesquisa, conversa e propõe; o domínio valida as regras; a Dona Maria decide, e só decisões confirmadas alteram o estado do negócio.

> O repositório documenta a implementação, as evidências e os limites da solução. Lucas e Hildebrando, obrigada pela conversa. Fico à disposição para as perguntas.

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

> Os testes determinísticos cobrem regras, limites, persistência e concorrência. O Hypothesis gera sequências de operações para achar casos extremos. A última regressão completa foi em 17 de novembro, com 948 aprovados e 2 ignorados, e a CI passou em Windows, Ubuntu e macOS. Os testes de integração exercitam o servidor MCP real por stdio.

> Nos evals do agente, eu não olho só a resposta escrita: confiro as ferramentas chamadas e o estado persistido. São 18 casos no recorte CLI assistido, com a revisão delegada declarada.

> Em 17 de novembro, conversei no Desktop com o perfil REAL e a planilha original. Foram pesquisa Exa real, receita web e adaptação, fatos da cozinha, plano e cinco aprovações locais, além de uma conversa nova que retomou tudo pelo SQLite. A jornada parou antes do aceite por falta de dados medidos. O ensaio completo até o preço foi em SIMULATION. Eu separo as duas evidências.

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
| Por que não LangGraph/Pydantic AI? | Hermes era requisito; runtime, MCP, skills e plugins aceleraram o protótipo. A recuperação após `SOURCE_NOT_LINKED` exigiu intervenção. LangGraph permitiria controle explícito de transições e retries, com mais código e manutenção. A escolha em produção depende dos requisitos e evals. Pydantic é usado para contratos, não Pydantic AI. |
| Como tratar preço faltante com alimento em estoque? | Disponibilidade e custo são independentes; readiness financeiro bloqueia a decisão definitiva. [cost_readiness.py](../../src/dona_maria/cost_readiness.py). |
| Uma nova sessão esquece as restrições? | A abertura consulta o mesmo workspace; revisão e decisões vêm do SQLite. Memória do LLM não é autoridade. [business_state.py](../../src/dona_maria/business_state.py). |
| Como escalar para multiusuário? | Aprovação autenticada na UI, diretamente ao backend, sem tool de aprovação para o modelo; preservar revisão, expiração, idempotência, transação e auditoria. Autorização e isolamento por restaurante, armazenamento concorrente, observabilidade e gestão de segredos. Trocar SQLite por PostgreSQL não resolve tudo. |
| Qual modelo teve melhor resultado? | Não há comparação controlada suficiente para declarar vencedor. Registre modelo/provider/versão e assistência de cada execução; não derive ranking de uma demo. |
| Por que não mostrar tudo do zero em oito minutos? | A jornada completa exige várias manifestações e atestações e, no ensaio, levou mais de uma hora. A demo rápida consulta um atendimento REAL preparado antes, sem novas propostas nem aprovações ao vivo. A jornada completa continua no guia interativo para validação técnica. |
| O que ainda não está homologado? | Aceite, CMV e preço com a planilha original. A jornada REAL de 17/11 foi até a viabilidade `PENDING`; o ensaio completo até o preço foi em `SIMULATION`. CI não instala o Hermes nem um modelo. [Jornada REAL](../verification-desktop-real.md), [jornada SIMULATION](../verification-desktop-e2e.md). |
| Por que o REAL parou? | Base cru/cozido `UNKNOWN` nas 9 linhas (o plano só soma linhas `RAW`), água sem custo, quatro lacunas declaradas na receita (tempo, peso da porção, requisitos, base) e interesse não registrado. Nenhum desses dados podia ser inventado. [planning.py](../../src/dona_maria/planning.py). |
| Por que o agente não mostrou o saldo de R$ 80? | Com demanda incompleta, `remaining_budget` é `null`. Mostrar R$ 80 seria afirmar que nada precisa ser comprado. O agente disse que não conseguia confirmar o saldo, que é o comportamento esperado. |
| Quanto daria o prato REAL? | Uma estimativa manual com os custos da planilha dá cerca de R$ 1,98 de ingredientes por porção e piso de R$ 2,21. Não é evidência: só a ferramenta, depois do aceite, calcula o valor oficial. O número também mostra por que chamo a diferença de sobra, e não de lucro. |
| Como você avalia o agente, e não só o código? | Agent Evals com cenário, tools chamadas e estado persistido; a resposta escrita sozinha não aprova. Falhas e tentativas ficam preservadas. O próximo passo é rodar os mesmos casos em outros modelos e na CI. [evals/README.md](../../evals/README.md). |
| E custo e latência? | Não medi de forma controlada. A arquitetura reduz o que o modelo precisa fazer (a matemática e as regras ficam no Python), mas o agente consulta o estado muitas vezes: 26 `get_business_state` no ensaio SIMULATION. Eu instrumentaria tokens, chamadas por etapa e tempo até a decisão. |
| Como observar isso em produção? | Logs estruturados já registram tool, resultado e duração por chamada MCP, sem dados privados. Faltam traces por atendimento, métricas de travamento por etapa e custo por conversa. |
| O que faria com mais duas semanas? | Concluir o REAL até o preço com dados medidos; simplificar o contrato de revisão de receita, que causou as recusas `SOURCE_NOT_LINKED`; trazer duas ou três candidatas por busca; comparar modelos nos evals; trocar o terminal por uma revisão autenticada. |
| O E2E foi autônomo? | Não. Duas propostas corretivas da adaptação foram preparadas pela operação, fora da conversa, depois de recusas `SOURCE_NOT_LINKED`; o primeiro aceite foi recusado por falta de interesse registrado; a pesquisa do perfil `SIMULATION` foi configurada manualmente. Nenhuma aprovação foi feita pelo agente. [Intervenções](../verification-desktop-e2e.md#intervenções-operacionais). |
| Por que agente em vez de formulário? | A elicitação é adaptativa: perguntas dependem das lacunas de cada cozinha. Ainda não há comparação controlada. Mediria taxa de conclusão, tempo até cardápio válido, abandono e custo por jornada; escolheria o formulário se entregar melhores resultados. |
| Como comprovar redução de alucinação? | Não há taxa comparativa medida. Os testes demonstram controles de domínio, não ausência de alucinação. Criaria dataset com diferentes perfis, contradições, dados ausentes e ataques; repetiria execuções por modelo e mediria afirmações sem evidência, precisão de tools, conclusão e violações de regras. |
| E se uma receita web mandar ignorar o orçamento? | Conteúdo externo é dado não confiável; pesquisa e catálogo restritos, validação determinística do teto agregado e ausência de tool de aprovação limitam o impacto mesmo com o modelo enganado. Riscos residuais: recomendações falsas ou persuasivas e falhas fora dos contratos. Complementaria com adversarial evals e regressão. |
