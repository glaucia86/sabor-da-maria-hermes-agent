# S17 — Pesquisa mediada e segurança de rede

**Status: CONCLUÍDO após HITL executado pela pessoa.** Quatro critérios verificados: pesquisa/extração RECIPE e QUOTE reais, fontes WEB, catálogo exato antes/depois do refresh, retomada/replay, dispatch MCP, 18 recusas no host e Harness estrutural. **Regressão final:673PASS/1SKIP.** A pessoa confirmou nesta conversa que o HITL já foi realizado; a pendência redundante foi removida. Nenhum commit, push, PR, merge ou S19 foi executado.

## Contexto conferido

Worktree `C:\Labs\sabor-da-maria-s17`, branch `feat/s17-mediated-research`, baseline/HEAD inicial `82c81689187d4215ed961a67f81006efee4a91c9`, árvore inicialmente limpa. As mudanças documentais do gate inicial foram preservadas. A pessoa confirmou os seams serviço/SQLite, MCP STDIO e transporte controlado antes dos testes novos.

RULES/AGENTS, Context Retrieval Contract, bloco S17 e encerramentos HITL de S13/S15 recuperados. IDs REQ-002/015, SEC-005/006, AC-023/030 e ADR-015 buscados literalmente na SPEC, com leituras delimitadas de §§3.6.1, 4.1.1, 4.7.1 e 4.8.1. Proveniência RF-02/15, RNF-04/05 e EV-18 conferida no PRD. Guias de arquitetura, desenvolvimento e testes consultados pelas fronteiras afetadas. Nenhum GLOSSARY ou grafo existente localizado.

## Interfaces entregues

O plugin registra somente:

- `search_culinary_sources(purpose=RECIPE|QUOTE, public_term_ids)`.
- `extract_culinary_source(research_result_id)`.

`ResearchService` reutiliza `AttendanceService` para validar caminho absoluto, banco existente, workspace e modo ATTENDANCE. Esses valores são settings locais, nunca argumentos do modelo. Termos publicáveis são liberados pelo operador nos settings do plugin; seu texto não pode ser alterado pela chamada do modelo. Consulta construída de termos liberados, em ordem determinística, com prefixo `receita` ou `oferta`. Extras, consulta/URL livre, termo desconhecido e limites de chamada são recusados antes da busca.

Cada pesquisa consulta novamente o provedor e cria uma observação própria, inclusive depois de uma busca vazia. Não há memoização permanente de ofertas. O plugin0.1.2 solicita um resultado ao provider; não trunca títulos nem descarta silenciosamente metadados recebidos. Qualquer resultado recebido acima dos limites continua recusado. IDs de resultados anteriores permanecem consultáveis. A extração de um ID completo tem replay estável: para uma nova observação, execute nova pesquisa. Nenhuma dessas operações consome estoque ou autoriza fatos, compras, aceite ou preço.

O MCP continua com as seis capacidades do atendimento. As duas capacidades novas pertencem ao plugin. `inspect_result` é uma leitura local do backend para evidências; não é uma terceira ferramenta do modelo. Bootstrap, migração, aprovação e diagnóstico não entram no catálogo.

## Hermes e contrato versionado

Identidade observada no `install-stamp.json`: **Hermes0.23.1**, commit **`3b421578588243f920886e6fe79a6faa87ea026e`**. `git rev-parse HEAD` da instalação confirmou o mesmo commit. A primeira tentativa teve recusa de proprietário do sandbox; a repetição com aprovação explícita funcionou, sem alterar configuração Git global.

Interfaces encontradas no código instalado e efetivamente usadas pelo adaptador:

