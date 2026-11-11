# Sabor da Maria — Instruções de Engenharia

## Escopo e navegação

Implemente somente o trabalho explicitamente autorizado. Prefira mudanças
pequenas, coesas e testáveis; não antecipe outras fatias ou funcionalidades.

- Visão, decisões técnicas e verificações: [README](README.md).
- Configuração e reprodução: [guia de instalação](docs/setup.md).
- Atendimento do Hermes: [.hermes.md](.hermes.md) e skill em `skills/`.
- Código em `src/dona_maria/`; testes em `tests/unit/` e `tests/integration/`.

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

Siga os comandos de pytest e Ruff do README. Aplique TDD nos comportamentos
acordados; use bancos temporários e fixtures sintéticas. Não acrescente
dependências ou abstrações sem necessidade concreta.

Preserve alterações preexistentes. Não exponha segredos, bancos pessoais,
credenciais, logs privados ou configurações da máquina. Não execute comandos
destrutivos sem aprovação; não faça commit, push ou PR automaticamente.
Informe alterações, comandos/resultados reais e limitações ao concluir.
