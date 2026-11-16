# Verificação S20 — 16/11/2026

Entrega preparada na branch `feat/s20-portable-onboarding`, sem commit, push,
merge ou publicação. S19/PR #18 e seus dados/perfis não foram alterados.
Este relatório separa provas executadas de pendências humanas; não é aceite HITL.

## Ambiente e comandos

Windows nativo; Python da aplicação **3.13.15**, uv **0.9.5**, MCP **2.3.0**,
Pydantic **2.14.3**, openpyxl **3.1.5**. `.venv` foi criado do zero com
`uv sync --locked --python 3.13`. Não houve alteração de dependências/lock.
Hermes **0.23.1**, commit **3b4215785882**, runtime Python **3.14.9**;
versão e help CLI/Desktop consultados. Runtime Hermes permanece separado.

| Verificação executada | Resultado e alcance |
|---|---|
| `python scripts/demo.py setup`, duas execuções | PASS: mesmo workspace sintético, sem sobrescrever banco; sync pelo lock |
| `doctor` no ambiente instalado | PASS: versões acima; sem leitura de credenciais |
| `check` | PASS: seis ferramentas MCP, leitura vinculada, recusa de `accept_recipe`, SIMULATION, orçamento 80.00, zero decisões humanas |
| `configure` pelo seed vazio | PASS no perfil novo exclusivo; não semeou modelo/provider pessoal |
| `verify-profile` | PASS: settings, bytes da política/orientação, descoberta da skill e conexão Hermes MCP; `model_configured=false` corretamente diagnosticado |
| `chat` sem modelo no perfil novo | Recusa esperada, exit 1: “Modelo ausente no perfil isolado; execute a ação model.” Nenhuma chamada de LLM |
| Testes novos de onboarding | 6 PASS, 6,13 s, após ciclos RED→GREEN |
| Regressão completa anterior à última correção de ambiente | 794 PASS, 2 SKIPPED, 347,96 s |
| Regressão final após isolamento do primeiro `uv sync` | **795 PASS, 2 SKIPPED, 347,51 s**; descoberta adicional da skill validada no smoke real separado |
| `ruff check src tests evals scripts` | PASS |
| `ruff format --check src tests evals scripts` | PASS, 75 arquivos |
| `git diff --check` | PASS |
| Links relativos nos documentos públicos alterados | 46 verificados, zero destino ausente |
| Arquivos publicáveis e padrões de credenciais | Sem SQLite, XLSX, `.env` ou artefato privado; nenhum padrão de token nos arquivos da entrega |
| Harness local `.harness/check.py` | Não disponível neste worktree; não restaurado de outro worktree |

Os comandos de pytest usaram `--basetemp artifacts/private/<rodada>` e
`--junitxml=artifacts/private/<rodada>.xml`: o diretório temporário global
apresentou erro de permissão. Saídas anteriores de erro de ambiente foram
preservadas, não tratadas como falhas ou sucessos de negócio. Os temporários
e XMLs não são artefatos públicos nem dependências do projeto.
Os dois skips finais são o anexo XLSX original ausente e criação de symlink
indisponível no Windows (erro 1314). Não foram convertidos em aprovação.
Foram conferidos 19 arquivos publicáveis; a exceção no `.gitignore` garante
que os três assets `dist` do Reveal acompanhem o próximo commit.

## TDD e revisão independente

Os testes exercitam a interface CLI/subprocesso e SQLite temporário, com MCP
stdio real; a fronteira de instalação usa subprocesso controlado no teste para
não modificar outro ambiente. Ciclos observados:

1. Módulo ausente → criação/reexecução idempotente e recusa de diretório alheio.
2. Manifesto com tipo inválido produzia traceback → diagnóstico seguro.
3. Opções extras de revisão chegavam à CLI interna → recusa de override e migração.
4. Primeiro `uv sync` herdava ambiente → filtragem também nessa chamada, com
   teste de `UV_PROJECT_ENVIRONMENT` e `PYTHONPATH` externos.

Revisor independente, somente leitura, apontou e conferiu correções:

- Criação Hermes sem clone podia herdar o bloco model/provider: origem vazia
  exclusiva, sem config e com `.env` vazio, evita semeadura.
- Wrapper review permitia opções de banco/workspace: parser limitado às quatro
  operações locais; contexto fica fixo.
- Chat sem preflight: validação crítica repetida antes de lançar a conversa.
- Erros próprios sem causa clara: mensagens seguras específicas para validações.
- Conversa sob Git herdava AGENTS.md de engenharia: cwd transferido para o
  perfil fora do checkout.
- Instalação com variável UV externa: ambiente mínimo em ambos os subprocessos.
- Roteiro negativo falava em cópia: segunda demo é criada do zero, com identidade
  própria, preservando o caso positivo.

Após os ajustes, o revisor não manteve pendências nos achados desta revisão.
Ele não reexecutou testes nem validou renderização; essas provas pertencem à
execução principal. Revisão não equivale a pentest ou garantia geral do host.