| Interface | Uso |
| --- | --- |
| `PluginContext.get_config` | Settings privados do próprio plugin |
| `PluginContext.register_tool` | Registro das duas ferramentas assíncronas, handlers com resultado JSON textual |
| `hermes_cli.version_info.get_version_info` | Recusa de versão/commit diferentes antes do registro |
| `agent.web_search_registry._configured_backend` / `get_provider` | Seleção explícita do provedor configurado, sem autodetecção |
| Protocolo `supports_search()` / `search(query, 1)` | Busca real pelo provedor instalado, solicitando um resultado |
| `tools.url_safety.create_ssrf_safe_async_client` | Cliente HTTP do host, reforçado por pin e verificação de peer |
| Hooks `post_api_request` / `pre_tool_call` | Política existente compara nome original e efetivo; permite os dois nomes novos exatos |

Não é usado `web_search_tool`: seu wrapper instalado admite cache/rescue/fallback entre serviços. O adaptador chama somente o provedor explicitamente selecionado. Interfaces internas de registro de provedor e transporte são versionadas pelo adaptador, sem promessa de estabilidade. Formato inesperado, mounts/proxies ou versão incompatível bloqueiam a capacidade. Nenhuma alteração no core Hermes.

A [documentação oficial de plugins](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins) confirma o mecanismo; o contrato específico foi inspecionado no código instalado. Testes controlados foram complementados pelas provas reais descritas abaixo, sem confundir os dois tipos de evidência. O plugin recusa commit/versão incompatíveis; interfaces internas de provider/transporte não são tratadas como API estável.

## Controles de rede

- Apenas HTTPS, porta padrão, URL estruturalmente inequívoca e sem credenciais.
- Bloqueio de loopback, privados IPv4/IPv6, link-local/metadados, multicast, reservados/não globais e IPv4 mapeado proibido.
- Todos os endereços DNS são validados; um único endereço proibido recusa a resolução inteira. TCP recebe um IP público fixado. Peer efetivo é conferido antes de TLS/envio; divergência fecha a conexão. Host/TLS/SNI conservam o hostname original e validação de certificado.
- Redirecionamento manual: até três destinos redirecionados, cada um revalidado em novo cliente/conexão. Sem reaproveitar DNS não validado ou seguir automaticamente um destino privado.
- `trust_env=False`, sem mounts de proxy, cookies, autenticação ou headers do modelo. Somente GET e headers fixos. Sem JavaScript, sub-recursos, navegador, arquivo ou shell como alternativa.
- Prazo assíncrono de20s. Resposta até1MiB tanto nos bytes de corpo recebidos quanto após descompressão; texto até64KiB em UTF-8. Contagem pelo stream, inclusive sem Content-Length/chunked. Gzip/deflate têm saída limitada e exigem stream completo; compressão concatenada/não suportada é recusada.
- HTTP206, Content-Range, erro HTTP, corpo truncado/vazio, excesso e ausência de texto são recusados. HTML é extraído sem scripts/styles/sub-recursos; text/plain conserva seus sinais literais. Codificação não UTF-8 é recusada explicitamente.

`ExtractionRecord` exige completude verdadeira, contagens estritas dentro dos limites, hash e1–4 destinos públicos coerentes com a URL final. A persistência também exige que o primeiro destino corresponda ao resultado pesquisado. A leitura reaplica o contrato. Não se promove um texto curto com `complete=False`, contagem excessiva ou destinos ausentes a fonte completa. Erros usam códigos permitidos e mensagens fixas; exceções externas, inclusive tipadas, não são devolvidas literalmente.

## Observações e proveniência

Schema SQLite **2→3**, migração explícita `approval_cli ... migrate-research --backup ...`, sem migração no startup. Usa backup SQLite consistente e transação; recusa schema futuro/corrompido, versão de entrada errada ou backup já existente. Não regrava workspaces, decisões ou operações históricas.

Uma tabela nova, `research_observations`, guarda lotes de observação com FK de workspace, identidade de pesquisa gerada no backend, consulta construída, propósito, provedor, versão do adaptador, resultados/URLs, horários reais UTC, hashes, destinos, contagens, segmentos e estado SEARCHED/COMPLETE. Payload versionado1.0 e digest são conferidos na leitura; metadados/segmentos ausentes ou incompatíveis são recusados. A escrita do lote e a conclusão de uma extração são atômicas e conferem a revisão do workspace após a rede. Falha não grava conteúdo parcial nem altera negócio.

