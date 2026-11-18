# Arquitetura e responsabilidades

Visão técnica do código entregue. O [README](../README.md#arquitetura) traz o
diagrama de componentes e as decisões; este documento detalha módulos, dados,
fronteiras de confiança e onde cada invariante é aplicado. Contratos canônicos
estão na [SPEC](../doc-specs/spec.md), especialmente **3.3 Componentes e
responsabilidades**, **3.4 Invariantes e autoridade** e **4.4 Catálogo MCP**.

## Processos

| Processo | Entrada | Código | Pode escrever no SQLite? |
| --- | --- | --- | --- |
| Host Hermes (Desktop ou CLI) | Conversa com a cozinheira | `.hermes.md`, skill, [`hermes_policy`](../src/dona_maria/hermes_policy/__init__.py), [`hermes_research`](../src/dona_maria/hermes_research/__init__.py) | Só o plugin de pesquisa, na tabela `research_observations` |
| Subprocesso MCP stdio | Tool calls do host | [`launcher`](../src/dona_maria/launcher.py) → [`mcp_server`](../src/dona_maria/mcp_server.py) → [`AttendanceService`](../src/dona_maria/business_state.py) | Sim: propostas (`propose_user_change`) e cálculos (`calculate_pricing_scenarios`) |
| Terminal da operadora | Comandos locais | [`onboarding`](../src/dona_maria/onboarding.py), [`approval_cli`](../src/dona_maria/approval_cli.py), [`bootstrap`](../src/dona_maria/bootstrap.py) | Sim: importação, migrações e aplicação de propostas aprovadas |

O processo MCP e o de revisão compartilham o mesmo arquivo SQLite e o código de
domínio, mas não uma instância em memória. O binding (banco, workspace e modo
`ATTENDANCE`) chega ao MCP por variáveis de ambiente definidas pelo operador; o
launcher descarta as demais, inclusive credenciais do provedor do modelo.

## Módulos

| Camada | Módulos | Responsabilidade |
| --- | --- | --- |
| Transporte | `mcp_server.py`, `launcher.py`, `limits.py` | MCP v2 por stdio, limite de frame e de coleções; nenhuma regra de negócio |
| Fronteira do atendimento | `business_state.py` | Catálogo de 6 tools (`ATTENDANCE_TOOLS`), projeções sem IDs internos, mensagens em linguagem simples |
| Propostas e aprovação | `approvals.py`, `approval_cli.py` | Proposta com hash, revisão e prazo de 10 min; aprovação com atestação, revalidação e aplicação atômica |
| Domínio | `planning.py`, `production.py`, `candidates.py`, `ingredients.py`, `quotes.py`, `pricing.py`, `cost_readiness.py`, `provenance.py` | Agregado do workspace, viabilidade, demanda e compras, conversões com escopo, cotações, CMV e cenários, proveniência por campo. Sem SQLite, MCP ou rede |
| Importação | `inventory.py`, `bootstrap.py` | Leitura do XLSX com limites, cruzamento das abas e origem por célula |
| Persistência | `persistence.py` | Repositório SQLite, revisões, operações idempotentes, auditoria e migrações com backup |
| Pesquisa | `research.py`, `research_network.py`, `hermes_research/` | Termos liberados, resultados registrados, extração com política de destinos contra SSRF |
| Host | `hermes_policy/`, `onboarding.py`, `hermes_gateway_check.py`, `hermes_research_check.py` | Allowlist por hooks, preparação do perfil, diagnósticos sem dados privados |

## Dados

| Tabela | Conteúdo |
| --- | --- |
| `workspaces` | Agregado do atendimento: receitas, fatos, plano, aceites, cálculos e escolhas, com revisão e `context_mode` (`REAL` ou `SIMULATION`) |
| `inventory_snapshots` | Fotografia imutável da planilha importada, com origem por célula |
| `decisions` | Histórico auditável das decisões aplicadas |
| `operations` | Operações idempotentes por `operation_id`, com a revisão confirmada |
| `user_change_proposals` | Propostas, hash de revisão, prazo e eventos de aprovação ou recusa |
| `research_observations` | Buscas e extrações registradas, consultadas por ID nas fontes WEB |
| `schema_migrations` | Versão do schema; migrações exigem backup explícito |

## Onde cada invariante é aplicado

| Invariante | Aplicação |
| --- | --- |
| Hermes orquestra; Python valida | O modelo só alcança 6 + 2 tools (`ATTENDANCE_TOOLS`, `hermes_policy.ALLOWED`); nenhuma delas aplica decisão humana |
| `UNKNOWN` ou `BLOCKED` não autorizam aceite | `planning._accept_recipe` exige avaliação atual, viabilidade sem `PENDING` ou `BLOCKED`, compras `CONFIRMED`, readiness financeira `READY`, interesse `INTERESTED` e aceite inequívoco |
| `Decimal`, nunca `float` | `pricing.FINANCIAL_CONTEXT` (34 dígitos, divisão por zero e overflow capturados); preço com `ROUND_CEILING` em centavos |
| Ausente não vira zero | Lacunas viram gaps (`MISSING_INFORMATION`, `UNIT_CONVERSION_REQUIRED`); `remaining_budget` fica `null` enquanto a demanda está incompleta |
| Orçamento agregado de R$ 80 | `planning.evaluate_plan` soma todos os pratos, arredonda pacotes para cima (`quotes.py`) e marca `OVER_BUDGET` |
| Selecionar cardápio não consome estoque | Nenhum comando altera `inventory_snapshots`; aquisições e conversões são overlays auditados |
| Estado separado da memória do LLM | Memória do Hermes desligada no perfil; `get_business_state` projeta o SQLite |
| Decisões humanas exigem confirmação explícita | `propose_user_change` só persiste a proposta; `ApprovalService.approve` exige `ATESTO <hash>` e revalida |
| Mudança de premissa invalida dependentes | `planning._invalidate_acceptances` e revisões de receita, plano e cotação |
| Conteúdo externo é dado não confiável | Fonte WEB só vale por `research_result_id` registrado; páginas e células não concedem autorização |

## Limites desta arquitetura

- STDIO local e UUID de workspace não oferecem isolamento multiusuário nem autenticação.
- Um perfil do Hermes restringe capacidades, mas não é sandbox do sistema operacional.
- O plugin de pesquisa depende de APIs internas do Hermes 0.23.1 e recusa outras versões.
- Não introduza ORM, filas, microserviços ou outro orquestrador sem um requisito concreto.