## Tentativas de host preservadas

A primeira estratégia, home Hermes dentro do checkout, acionou preparação de
outro runtime e falhou com caminhos longos no Windows. A implementação final
usa o root nativo e o runtime instalado, com perfil novo e origem vazia.

Uma tentativa intermediária usou `profile create --no-skills` diretamente e
herdou configuração de modelo. O perfil descartável criado nessa tentativa foi
removido pelo comando nativo, sem alterar o perfil pessoal; nenhum valor de
credencial foi lido ou publicado. A versão final não depende desse procedimento.

O smoke também identificou strings com aspas extras em `config set` e coerção
de `display.tool_progress=off` para booleano falso. Os argumentos e a comparação
foram ajustados à semântica conferida na fonte do Hermes; nova leitura e conexão
passaram. Perfis finais de smoke permanecem sem modelo/credenciais configurados.

## Apresentação

Reveal.js **5.2.1**, assets oficiais e licença MIT locais; nenhuma dependência
Node foi adicionada ao projeto. Referência editorial consultada no repositório
do workshop indicado pela pessoa.

O navegador integrado/CUA estava indisponível. Foi usado teste **headless** com
Playwright/Chromium já instalados, servidor ligado somente a `127.0.0.1` e raiz
HTTP limitada a `docs/speaker/slides`:

- 15 slides, 15 notas e soma dos tempos **1.200 segundos**.
- Navegação por teclado e popup de speaker notes com conteúdo do slide corrente.
- Zero erro JavaScript, requisição externa ou resposta HTTP de erro no deck.
- Sem corte vertical nos 15 slides em viewport 1440×1000.
- Capturas locais inspecionadas de arquitetura, HITL, finanças e notas. A primeira
  inspeção revelou fundo branco inadequado e captura no meio do fade; CSS
  corrigido e capturas repetidas após a transição.

Isso comprova renderização headless local, não ensaio presencial, projeção em
qualquer resolução, impressão/PDF ou operação do navegador integrado.
O guia e o roteiro incluem cortes de tempo, estado inicial, prompts, ferramentas,
passos do operador, efeitos esperados e alternativas honestas.

## Pendências HITL e limites

- Configurar o modelo e autenticar **localmente no perfil novo**, sem copiar
  segredos. Ensaiar conversa e conferir canal, catálogo/dispatch, skill e retomada.
- Fazer as manifestações e atestações do cenário hipotético. Nenhuma atestação
  foi executada pelo onboarding nem foi apresentada como aprovação humana.
- Pesquisa mediada desabilitada no P0; prova real em outro perfil exige S17 e
  homologação própria. Desktop não homologado. Não há cliques presumidos.
- S19 e seus Agent Evals não foram executados aqui; resultados históricos e
  NOT_RUN não foram alterados. Passar pytest não aprova conversa.
- macOS/Linux não executados localmente no S20; aguardar CI desta alteração.
  Instalação em VM sem caches, exportação PDF e demo de 10 minutos com LLM real
  não foram verificadas nesta sessão.
- Perfil é controle de capacidades, não sandbox contra código na mesma conta.
  O aprovador é a sessão local do operador, não identidade forte da cozinheira.

## Integração com S19

Comparação somente leitura entre refs locais, sem entrar no worktree S19:
S19 também altera `README.md`, `docs/setup.md`, `.hermes.md` e a skill. No README,
preservar o catálogo integrado de 18 evals e os status reais que S19 trouxer,
junto do Quick Start S20. No setup, conservar a observação S19 de que mudar
somente `env` pode manter conexão antiga e seus links de roteiro, junto do
onboarding S20 e das correções de texto legado.

O plano local será um ponto de conflito por handoffs concorrentes: concatenar
registros preservando o histórico, nunca escolher apenas um lado. O onboarding
copia a política e as orientações do checkout atual; após integração, prepare
perfil novo ou revise explicitamente o perfil de demo e repita o preflight.
Não reutilize uma prova de bytes/configuração feita antes de integrar a skill.
Novos arquivos `onboarding.py`, `scripts/demo.py`, teste S20 e `docs/speaker/`
não tinham correspondentes na comparação local de S19.

Próximos passos: revisão humana do diff/material → integração deliberada após
S19 → nova verificação e ensaio → commit/push somente por autorização posterior.

## Arquivos da entrega

- `src/dona_maria/onboarding.py`, `scripts/demo.py` e
  `tests/integration/test_onboarding.py`.
- `README.md`, `docs/setup.md`, `doc-specs/implementation-slices.md` e exceção
  restrita no `.gitignore` para os três assets oficiais da pasta `dist` do Reveal.
- `docs/speaker/README.md`, `guia-apresentacao-lucas.md`, `demo-hermes.md`,
  este relatório, `slides/index.html`, `slides/assets/deck.css`.
- Seis arquivos oficiais sob `slides/vendor/reveal-5.2.1/`, incluindo licença.

Artefatos privados de smoke, bancos, perfis, XMLs e capturas ficam fora do Git.