Na proposta vinculada, a fonte WEB nova contém somente `kind`, `research_result_id` e `segment`. Backend recupera URL, título, trecho, horário e hash da observação completa no mesmo workspace e propósito. Receipts com metadados divergentes, ID inexistente/estrangeiro, segmento inexistente, origem RECIPE usada como QUOTE ou registro incompleto são recusados. O ID não é autorização suficiente. Aprovação local existente continua necessária para aplicar a proposta; registrar uma oferta não a confirma.

`WebSource.content_sha256` é aditivo e omitido quando ausente, preservando serialização legada. Fontes antigas continuam legíveis, sem ganhar observação verificada retroativamente. Revisões conservam fontes históricas inalteradas; nova fonte exige vínculo registrado. A projeção do atendimento mostra fonte registrada sem IDs privados e distingue origem humana/legada. Origem WEB não comprova semanticamente cada afirmação do modelo nem condições da cozinha; revisão humana e guards do domínio permanecem.

## Arquivos afetados

| Grupo | Caminhos |
| --- | --- |
| Plugin | `src/dona_maria/hermes_research/__init__.py`, `plugin.yaml`, package-data em `pyproject.toml` |
| Pesquisa/rede | `src/dona_maria/research.py`, `research_network.py` |
| Proveniência/persistência | `provenance.py`, `approvals.py`, `persistence.py`, `approval_cli.py` |
| Atendimento/política | `business_state.py`, `hermes_policy/__init__.py`, `hermes_policy/plugin.yaml` |
| Importação | `inventory.py`: Excel carregado somente na importação de inventário, sem exigir essa dependência para ler o SQLite no host |
| Testes | `test_mediated_research.py`, `test_research_network.py`, `test_hermes_research_plugin.py`, `test_research_stdio.py`, extensão de `test_hermes_attendance_policy.py` e fixture em `tests/conftest.py` |
| Orientação/configuração | `.hermes.md`, skill de atendimento, `README.md`, `docs/setup.md`, `config/hermes.s17.example.yaml`, este relatório |
| Continuidade | Bloco/handoff S17 no plano e registros locais `.harness/` |

Nenhuma dependência acrescentada à aplicação; lock preservado. A pessoa autorizou e executou a instalação do extra DDGS no runtime compartilhado do Hermes, conforme registro abaixo. Não houve alteração em banco/perfil pessoal, credenciais, outros worktrees ou branch integradora pelo agente; sem commit/push/PR/merge.

## Evidências RED → GREEN e revisão

Seams confirmados pela pessoa. Ciclos verticais observaram falhas relevantes para: capacidade inexistente; resultado HTTP/interno aceito indevidamente; extrator inexistente; redirect não seguido/revalidado; limites de corpo/texto/descompressão ausentes; HTTP parcial/vazio e script tratado como texto; proposta exigindo metadados WEB em vez de referência; projeção rotulando pesquisa nova como histórica; ordem de segment-10 antes de segment-2 após serialização; vazamento de exceção tipada; política recusando nomes mediados; CLI de migração inexistente; cache mantendo busca vazia; quatro registros de transporte incompletos promovidos a COMPLETE; metadado persistido ausente aceito com digest correspondente; text/plain interpretado como HTML. Cada correção foi seguida de pytest focado PASS.

Erros de posicionamento de asserts/trechos em testes foram corrigidos e não são apresentados como RED de produto. A revisão da skill code-review foi feita em dois agentes somente leitura: Standards sem violação de alta confiança; Spec apontou os dois P2 de cache e completude, corrigidos com RED/GREEN e revalidados por leitura. Refatoração restrita a contratos tipados, projeção e fixture reaproveitada; Ruff organiza imports/formatação.

