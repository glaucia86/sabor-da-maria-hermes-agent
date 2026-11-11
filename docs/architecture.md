# Arquitetura e responsabilidades

Consulte ao alterar limites entre componentes, contratos ou persistência.
Fonte técnica: [SPEC](../doc-specs/spec.md), especialmente **3.3 Componentes e
responsabilidades** e **3.7 Progressive Disclosure e layout futuro**.
Leia outros contratos somente quando forem afetados pela tarefa.

## Estado atual e estrutura proposta

O repositório contém orientação em `AGENTS.md`, guias em `docs/` e fontes
locais em `doc-specs/`. Ainda não há código de aplicação, manifesto ou suíte.

O layout da SPEC é uma proposta a concretizar nas fatias autorizadas:

- `src/dona_maria/`: domínio, serviços, contratos, persistência e adaptador MCP.
- `tests/unit/`, `tests/integration/`, `tests/agent_evals/`: verificações por nível.
- `skills/dona-maria-cardapio/`: fluxo de produção e referências sob demanda.

Não crie módulos apenas para preencher esse layout. Registre caminhos reais
no handoff conforme forem implementados. Preserve a planilha original em
`doc-specs/`; não crie outra fonte de verdade concorrente.

## Limites de autoridade

- **Hermes:** pesquisa, elicitação, espera pela confirmação humana e explicação.
- **Adaptador MCP:** transporte, schemas e erros; delega regras aos serviços.
- **Serviços e domínio Python:** guards, viabilidade, compras e cálculos
  determinísticos. O domínio não importa Hermes nem depende de rede.
- **Pydantic 2.x:** validação de fronteira e serialização conforme os contratos.
- **SQLite:** estado, revisões, transações e decisões, separados da memória do LLM.

Use interfaces explícitas e permita controlar relógio e repositório nos testes.
Não introduza ORM, filas, microserviços ou framework de workflows no MVP.

## Localização dos detalhes canônicos

Busque na SPEC o título exato correspondente à alteração:

- **4.1 Convenções comuns** e **4.4 Catálogo MCP da aplicação**: fronteiras.
- **3.4 Invariantes e autoridade**: regras transversais.
- **4.8 Persistência, transações, invalidação e reset**: estado e gravações.
- **3.6 Segurança e confiança**: dados externos e autoridade.

Esses localizadores não autorizam implementar funcionalidades de outras fatias.
