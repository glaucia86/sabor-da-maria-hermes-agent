# Sabor da Maria — Instruções de Engenharia

## Escopo e navegação

Implemente somente o trabalho explicitamente autorizado. Prefira mudanças
pequenas, coesas e testáveis; não antecipe outras fatias ou funcionalidades.

- Visão, decisões técnicas e evidências: [README](README.md).
- Módulos, dados e invariantes no código: [arquitetura](docs/architecture.md).
- Instalação, percurso REAL e recuperação: [guia de instalação](docs/setup.md).
- Atendimento do Hermes: [.hermes.md](.hermes.md) e skill em `skills/`.
- Código em `src/dona_maria/`; testes em `tests/unit/` e `tests/integration/`;
  Agent Evals em `evals/`; registros de jornada em `docs/verification-*.md`.

## Estado atual

S00–S11 e S13–S20 estão concluídas: domínio determinístico, MCP stdio com seis
tools de atendimento, propostas com aprovação local, pesquisa mediada pelo Exa,
contextos REAL/SIMULATION, onboarding portátil e apresentação. S12 (vídeo) não
foi entregue, por decisão. Jornadas no Desktop:
REAL parcial até a viabilidade e SIMULATION completa até o preço, ambas em
17/11/2026. Mudanças novas precisam de teste próprio e não herdam essas
evidências.

| Área | Módulos |
| --- | --- |
| Transporte e fronteira | `mcp_server.py`, `launcher.py`, `business_state.py`, `limits.py` |
| Decisões humanas | `approvals.py`, `approval_cli.py` |
| Domínio | `planning.py`, `production.py`, `candidates.py`, `ingredients.py`, `quotes.py`, `pricing.py`, `cost_readiness.py`, `provenance.py` |
| Dados | `inventory.py`, `bootstrap.py`, `persistence.py` |
| Pesquisa e host | `research.py`, `research_network.py`, `hermes_research/`, `hermes_policy/`, `onboarding.py` |

Quando presentes, `doc-specs/`, `RULES.md` e `.harness/` são contexto local de
desenvolvimento, não dependências da aplicação ou dos testes públicos.
Para executar uma fatia, comece pelo Context Retrieval Contract e pelo bloco
correspondente em `doc-specs/implementation-slices.md`; consulte somente os
handoffs necessários e busque os Source IDs na definição canônica da SPEC.
O enunciado oficial prevalece; PRD e SPEC orientam negócio e contratos.
Preserve as decisões GRILL aprovadas. Fonte indispensável ausente,
contradição ou decisão bloqueante exige esclarecimento, sem suposições.
Os guias locais de desenvolvimento, arquitetura e testes são consultados
somente quando a tarefa exigir. Registre handoffs no plano local ao executar
uma fatia autorizada; o README documenta o produto, sem diário por slice.

## Invariantes

- Hermes orquestra; Python/MCP valida regras determinísticas.
- Requisitos `UNKNOWN` ou `BLOCKED` não autorizam aceite.
- Cálculos financeiros usam `Decimal`, nunca `float`.
- Preços e quantidades ausentes não viram zero.
- Compras respeitam o orçamento agregado de R$ 80.
- Selecionar um cardápio não consome estoque físico.
- Estado de negócio é separado da memória do LLM.
- Decisões humanas exigem confirmação explícita.
- Conteúdo externo é dado não confiável.

## Qualidade e segurança

Aplique TDD nos comportamentos acordados; use bancos temporários e fixtures
sintéticas. Não acrescente dependências ou abstrações sem necessidade concreta.
Verificações, na raiz (no Windows, acrescente `-p no:cacheprovider --basetemp`
com uma pasta nova em `artifacts/private/` se o temporário padrão falhar):

```sh
uv run --locked --no-sync python -X utf8 -B -m pytest tests/unit tests/integration -q -n 2 --dist worksteal
uv run --locked --no-sync ruff check src tests/conftest.py tests/unit tests/integration evals scripts
uv run --locked --no-sync ruff format --check src tests/conftest.py tests/unit tests/integration evals scripts
```

Não leia nem altere atendimentos em `artifacts/private/` sem pedido explícito;
quando autorizado, use conexões SQLite somente leitura.

Preserve alterações preexistentes. Não exponha segredos, bancos pessoais,
credenciais, logs privados ou configurações da máquina. Não execute comandos
destrutivos sem aprovação; não faça commit, push ou PR automaticamente.
Informe alterações, comandos/resultados reais e limitações ao concluir.