Versões locais: Python3.13.15, SQLite3.50.4, MCP2.3.0, Pydantic2.14.3, pytest9.2.0, Hypothesis6.170.15, Ruff0.17.4, httpx2/httpcore2 2.16.0.

Regressão da primeira entrega:656PASS,1SKIP,419.88s. O único SKIP é a conferência do XLSX original, fornecido somente localmente. Depois foram acrescentadas três verificações de migração sem alterar produto: histórico não vazio com fontes/decisões/hashes/replay preservados, schema futuro e backup preexistente. O módulo de pesquisa/migração completo passou29/29 em2.34s. As rodadas finais após as correções do HITL estão registradas abaixo.

Rodada intermediária preservada:646PASS,1SKIP,1FAIL/351.25s; o teste S17 STDIO falhou durante a evolução do contrato entre processos. Não foi usada como aceite. Após atualização explícita das fixtures, STDIO/plugin passaram4/4 em7.83s. JUnits inicial/final estão no Harness local. O teste adicional de histórico inicialmente omitiu a evidência humana obrigatória da fixture; corrigida a preparação, passou sem mudança de produto. Isso não é apresentado como RED de produto.

## Revisão de qualidade e segurança — 15/11/2026

Revisão exclusiva do S17 com `clean-code` e `code-review-and-quality`, nos
cinco eixos e com revisor independente somente leitura. Baseline preservado
em `.harness/s17-quality-review/baseline`; a revisão altera somente
`research.py` e `test_mediated_research.py`, além destes registros.

Corrigido P2 de integridade: a leitura aceitava observações sem `query` ou
`provider`, inclusive com digests correspondentes ao documento incompleto.
Ambos agora exigem texto não vazio antes de consultar/materializar a fonte.
Não foi demonstrada exploração remota. A validação de texto, tamanho e hash
de conteúdo reutiliza `ExtractionRecord`, sem checagens duplicadas, nova
dependência, mudança de schema ou regravação de registros históricos.

O teste parte de COMPLETE e cobre título/consulta/provedor ausentes, vazios
ou numéricos, recalculando ambos os digests. Consulta e materialização
recusam os nove casos e preservam o payload. RED: seis falhas relevantes e
três casos já protegidos; GREEN: nove PASS. Uma mutação que removeu o guard
do provedor gerou três falhas; fonte restaurada byte a byte em `finally`.
Revisão final independente sem Required/Critical remanescente ou código órfão.
Regressão completa desta revisão: **667 PASS, 1 SKIP, 375.04s**; SKIP do XLSX
original ausente. Ruff check PASS, format check64arquivos PASS e diff-check
PASS. JUnits, comandos e limitações em `.harness/s17-quality-review/` e
`.harness/verification.md`.
Após a correção de bootstrap0.1.1 descrita abaixo, regressão completa: **671 PASS, 1 SKIP, 311.190s**, zero falhas/erros, JUnit `.harness/s17-bootstrap-regression-final.xml`. Essas evidências não homologam o Hermes nem pesquisa real e não encerram S17.

## Gate do perfil e prova real

Perfil exclusivo criado pela pessoa: `s17-mediated-research-review`. Banco sintético schema3 criado em `artifacts/private/s17-review/` deste worktree, sem usar perfis/bancos S16/S18. A pessoa configurou DDGS explicitamente, sem keyless fallback, tool_search ou memória, e liberou somente `arroz` (`receita arroz`/`oferta arroz`). As execuções humanas de modelo/pesquisa e as verificações locais estão discriminadas abaixo.

Antes de qualquer alteração, apresentar exatamente os arquivos/settings do novo perfil. O template S17 é complementar ao exemplo base: seis ferramentas MCP mais toolset `culinary_research`, política local e somente o provider explicitamente escolhido; web livre, administração, descoberta dinâmica, memória e wrappers ficam desabilitados. Credenciais de busca/modelo ficam no perfil Hermes, sem chegar ao MCP.

O Doctor real inicialmente recusou o plugin com `No module named 'dona_maria'`. A inspeção identificou que o gerenciador de ambiente substitui PYTHONPATH. O plugin0.1.1 carrega o pacote pela origem absoluta `application_source`, configurada pelo operador; recusa namespace de outra origem e não altera sys.path, runtime global ou core. Excel é importado somente quando usado pelo importador de inventário. Teste frio sem pacote no path reproduziu RED; bootstrap, dispatch e guards passaram no GREEN (recorte132PASS/1SKIP). A pessoa copiou os dois arquivos e reaplicou settings; hashes conferidos pelo agente.

Em processo novo, `tools list --platform cli` confirmou `culinary_research` habilitado, todos os toolsets genéricos desabilitados e MCP dona_maria habilitado. A conexão real MCP descobriu exatamente as seis ferramentas permitidas. A validação final conferiu o catálogo individual de oito ferramentas, dispatch, provider/cliente HTTP em uso, refresh e retomada, além dessa descoberta inicial.

A pessoa recarregou o plugin pesquisa por disable/enable no mesmo perfil, sem override. O gateway confirmou ferramentas para a próxima sessão. A tentativa03 fez dispatch real de `search_culinary_sources` com RECIPE/arroz; devolveu `DATA_SOURCE_UNAVAILABLE` em11ms, sem extração. Leitura do estado de instalação do PM confirmou ausência de `ddgs` no ambiente selecionado, extras `[all]`; o provider retorna falha antes da rede nessa condição. O extra oficial fixa ddgs9.16.0. O comando suportado `tools post-setup ddgs` chama `pm.sync_venv`, que altera o ambiente compartilhado de aplicação: `-p` não isola essa instalação. Essa alteração exigiu exceção explícita ao escopo de isolamento original, autorizada na etapa seguinte. Nenhum fallback foi habilitado.

Depois de apresentada essa exceção, a pessoa executou o post-setup oficial. O PM passou a registrar `[all, ddgs]` e a distribuição9.16.0 está presente. O runtime instalado fixa o ambiente de dependências no boot; não troca sys.path de processos vivos. Por isso a instalação exigiu uma nova inicialização do gateway, autorizada e executada pela pessoa na etapa seguinte.

A pessoa autorizou o reinício compartilhado e executou `hermes gateway restart --interrupt --detach`. O host informou que não havia gateway/serviço, ofereceu instalação como tarefa agendada e UAC; a pessoa respondeu afirmativamente aos dois prompts. A saída confirmou início em segundo plano e lançamento do instalador elevado, sem demonstrar conclusão da instalação da tarefa. Não se declara reinício de processo anterior nem instalação concluída.

**Prova real de receita, tentativa04: PASS para busca/extração e materialização WEB.** Na sessão nova, o Hermes chamou as duas capacidades permitidas: consulta efetiva `receita arroz`, provider DDGS, cinco resultados; extração do primeiro retornou COMPLETE. Registro persistido e validado pelo backend em SQLite: URL `https://www.tudogostoso.com.br/receita/770-arroz-branco.html`, observação `2026-11-15T17:59:40.535496+00:00`, recuperação `2026-11-15T17:59:44.818270+00:00`, destino `104.19.177.52:443`, zero redirecionamentos. Foram recebidos61890bytes, descomprimidos535661bytes e extraídos15342bytes UTF-8 em quatro segmentos. Hash do conteúdo `64314ce1726bcacf86009ab9b2caa9a7c99c99784276ad35ef88d560eefc57ef`; hash do texto refeito independentemente a partir dos segmentos e conferido.

`ResearchService.materialize_source` recuperou o registro e materializou `WebSource` com `segment-2`, contendo ingredientes/preparo, e metadados correspondentes; evidência privada `real-research-04-web-source.json`. A inspeção não escreveu no banco. Comparação de todas as linhas de inventário/workspaces/decisões/operações/propostas com o backup schema2 anterior à pesquisa confirmou igualdade e revisão0. A decisão/operação de bootstrap preexistente foi preservada. O canário sintético do inventário não aparece no stream capturado; a consulta persistida contém exclusivamente o termo aprovado. Evidências privadas em `artifacts/private/s17-review/real-research-04*.json*`. Corpo HTTP bruto não foi retido; o hash de conteúdo foi produzido pelo extrator no fluxo real, e não recalculado depois a partir de um corpo ausente. Não há captura completa do tráfego interno do provider DDGS; não se afirma auditoria de todos os seus destinos.

RULES §5 mantém a experimentação humana um passo por vez. A pessoa executou `hermes --version`: Hermes0.23.1/3b4215785882, instalação git, Python3.14.9 e OpenAI SDK2.54.0. A identidade corresponde ao adaptador; o runtime difere do Python3.13.15 da suíte. A pessoa selecionou o modelo; leitura delimitada confirmou `openai/gpt-6.1-sol`, provider `nous`. Autenticação e dispatch foram exercitados nas pesquisas reais. As evidências incluem consulta, peer/destinos, resultado, extração, horário, hashes, segmento e WebSource materializado pelo backend; texto final do modelo não foi considerado prova suficiente.

**Host/plugin, MCP, retomada/replay e pesquisas reais RECIPE/QUOTE: PASS.** Retomada01 reusou a mesma sessão e retornou hash/fetched_at anteriores; o arquivo SQLite inteiro permaneceu byte a byte idêntico e o MCP confirmou orçamento80.00 sem novas propostas. Vetores pertinentes do EV-18 foram exercitados no contrato real de segurança com intenções sintéticas, conforme a prova final abaixo. Não houve campanha conversacional global de prompt injection/S19; essa prova de contrato não é apresentada como conversa adversarial com LLM real.

## Cotação, prova de segurança e regressão finais

O diagnóstico humano da primeira cotação confirmou título255>200 em um retorno do provider; a recusa preservou o banco. Um teste de dispatch reproduziu RED; o plugin0.1.2 passou a solicitar1resultado ao provider, sem cortar metadados ou aumentar limites. GREEN e teste negativo confirmaram que título excessivo recebido continua recusado com DB idêntico. Recorte final94PASS/31.42s; nenhuma nova migração ou dependência de aplicação.

**Cotação02 real: PASS.** Consulta `oferta arroz`, DDGS, um resultado; URL `https://www.catalogosofertas.com.br/ofertas/arroz`, observada `2026-11-15T18:58:46.971572+00:00`, recuperada `2026-11-15T18:58:52.885777+00:00`. Peer IPv6 público `[2600:9000:2399:fa00:e:35a:6680:93a1]:443`, zero redirects;64384bytes recebidos/412276descomprimidos/10208UTF-8 em3segmentos, COMPLETE. Hash do conteúdo `5d034d46cabd2db0d7b8d33b898fcb71b81c6ac9d9a9e5081d3265e3c715bcf2`; hash do texto refeito e conferido. Backend materializou WebSource QUOTE/segment-1 com ofertas/preços publicados. Todas as tabelas de negócio permaneceram iguais ao backup anterior; a fonte RECIPE anterior continuou idêntica. Preços/disponibilidade não foram confirmados para compra; nenhuma proposta ou decisão financeira foi criada. Evidências privadas `real-quote-02-verification.json` e `real-quote-02-web-source.json`.

**Segurança/contrato no host real:18PASS**, com intenções sintéticas e sem LLM ou nova pesquisa. Recusados: termo não aprovado, consulta/URL livre, argumento de contexto, resultado inexistente, receipt/headers/cookies fabricados, seis ferramentas livres/administrativas, intenção ausente/renomeada, outro contexto, segmento inexistente e fonte divergente. O preflight exigiu bloqueio do hook antes de tentar dispatch genérico. SDK/hooks e backend usados são os reais da versão/commit registrados; não foi usado provider-fixture para alegar pesquisa real.

RPCs reais `session.resume`, `tools.show` e `reload.mcp` conferiram exatamente os mesmos oito nomes antes/depois do refresh exclusivo S17: `search_culinary_sources`, `extract_culinary_source` e MCP `get_business_state`, `get_inventory_snapshot`, `evaluate_recipe_feasibility`, `evaluate_purchase_plan`, `propose_user_change`, `calculate_pricing_scenarios`. SQLite permaneceu byte a byte idêntico, conferido também após a execução. Evidência privada `host-security-report.json`; canário de inventário ausente das capturas e termos privados não chegaram à construção das consultas.

**Regressão final:673PASS,1SKIP,343.86s**, zero falhas/erros, JUnit `.harness/s17-quote-limit-regression-final.xml`. Inclui37testes de pesquisa/migração,47de rede controlada,8de plugin e2de STDIO; Hypothesis de rede com30exemplos, além das propriedades do domínio. O SKIP continua sendo o XLSX original ausente. Ruff check PASS, format64arquivos PASS. Comandos finais na venv local:

```text
python -X utf8 -B -m pytest tests/unit tests/integration -q --junitxml=.harness/s17-quote-limit-regression-final.xml
python -m ruff check src tests/unit tests/integration evals
python -m ruff format --check src tests/unit tests/integration evals
git diff --check
python -X utf8 -B -m unittest discover -s C:\Labs\sabor-da-maria-hermes-agent\tests\harness -v
```

## Harness, aceite e integração

O bundle canônico, inicialmente ausente neste worktree, foi localizado na cópia principal `C:/Labs/sabor-da-maria-hermes-agent`, somente para leitura. A API pública `refresh_index(root); check(root)` do programa original foi executada apontando explicitamente o worktree S17; código e testes do checker não foram alterados, nem arquivos da cópia principal. Foram criados somente os registros locais README/tools ausentes. A primeira execução detectou que o status S17 perdera sua prioridade P0; o formato foi corrigido somente nesse bloco. **Harness estrutural: PASS; suíte pública original:9PASS/0.268s**, com fixtures temporárias. Hash SHA256 do checker `3210819f088de00f62a006ab4f30b34e1fbd0a363dbf575886514efe76d29a04`; evidência `.harness/s17-harness-verification.json`. O índice S17 foi regenerado pela API, sem editar critérios derivados manualmente.

AC-023/030: quatro critérios tecnicamente verificados — (1) consulta/URL/receipt/contexto recusados em serviço/SQLite e host; (2) DNS/redirects/limites/parcialidade recusados no transporte controlado, sem escrita parcial; (3) compatibilidade real, catálogo exato, refresh/retomada e ausência de fallback; (4) pesquisas RECIPE/QUOTE reais com registro completo e fonte correspondente. **HITL final realizado pela pessoa; encerramento registrado nesta conversa.** COMPLETE identifica transferência/extração do conteúdo disponível; não garante rendimento/custos, disponibilidade local ou verdade semântica de cada afirmação. Corpo HTTP bruto não foi retido, nem todo o tráfego interno do DDGS capturado; o hash do corpo foi produzido pelo extrator no fluxo real e não recalculado posteriormente. Lacunas e decisões continuam sujeitas aos guards existentes.

Integração posterior exige conciliar mudanças de S16/S18 em `provenance.py`, `approvals.py`, `persistence.py`, projeções e fixtures. S17 reserva schema SQL3 para observações: qualquer migração concorrente com esse número precisa de ordenação explícita e testes de backup/replay pelo integrador. Campos antigos e regras financeiras foram preservados; S16/S18 não foram implementados aqui.

Readiness: **S17 concluído e pronto para integração posterior controlada**, com conciliação dos contratos/migrações acima quando solicitada. Não iniciar S19 automaticamente. A instalação da tarefa agendada foi autorizada nos prompts do Windows, mas sua conclusão não foi comprovada; não é usada como evidência de aceite do slice.

